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