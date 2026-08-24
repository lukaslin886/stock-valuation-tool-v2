"""
Bug Condition Exploration Tests for growth_optimizer.py

These tests verify the bug conditions described in the bugfix spec:
  - DCFCalculator has no attribute `recent_weight_ratio`
  - DCFCalculator has no method `calculate(stock_code, data_manager)`
  - DataManagerV2 has no method `get_current_price`

Tests 1-3 PASS when the attributes/methods are absent (confirming the bug condition).
Test 4 confirms the correct APIs DO exist (so the fix can use them).

**Validates: Requirements 1.1, 1.2, 1.3**

Run from project root:
    cd app && python -m pytest ../tests/unit/test_growth_optimizer_bug.py -v
or:
    python -m pytest tests/unit/test_growth_optimizer_bug.py -v --co
"""

import pytest
import sys
import os

# Ensure app directory is on sys.path for direct imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'app')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


# ---------------------------------------------------------------------------
# Property 1 — Bug Condition: DCFCalculator.recent_weight_ratio does not exist
# ---------------------------------------------------------------------------

def test_dcf_calculator_has_no_recent_weight_ratio():
    """
    Confirm DCFCalculator has NO `recent_weight_ratio` attribute.

    The buggy growth_optimizer.py code does:
        original_lambda = dcf_calculator.recent_weight_ratio
    which raises AttributeError because the attribute was never defined in
    DCFCalculator.__init__. `recent_weight_ratio` is actually a *parameter* of
    DataManagerV2.calculate_historical_growth_rate(), not a calculator attribute.

    This test PASSES when the attribute is absent — confirming the bug exists.
    **Validates: Requirements 1.1**
    """
    from dcf_calculator import DCFCalculator

    calc = DCFCalculator(enable_slippage=False)
    assert not hasattr(calc, 'recent_weight_ratio'), (
        "Bug exists: DCFCalculator should NOT have 'recent_weight_ratio' — "
        "it is a parameter of DataManagerV2.calculate_historical_growth_rate(), "
        "not a DCFCalculator attribute."
    )


# ---------------------------------------------------------------------------
# Property 2 — Bug Condition: DCFCalculator.calculate() does not exist
# ---------------------------------------------------------------------------

def test_dcf_calculator_has_no_calculate_method():
    """
    Confirm DCFCalculator has NO `calculate(stock_code, data_manager)` method.

    The buggy code calls:
        result = dcf_calculator.calculate(stock_code, data_manager)
    but this method has never existed. The correct method is
    `calculate_dcf_value(current_price, current_eps, growth_rates, ...)`.

    This test PASSES when the method is absent — confirming the bug exists.
    **Validates: Requirements 1.2**
    """
    from dcf_calculator import DCFCalculator

    calc = DCFCalculator(enable_slippage=False)
    assert not hasattr(calc, 'calculate'), (
        "Bug exists: DCFCalculator should NOT have a 'calculate()' method — "
        "the correct method is 'calculate_dcf_value(...)'."
    )


# ---------------------------------------------------------------------------
# Property 3 — Bug Condition: DataManagerV2.get_current_price does not exist
# ---------------------------------------------------------------------------

def test_data_manager_has_no_get_current_price():
    """
    Confirm DataManagerV2 has NO `get_current_price` method.

    The buggy growth_optimizer.py also calls:
        current_price = data_manager.get_current_price(stock_code)
    but the correct method is `get_latest_price(stock_code)`.

    This test PASSES when the method is absent — confirming the bug exists.
    **Validates: Requirements 1.3**
    """
    from data.manager import DataManagerV2

    assert not hasattr(DataManagerV2, 'get_current_price'), (
        "Bug exists: DataManagerV2 should NOT have 'get_current_price()' — "
        "the correct method is 'get_latest_price()'."
    )


# ---------------------------------------------------------------------------
# Property 4 — Correct APIs DO exist (fix prerequisites)
# ---------------------------------------------------------------------------

def test_correct_apis_exist():
    """
    Confirm the correct replacement APIs are available so the fix can use them.

    The fix requires:
      - DCFCalculator.calculate_dcf_value(...)
      - DataManagerV2.calculate_historical_growth_rate(...)
      - DataManagerV2.get_latest_eps(...)
      - DataManagerV2.get_latest_price(...)

    This test confirms the fix target APIs are present before applying the fix.
    **Validates: Requirements 2.1, 2.2, 2.3**
    """
    from dcf_calculator import DCFCalculator
    from data.manager import DataManagerV2

    calc = DCFCalculator(enable_slippage=False)

    # DCFCalculator correct API
    assert hasattr(calc, 'calculate_dcf_value'), (
        "DCFCalculator must have 'calculate_dcf_value' method for the fix."
    )

    # DataManagerV2 correct APIs
    assert hasattr(DataManagerV2, 'calculate_historical_growth_rate'), (
        "DataManagerV2 must have 'calculate_historical_growth_rate' method for the fix."
    )
    assert hasattr(DataManagerV2, 'get_latest_eps'), (
        "DataManagerV2 must have 'get_latest_eps' method for the fix."
    )
    assert hasattr(DataManagerV2, 'get_latest_price'), (
        "DataManagerV2 must have 'get_latest_price' method for the fix."
    )


# ---------------------------------------------------------------------------
# Property 5 — Direct AttributeError reproduction
# ---------------------------------------------------------------------------

def test_accessing_recent_weight_ratio_raises_attribute_error():
    """
    Directly reproduce the crash: accessing `dcf_calculator.recent_weight_ratio`
    on a real DCFCalculator instance raises AttributeError.

    This is the exact counterexample from the bug report:
        AttributeError: 'DCFCalculator' object has no attribute 'recent_weight_ratio'

    **Validates: Requirements 1.1**
    """
    from dcf_calculator import DCFCalculator

    calc = DCFCalculator(enable_slippage=False)
    with pytest.raises(AttributeError, match="recent_weight_ratio"):
        _ = calc.recent_weight_ratio
