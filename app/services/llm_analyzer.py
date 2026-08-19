"""LLM 智慧分析報告模組。

整合四季財報、DCF 估值結果、60 日價格走勢與法人籌碼變化，
透過可抽換的 LLM 後端產出結構化分析報告。
提供 rule-based 降級策略，確保在 LLM 不可用時仍能產出基礎分析。

核心特性：
    - 可抽換 LLM 後端（透過 LLMBackendProtocol DI 注入）
    - 逾時 30 秒保護（ThreadPoolExecutor）
    - Rule-based 降級：API 失敗或逾時自動切換
    - 資料來源與計算日期追溯
    - 結構化報告輸出（AnalysisReport dataclass）

Usage::

    from app.services.llm_analyzer import LLMAnalyzer

    analyzer = LLMAnalyzer(llm_backend=my_llm, data_pipeline=pipeline)
    report = analyzer.generate_report("2330", dcf_result=dcf)
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.models.financial import DCFResult
from app.core.protocols import LLMBackendProtocol
from app.infra.logging import get_logger, get_stock_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# AnalysisReport 資料結構
# ---------------------------------------------------------------------------


@dataclass
class AnalysisReport:
    """LLM 分析報告。

    封裝結構化的投資分析結果，包含投資摘要、財務體質評分、
    風險因子與建議操作。標明資料來源與計算日期以確保可追溯性。

    Attributes:
        summary: 投資摘要（不超過 100 字）。
        health_score: 財務體質評分（1-10，10 為最佳）。
        risk_factors: 風險因子列表。
        recommendation: 建議操作（買入/持有/減碼/賣出）。
        data_sources: 資料來源列表，每項含 name 與 date。
        generated_at: 報告產生時間。
        is_ai_generated: True 表示由 LLM 產生，False 表示 rule-based。
        warning: 附加警告訊息（如使用降級策略時）。
    """

    summary: str
    health_score: int
    risk_factors: List[str]
    recommendation: str
    data_sources: List[Dict[str, str]]
    generated_at: datetime
    is_ai_generated: bool
    warning: Optional[str] = None


# ---------------------------------------------------------------------------
# 有效建議操作常數
# ---------------------------------------------------------------------------

_VALID_RECOMMENDATIONS = ("買入", "持有", "減碼", "賣出")


# ---------------------------------------------------------------------------
# LLMAnalyzer 主類別
# ---------------------------------------------------------------------------


class LLMAnalyzer:
    """LLM 智慧分析器。

    整合多維度資料（財報、DCF、價格走勢、籌碼）並透過 LLM 產出
    結構化投資分析報告。當 LLM 不可用或逾時時，自動降級為
    rule-based 基礎分析。

    Args:
        llm_backend: LLM 後端實例（實作 LLMBackendProtocol）。
            若為 None，則一律使用 rule-based 分析。
        data_pipeline: 資料管線實例，用於取得財報與價格資料。
            若為 None，則僅使用傳入的 dcf_result 進行分析。
        timeout: LLM API 呼叫逾時秒數，預設 30.0。

    Example::

        from app.services.llm_analyzer import LLMAnalyzer

        analyzer = LLMAnalyzer(llm_backend=openai_backend, timeout=30.0)
        report = analyzer.generate_report("2330", dcf_result=my_dcf)
        print(report.summary)
        print(report.health_score)
    """

    def __init__(
        self,
        llm_backend: Optional[LLMBackendProtocol] = None,
        data_pipeline: Optional[Any] = None,
        timeout: float = 30.0,
    ) -> None:
        """初始化 LLM 分析器。

        Args:
            llm_backend: LLM 後端實例，若為 None 則使用 rule-based。
            data_pipeline: 資料管線實例（DataPipeline），可選。
            timeout: LLM 呼叫逾時秒數，預設 30.0。
        """
        self._llm_backend = llm_backend
        self._data_pipeline = data_pipeline
        self._timeout = timeout

        logger.info(
            "LLMAnalyzer initialized: llm_backend=%s, timeout=%.1fs",
            type(llm_backend).__name__ if llm_backend else "None",
            timeout,
        )

    # ------------------------------------------------------------------
    # 公開介面
    # ------------------------------------------------------------------

    def generate_report(
        self,
        stock_code: str,
        dcf_result: Optional[DCFResult] = None,
        financial_data: Optional[List[Dict[str, Any]]] = None,
        price_trend: Optional[List[Dict[str, Any]]] = None,
        chip_data: Optional[Dict[str, Any]] = None,
    ) -> AnalysisReport:
        """產生結構化投資分析報告。

        整合各維度資料後嘗試使用 LLM 產出分析；
        若 LLM 不可用、逾時或失敗則自動降級為 rule-based 分析。

        Args:
            stock_code: 股票代碼。
            dcf_result: DCF 估值結果（可選）。
            financial_data: 最近四季財報資料列表（可選）。
                每筆為 dict，含 period, eps, roe, pe_ratio 等欄位。
            price_trend: 近 60 日價格走勢列表（可選）。
                每筆為 dict，含 date, close 等欄位。
            chip_data: 法人籌碼變化資料（可選）。
                含 foreign_consecutive_buy, trust_consecutive_buy 等欄位。

        Returns:
            AnalysisReport 結構化報告。
        """
        stock_log = get_stock_logger(__name__, stock_code)

        # 彙整分析資料
        data = self._collect_analysis_data(
            stock_code=stock_code,
            dcf_result=dcf_result,
            financial_data=financial_data,
            price_trend=price_trend,
            chip_data=chip_data,
        )

        # 無 LLM 後端 -> 直接 rule-based
        if self._llm_backend is None:
            stock_log.info("無 LLM 後端，使用 rule-based 分析")
            return self._generate_rule_based(stock_code, data)

        # 嘗試 LLM 分析
        prompt = self._build_analysis_prompt(stock_code, data)
        llm_response = self._generate_with_llm(prompt)

        if llm_response is not None:
            # 嘗試解析 LLM 回應
            report = self._parse_llm_response(llm_response, stock_code, data)
            if report is not None:
                stock_log.info("[OK] LLM 分析報告產生成功")
                return report
            else:
                stock_log.warning("LLM 回應解析失敗，降級為 rule-based")

        # LLM 失敗 -> rule-based 降級
        stock_log.info("降級為 rule-based 基礎分析")
        report = self._generate_rule_based(stock_code, data)
        report.warning = "LLM 分析不可用，已使用規則式基礎分析"
        return report

    # ------------------------------------------------------------------
    # LLM 呼叫（含逾時保護）
    # ------------------------------------------------------------------

    def _generate_with_llm(self, prompt: str) -> Optional[str]:
        """透過 LLM 後端產生回應，含 30 秒逾時保護。

        使用 ThreadPoolExecutor 包裹 LLM 呼叫，在逾時後回傳 None
        觸發降級策略。

        Args:
            prompt: 分析提示詞文字。

        Returns:
            LLM 產生的文字回應，若逾時或失敗則回傳 None。
        """
        if self._llm_backend is None:
            return None

        def _call_llm() -> str:
            return self._llm_backend.generate(prompt, max_tokens=2000)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call_llm)
            try:
                result = future.result(timeout=self._timeout)
                return result
            except FuturesTimeoutError:
                logger.warning(
                    "LLM API 呼叫逾時 (>%.0fs)，啟動降級策略",
                    self._timeout,
                )
                return None
            except Exception as exc:
                logger.warning(
                    "LLM API 呼叫失敗: %s，啟動降級策略",
                    str(exc)[:200],
                )
                return None

    # ------------------------------------------------------------------
    # Rule-based 降級分析
    # ------------------------------------------------------------------

    def _generate_rule_based(
        self, stock_code: str, data: Dict[str, Any]
    ) -> AnalysisReport:
        """以規則式邏輯產出基礎分析報告。

        根據 DCF upside_potential 決定建議操作，
        依據 ROE、PE ratio、成長率計算財務體質評分，
        從明顯指標列出風險因子。

        Args:
            stock_code: 股票代碼。
            data: 彙整後的分析資料字典。

        Returns:
            AnalysisReport 結構化報告（is_ai_generated=False）。
        """
        # 計算財務體質評分
        health_score = self._calculate_health_score(data)

        # 判斷建議操作
        recommendation = self._determine_recommendation(data)

        # 列出風險因子
        risk_factors = self._identify_risk_factors(data)

        # 產出投資摘要
        summary = self._generate_summary(stock_code, data, recommendation)

        # 彙整資料來源
        data_sources = self._collect_data_source_refs(data)

        return AnalysisReport(
            summary=summary,
            health_score=health_score,
            risk_factors=risk_factors,
            recommendation=recommendation,
            data_sources=data_sources,
            generated_at=datetime.now(),
            is_ai_generated=False,
        )

    def _calculate_health_score(self, data: Dict[str, Any]) -> int:
        """根據財務指標計算體質評分。

        評分維度（各 0-2 分，基礎 1 分，滿分 10）：
        - ROE（>15% 加 2，>8% 加 1）
        - PE ratio（<15 加 2，<25 加 1）
        - 成長性（EPS 季增率 > 0 加 1-2）
        - DCF 安全邊際（upside > 20% 加 2，> 0% 加 1）
        - 籌碼面（法人買超加 1-2）

        Args:
            data: 彙整後的分析資料字典。

        Returns:
            財務體質評分，範圍 1-10。
        """
        score = 1  # 基礎分

        # ROE 評分
        roe = data.get("latest_roe")
        if roe is not None:
            if roe > 15:
                score += 2
            elif roe > 8:
                score += 1

        # PE ratio 評分
        pe = data.get("latest_pe")
        if pe is not None and pe > 0:
            if pe < 15:
                score += 2
            elif pe < 25:
                score += 1

        # 成長性評分
        eps_growth = data.get("eps_growth")
        if eps_growth is not None:
            if eps_growth > 0.2:
                score += 2
            elif eps_growth > 0:
                score += 1

        # DCF 安全邊際
        upside = data.get("upside_potential")
        if upside is not None:
            if upside > 0.2:
                score += 2
            elif upside > 0:
                score += 1

        # 籌碼面
        foreign_buy = data.get("foreign_consecutive_buy", 0) or 0
        trust_buy = data.get("trust_consecutive_buy", 0) or 0
        if foreign_buy >= 5 or trust_buy >= 5:
            score += 2
        elif foreign_buy >= 3 or trust_buy >= 3:
            score += 1

        # 限制範圍 1-10
        return max(1, min(10, score))

    def _determine_recommendation(self, data: Dict[str, Any]) -> str:
        """根據 DCF upside_potential 與籌碼面決定建議操作。

        決策規則：
        - upside > 30% 且法人買超 -> 買入
        - upside > 10% -> 持有
        - upside < -10% -> 減碼
        - upside < -20% 或嚴重風險 -> 賣出
        - 無 DCF 資料 -> 持有（保守）

        Args:
            data: 彙整後的分析資料字典。

        Returns:
            建議操作字串（買入/持有/減碼/賣出）。
        """
        upside = data.get("upside_potential")

        if upside is None:
            return "持有"

        foreign_buy = data.get("foreign_consecutive_buy", 0) or 0

        if upside > 0.3 and foreign_buy >= 3:
            return "買入"
        elif upside > 0.3:
            return "買入"
        elif upside > 0.1:
            return "持有"
        elif upside > -0.1:
            return "持有"
        elif upside > -0.2:
            return "減碼"
        else:
            return "賣出"

    def _identify_risk_factors(self, data: Dict[str, Any]) -> List[str]:
        """從財務指標中辨識風險因子。

        檢查項目：
        - 高本益比（PE > 40）
        - 低 ROE（< 5%）
        - EPS 衰退
        - 法人連續賣超
        - 股價位於高檔
        - DCF 顯示高估

        Args:
            data: 彙整後的分析資料字典。

        Returns:
            風險因子描述字串列表。
        """
        risks: List[str] = []

        pe = data.get("latest_pe")
        if pe is not None and pe > 40:
            risks.append(f"本益比偏高 ({pe:.1f})")

        roe = data.get("latest_roe")
        if roe is not None and roe < 5:
            risks.append(f"ROE 偏低 ({roe:.1f}%)")

        eps_growth = data.get("eps_growth")
        if eps_growth is not None and eps_growth < -0.1:
            risks.append(f"EPS 衰退 ({eps_growth*100:.1f}%)")

        foreign_buy = data.get("foreign_consecutive_buy", 0) or 0
        if foreign_buy < -3:
            risks.append(f"外資連續賣超 {abs(foreign_buy)} 日")

        upside = data.get("upside_potential")
        if upside is not None and upside < -0.2:
            risks.append("DCF 估值顯示高估超過 20%")

        price_position = data.get("price_position")
        if price_position is not None and price_position > 0.9:
            risks.append("股價接近 52 週高點")

        if not risks:
            risks.append("目前未偵測到明顯風險因子")

        return risks

    def _generate_summary(
        self,
        stock_code: str,
        data: Dict[str, Any],
        recommendation: str,
    ) -> str:
        """產出投資摘要文字（不超過 100 字）。

        Args:
            stock_code: 股票代碼。
            data: 彙整後的分析資料字典。
            recommendation: 建議操作。

        Returns:
            投資摘要字串，長度不超過 100 字。
        """
        parts: List[str] = [f"{stock_code}"]

        upside = data.get("upside_potential")
        if upside is not None:
            if upside > 0:
                parts.append(f"目前低估約{upside*100:.0f}%")
            else:
                parts.append(f"目前高估約{abs(upside)*100:.0f}%")

        roe = data.get("latest_roe")
        if roe is not None:
            parts.append(f"ROE {roe:.1f}%")

        pe = data.get("latest_pe")
        if pe is not None and pe > 0:
            parts.append(f"PE {pe:.1f}")

        parts.append(f"建議{recommendation}")

        summary = "，".join(parts) + "。"

        # 確保不超過 100 字
        if len(summary) > 100:
            summary = summary[:97] + "..."

        return summary

    # ------------------------------------------------------------------
    # 資料彙整
    # ------------------------------------------------------------------

    def _collect_analysis_data(
        self,
        stock_code: str,
        dcf_result: Optional[DCFResult],
        financial_data: Optional[List[Dict[str, Any]]],
        price_trend: Optional[List[Dict[str, Any]]],
        chip_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """彙整各維度分析資料為統一字典。

        Args:
            stock_code: 股票代碼。
            dcf_result: DCF 估值結果。
            financial_data: 四季財報資料列表。
            price_trend: 60 日價格走勢。
            chip_data: 法人籌碼變化。

        Returns:
            包含所有可用分析資料的字典。
        """
        data: Dict[str, Any] = {
            "stock_code": stock_code,
            "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        }

        # DCF 資料
        if dcf_result is not None:
            data["upside_potential"] = dcf_result.upside_potential
            data["intrinsic_value"] = dcf_result.intrinsic_value
            data["current_price"] = dcf_result.current_price
            data["discount_rate"] = dcf_result.discount_rate
            data["dcf_recommendation"] = dcf_result.recommendation
            data["dcf_source"] = dcf_result.data_source
            data["dcf_calculated_at"] = (
                dcf_result.calculated_at.strftime("%Y-%m-%d")
                if dcf_result.calculated_at
                else None
            )

        # 財報資料
        if financial_data:
            data["financial_quarters"] = financial_data
            latest = financial_data[0] if financial_data else {}
            data["latest_roe"] = latest.get("roe")
            data["latest_pe"] = latest.get("pe_ratio")
            data["latest_eps"] = latest.get("eps")

            # 計算 EPS 成長率（最新 vs 去年同期）
            if len(financial_data) >= 4:
                latest_eps = financial_data[0].get("eps")
                prev_eps = financial_data[3].get("eps")
                if (
                    latest_eps is not None
                    and prev_eps is not None
                    and prev_eps != 0
                ):
                    data["eps_growth"] = (latest_eps - prev_eps) / abs(
                        prev_eps
                    )

        # 價格走勢
        if price_trend:
            data["price_trend"] = price_trend
            if len(price_trend) >= 2:
                first_close = price_trend[0].get("close", 0)
                last_close = price_trend[-1].get("close", 0)
                if first_close and first_close > 0:
                    data["price_change_60d"] = (
                        (last_close - first_close) / first_close
                    )
                # 計算股價位階（簡易版）
                closes = [
                    p.get("close", 0)
                    for p in price_trend
                    if p.get("close", 0) > 0
                ]
                if closes:
                    min_p = min(closes)
                    max_p = max(closes)
                    if max_p > min_p:
                        data["price_position"] = (
                            (closes[-1] - min_p) / (max_p - min_p)
                        )

        # 籌碼資料
        if chip_data:
            data["foreign_consecutive_buy"] = chip_data.get(
                "foreign_consecutive_buy"
            )
            data["trust_consecutive_buy"] = chip_data.get(
                "trust_consecutive_buy"
            )
            data["total_institutional_buy"] = chip_data.get(
                "total_institutional_buy"
            )

        return data

    def _collect_data_source_refs(
        self, data: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """彙整報告中使用的資料來源參考。

        Args:
            data: 彙整後的分析資料字典。

        Returns:
            資料來源列表，每項含 name 與 date 鍵。
        """
        sources: List[Dict[str, str]] = []
        analysis_date = data.get("analysis_date", "N/A")

        if data.get("upside_potential") is not None:
            dcf_date = data.get("dcf_calculated_at", analysis_date)
            sources.append({
                "name": "DCF 估值結果",
                "date": dcf_date or analysis_date,
            })

        if data.get("financial_quarters"):
            sources.append({
                "name": "季度財報資料",
                "date": analysis_date,
            })

        if data.get("price_trend"):
            sources.append({
                "name": "60 日價格走勢",
                "date": analysis_date,
            })

        if data.get("foreign_consecutive_buy") is not None:
            sources.append({
                "name": "法人籌碼資料",
                "date": analysis_date,
            })

        if not sources:
            sources.append({
                "name": "基礎分析",
                "date": analysis_date,
            })

        return sources

    # ------------------------------------------------------------------
    # LLM 提示詞建構
    # ------------------------------------------------------------------

    def _build_analysis_prompt(
        self, stock_code: str, data: Dict[str, Any]
    ) -> str:
        """建構 LLM 分析提示詞。

        將彙整後的各維度資料格式化為結構化提示詞，
        指示 LLM 產出 JSON 格式的結構化報告。

        Args:
            stock_code: 股票代碼。
            data: 彙整後的分析資料字典。

        Returns:
            完整的分析提示詞文字。
        """
        sections: List[str] = []

        sections.append(
            f"你是一位專業的台股投資分析師。請分析股票 {stock_code} "
            f"的投資價值，並以 JSON 格式回覆。"
        )

        # DCF 資料
        if data.get("upside_potential") is not None:
            sections.append(
                "\n## DCF 估值結果\n"
                f"- 目前股價: {data.get('current_price', 'N/A')}\n"
                f"- 內在價值: {data.get('intrinsic_value', 'N/A')}\n"
                f"- 潛在獲利率: {data['upside_potential']*100:.1f}%\n"
                f"- 折現率: {data.get('discount_rate', 'N/A')}"
            )

        # 財報資料
        if data.get("financial_quarters"):
            quarters = data["financial_quarters"][:4]
            fin_lines = ["\n## 最近四季財報"]
            for q in quarters:
                period = q.get("period", "N/A")
                eps = q.get("eps", "N/A")
                roe = q.get("roe", "N/A")
                pe = q.get("pe_ratio", "N/A")
                fin_lines.append(
                    f"- {period}: EPS={eps}, ROE={roe}%, PE={pe}"
                )
            sections.append("\n".join(fin_lines))

        # 價格走勢
        price_change = data.get("price_change_60d")
        if price_change is not None:
            sections.append(
                f"\n## 60 日價格走勢\n"
                f"- 60 日漲跌幅: {price_change*100:.1f}%\n"
                f"- 價格位階: {data.get('price_position', 'N/A')}"
            )

        # 籌碼資料
        foreign_buy = data.get("foreign_consecutive_buy")
        trust_buy = data.get("trust_consecutive_buy")
        if foreign_buy is not None or trust_buy is not None:
            sections.append(
                f"\n## 法人籌碼\n"
                f"- 外資連續買超天數: {foreign_buy or 'N/A'}\n"
                f"- 投信連續買超天數: {trust_buy or 'N/A'}\n"
                f"- 三大法人合計: "
                f"{data.get('total_institutional_buy', 'N/A')} 張"
            )

        # 輸出格式要求
        sections.append(
            '\n## 請以下列 JSON 格式回覆\n'
            '```json\n'
            '{\n'
            '  "summary": "投資摘要（不超過100字）",\n'
            '  "health_score": 7,\n'
            '  "risk_factors": ["風險1", "風險2"],\n'
            '  "recommendation": "買入/持有/減碼/賣出"\n'
            '}\n'
            '```\n'
            "注意：summary 不超過 100 字；"
            "health_score 為 1-10 整數；"
            "recommendation 僅能為「買入」「持有」「減碼」「賣出」四者之一。"
        )

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # LLM 回應解析
    # ------------------------------------------------------------------

    def _parse_llm_response(
        self,
        response: str,
        stock_code: str,
        data: Dict[str, Any],
    ) -> Optional[AnalysisReport]:
        """解析 LLM 回應為 AnalysisReport。

        嘗試從 LLM 文字回應中提取 JSON 區塊並建構報告。
        解析失敗時回傳 None（觸發降級策略）。

        Args:
            response: LLM 回傳的原始文字。
            stock_code: 股票代碼。
            data: 彙整後的分析資料字典。

        Returns:
            AnalysisReport 實例，解析失敗回傳 None。
        """
        try:
            # 嘗試提取 JSON 區塊
            json_str = self._extract_json(response)
            if json_str is None:
                return None

            parsed = json.loads(json_str)

            # 驗證必要欄位
            summary = parsed.get("summary", "")
            health_score = parsed.get("health_score", 5)
            risk_factors = parsed.get("risk_factors", [])
            recommendation = parsed.get("recommendation", "持有")

            # 摘要長度限制
            if len(summary) > 100:
                summary = summary[:97] + "..."

            # 評分範圍限制
            health_score = max(1, min(10, int(health_score)))

            # 建議操作驗證
            if recommendation not in _VALID_RECOMMENDATIONS:
                recommendation = "持有"

            # 風險因子確保為列表
            if not isinstance(risk_factors, list):
                risk_factors = [str(risk_factors)]
            risk_factors = [str(r) for r in risk_factors]

            return AnalysisReport(
                summary=summary,
                health_score=health_score,
                risk_factors=risk_factors,
                recommendation=recommendation,
                data_sources=self._collect_data_source_refs(data),
                generated_at=datetime.now(),
                is_ai_generated=True,
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "LLM 回應解析失敗: %s", str(exc)[:200]
            )
            return None

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """從文字中提取 JSON 區塊。

        支援從 markdown code block 或直接 JSON 文字中提取。

        Args:
            text: 包含 JSON 的原始文字。

        Returns:
            JSON 字串，若未找到回傳 None。
        """
        # 嘗試 markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 嘗試直接尋找 { ... }
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            return match.group(0)

        return None
