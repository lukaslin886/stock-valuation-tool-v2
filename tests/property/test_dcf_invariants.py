"""DCF Calculator property-based tests.

Validates correctness properties of the DCF Calculator using Hypothesis:
- Property 2: DCF intrinsic_value is a finite positive number for valid inputs.
- Property 5: Constant EPS history yields growth rate of 0.

**Validates: Requirements 18.1, 18.5**
"""

from __future__ import annotations

import math

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from app.core.models.stock import Market
from app.services.dcf_calculator import DCFCalculator


# ---------------------------------------------------------------------------
# Property 2: DCF intrinsic value is finite positive
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=30000)
@given(
    eps=st.floats(min_value=0.01, max_value=10000.0),
    growth_rate_1=st.floats(min_value=-0.5, max_value=0.5),
    growth_rate_2=st.floats(min_value=-0.5, max_value=0.5),
    current_price=st.floats(min_value=0.01, max_value=100000.0),
)
def test_dcf_intrinsic_value_finite_positive(
    eps: float,
    growth_rate_1: float,
    growth_rate_2: float,
    current_price: float,
) -> None:
    """Property 2: For any positive EPS and reasonable growth rates,
    with discount_rate > perpetual_growth, DCF intrinsic_value is finite positive.

    Feature: stock-valuation-optimization, Property 2: DCF intrinsic value finite positive

    **Validates: Requirements 18.1**
    """
    # Filter out NaN/Inf from floats strategy edge cases
    assume(math.isfinite(eps))
    assume(math.isfinite(growth_rate_1))
    assume(math.isfinite(growth_rate_2))
    assume(math.isfinite(current_price))

    calculator = DCFCalculator(market=Market.TW)
    growth_rates = [growth_rate_1, growth_rate_2]

    # Use CAPM-calculated discount rate which for TW market is:
    # risk_free_rate(0.04) + risk_premium(0.04) + inflation_rate(0.03) = 0.11
    # This is always > perpetual_growth (0.02), satisfying the precondition.
    # We call the internal calculation logic directly to avoid Pydantic
    # upside_potential bounds rejection on extreme values.
    params = calculator.default_params
    discount_rate = (
        params["risk_free_rate"] + params["risk_premium"] + params["inflation_rate"]
    )
    perpetual_growth = params["perpetual_growth"]

    # Precondition: discount_rate > perpetual_growth
    assert discount_rate > perpetual_growth

    # Compute projected cash flows
    cash_flows = calculator._project_cash_flows(eps, growth_rates, years=10)

    # Compute present values
    present_values = calculator._calculate_present_values(cash_flows, discount_rate)

    # Compute terminal value
    terminal_value = calculator._calculate_terminal_value(
        cash_flows, discount_rate, perpetual_growth
    )

    # Intrinsic value = sum of present values + terminal value
    intrinsic_value = sum(present_values) + terminal_value

    # Property assertion: intrinsic value must be finite and positive
    assert math.isfinite(intrinsic_value), (
        f"intrinsic_value is not finite: {intrinsic_value}"
    )
    assert intrinsic_value > 0, (
        f"intrinsic_value is not positive: {intrinsic_value}"
    )


# ---------------------------------------------------------------------------
# Property 5: Constant EPS growth rate is zero
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=30000, suppress_health_check=[HealthCheck.too_slow])
@given(
    constant_eps=st.floats(min_value=0.01, max_value=10000.0),
    n_periods=st.integers(min_value=2, max_value=20),
)
def test_constant_eps_growth_rate_zero(
    constant_eps: float,
    n_periods: int,
) -> None:
    """Property 5: When all EPS values in history are identical (constant c > 0,
    repeated N >= 2 times), calculate_growth_rate returns 0 (tolerance +/-0.001).

    Feature: stock-valuation-optimization, Property 5: Constant EPS growth rate zero

    **Validates: Requirements 18.5**
    """
    assume(math.isfinite(constant_eps))

    calculator = DCFCalculator()
    eps_history = [constant_eps] * n_periods

    growth_rate = calculator.calculate_growth_rate(eps_history)

    assert abs(growth_rate) < 0.001, (
        f"Expected growth_rate ~0 for constant EPS={constant_eps} "
        f"repeated {n_periods} times, got {growth_rate}"
    )
