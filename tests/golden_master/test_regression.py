"""Golden Master regression test verifying Canonical Core equivalence.

Validates Property 1: Canonical_Core output equivalence with baseline snapshot (< 1% error).
Validates: Requirements 1.4, 4.2, 6.1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from app.services.dcf_calculator import DCFCalculator as LayeredDCFCalculator
from app.services.dcf_legacy_adapter import LegacyDCFAdapter


BASELINE_FILE = Path(__file__).parent / "baseline.json"


@pytest.fixture(scope="module")
def baseline_data() -> Dict[str, Any]:
    """Load the golden master baseline snapshot."""
    if not BASELINE_FILE.exists():
        pytest.fail(f"Baseline file missing at {BASELINE_FILE}")
    with open(BASELINE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


class TestGoldenMasterRegression:
    """Regression test suite comparing current calculator/adapter against baseline."""

    def test_baseline_structure(self, baseline_data: Dict[str, Any]) -> None:
        """Verify baseline metadata and case count."""
        assert baseline_data.get("schema_version") == 1
        assert "cases" in baseline_data
        assert len(baseline_data["cases"]) >= 20

    def test_layered_calculator_numerical_equivalence(
        self, baseline_data: Dict[str, Any]
    ) -> None:
        """Verify that LayeredDCFCalculator produces intrinsic value within 1% of baseline."""
        layered = LayeredDCFCalculator()

        for case in baseline_data["cases"]:
            stock_code = case["stock_code"]
            inputs = case["inputs"]
            expected_layered = case["layered"]

            result = layered.calculate_dcf_value(**inputs)

            # Check intrinsic value
            exp_val = expected_layered["intrinsic_value"]
            actual_val = result.intrinsic_value

            if exp_val == 0.0:
                assert actual_val == 0.0, f"Mismatch for {stock_code}: {actual_val} vs {exp_val}"
            else:
                rel_err = abs(actual_val - exp_val) / abs(exp_val)
                assert rel_err < 0.01, (
                    f"Stock {stock_code} intrinsic value error {rel_err:.4%} exceeds 1%: "
                    f"actual={actual_val}, expected={exp_val}"
                )

            # Check upside potential
            exp_upside = expected_layered["upside_potential"]
            actual_upside = result.upside_potential
            assert abs(actual_upside - exp_upside) < 0.01, (
                f"Stock {stock_code} upside mismatch: actual={actual_upside}, expected={exp_upside}"
            )

    def test_legacy_adapter_contract_and_values(
        self, baseline_data: Dict[str, Any]
    ) -> None:
        """Verify that LegacyDCFAdapter preserves dictionary shape and matches legacy baseline."""
        adapter = LegacyDCFAdapter()

        for case in baseline_data["cases"]:
            stock_code = case["stock_code"]
            inputs = case["inputs"]
            expected_legacy = case["legacy"]

            result_dict = adapter.calculate_dcf_value(**inputs)

            # Verify dictionary keys expected by legacy views
            assert "intrinsic_value" in result_dict
            assert "upside_potential" in result_dict
            assert "cash_flows" in result_dict
            assert "present_values" in result_dict
            assert "input_parameters" in result_dict

            # Numerical check against legacy baseline
            exp_val = expected_legacy["intrinsic_value"]
            actual_val = result_dict["intrinsic_value"]
            rel_err = abs(actual_val - exp_val) / abs(exp_val)
            assert rel_err < 0.01, (
                f"Stock {stock_code} legacy adapter error {rel_err:.4%}: "
                f"actual={actual_val}, expected={exp_val}"
            )

            # Check cash flow length
            assert len(result_dict["cash_flows"]) == inputs["years"]
            assert len(result_dict["present_values"]) == inputs["years"]

    def test_scenario_comparison_compatibility(self) -> None:
        """Verify that adapter scenario comparison returns traditional Chinese keys."""
        adapter = LegacyDCFAdapter()
        scenarios = adapter.calculate_scenario_comparison(
            current_price=100.0,
            current_eps=5.0,
            base_growth_rates=[0.10, 0.05],
            discount_rate=0.08,
            stock_code="2330",
        )

        assert "保守" in scenarios
        assert "中性" in scenarios
        assert "樂觀" in scenarios

        for name, data in scenarios.items():
            assert "intrinsic_value" in data
            assert "upside_potential" in data
            assert "cash_flows" in data
            assert "color" in data

    def test_sensitivity_analysis_compatibility(self) -> None:
        """Verify that adapter sensitivity analysis returns traditional Chinese keys."""
        adapter = LegacyDCFAdapter()
        matrix = adapter.sensitivity_analysis(
            current_price=100.0,
            current_eps=5.0,
            base_growth_rates=[0.10, 0.05],
            discount_rate=0.08,
            stock_code="2330",
        )

        assert "悲觀" in matrix
        assert "基準" in matrix
        assert "樂觀" in matrix

        for scenario_name, rates in matrix.items():
            for rate_key, values in rates.items():
                assert "內在價值" in values
                assert "潛在獲利率" in values
