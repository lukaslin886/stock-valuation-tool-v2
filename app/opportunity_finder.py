"""
OpportunityFinder - 新標的推薦系統 (P2-38 ~ P2-43)

掃描市場候選股票，結合基本面篩選與 DCF 估值，
找出被低估且具投資潛力的個股，並依優先級排序。
"""

from typing import Optional, List, Dict, Any, Callable
import logging

logger = logging.getLogger(__name__)


class OpportunityFinder:
    """
    新標的推薦掃描器

    流程：
    1. 從市場快照或預設候選清單取得股票
    2. 以基本面條件（ROE、市值、成交量）初篩
    3. 對通過初篩的股票執行 DCF 估值
    4. 以 DCF 低估門檻二次篩選
    5. 依優先級（A/B/C）排序輸出

    Args:
        data_manager: DataManagerV2 實例
        dcf_calculator: DCFCalculator 實例
        market_scanner: MarketScanner 實例（可選；提供時優先使用快照）
    """

    # 台灣主要大型股候選清單（市值前50）
    TAIWAN_50_STOCKS: List[Dict[str, str]] = [
        {"stock_id": "2330", "stock_name": "台積電"},
        {"stock_id": "2317", "stock_name": "鴻海"},
        {"stock_id": "2454", "stock_name": "聯發科"},
        {"stock_id": "2412", "stock_name": "中華電"},
        {"stock_id": "2882", "stock_name": "國泰金"},
        {"stock_id": "2881", "stock_name": "富邦金"},
        {"stock_id": "2886", "stock_name": "兆豐金"},
        {"stock_id": "2892", "stock_name": "第一金"},
        {"stock_id": "2891", "stock_name": "中信金"},
        {"stock_id": "2883", "stock_name": "開發金"},
        {"stock_id": "2885", "stock_name": "元大金"},
        {"stock_id": "2884", "stock_name": "玉山金"},
        {"stock_id": "2890", "stock_name": "永豐金"},
        {"stock_id": "2887", "stock_name": "台新金"},
        {"stock_id": "5880", "stock_name": "合庫金"},
        {"stock_id": "1301", "stock_name": "台塑"},
        {"stock_id": "1303", "stock_name": "南亞"},
        {"stock_id": "1326", "stock_name": "台化"},
        {"stock_id": "1101", "stock_name": "台泥"},
        {"stock_id": "1216", "stock_name": "統一"},
        {"stock_id": "2308", "stock_name": "台達電"},
        {"stock_id": "2002", "stock_name": "中鋼"},
        {"stock_id": "2603", "stock_name": "長榮"},
        {"stock_id": "2609", "stock_name": "陽明"},
        {"stock_id": "2615", "stock_name": "萬海"},
        {"stock_id": "3008", "stock_name": "大立光"},
        {"stock_id": "2357", "stock_name": "華碩"},
        {"stock_id": "2382", "stock_name": "廣達"},
        {"stock_id": "4938", "stock_name": "和碩"},
        {"stock_id": "2395", "stock_name": "研華"},
        {"stock_id": "2303", "stock_name": "聯電"},
        {"stock_id": "3711", "stock_name": "日月光投控"},
        {"stock_id": "5347", "stock_name": "世界先進"},
        {"stock_id": "3034", "stock_name": "聯詠"},
        {"stock_id": "2379", "stock_name": "瑞昱"},
        {"stock_id": "6415", "stock_name": "矽力-KY"},
        {"stock_id": "2301", "stock_name": "光寶科"},
        {"stock_id": "2474", "stock_name": "可成"},
        {"stock_id": "2912", "stock_name": "統一超"},
        {"stock_id": "2207", "stock_name": "和泰車"},
        {"stock_id": "1590", "stock_name": "亞德客-KY"},
        {"stock_id": "9910", "stock_name": "豐泰"},
        {"stock_id": "3231", "stock_name": "緯創"},
        {"stock_id": "2388", "stock_name": "威盛"},
        {"stock_id": "2439", "stock_name": "美律"},
        {"stock_id": "3706", "stock_name": "神達"},
        {"stock_id": "2105", "stock_name": "正新"},
        {"stock_id": "5904", "stock_name": "寶雅"},
        {"stock_id": "2812", "stock_name": "台中銀"},
        {"stock_id": "0050", "stock_name": "元大台灣50"},
    ]

    def __init__(self, data_manager: Any, dcf_calculator: Any, market_scanner: Optional[Any] = None) -> None:
        """
        初始化 OpportunityFinder。

        Args:
            data_manager: DataManagerV2 實例，提供 EPS/財務/股價資料。
            dcf_calculator: DCFCalculator 實例，執行 DCF 計算。
            market_scanner: MarketScanner 實例（可選）。
        """
        self.data_manager = data_manager
        self.dcf_calculator = dcf_calculator
        self.market_scanner = market_scanner

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_opportunities(
        self,
        candidate_stocks: Optional[List[Dict[str, str]]] = None,
        dcf_threshold: float = 0.20,
        min_roe: float = 0.05,
        min_market_cap_b: float = 10.0,
        min_avg_volume: int = 500_000,
        use_market_snapshot: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        掃描候選股票，返回符合條件的推薦清單。

        Args:
            candidate_stocks: 候選股票清單，元素格式為 ``{"stock_id": "2330", "stock_name": "台積電"}``。
                              為 None 時使用 ``TAIWAN_50_STOCKS``。
            dcf_threshold: DCF 低估門檻（upside_potential），預設 0.20（即 20%）。
            min_roe: 最低 ROE 要求，預設 0.05（5%）。
            min_market_cap_b: 最低市值（十億台幣），預設 10.0（100 億）。
            min_avg_volume: 最低平均成交量，預設 500,000 股。
            use_market_snapshot: 是否優先使用市場快照資料（節省 API 呼叫），預設 True。
            progress_callback: 進度回調函數，簽名為 ``(current, total, stock_code)``。

        Returns:
            推薦股票清單，每個元素包含：
            ``stock_code, stock_name, current_price, dcf_value, upside_pct,
            roe, market_cap_b, avg_volume, buy_price, priority, reason``。
            依 priority（A→B→C）再依 upside_pct 降序排列。
        """
        stocks = candidate_stocks if candidate_stocks is not None else self.TAIWAN_50_STOCKS

        # 嘗試從市場快照批次取得基本面資料
        snapshot_map: Dict[str, Any] = {}
        if use_market_snapshot and self.market_scanner is not None:
            try:
                snapshot_df = self.market_scanner.get_market_snapshot()
                if snapshot_df is not None and not snapshot_df.empty:
                    snapshot_map = {
                        str(row["stock_code"]): row
                        for _, row in snapshot_df.iterrows()
                    }
            except Exception as e:
                logger.warning("無法取得市場快照，改用個別 API 查詢: %s", e)

        results: List[Dict[str, Any]] = []
        total = len(stocks)

        for idx, stock in enumerate(stocks):
            stock_code = str(stock.get("stock_id", ""))
            stock_name = str(stock.get("stock_name", stock_code))

            if progress_callback:
                try:
                    progress_callback(idx + 1, total, stock_code)
                except Exception:
                    pass

            if not stock_code:
                continue

            snapshot_row = snapshot_map.get(stock_code)
            result = self._process_stock(
                stock_code=stock_code,
                stock_name=stock_name,
                snapshot_row=snapshot_row,
                dcf_threshold=dcf_threshold,
                min_roe=min_roe,
                min_market_cap_b=min_market_cap_b,
                min_avg_volume=min_avg_volume,
            )
            if result is not None:
                results.append(result)

        # 排序：A > B > C，同優先級內依 upside_pct 降序
        priority_order = {"A": 0, "B": 1, "C": 2}
        results.sort(key=lambda r: (priority_order.get(r["priority"], 9), -r["upside_pct"]))
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_stock(
        self,
        stock_code: str,
        stock_name: str,
        snapshot_row: Optional[Any],
        dcf_threshold: float,
        min_roe: float,
        min_market_cap_b: float,
        min_avg_volume: int,
    ) -> Optional[Dict[str, Any]]:
        """
        處理單一股票的篩選與 DCF 估值。

        Args:
            stock_code: 股票代碼。
            stock_name: 股票名稱。
            snapshot_row: 市場快照列資料（可為 None）。
            dcf_threshold: DCF 低估門檻。
            min_roe: 最低 ROE。
            min_market_cap_b: 最低市值（十億台幣）。
            min_avg_volume: 最低成交量。

        Returns:
            推薦資訊字典，不符合條件時返回 None。
        """
        try:
            # ── Step 1: 取得基本面資料 ──────────────────────────────
            current_price: Optional[float] = None
            roe: Optional[float] = None
            market_cap_b: Optional[float] = None
            avg_volume: Optional[float] = None

            if snapshot_row is not None:
                current_price = self._safe_float(snapshot_row.get("current_price"))
                roe = self._safe_float(snapshot_row.get("roe"))
                market_cap = self._safe_float(snapshot_row.get("market_cap"))
                market_cap_b = market_cap / 1e9 if market_cap else None
                avg_volume = self._safe_float(snapshot_row.get("avg_volume"))

            # 快照缺失時補充取得股價
            if current_price is None or current_price <= 0:
                current_price = self._safe_float(self.data_manager.get_latest_price(stock_code))

            if current_price is None or current_price <= 0:
                return None

            # ── Step 2: 基本面初篩 ─────────────────────────────────
            if roe is not None and roe < min_roe:
                return None
            if market_cap_b is not None and market_cap_b < min_market_cap_b:
                return None
            if avg_volume is not None and avg_volume < min_avg_volume:
                return None

            # ── Step 3: DCF 估值 ───────────────────────────────────
            dcf_result = self._run_dcf(stock_code, stock_name, current_price)
            if dcf_result is None:
                return None

            upside_pct: float = dcf_result.get("upside_potential", 0.0)
            intrinsic_value: float = dcf_result.get("intrinsic_value", 0.0)

            if upside_pct < dcf_threshold:
                return None

            # ── Step 4: 取得買入建議價 ─────────────────────────────
            buy_rec = self.dcf_calculator.calculate_buy_recommendation(
                intrinsic_value=intrinsic_value,
                current_price=current_price,
            )
            buy_price: float = buy_rec.get("recommended_buy_price", intrinsic_value * 0.85)

            # ── Step 5: 優先級與推薦原因 ───────────────────────────
            roe_val = roe if roe is not None else 0.0
            priority = self._assign_priority(upside_pct, roe_val)
            reason = self._build_reason(upside_pct, roe_val, priority)

            return {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "current_price": round(current_price, 2),
                "dcf_value": round(intrinsic_value, 2),
                "upside_pct": round(upside_pct, 4),
                "roe": round(roe_val, 4) if roe is not None else None,
                "market_cap_b": round(market_cap_b, 2) if market_cap_b is not None else None,
                "avg_volume": int(avg_volume) if avg_volume is not None else None,
                "buy_price": round(buy_price, 2),
                "priority": priority,
                "reason": reason,
            }

        except Exception as e:
            logger.debug("處理 %s 時發生錯誤: %s", stock_code, e)
            return None

    def _run_dcf(
        self, stock_code: str, stock_name: str, current_price: float
    ) -> Optional[Dict[str, Any]]:
        """
        取得 EPS 與成長率，執行 DCF 計算。

        Args:
            stock_code: 股票代碼。
            stock_name: 股票名稱。
            current_price: 目前股價。

        Returns:
            DCF 計算結果字典，失敗時返回 None。
        """
        eps = self.data_manager.get_latest_eps(stock_code)
        if not eps or eps <= 0:
            return None

        growth_info = self.data_manager.calculate_historical_growth_rate(stock_code)
        growth_rates = [
            growth_info.get("growth_rate_1_5", 0.15),
            growth_info.get("growth_rate_6_10", 0.08),
        ]
        weighting_method = growth_info.get("weighting_method", "unknown")

        dcf_result = self.dcf_calculator.calculate_dcf_value(
            current_price=current_price,
            current_eps=eps,
            growth_rates=growth_rates,
            stock_code=stock_code,
            stock_name=stock_name,
            data_source=weighting_method,
            weighting_method=weighting_method,
        )
        return dcf_result

    def _assign_priority(self, upside_pct: float, roe: float) -> str:
        """
        依 DCF 低估幅度與 ROE 指定優先級。

        優先級規則：
        - A：upside >= 30% 且 ROE >= 15%
        - B：upside >= 20% 且 ROE >= 10%
        - C：upside >= 20%（其他）

        Args:
            upside_pct: DCF 潛在獲利率（小數，如 0.25 代表 25%）。
            roe: 股東權益報酬率（小數）。

        Returns:
            優先級代碼 "A"、"B" 或 "C"。
        """
        if upside_pct >= 0.30 and roe >= 0.15:
            return "A"
        if upside_pct >= 0.20 and roe >= 0.10:
            return "B"
        return "C"

    @staticmethod
    def _build_reason(upside_pct: float, roe: float, priority: str) -> str:
        """
        產生簡短推薦理由文字。

        Args:
            upside_pct: DCF 潛在獲利率（小數）。
            roe: ROE（小數）。
            priority: 優先級代碼。

        Returns:
            推薦理由字串。
        """
        upside_str = f"DCF 低估 {upside_pct * 100:.1f}%"
        roe_str = f"ROE {roe * 100:.1f}%" if roe else ""
        parts = [p for p in [upside_str, roe_str] if p]
        base = "、".join(parts)

        if priority == "A":
            return f"優質標的：{base}，強烈建議關注"
        if priority == "B":
            return f"潛力標的：{base}，值得追蹤"
        return f"候選標的：{base}"

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        """安全地將值轉換為 float，失敗時返回 None。"""
        if value is None:
            return None
        try:
            f = float(value)
            if f != f:  # NaN check
                return None
            return f
        except (TypeError, ValueError):
            return None
