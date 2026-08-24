"""
Growth Optimizer Bugfix 簡化驗證測試

直接測試修復是否成功：
  1. DCFCalculator 沒有 recent_weight_ratio 屬性
  2. DCFCalculator 沒有 calculate() 方法
  3. DataManagerV2 沒有 get_current_price() 方法
  4. 修復後的程式碼應能正確呼叫 API
"""

import pytest
import sys
import os

# 確保 app 目錄在 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'app')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


class TestBugConditionVerification:
    """驗證 Bug Condition 的存在（API 設計）"""

    def test_dcf_calculator_no_recent_weight_ratio_attribute(self):
        """Bug Condition：DCFCalculator 沒有 recent_weight_ratio 屬性"""
        from app.dcf_calculator import DCFCalculator
        calc = DCFCalculator()
        assert not hasattr(calc, 'recent_weight_ratio')

    def test_dcf_calculator_no_calculate_method(self):
        """Bug Condition：DCFCalculator 沒有 calculate() 方法"""
        from app.dcf_calculator import DCFCalculator
        calc = DCFCalculator()
        assert not hasattr(calc, 'calculate')

    def test_data_manager_no_get_current_price(self):
        """Bug Condition：DataManagerV2 沒有 get_current_price() 方法"""
        from app.data.manager import DataManagerV2
        assert not hasattr(DataManagerV2, 'get_current_price')

    def test_dcf_calculator_has_calculate_dcf_value(self):
        """Fix：DCFCalculator 有 calculate_dcf_value 方法"""
        from app.dcf_calculator import DCFCalculator
        calc = DCFCalculator()
        assert hasattr(calc, 'calculate_dcf_value')

    def test_data_manager_has_get_latest_price(self):
        """Fix：DataManagerV2 有 get_latest_price 方法"""
        from app.data.manager import DataManagerV2
        assert hasattr(DataManagerV2, 'get_latest_price')

    def test_data_manager_has_get_latest_eps(self):
        """Fix：DataManagerV2 有 get_latest_eps 方法"""
        from app.data.manager import DataManagerV2
        assert hasattr(DataManagerV2, 'get_latest_eps')

    def test_data_manager_has_calculate_historical_growth_rate(self):
        """Fix：DataManagerV2 有 calculate_historical_growth_rate 方法"""
        from app.data.manager import DataManagerV2
        assert hasattr(DataManagerV2, 'calculate_historical_growth_rate')


class TestFixedCodeSyntax:
    """驗證修復後的程式碼語法正確"""

    def test_growth_optimizer_module_imports(self):
        """測試模組可正常匯入"""
        try:
            from app.views import growth_optimizer
            assert hasattr(growth_optimizer, 'show_growth_optimizer')
        except ImportError as e:
            pytest.fail(f"模組匯入失敗: {e}")

    def test_fixed_code_no_obvious_attribute_errors(self):
        """驗證修復後的程式碼不包含明顯的 AttributeError 觸發點"""
        import inspect
        from app.views import growth_optimizer

        source = inspect.getsource(growth_optimizer.show_growth_optimizer)

        # 修復後不應出現的錯誤呼叫
        assert 'dcf_calculator.recent_weight_ratio' not in source, \
            "程式碼仍包含錯誤的 recent_weight_ratio 屬性存取"
        assert 'dcf_calculator.calculate(' not in source, \
            "程式碼仍包含錯誤的 calculate() 方法呼叫"
        assert 'get_current_price' not in source, \
            "程式碼仍包含錯誤的 get_current_price() 方法呼叫"

        # 修復後應包含的正確呼叫
        assert 'get_latest_eps' in source, "修復後應包含 get_latest_eps 呼叫"
        assert 'get_latest_price' in source, "修復後應包含 get_latest_price 呼叫"
        assert 'calculate_historical_growth_rate' in source, \
            "修復後應包含 calculate_historical_growth_rate 呼叫"
        assert 'calculate_dcf_value' in source, "修復後應包含 calculate_dcf_value 呼叫"

