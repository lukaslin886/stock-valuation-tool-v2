"""Legacy-compatible facade for the layered DCF calculator."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.models.financial import DCFResult
from app.core.models.stock import Market
from app.services.dcf_calculator import DCFCalculator


class LegacyDCFAdapter:
    """Expose the legacy DCF dictionary contract over the layered calculator.

    The numerical calculation remains owned by ``app.services.dcf_calculator``.
    This facade only restores fields consumed by the existing views while the
    remaining view APIs are migrated incrementally.
    """

    def __init__(self, calculator: Optional[DCFCalculator] = None) -> None:
        """Initialize the adapter with an injectable layered calculator."""
        self._calculator = calculator or DCFCalculator()

    def calculate_dcf_value(
        self,
        current_price: float,
        current_eps: float,
        growth_rates: List[float],
        discount_rate: Optional[float] = None,
        years: int = 10,
        stock_code: Optional[str] = None,
        stock_name: Optional[str] = None,
        data_source: Optional[str] = None,
        weighting_method: Optional[str] = None,
        market: Optional[Market] = None,
    ) -> Dict[str, Any]:
        """Calculate DCF and return the legacy dictionary-shaped result."""
        result = self._calculator.calculate_dcf_value(
            current_price=current_price,
            current_eps=current_eps,
            growth_rates=growth_rates,
            discount_rate=discount_rate,
            years=years,
            stock_code=stock_code,
            stock_name=stock_name,
            market=market,
            data_source=data_source,
            weighting_method=weighting_method,
        )
        return self._to_legacy_dict(
            result=result,
            current_eps=current_eps,
            years=years,
            weighting_method=weighting_method,
        )

    def _to_legacy_dict(
        self,
        result: DCFResult,
        current_eps: float,
        years: int,
        weighting_method: Optional[str],
    ) -> Dict[str, Any]:
        """Restore legacy detail fields without duplicating DCF formulas."""
        cash_flows = self._calculator._project_cash_flows(
            current_eps, result.growth_rates, years
        )
        present_values = self._calculator._calculate_present_values(
            cash_flows, result.discount_rate
        )
        return {
            "current_price": result.current_price,
            "intrinsic_value": result.intrinsic_value,
            "upside_potential": result.upside_potential,
            "discount_rate": result.discount_rate,
            "cash_flows": cash_flows,
            "present_values": present_values,
            "terminal_value": result.terminal_value,
            "recommendation": result.recommendation,
            "input_parameters": {
                "timestamp": result.calculated_at.isoformat(),
                "stock_code": result.stock_code or None,
                "stock_name": result.stock_name or None,
                "current_price": result.current_price,
                "current_eps": current_eps,
                "growth_rates": {
                    "1-5年": result.growth_rates[0]
                    if result.growth_rates
                    else None,
                    "6-10年": result.growth_rates[1]
                    if len(result.growth_rates) > 1
                    else None,
                },
                "discount_rate": result.discount_rate,
                "years": years,
                "data_source": result.data_source or "未指定",
                "weighting_method": weighting_method or "unknown",
            },
        }