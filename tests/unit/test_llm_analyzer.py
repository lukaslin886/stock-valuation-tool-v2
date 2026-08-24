"""LLM Analyzer 單元測試。

驗證 LLMAnalyzer 的核心邏輯：
- Rule-based 降級分析正確性
- LLM 逾時保護（ThreadPoolExecutor 30s）
- LLM 回應解析
- 結構化報告欄位驗證
- 資料來源追溯
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from app.core.models.financial import DCFResult
from app.services.llm_analyzer import (
    AnalysisReport,
    LLMAnalyzer,
    _VALID_RECOMMENDATIONS,
)


# ---------------------------------------------------------------------------
# 測試用 Mock LLM Backend
# ---------------------------------------------------------------------------


class MockLLMBackend:
    """測試用 LLM 後端。"""

    def __init__(
        self,
        response: str = "",
        delay: float = 0.0,
        error: Optional[Exception] = None,
    ) -> None:
        self.response = response
        self.delay = delay
        self.error = error
        self.call_count = 0
        self.last_prompt: Optional[str] = None

    def generate(self, prompt: str, max_tokens: int = 2000) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        if self.delay > 0:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.response


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_dcf() -> DCFResult:
    """產生測試用 DCF 結果。"""
    return DCFResult(
        stock_code="2330",
        stock_name="台積電",
        current_price=600.0,
        intrinsic_value=800.0,
        upside_potential=0.33,
        discount_rate=0.08,
        growth_rates=[0.15, 0.10],
        terminal_value=12000.0,
        recommendation="買入",
        data_source="test",
    )


@pytest.fixture
def sample_financial_data() -> List[Dict[str, Any]]:
    """產生測試用四季財報。"""
    return [
        {"period": "2024Q4", "eps": 10.0, "roe": 25.0, "pe_ratio": 18.0},
        {"period": "2024Q3", "eps": 9.5, "roe": 24.0, "pe_ratio": 19.0},
        {"period": "2024Q2", "eps": 9.0, "roe": 23.0, "pe_ratio": 20.0},
        {"period": "2024Q1", "eps": 8.0, "roe": 22.0, "pe_ratio": 21.0},
    ]


@pytest.fixture
def sample_chip_data() -> Dict[str, Any]:
    """產生測試用籌碼資料。"""
    return {
        "foreign_consecutive_buy": 5,
        "trust_consecutive_buy": 3,
        "total_institutional_buy": 12000,
    }


# ---------------------------------------------------------------------------
# 測試：Rule-based 降級分析
# ---------------------------------------------------------------------------


class TestRuleBasedAnalysis:
    """測試 rule-based 基礎分析邏輯。"""

    def test_no_llm_backend_uses_rule_based(
        self, sample_dcf: DCFResult
    ) -> None:
        """無 LLM 後端時應使用 rule-based 分析。"""
        analyzer = LLMAnalyzer(llm_backend=None)
        report = analyzer.generate_report("2330", dcf_result=sample_dcf)

        assert report.is_ai_generated is False
        assert report.recommendation in _VALID_RECOMMENDATIONS
        assert 1 <= report.health_score <= 10
        assert len(report.summary) <= 100

    def test_recommendation_buy_on_high_upside(
        self, sample_dcf: DCFResult
    ) -> None:
        """DCF 高低估 + 法人買超應建議買入。"""
        analyzer = LLMAnalyzer(llm_backend=None)
        chip = {"foreign_consecutive_buy": 5, "trust_consecutive_buy": 3}
        report = analyzer.generate_report(
            "2330", dcf_result=sample_dcf, chip_data=chip
        )
        assert report.recommendation == "買入"

    def test_recommendation_sell_on_overvalued(self) -> None:
        """DCF 高估超過 20% 應建議賣出。"""
        dcf = DCFResult(
            stock_code="2330",
            current_price=1000.0,
            intrinsic_value=700.0,
            upside_potential=-0.30,
            discount_rate=0.08,
            growth_rates=[0.05],
            terminal_value=5000.0,
        )
        analyzer = LLMAnalyzer(llm_backend=None)
        report = analyzer.generate_report("2330", dcf_result=dcf)
        assert report.recommendation == "賣出"

    def test_recommendation_hold_when_no_dcf(self) -> None:
        """無 DCF 資料時預設建議持有。"""
        analyzer = LLMAnalyzer(llm_backend=None)
        report = analyzer.generate_report("2330")
        assert report.recommendation == "持有"

    def test_health_score_high_quality(
        self,
        sample_dcf: DCFResult,
        sample_financial_data: List[Dict[str, Any]],
        sample_chip_data: Dict[str, Any],
    ) -> None:
        """高品質股票應有高體質評分。"""
        analyzer = LLMAnalyzer(llm_backend=None)
        report = analyzer.generate_report(
            "2330",
            dcf_result=sample_dcf,
            financial_data=sample_financial_data,
            chip_data=sample_chip_data,
        )
        # 高 ROE + 低 PE + 高 upside + 法人買超 -> 高分
        assert report.health_score >= 7

    def test_health_score_low_quality(self) -> None:
        """低品質指標應有低體質評分。"""
        dcf = DCFResult(
            stock_code="9999",
            current_price=100.0,
            intrinsic_value=80.0,
            upside_potential=-0.2,
            discount_rate=0.08,
            growth_rates=[0.01],
            terminal_value=1000.0,
        )
        bad_fin = [
            {"period": "2024Q4", "eps": 1.0, "roe": 3.0, "pe_ratio": 50.0},
            {"period": "2024Q3", "eps": 1.5, "roe": 3.5, "pe_ratio": 45.0},
            {"period": "2024Q2", "eps": 1.8, "roe": 4.0, "pe_ratio": 40.0},
            {"period": "2024Q1", "eps": 2.0, "roe": 4.5, "pe_ratio": 38.0},
        ]
        analyzer = LLMAnalyzer(llm_backend=None)
        report = analyzer.generate_report(
            "9999", dcf_result=dcf, financial_data=bad_fin
        )
        assert report.health_score <= 4

    def test_risk_factors_high_pe(self) -> None:
        """高 PE 應列入風險因子。"""
        fin = [{"period": "2024Q4", "eps": 2.0, "roe": 8.0, "pe_ratio": 55.0}]
        analyzer = LLMAnalyzer(llm_backend=None)
        report = analyzer.generate_report("2330", financial_data=fin)
        assert any("本益比" in r for r in report.risk_factors)

    def test_risk_factors_low_roe(self) -> None:
        """低 ROE 應列入風險因子。"""
        fin = [{"period": "2024Q4", "eps": 2.0, "roe": 3.0, "pe_ratio": 15.0}]
        analyzer = LLMAnalyzer(llm_backend=None)
        report = analyzer.generate_report("2330", financial_data=fin)
        assert any("ROE" in r for r in report.risk_factors)

    def test_data_sources_populated(
        self, sample_dcf: DCFResult, sample_financial_data: List[Dict[str, Any]]
    ) -> None:
        """報告應包含資料來源與日期。"""
        analyzer = LLMAnalyzer(llm_backend=None)
        report = analyzer.generate_report(
            "2330", dcf_result=sample_dcf, financial_data=sample_financial_data
        )
        assert len(report.data_sources) >= 2
        for src in report.data_sources:
            assert "name" in src
            assert "date" in src

    def test_summary_within_100_chars(
        self, sample_dcf: DCFResult, sample_financial_data: List[Dict[str, Any]]
    ) -> None:
        """投資摘要不應超過 100 字。"""
        analyzer = LLMAnalyzer(llm_backend=None)
        report = analyzer.generate_report(
            "2330", dcf_result=sample_dcf, financial_data=sample_financial_data
        )
        assert len(report.summary) <= 100


# ---------------------------------------------------------------------------
# 測試：LLM 整合與逾時保護
# ---------------------------------------------------------------------------


class TestLLMIntegration:
    """測試 LLM 後端整合與逾時保護。"""

    def test_llm_success_produces_ai_report(self) -> None:
        """LLM 成功回應應產出 AI 生成報告。"""
        response = '''```json
{
  "summary": "台積電基本面強勁，建議買入",
  "health_score": 8,
  "risk_factors": ["半導體週期風險", "地緣政治風險"],
  "recommendation": "買入"
}
```'''
        backend = MockLLMBackend(response=response)
        analyzer = LLMAnalyzer(llm_backend=backend)
        dcf = DCFResult(
            stock_code="2330",
            current_price=600.0,
            intrinsic_value=800.0,
            upside_potential=0.33,
            discount_rate=0.08,
            growth_rates=[0.15],
            terminal_value=10000.0,
        )
        report = analyzer.generate_report("2330", dcf_result=dcf)

        assert report.is_ai_generated is True
        assert report.health_score == 8
        assert report.recommendation == "買入"
        assert len(report.risk_factors) == 2

    def test_llm_timeout_triggers_fallback(self) -> None:
        """LLM 逾時應降級為 rule-based。"""
        backend = MockLLMBackend(delay=5.0)  # 模擬慢回應
        analyzer = LLMAnalyzer(llm_backend=backend, timeout=0.5)
        dcf = DCFResult(
            stock_code="2330",
            current_price=600.0,
            intrinsic_value=800.0,
            upside_potential=0.33,
            discount_rate=0.08,
            growth_rates=[0.15],
            terminal_value=10000.0,
        )
        report = analyzer.generate_report("2330", dcf_result=dcf)

        assert report.is_ai_generated is False
        assert report.warning is not None
        assert "規則式" in report.warning or "rule" in report.warning.lower()

    def test_llm_error_triggers_fallback(self) -> None:
        """LLM API 錯誤應降級為 rule-based。"""
        backend = MockLLMBackend(error=RuntimeError("API unavailable"))
        analyzer = LLMAnalyzer(llm_backend=backend)
        report = analyzer.generate_report("2330")

        assert report.is_ai_generated is False
        assert report.warning is not None

    def test_llm_invalid_json_triggers_fallback(self) -> None:
        """LLM 回傳無效 JSON 應降級為 rule-based。"""
        backend = MockLLMBackend(response="This is not JSON at all")
        analyzer = LLMAnalyzer(llm_backend=backend)
        report = analyzer.generate_report("2330")

        assert report.is_ai_generated is False

    def test_llm_partial_json_with_missing_fields(self) -> None:
        """LLM 回傳缺少欄位的 JSON 應有合理預設值。"""
        response = '{"summary": "test", "health_score": 6}'
        backend = MockLLMBackend(response=response)
        analyzer = LLMAnalyzer(llm_backend=backend)
        report = analyzer.generate_report("2330")

        assert report.is_ai_generated is True
        assert report.health_score == 6
        # 缺少 recommendation -> 預設 "持有"
        assert report.recommendation == "持有"

    def test_llm_health_score_clamped(self) -> None:
        """LLM 回傳超出範圍的 health_score 應被限制。"""
        response = '''{
  "summary": "test",
  "health_score": 15,
  "risk_factors": [],
  "recommendation": "買入"
}'''
        backend = MockLLMBackend(response=response)
        analyzer = LLMAnalyzer(llm_backend=backend)
        report = analyzer.generate_report("2330")

        assert report.is_ai_generated is True
        assert report.health_score == 10

    def test_llm_invalid_recommendation_defaults(self) -> None:
        """LLM 回傳無效 recommendation 應預設持有。"""
        response = '''{
  "summary": "test",
  "health_score": 5,
  "risk_factors": [],
  "recommendation": "invalid_value"
}'''
        backend = MockLLMBackend(response=response)
        analyzer = LLMAnalyzer(llm_backend=backend)
        report = analyzer.generate_report("2330")

        assert report.recommendation == "持有"

    def test_prompt_includes_data_sections(
        self, sample_dcf: DCFResult
    ) -> None:
        """提示詞應包含傳入的各維度資料。"""
        response = '{"summary":"x","health_score":5,"risk_factors":[],"recommendation":"持有"}'
        backend = MockLLMBackend(response=response)
        analyzer = LLMAnalyzer(llm_backend=backend)
        fin = [{"period": "2024Q4", "eps": 10.0, "roe": 25.0, "pe_ratio": 18.0}]
        chip = {"foreign_consecutive_buy": 3, "trust_consecutive_buy": 2}

        analyzer.generate_report(
            "2330",
            dcf_result=sample_dcf,
            financial_data=fin,
            chip_data=chip,
        )

        prompt = backend.last_prompt
        assert prompt is not None
        assert "2330" in prompt
        assert "DCF" in prompt
        assert "財報" in prompt
        assert "籌碼" in prompt
