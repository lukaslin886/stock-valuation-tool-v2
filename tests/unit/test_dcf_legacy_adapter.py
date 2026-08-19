"""Tests for the Legacy-compatible layered DCF facade."""

from __future__ import annotations

from app.services.dcf_legacy_adapter import LegacyDCFAdapter


def test_adapter_preserves_legacy_detail_contract() -> None:
    """The adapter returns legacy fields using layered numerical results."""
    adapter = LegacyDCFAdapter()

    result = adapter.calculate_dcf_value(
        current_price=100.0,
        current_eps=10.0,
        growth_rates=[0.1, 0.05],
        discount_rate=0.08,
        years=10,
        stock_code="2330",
    )

    assert result["intrinsic_value"] == 265.1034647491111
    assert result["upside_potential"] == 1.6510346474911108
    assert len(result["cash_flows"]) == 10
    assert len(result["present_values"]) == 10
    assert result["input_parameters"]["stock_code"] == "2330"


def test_adapter_preserves_scenario_and_sensitivity_contracts() -> None:
    """Scenario and sensitivity outputs remain consumable by legacy views."""
    adapter = LegacyDCFAdapter()

    scenarios = adapter.calculate_scenario_comparison(
        current_price=100.0,
        current_eps=10.0,
        base_growth_rates=[0.1, 0.05],
        discount_rate=0.08,
        stock_code="2330",
    )
    sensitivity = adapter.sensitivity_analysis(
        current_price=100.0,
        current_eps=10.0,
        base_growth_rates=[0.1, 0.05],
        stock_code="2330",
    )

    assert set(scenarios) == {"保守", "中性", "樂觀"}
    assert "intrinsic_value" in scenarios["中性"]
    assert set(sensitivity) == {"悲觀", "基準", "樂觀"}
    assert "內在價值" in sensitivity["基準"]["折現率8.0%"]