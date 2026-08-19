"""籌碼分析器模組。

從 FinMind API 取得外資、投信、自營商每日買賣超張數資料，
計算衍生指標（連續買超天數、持股比例變化 5/20/60 日），
並透過 SQLiteCache 持久化快取（有效期 4 小時）。

資料取得失敗時標示「籌碼資料不可用」，而非隱藏該欄位。

Usage::

    from app.services.chip_analyzer import ChipAnalyzer

    analyzer = ChipAnalyzer(
        data_pipeline=pipeline,
        sqlite_cache=sqlite_cache,
        error_handler=error_handler,
    )
    result = analyzer.get_chip_data("2330")
    if result.data_available:
        print(result.foreign_consecutive_buy)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from app.core.errors import DataSourceError
from app.infra.cache.sqlite_cache import SQLiteCache
from app.infra.error_handler import ErrorHandler
from app.infra.logging import get_logger, get_stock_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 常數
# ---------------------------------------------------------------------------

_CHIP_CACHE_TTL_HOURS = 4
"""籌碼資料快取有效期（小時）。"""

_FINMIND_DATASET = "TaiwanStockInstitutionalInvestorsBuySell"
"""FinMind 三大法人買賣超資料集名稱。"""


# ---------------------------------------------------------------------------
# ChipAnalysisResult 資料結構
# ---------------------------------------------------------------------------


@dataclass
class ChipAnalysisResult:
    """籌碼分析結果。

    Attributes:
        stock_code: 股票代碼。
        data_available: 籌碼資料是否可用。
        foreign_consecutive_buy: 外資連續買超天數。
        trust_consecutive_buy: 投信連續買超天數。
        dealer_consecutive_buy: 自營商連續買超天數。
        holding_change_5d: 近 5 日持股比例變化（百分比）。
        holding_change_20d: 近 20 日持股比例變化（百分比）。
        holding_change_60d: 近 60 日持股比例變化（百分比）。
        last_updated: 資料最後更新時間（ISO 格式）。
        unavailable_reason: 資料不可用的原因說明。
    """

    stock_code: str
    data_available: bool = False
    foreign_consecutive_buy: int = 0
    trust_consecutive_buy: int = 0
    dealer_consecutive_buy: int = 0
    holding_change_5d: float = 0.0
    holding_change_20d: float = 0.0
    holding_change_60d: float = 0.0
    last_updated: Optional[str] = None
    unavailable_reason: Optional[str] = None


@dataclass
class UpdateResult:
    """批次更新結果。

    Attributes:
        total: 總共要更新的股票數量。
        success_count: 成功更新的股票數量。
        failed_count: 更新失敗的股票數量。
        failed_codes: 更新失敗的股票代碼列表。
    """

    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    failed_codes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ChipAnalyzer 主類別
# ---------------------------------------------------------------------------


class ChipAnalyzer:
    """籌碼分析器。

    整合 FinMind API 取得三大法人買賣超資料，計算連續買超天數與
    持股比例變化等衍生指標。資料快取至 SQLite，有效期 4 小時。

    Args:
        data_pipeline: 資料管線實例（用於存取 FinMind 來源）。
        sqlite_cache: SQLite 快取實例（用於持久化籌碼資料）。
        error_handler: 統一錯誤處理器。
        time_func: 時間函式，預設 time.time。可注入自訂函式以利測試。
    """

    def __init__(
        self,
        data_pipeline: Any,
        sqlite_cache: SQLiteCache,
        error_handler: ErrorHandler,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        """初始化籌碼分析器。

        Args:
            data_pipeline: 資料管線實例（DataPipeline 或任何提供
                get_available_sources() 的物件）。
            sqlite_cache: SQLite 快取實例。
            error_handler: 統一錯誤處理器。
            time_func: 取得目前時間的函式（epoch seconds）。
        """
        self._data_pipeline = data_pipeline
        self._sqlite_cache = sqlite_cache
        self._error_handler = error_handler
        self._time_func = time_func

        logger.info("ChipAnalyzer initialized")

    # ------------------------------------------------------------------
    # 公開介面
    # ------------------------------------------------------------------

    def get_chip_data(
        self, stock_code: str, days: int = 60
    ) -> ChipAnalysisResult:
        """取得指定股票的籌碼分析結果。

        優先從 SQLite 快取讀取（4 小時內有效），若快取過期或不存在
        則嘗試從 FinMind API 取得新資料。取得失敗時回傳
        data_available=False 的結果。

        Args:
            stock_code: 股票代碼（如 "2330"）。
            days: 分析回溯天數，預設 60 天。

        Returns:
            ChipAnalysisResult 包含分析指標或不可用標示。
        """
        stock_log = get_stock_logger(__name__, stock_code)

        # 嘗試從 SQLite 快取取得
        cached_records = self._sqlite_cache.get_chip_data(stock_code, days)
        if cached_records and self._is_cache_valid(cached_records):
            stock_log.debug("使用快取的籌碼資料 (%d 筆)", len(cached_records))
            return self._build_analysis_result(stock_code, cached_records)

        # 快取無效或不存在，嘗試從 FinMind 取得
        stock_log.info("籌碼快取過期或不存在，嘗試更新")
        fresh_data = self._fetch_chip_data_from_api(stock_code, days)

        if fresh_data is not None and not fresh_data.empty:
            # 寫入 SQLite 快取
            self._persist_chip_data(stock_code, fresh_data)
            # 重新從快取讀取（確保格式一致）
            cached_records = self._sqlite_cache.get_chip_data(
                stock_code, days
            )
            if cached_records:
                stock_log.info(
                    "[OK] 籌碼資料更新成功 (%d 筆)", len(cached_records)
                )
                return self._build_analysis_result(stock_code, cached_records)

        # 即使 API 失敗，若有舊快取資料仍可使用（標示為過期）
        if cached_records:
            stock_log.warning("API 更新失敗，使用過期的快取資料")
            result = self._build_analysis_result(stock_code, cached_records)
            result.unavailable_reason = "資料可能已過期（超過 4 小時未更新）"
            return result

        # 完全無資料
        stock_log.warning("[FAIL] 籌碼資料不可用")
        return ChipAnalysisResult(
            stock_code=stock_code,
            data_available=False,
            unavailable_reason="籌碼資料不可用",
        )

    def calculate_consecutive_buy_days(
        self, stock_code: str
    ) -> Dict[str, int]:
        """計算各法人的連續買超天數。

        從 SQLite 快取取得最近的籌碼資料，逐日倒序檢查
        淨買超是否為正（買 > 賣），計算連續天數直到遇到
        淨賣超或賣超為止。

        Args:
            stock_code: 股票代碼。

        Returns:
            字典包含各法人連續買超天數：
            - "foreign": 外資連續買超天數
            - "trust": 投信連續買超天數
            - "dealer": 自營商連續買超天數
        """
        records = self._sqlite_cache.get_chip_data(stock_code, days=60)
        if not records:
            return {"foreign": 0, "trust": 0, "dealer": 0}

        # 記錄已按 trade_date DESC 排列
        foreign_days = self._count_consecutive_buy(
            records, "foreign_buy", "foreign_sell"
        )
        trust_days = self._count_consecutive_buy(
            records, "trust_buy", "trust_sell"
        )
        dealer_days = self._count_consecutive_buy(
            records, "dealer_buy", "dealer_sell"
        )

        return {
            "foreign": foreign_days,
            "trust": trust_days,
            "dealer": dealer_days,
        }

    def calculate_holding_change(
        self, stock_code: str
    ) -> Dict[str, float]:
        """計算法人持股比例變化（近 5/20/60 日）。

        以各法人每日淨買超張數的累計值來近似持股比例變化。
        因為精確的持股比例需要總股本資料，此處以淨買超累計量
        （單位：張）除以期間天數再乘 100，作為百分比近似值。

        Args:
            stock_code: 股票代碼。

        Returns:
            字典包含三個期間的合計法人持股比例變化：
            - "5d": 近 5 日合計持股變化（%）
            - "20d": 近 20 日合計持股變化（%）
            - "60d": 近 60 日合計持股變化（%）
        """
        records = self._sqlite_cache.get_chip_data(stock_code, days=60)
        if not records:
            return {"5d": 0.0, "20d": 0.0, "60d": 0.0}

        # 記錄按 trade_date DESC 排列，取最近 N 天
        change_5d = self._sum_net_buy(records[:5])
        change_20d = self._sum_net_buy(records[:20])
        change_60d = self._sum_net_buy(records[:60])

        return {
            "5d": change_5d,
            "20d": change_20d,
            "60d": change_60d,
        }

    def update_chip_data(
        self, stock_codes: List[str]
    ) -> UpdateResult:
        """批次更新多支股票的籌碼資料。

        從 FinMind API 取得每支股票的法人買賣超資料並寫入 SQLite。
        個別股票錯誤不影響整體流程，記錄後繼續處理下一支。

        Args:
            stock_codes: 要更新的股票代碼列表。

        Returns:
            UpdateResult 包含更新統計（成功/失敗數量與失敗代碼）。
        """
        result = UpdateResult(total=len(stock_codes))

        for code in stock_codes:
            try:
                fresh_data = self._fetch_chip_data_from_api(code, days=60)
                if fresh_data is not None and not fresh_data.empty:
                    self._persist_chip_data(code, fresh_data)
                    result.success_count += 1
                else:
                    result.failed_count += 1
                    result.failed_codes.append(code)
            except Exception as exc:
                self._error_handler.handle_stock_batch_error(
                    error=exc,
                    stock_code=code,
                    batch_context={"operation": "update_chip_data"},
                )
                result.failed_count += 1
                result.failed_codes.append(code)

        logger.info(
            "update_chip_data 完成: %d/%d 成功, 失敗: %s",
            result.success_count,
            result.total,
            ", ".join(result.failed_codes[:10]) if result.failed_codes else "無",
        )
        return result

    # ------------------------------------------------------------------
    # 內部方法：資料取得
    # ------------------------------------------------------------------

    def _fetch_chip_data_from_api(
        self, stock_code: str, days: int = 60
    ) -> Optional[pd.DataFrame]:
        """從 FinMind API 取得三大法人買賣超資料。

        使用 FinMind DataLoader 的 taiwan_stock_institutional_investors
        端點取得外資、投信、自營商每日買賣超張數。

        Args:
            stock_code: 股票代碼。
            days: 回溯天數，預設 60 天。

        Returns:
            包含 trade_date, foreign_buy, foreign_sell, trust_buy,
            trust_sell, dealer_buy, dealer_sell 欄位的 DataFrame。
            若取得失敗回傳 None。
        """
        stock_log = get_stock_logger(__name__, stock_code)

        end_date = datetime.now(tz=timezone.utc)
        start_date = end_date - timedelta(days=days + 10)  # 多取幾天確保足夠

        try:
            dl = self._get_finmind_loader()
            if dl is None:
                stock_log.warning("FinMind DataLoader 不可用")
                return None

            df = dl.taiwan_stock_institutional_investors(
                stock_id=stock_code,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
        except Exception as exc:
            stock_log.warning(
                "FinMind 取得籌碼資料失敗: %s", str(exc)[:200]
            )
            self._error_handler.handle_error(
                exc, context={"stock_code": stock_code}
            )
            return None

        if df is None or df.empty:
            stock_log.debug("FinMind 無籌碼資料")
            return None

        # 轉換 FinMind 格式為標準化格式
        normalized = self._normalize_institutional_data(df, stock_code)
        stock_log.debug(
            "FinMind 取得 %d 筆籌碼資料",
            len(normalized) if normalized is not None else 0,
        )
        return normalized

    def _get_finmind_loader(self) -> Optional[Any]:
        """取得 FinMind DataLoader 實例（懶載入）。

        嘗試從環境變數取得 FinMind token 並建立 DataLoader。
        若 FinMind 套件未安裝或 token 未設定則回傳 None。

        Returns:
            已登入的 FinMind DataLoader 實例，或 None。
        """
        try:
            import os

            from FinMind.data import DataLoader  # type: ignore[import-untyped]

            token = os.environ.get("FINMIND_TOKEN", "")
            if not token:
                logger.debug("FINMIND_TOKEN 未設定，無法使用 FinMind")
                return None

            dl = DataLoader()
            dl.login_by_token(api_token=token)
            return dl
        except ImportError:
            logger.debug("FinMind 套件未安裝")
            return None
        except Exception as exc:
            logger.warning("FinMind DataLoader 初始化失敗: %s", str(exc)[:200])
            return None

    def _normalize_institutional_data(
        self, df: pd.DataFrame, stock_code: str
    ) -> Optional[pd.DataFrame]:
        """將 FinMind 三大法人買賣超原始資料正規化。

        FinMind 的 TaiwanStockInstitutionalInvestorsBuySell 回傳格式
        為每列一個法人+日期的組合，需要轉換為每日一列、各法人分欄的格式。

        典型欄位：date, name, buy, sell
        name 可能為：外資, 投信, 自營商 等

        Args:
            df: FinMind 原始 DataFrame。
            stock_code: 股票代碼。

        Returns:
            正規化的 DataFrame，每日一列，或 None。
        """
        if df.empty:
            return None

        # 識別 FinMind 欄位名稱（可能為英文或中文）
        date_col = None
        name_col = None
        buy_col = None
        sell_col = None

        for col in df.columns:
            col_lower = col.lower()
            if col_lower in ("date", "trade_date"):
                date_col = col
            elif col_lower in ("name", "investor_name", "investor"):
                name_col = col
            elif col_lower in ("buy", "buy_volume", "buy_amount"):
                buy_col = col
            elif col_lower in ("sell", "sell_volume", "sell_amount"):
                sell_col = col

        if not all([date_col, name_col, buy_col, sell_col]):
            logger.warning(
                "FinMind 籌碼資料欄位不符預期: %s",
                list(df.columns),
            )
            return None

        # 分組：按日期匯總各法人買賣超
        result_rows: List[Dict[str, Any]] = []
        grouped = df.groupby(date_col)

        for trade_date, group in grouped:
            row: Dict[str, Any] = {
                "stock_code": stock_code,
                "trade_date": str(trade_date),
                "foreign_buy": 0,
                "foreign_sell": 0,
                "trust_buy": 0,
                "trust_sell": 0,
                "dealer_buy": 0,
                "dealer_sell": 0,
            }

            for _, record in group.iterrows():
                name = str(record[name_col])
                buy_val = int(record[buy_col] or 0)
                sell_val = int(record[sell_col] or 0)

                if self._is_foreign_investor(name):
                    row["foreign_buy"] += buy_val
                    row["foreign_sell"] += sell_val
                elif self._is_trust_investor(name):
                    row["trust_buy"] += buy_val
                    row["trust_sell"] += sell_val
                elif self._is_dealer_investor(name):
                    row["dealer_buy"] += buy_val
                    row["dealer_sell"] += sell_val

            result_rows.append(row)

        if not result_rows:
            return None

        return pd.DataFrame(result_rows)

    # ------------------------------------------------------------------
    # 內部方法：快取管理
    # ------------------------------------------------------------------

    def _is_cache_valid(self, records: List[Dict[str, Any]]) -> bool:
        """檢查快取的籌碼資料是否仍在有效期內（4 小時）。

        以最新一筆記錄的 last_updated 欄位判斷。

        Args:
            records: 從 SQLite 取得的籌碼記錄列表（按 trade_date DESC）。

        Returns:
            True 表示快取仍有效，False 表示已過期。
        """
        if not records:
            return False

        last_updated_str = records[0].get("last_updated", "")
        if not last_updated_str:
            return False

        try:
            last_updated = datetime.strptime(
                last_updated_str, "%Y-%m-%d %H:%M:%S"
            )
            last_updated = last_updated.replace(tzinfo=timezone.utc)
            now = datetime.fromtimestamp(self._time_func(), tz=timezone.utc)
            age_hours = (now - last_updated).total_seconds() / 3600
            return age_hours < _CHIP_CACHE_TTL_HOURS
        except (ValueError, TypeError):
            return False

    def _persist_chip_data(
        self, stock_code: str, df: pd.DataFrame
    ) -> None:
        """將籌碼資料寫入 SQLite 快取。

        使用 bulk_upsert_chip_data 批次寫入。

        Args:
            stock_code: 股票代碼。
            df: 正規化的籌碼 DataFrame。
        """
        records: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            records.append({
                "stock_code": stock_code,
                "trade_date": str(row.get("trade_date", "")),
                "foreign_buy": int(row.get("foreign_buy", 0)),
                "foreign_sell": int(row.get("foreign_sell", 0)),
                "trust_buy": int(row.get("trust_buy", 0)),
                "trust_sell": int(row.get("trust_sell", 0)),
                "dealer_buy": int(row.get("dealer_buy", 0)),
                "dealer_sell": int(row.get("dealer_sell", 0)),
            })

        if records:
            self._sqlite_cache.bulk_upsert_chip_data(records)

    # ------------------------------------------------------------------
    # 內部方法：計算邏輯
    # ------------------------------------------------------------------

    def _build_analysis_result(
        self,
        stock_code: str,
        records: List[Dict[str, Any]],
    ) -> ChipAnalysisResult:
        """從快取記錄建構分析結果。

        Args:
            stock_code: 股票代碼。
            records: 籌碼記錄列表（按 trade_date DESC）。

        Returns:
            完整的 ChipAnalysisResult。
        """
        consecutive = self._calculate_consecutive_from_records(records)
        holding_change = self._calculate_holding_change_from_records(records)
        last_updated = records[0].get("last_updated") if records else None

        return ChipAnalysisResult(
            stock_code=stock_code,
            data_available=True,
            foreign_consecutive_buy=consecutive["foreign"],
            trust_consecutive_buy=consecutive["trust"],
            dealer_consecutive_buy=consecutive["dealer"],
            holding_change_5d=holding_change["5d"],
            holding_change_20d=holding_change["20d"],
            holding_change_60d=holding_change["60d"],
            last_updated=last_updated,
        )

    def _calculate_consecutive_from_records(
        self, records: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """從記錄列表計算各法人連續買超天數。

        Args:
            records: 按 trade_date DESC 排列的記錄列表。

        Returns:
            字典包含 foreign, trust, dealer 三個法人的連續買超天數。
        """
        foreign_days = self._count_consecutive_buy(
            records, "foreign_buy", "foreign_sell"
        )
        trust_days = self._count_consecutive_buy(
            records, "trust_buy", "trust_sell"
        )
        dealer_days = self._count_consecutive_buy(
            records, "dealer_buy", "dealer_sell"
        )
        return {
            "foreign": foreign_days,
            "trust": trust_days,
            "dealer": dealer_days,
        }

    def _count_consecutive_buy(
        self,
        records: List[Dict[str, Any]],
        buy_key: str,
        sell_key: str,
    ) -> int:
        """計算連續買超天數。

        從最近一天開始倒序計算，直到遇到淨賣超或平盤為止。

        Args:
            records: 按 trade_date DESC 排列的記錄列表。
            buy_key: 買超欄位名稱。
            sell_key: 賣超欄位名稱。

        Returns:
            連續買超天數（非負整數）。
        """
        count = 0
        for record in records:
            buy = int(record.get(buy_key, 0))
            sell = int(record.get(sell_key, 0))
            net_buy = buy - sell
            if net_buy > 0:
                count += 1
            else:
                break
        return count

    def _calculate_holding_change_from_records(
        self, records: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """從記錄列表計算持股比例變化。

        以各法人每日淨買超張數的累計值作為持股比例變化的近似。
        淨買超 = (foreign_buy - foreign_sell) + (trust_buy - trust_sell)
                + (dealer_buy - dealer_sell)

        Args:
            records: 按 trade_date DESC 排列的記錄列表。

        Returns:
            字典包含 5d, 20d, 60d 三個期間的累計淨買超張數。
        """
        change_5d = self._sum_net_buy(records[:5])
        change_20d = self._sum_net_buy(records[:20])
        change_60d = self._sum_net_buy(records[:60])
        return {"5d": change_5d, "20d": change_20d, "60d": change_60d}

    def _sum_net_buy(self, records: List[Dict[str, Any]]) -> float:
        """計算一段期間內三大法人合計淨買超張數。

        Args:
            records: 籌碼記錄列表。

        Returns:
            合計淨買超張數（正表示淨買超，負表示淨賣超）。
        """
        total = 0.0
        for record in records:
            foreign_net = (
                int(record.get("foreign_buy", 0))
                - int(record.get("foreign_sell", 0))
            )
            trust_net = (
                int(record.get("trust_buy", 0))
                - int(record.get("trust_sell", 0))
            )
            dealer_net = (
                int(record.get("dealer_buy", 0))
                - int(record.get("dealer_sell", 0))
            )
            total += foreign_net + trust_net + dealer_net
        return total

    # ------------------------------------------------------------------
    # 內部方法：法人名稱辨識
    # ------------------------------------------------------------------

    def _is_foreign_investor(self, name: str) -> bool:
        """判斷名稱是否為外資類別。

        Args:
            name: 法人名稱字串。

        Returns:
            True 表示為外資。
        """
        foreign_keywords = (
            "Foreign", "foreign", "外資", "外國", "FINI",
            "Foreign_Investor",
        )
        return any(kw in name for kw in foreign_keywords)

    def _is_trust_investor(self, name: str) -> bool:
        """判斷名稱是否為投信類別。

        Args:
            name: 法人名稱字串。

        Returns:
            True 表示為投信。
        """
        trust_keywords = (
            "Investment_Trust", "investment_trust", "投信",
            "Trust", "SITC",
        )
        return any(kw in name for kw in trust_keywords)

    def _is_dealer_investor(self, name: str) -> bool:
        """判斷名稱是否為自營商類別。

        Args:
            name: 法人名稱字串。

        Returns:
            True 表示為自營商。
        """
        dealer_keywords = (
            "Dealer", "dealer", "自營商", "自營",
        )
        return any(kw in name for kw in dealer_keywords)
