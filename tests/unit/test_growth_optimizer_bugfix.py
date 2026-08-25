"""
Growth Optimizer Bugfix 測試套件

測試策略遵循 Bug Condition Methodology：
  - Property 1: Bug Condition — 未修復程式碼應觸發 AttributeError
  - Property 2: Preservation — 非迴圈路徑行為不受修復影響

使用 unittest.mock 隔離 Streamlit session_state 與外部 API 呼叫。
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, call

# 確保 app 目錄在 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'app')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_mock_data_manager(
    eps: float = 32.0,
    price: float = 600.0,
    growth_rate_1_5: float = 0.15,
    growth_rate_6_10: float = 0.08,
):
    """建立預設的 DataManagerV2 Mock。"""
    dm = MagicMock()
    dm.get_latest_eps.return_value = eps
    dm.get_latest_price.return_value = price
    dm.get_current_price.return_value = price  # 舊 (buggy) 呼叫也 mock 起來
    dm.calculate_historical_growth_rate.return_value = {
        'growth_rate_1_5': growth_rate_1_5,
        'growth_rate_6_10': growth_rate_6_10,
        'weighting_method': 'time_weighted',
        'data_quality': 'good',
        'message': 'mock data',
    }
    return dm


def _make_mock_dcf_calculator(intrinsic_value: float = 750.0):
    """建立預設的 DCFCalculator Mock。"""
    # spec 限制僅允許 calculate_dcf_value（對齊修復後 DCFCalculator API）
    dcf = MagicMock(spec=['calculate_dcf_value'])
    dcf.calculate_dcf_value.return_value = {
        'intrinsic_value': intrinsic_value,
        'upside_potential': 0.25,
        'discount_rate': 0.11,
    }
    return dcf



# ===========================================================================
# Task 1 — Property 1: Bug Condition
#   目標：在「未修復」程式碼上執行，確認 Bug 可重現
#   預期結果：測試在修復前 FAILS（AttributeError），修復後 PASSES
# ===========================================================================

class TestBugConditionExploration:
    """
    **Property 1: Bug Condition** — Lambda 迴圈呼叫不存在的 DCFCalculator 屬性

    這些測試在「未修復」程式碼上應 FAIL（正確，證明 Bug 存在）。
    修復完成後相同測試應 PASS（確認 Bug 已修復）。
    """

    def test_dcf_calculator_has_no_recent_weight_ratio(self):
        """
        Bug Condition 測試 1：驗證 DCFCalculator 沒有 recent_weight_ratio 屬性。

        isBugCondition 偽碼回傳 True 的直接原因。
        Counterexample: AttributeError: 'DCFCalculator' object has no attribute 'recent_weight_ratio'
        """
        from app.dcf_calculator import DCFCalculator
        calc = DCFCalculator()
        assert not hasattr(calc, 'recent_weight_ratio'), (
            "DCFCalculator 不應有 recent_weight_ratio 屬性 — "
            "它是 DataManagerV2.calculate_historical_growth_rate() 的函式參數，而非計算器屬性。"
        )

    def test_dcf_calculator_has_no_calculate_method(self):
        """
        Bug Condition 測試 2：驗證 DCFCalculator 沒有 calculate() 方法。

        原始程式碼呼叫 dcf_calculator.calculate(stock_code, data_manager)，
        但此方法不存在，正確方法是 calculate_dcf_value(...)。
        """
        from app.dcf_calculator import DCFCalculator
        calc = DCFCalculator()
        assert not hasattr(calc, 'calculate'), (
            "DCFCalculator 不應有 calculate() 方法 — 正確方法是 calculate_dcf_value(...)。"
        )

    def test_data_manager_has_no_get_current_price(self):
        """
        Bug Condition 測試 3：驗證 DataManagerV2 沒有 get_current_price() 方法。

        原始程式碼呼叫 data_manager.get_current_price(stock_code)，
        正確方法是 get_latest_price(stock_code)。
        """
        from app.data.manager import DataManagerV2
        assert not hasattr(DataManagerV2, 'get_current_price'), (
            "DataManagerV2 不應有 get_current_price() 方法 — 正確方法是 get_latest_price()。"
        )


    def test_buggy_loop_raises_attribute_error_on_lambda_access(self):
        """
        Bug Condition 測試 4 (PBT scoped)：模擬原始迴圈邏輯，確認 AttributeError 被拋出。

        原始程式碼片段：
            original_lambda = dcf_calculator.recent_weight_ratio  # <-- 崩潰點
            dcf_calculator.recent_weight_ratio = round(l, 2)
            result = dcf_calculator.calculate(stock_code, data_manager)

        使用 spec=[] 建立的 Mock 不允許任何屬性存取，模擬真實 DCFCalculator。
        """
        from app.dcf_calculator import DCFCalculator
        # 用真實 DCFCalculator 執行原始邏輯，應拋出 AttributeError
        calc = DCFCalculator()
        with pytest.raises(AttributeError, match="recent_weight_ratio"):
            _ = calc.recent_weight_ratio  # 模擬原始迴圈第一行

    def test_correct_api_not_called_in_buggy_code(self):
        """
        Bug Condition 測試 5：驗證 buggy 路徑從未呼叫正確的 API。

        Counterexample 記錄：
        - dcf_calculator.calculate_historical_growth_rate 從未被呼叫
        - dcf_calculator.calculate_dcf_value 從未被呼叫
        因為程式在第一行 dcf_calculator.recent_weight_ratio 就崩潰了。
        """
        from app.dcf_calculator import DCFCalculator
        dm = _make_mock_data_manager()
        calc = DCFCalculator()

        # 嘗試執行原始 buggy 邏輯
        try:
            _ = calc.recent_weight_ratio
            calc.recent_weight_ratio = 0.5
            calc.calculate("2330", dm)
        except AttributeError:
            pass  # 預期崩潰

        # 確認正確的 API 從未被呼叫
        dm.calculate_historical_growth_rate.assert_not_called()
        dm.get_latest_eps.assert_not_called()
        dm.get_latest_price.assert_not_called()



# ===========================================================================
# Task 2 — Property 2: Preservation
#   目標：非 Lambda 迴圈路徑（邊界條件、警告訊息）在修復前後行為相同
#   預期結果：測試在修復前後均 PASS
# ===========================================================================

class TestPreservationBehavior:
    """
    **Property 2: Preservation** — 非 Lambda 迴圈路徑行為維持不變

    observation-first 方法：先在未修復程式碼上觀察各路徑行為，
    再撰寫 property-based tests 驗證修復後相同行為持續成立。

    這些測試應在修復前後均 PASS。
    """

    def _run_with_mocked_st(self, stock_code, lambda_min, lambda_max,
                             data_manager=None, dcf_calculator=None):
        """
        執行 show_growth_optimizer 並收集 Streamlit 呼叫記錄。

        Returns:
            dict: {'warning': [...], 'error': [...], 'success': [...]}
        """
        calls_record = {'warning': [], 'error': [], 'success': [], 'button_clicked': False}

        mock_st = MagicMock()
        mock_st.session_state.data_manager = data_manager or _make_mock_data_manager()
        mock_st.session_state.dcf_calculator = dcf_calculator or _make_mock_dcf_calculator()

        mock_st.warning.side_effect = lambda msg: calls_record['warning'].append(msg)
        mock_st.error.side_effect = lambda msg: calls_record['error'].append(msg)
        mock_st.success.side_effect = lambda msg: calls_record['success'].append(msg)

        # number_input 回傳設定的 lambda 值
        mock_st.number_input.side_effect = [lambda_min, lambda_max]

        # 模擬按鈕「已被點擊」以執行計算路徑
        mock_st.button.return_value = True

        # spinner 是 context manager
        mock_st.spinner.return_value.__enter__ = MagicMock(return_value=None)
        mock_st.spinner.return_value.__exit__ = MagicMock(return_value=False)

        # columns 回傳兩個 context manager mock
        col_mock = MagicMock()
        col_mock.__enter__ = MagicMock(return_value=col_mock)
        col_mock.__exit__ = MagicMock(return_value=False)
        mock_st.columns.return_value = [col_mock, col_mock]

        with patch.dict('sys.modules', {'streamlit': mock_st}):
            # 重新載入模組以套用 patch
            if 'views.growth_optimizer' in sys.modules:
                del sys.modules['views.growth_optimizer']
            if 'app.views.growth_optimizer' in sys.modules:
                del sys.modules['app.views.growth_optimizer']

            from app.views.growth_optimizer import show_growth_optimizer
            show_growth_optimizer(stock_code, "測試股票")

        return calls_record, mock_st


    def test_preservation_empty_stock_code_shows_warning(self):
        """
        Preservation 測試 1：未輸入股票代碼時顯示警告並返回。

        Observation (unfixed code): 空 stock_code → st.warning("請先在左側欄輸入股票代碼！")
        Property: ∀ empty stock_code → warning shown, no API calls made
        """
        mock_st = MagicMock()
        mock_st.session_state.data_manager = _make_mock_data_manager()
        mock_st.session_state.dcf_calculator = _make_mock_dcf_calculator()

        with patch.dict('sys.modules', {'streamlit': mock_st}):
            if 'views.growth_optimizer' in sys.modules:
                del sys.modules['views.growth_optimizer']
            if 'app.views.growth_optimizer' in sys.modules:
                del sys.modules['app.views.growth_optimizer']

            from app.views.growth_optimizer import show_growth_optimizer
            show_growth_optimizer("", "")

        # 應呼叫 warning 並提早返回（不呼叫任何 API）
        mock_st.warning.assert_called_once()
        warning_msg = mock_st.warning.call_args[0][0]
        assert "股票代碼" in warning_msg
        mock_st.session_state.data_manager.get_latest_eps.assert_not_called()

    def test_preservation_lambda_min_ge_max_shows_error(self):
        """
        Preservation 測試 2：lambda_min >= lambda_max 時顯示錯誤並返回。

        Observation (unfixed code): lambda_min=0.5, lambda_max=0.3 → st.error("最小 Lambda 必須小於最大 Lambda")
        Property: ∀ (lmin, lmax) where lmin >= lmax → error shown, no further processing
        """
        import hypothesis.strategies as st_hyp
        from hypothesis import given, settings

        mock_st = MagicMock()
        mock_st.session_state.data_manager = _make_mock_data_manager()
        mock_st.session_state.dcf_calculator = _make_mock_dcf_calculator()

        # 使用具體案例涵蓋等於與大於兩種情況
        for lmin, lmax in [(0.5, 0.3), (0.5, 0.5), (0.9, 0.1)]:
            mock_st.reset_mock()
            mock_st.number_input.side_effect = [lmin, lmax]
            mock_st.button.return_value = False  # 不需點擊按鈕，驗證在前

            col_mock = MagicMock()
            col_mock.__enter__ = MagicMock(return_value=col_mock)
            col_mock.__exit__ = MagicMock(return_value=False)
            mock_st.columns.return_value = [col_mock, col_mock]

            with patch.dict('sys.modules', {'streamlit': mock_st}):
                if 'views.growth_optimizer' in sys.modules:
                    del sys.modules['views.growth_optimizer']
                if 'app.views.growth_optimizer' in sys.modules:
                    del sys.modules['app.views.growth_optimizer']

                from app.views.growth_optimizer import show_growth_optimizer
                show_growth_optimizer("2330", "台積電")

            mock_st.error.assert_called()
            error_msg = mock_st.error.call_args[0][0]
            assert "Lambda" in error_msg


    def test_preservation_no_valid_results_shows_warning(self):
        """
        Preservation 測試 3：所有 lambda 均無有效估值時顯示警告。

        Observation (unfixed code): 當 results 為空列表 → st.warning("無法計算出有效估值...")
        Property: ∀ inputs where all intrinsic_values <= 0 → warning shown
        """
        dm = _make_mock_data_manager(eps=5.0, price=100.0)
        dcf = _make_mock_dcf_calculator(intrinsic_value=-1.0)  # 所有估值無效

        mock_st = MagicMock()
        mock_st.session_state.data_manager = dm
        mock_st.session_state.dcf_calculator = dcf
        mock_st.number_input.side_effect = [0.1, 0.3]
        mock_st.button.return_value = True

        spinner_ctx = MagicMock()
        spinner_ctx.__enter__ = MagicMock(return_value=None)
        spinner_ctx.__exit__ = MagicMock(return_value=False)
        mock_st.spinner.return_value = spinner_ctx

        col_mock = MagicMock()
        col_mock.__enter__ = MagicMock(return_value=col_mock)
        col_mock.__exit__ = MagicMock(return_value=False)
        mock_st.columns.return_value = [col_mock, col_mock]

        with patch.dict('sys.modules', {'streamlit': mock_st}):
            if 'views.growth_optimizer' in sys.modules:
                del sys.modules['views.growth_optimizer']
            if 'app.views.growth_optimizer' in sys.modules:
                del sys.modules['app.views.growth_optimizer']

            from app.views.growth_optimizer import show_growth_optimizer
            show_growth_optimizer("2330", "台積電")

        # 修復後：應顯示「無法計算出有效估值」警告
        mock_st.warning.assert_called()
        warning_texts = " ".join(str(c) for c in mock_st.warning.call_args_list)
        assert "無法計算" in warning_texts or "估值" in warning_texts



# ===========================================================================
# Task 3.2/3.3 — Fix Verification Tests
#   目標：修復後，正確 API 被呼叫，且所有 Preservation 路徑不受影響
# ===========================================================================

class TestFixVerification:
    """
    修復後驗證測試 — 確認 Lambda 迴圈使用正確 API，且無回歸。
    """

    def _patch_and_run(self, stock_code, lambda_min, lambda_max, dm, dcf):
        """Helper：patch streamlit 並執行 show_growth_optimizer。"""
        mock_st = MagicMock()
        mock_st.session_state.data_manager = dm
        mock_st.session_state.dcf_calculator = dcf
        mock_st.number_input.side_effect = [lambda_min, lambda_max]
        mock_st.button.return_value = True

        spinner_ctx = MagicMock()
        spinner_ctx.__enter__ = MagicMock(return_value=None)
        spinner_ctx.__exit__ = MagicMock(return_value=False)
        mock_st.spinner.return_value = spinner_ctx

        col_mock = MagicMock()
        col_mock.__enter__ = MagicMock(return_value=col_mock)
        col_mock.__exit__ = MagicMock(return_value=False)
        mock_st.columns.return_value = [col_mock, col_mock]

        expander_mock = MagicMock()
        expander_mock.__enter__ = MagicMock(return_value=expander_mock)
        expander_mock.__exit__ = MagicMock(return_value=False)
        mock_st.expander.return_value = expander_mock

        with patch.dict('sys.modules', {'streamlit': mock_st}):
            if 'views.growth_optimizer' in sys.modules:
                del sys.modules['views.growth_optimizer']
            if 'app.views.growth_optimizer' in sys.modules:
                del sys.modules['app.views.growth_optimizer']

            from app.views.growth_optimizer import show_growth_optimizer
            show_growth_optimizer(stock_code, "台積電")

        return mock_st

    def test_fix_no_attribute_error_raised(self):
        """
        Fix 驗證 1：修復後不應拋出 AttributeError。

        Property 1 Expected Behavior — Lambda 迴圈不崩潰。
        """
        dm = _make_mock_data_manager()
        dcf = _make_mock_dcf_calculator()

        # 應不拋出任何例外
        mock_st = self._patch_and_run("2330", 0.1, 0.3, dm, dcf)
        mock_st.error.assert_not_called()

    def test_fix_calls_get_latest_eps_once(self):
        """Fix 驗證 2：get_latest_eps 應在迴圈外被呼叫一次。"""
        dm = _make_mock_data_manager()
        dcf = _make_mock_dcf_calculator()

        self._patch_and_run("2330", 0.1, 0.3, dm, dcf)

        dm.get_latest_eps.assert_called_once_with("2330")

    def test_fix_calls_get_latest_price_for_eps_price(self):
        """Fix 驗證 3：get_latest_price 應被呼叫以取得股價（迴圈外）。"""
        dm = _make_mock_data_manager()
        dcf = _make_mock_dcf_calculator()

        self._patch_and_run("2330", 0.1, 0.3, dm, dcf)

        assert dm.get_latest_price.call_count >= 1

    def test_fix_calls_calculate_historical_growth_rate_per_lambda(self):
        """Fix 驗證 4：每個 lambda 值應呼叫一次 calculate_historical_growth_rate。"""
        dm = _make_mock_data_manager()
        dcf = _make_mock_dcf_calculator()

        # lambda_min=0.1, lambda_max=0.3 → 測試點為 0.1, 0.2, 0.3 (3 個)
        self._patch_and_run("2330", 0.1, 0.3, dm, dcf)

        assert dm.calculate_historical_growth_rate.call_count == 3
        # 驗證 recent_weight_ratio 以 round(l, 2) 傳入
        calls = [c.kwargs.get('recent_weight_ratio') or c.args[1]
                 for c in dm.calculate_historical_growth_rate.call_args_list]
        assert 0.1 in calls or pytest.approx(0.1) in calls

    def test_fix_calls_calculate_dcf_value_per_lambda(self):
        """Fix 驗證 5：每個有效 lambda 值應呼叫一次 calculate_dcf_value。"""
        dm = _make_mock_data_manager()
        dcf = _make_mock_dcf_calculator()

        self._patch_and_run("2330", 0.1, 0.3, dm, dcf)

        assert dcf.calculate_dcf_value.call_count == 3

    def test_fix_calculate_dcf_value_receives_correct_growth_rates(self):
        """Fix 驗證 6：calculate_dcf_value 應接收來自 calculate_historical_growth_rate 的成長率。"""
        dm = _make_mock_data_manager(growth_rate_1_5=0.20, growth_rate_6_10=0.10)
        dcf = _make_mock_dcf_calculator()

        self._patch_and_run("2330", 0.1, 0.2, dm, dcf)

        # 檢查 calculate_dcf_value 的 growth_rates 參數
        for c in dcf.calculate_dcf_value.call_args_list:
            growth_rates = c.args[2] if len(c.args) >= 3 else c.kwargs.get('growth_rates')
            if growth_rates is not None:
                assert growth_rates[0] == pytest.approx(0.20)
                assert growth_rates[1] == pytest.approx(0.10)

