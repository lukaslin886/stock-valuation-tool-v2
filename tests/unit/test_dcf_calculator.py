"""
DCFCalculator 測試套件

測試涵蓋：
- DCF 價值計算
- CAPM 折現率計算
- 現金流預測
- 現值與終值計算
- 投資建議生成
- 敏感性分析
- 邊界條件處理
"""

import pytest
import numpy as np
from app.dcf_calculator import DCFCalculator


# ============================================================================
# Test Class: DCFCalculator 初始化
# ============================================================================

class TestDCFCalculatorInit:
    """測試 DCFCalculator 初始化"""
    
    def test_init_default_params(self):
        """測試預設參數初始化"""
        calculator = DCFCalculator()
        
        assert calculator.default_params['risk_free_rate'] == 0.04
        assert calculator.default_params['risk_premium'] == 0.04
        assert calculator.default_params['inflation_rate'] == 0.03
        assert calculator.default_params['perpetual_growth'] == 0.02
    
    def test_init_creates_valid_object(self):
        """測試初始化建立有效物件"""
        calculator = DCFCalculator()
        
        assert calculator is not None
        assert hasattr(calculator, 'default_params')
        assert hasattr(calculator, 'calculate_dcf_value')


# ============================================================================
# Test Class: CAPM 折現率計算
# ============================================================================

class TestCAPMRateCalculation:
    """測試 CAPM 折現率計算"""
    
    def test_capm_rate_default(self, dcf_calculator):
        """測試預設 CAPM 利率計算"""
        rate = dcf_calculator._calculate_capm_rate()
        
        # 應該等於 risk_free_rate + risk_premium + inflation_rate
        expected = 0.04 + 0.04 + 0.03  # 0.11 (11%)
        assert rate == pytest.approx(expected)
    
    def test_capm_rate_modified_params(self, dcf_calculator):
        """測試修改參數後的 CAPM 計算"""
        dcf_calculator.default_params['risk_free_rate'] = 0.05
        dcf_calculator.default_params['risk_premium'] = 0.06
        dcf_calculator.default_params['inflation_rate'] = 0.02
        
        rate = dcf_calculator._calculate_capm_rate()
        expected = 0.05 + 0.06 + 0.02  # 0.13 (13%)
        assert rate == pytest.approx(expected)
    
    def test_capm_rate_zero_risk(self, dcf_calculator):
        """測試零風險情境"""
        dcf_calculator.default_params['risk_free_rate'] = 0.0
        dcf_calculator.default_params['risk_premium'] = 0.0
        dcf_calculator.default_params['inflation_rate'] = 0.0
        
        rate = dcf_calculator._calculate_capm_rate()
        assert rate == 0.0


# ============================================================================
# Test Class: 現金流預測
# ============================================================================

class TestCashFlowProjection:
    """測試現金流預測"""
    
    def test_project_cash_flows_basic(self, dcf_calculator):
        """測試基本現金流預測"""
        current_eps = 10.0
        growth_rates = [0.10, 0.05]  # 前5年10%, 後5年5%
        years = 10
        
        cash_flows = dcf_calculator._project_cash_flows(
            current_eps, growth_rates, years
        )
        
        assert len(cash_flows) == years
        assert cash_flows[0] > current_eps  # 第一年應大於當前 EPS
        assert cash_flows[-1] > cash_flows[0]  # 最後一年應大於第一年
    
    def test_project_cash_flows_growth_pattern(self, dcf_calculator):
        """測試成長模式正確性"""
        current_eps = 100.0
        growth_rates = [0.20, 0.10]  # 前5年20%, 後5年10%
        years = 10
        
        cash_flows = dcf_calculator._project_cash_flows(
            current_eps, growth_rates, years
        )
        
        # 檢查前5年的成長率
        for i in range(4):
            growth = (cash_flows[i+1] - cash_flows[i]) / cash_flows[i]
            assert growth == pytest.approx(0.20, rel=1e-6)
        
        # 檢查後5年的成長率
        for i in range(5, 9):
            growth = (cash_flows[i] - cash_flows[i-1]) / cash_flows[i-1]
            assert growth == pytest.approx(0.10, rel=1e-6)
    
    def test_project_cash_flows_single_growth_rate(self, dcf_calculator):
        """測試單一成長率"""
        current_eps = 50.0
        growth_rates = [0.15]  # 只提供一個成長率
        years = 5
        
        cash_flows = dcf_calculator._project_cash_flows(
            current_eps, growth_rates, years
        )
        
        assert len(cash_flows) == years
        # 應該使用相同成長率
        expected = current_eps * (1.15 ** np.arange(1, years + 1))
        np.testing.assert_array_almost_equal(cash_flows, expected, decimal=2)
    
    def test_project_cash_flows_negative_growth(self, dcf_calculator):
        """測試負成長率"""
        current_eps = 100.0
        growth_rates = [-0.10, -0.05]  # 負成長
        years = 5
        
        cash_flows = dcf_calculator._project_cash_flows(
            current_eps, growth_rates, years
        )
        
        assert len(cash_flows) == years
        assert all(cf < current_eps for cf in cash_flows)  # 所有現金流應小於初始值
        # 負成長率：第一年應大於最後一年（逐年遞減）
        assert cash_flows[0] > cash_flows[-1]
    
    def test_project_cash_flows_zero_growth(self, dcf_calculator):
        """測試零成長率"""
        current_eps = 75.0
        growth_rates = [0.0, 0.0]
        years = 10
        
        cash_flows = dcf_calculator._project_cash_flows(
            current_eps, growth_rates, years
        )
        
        # 所有現金流應該相等
        assert all(cf == pytest.approx(current_eps) for cf in cash_flows)


# ============================================================================
# Test Class: 現值計算
# ============================================================================

class TestPresentValueCalculation:
    """測試現值計算"""
    
    def test_calculate_present_values_basic(self, dcf_calculator):
        """測試基本現值計算"""
        cash_flows = [100, 110, 121, 133.1, 146.41]
        discount_rate = 0.10
        
        present_values = dcf_calculator._calculate_present_values(
            cash_flows, discount_rate
        )
        
        assert len(present_values) == len(cash_flows)
        # 現值應該小於原始現金流（除了第一年可能接近）
        for i, pv in enumerate(present_values):
            assert pv <= cash_flows[i] * 1.01  # 容許微小誤差
        # 檢查第一個現值小於對應現金流
        assert present_values[0] < cash_flows[0]
    
    def test_calculate_present_values_formula(self, dcf_calculator):
        """測試現值公式正確性"""
        cash_flows = [100.0]
        discount_rate = 0.08
        
        present_values = dcf_calculator._calculate_present_values(
            cash_flows, discount_rate
        )
        
        # PV = CF / (1 + r)^n
        expected = 100.0 / (1.08 ** 1)
        assert present_values[0] == pytest.approx(expected)
    
    def test_calculate_present_values_high_discount_rate(self, dcf_calculator):
        """測試高折現率"""
        cash_flows = [100, 100, 100]
        discount_rate = 0.50  # 50% 折現率
        
        present_values = dcf_calculator._calculate_present_values(
            cash_flows, discount_rate
        )
        
        # 高折現率應產生較小的現值
        assert present_values[0] < 70
        assert present_values[2] < 30
    
    def test_calculate_present_values_empty_list(self, dcf_calculator):
        """測試空現金流列表"""
        cash_flows = []
        discount_rate = 0.10
        
        present_values = dcf_calculator._calculate_present_values(
            cash_flows, discount_rate
        )
        
        assert present_values == []


# ============================================================================
# Test Class: 終值計算
# ============================================================================

class TestTerminalValueCalculation:
    """測試終值計算"""
    
    def test_calculate_terminal_value_basic(self, dcf_calculator):
        """測試基本終值計算"""
        cash_flows = [100] * 10  # 10年，每年100
        discount_rate = 0.11
        
        terminal_value = dcf_calculator._calculate_terminal_value(
            cash_flows, discount_rate
        )
        
        assert terminal_value > 0
        # 終值應該是一個合理的正數
        assert 0 < terminal_value < 10000
    
    def test_calculate_terminal_value_formula(self, dcf_calculator):
        """測試終值公式正確性"""
        cash_flows = [100]  # 1年
        discount_rate = 0.11
        perpetual_growth = dcf_calculator.default_params['perpetual_growth']  # 0.02
        
        terminal_value = dcf_calculator._calculate_terminal_value(
            cash_flows, discount_rate
        )
        
        # TV = CFn+1 / (r - g) / (1 + r)^n
        # CFn+1 = 100 * 1.02 = 102
        # TV = 102 / (0.11 - 0.02) / (1.11)^1
        expected_tv_before_discount = 102 / (0.11 - 0.02)
        expected = expected_tv_before_discount / (1.11 ** 1)
        
        assert terminal_value == pytest.approx(expected, rel=1e-4)
    
    def test_calculate_terminal_value_empty_cash_flows(self, dcf_calculator):
        """測試空現金流"""
        cash_flows = []
        discount_rate = 0.11
        
        terminal_value = dcf_calculator._calculate_terminal_value(
            cash_flows, discount_rate
        )
        
        assert terminal_value == 0
    
    def test_calculate_terminal_value_long_period(self, dcf_calculator):
        """測試長期現金流"""
        cash_flows = [100] * 20  # 20年
        discount_rate = 0.11
        
        terminal_value = dcf_calculator._calculate_terminal_value(
            cash_flows, discount_rate
        )
        
        # 20年後的終值現值應該相對較小
        assert terminal_value > 0
        assert terminal_value < 2000  # 相對合理的上限


# ============================================================================
# Test Class: 投資建議
# ============================================================================

class TestInvestmentRecommendation:
    """測試投資建議生成"""
    
    def test_recommendation_strong_buy(self, dcf_calculator):
        """測試強烈推薦建議 (>50%)"""
        upside_potential = 0.60  # 60%
        recommendation = dcf_calculator._get_investment_recommendation(upside_potential)
        assert "強烈推薦" in recommendation
    
    def test_recommendation_buy(self, dcf_calculator):
        """測試推薦建議 (30-50%)"""
        upside_potential = 0.40  # 40%
        recommendation = dcf_calculator._get_investment_recommendation(upside_potential)
        assert "推薦" in recommendation
        assert "強烈" not in recommendation
    
    def test_recommendation_consider(self, dcf_calculator):
        """測試考慮建議 (10-30%)"""
        upside_potential = 0.20  # 20%
        recommendation = dcf_calculator._get_investment_recommendation(upside_potential)
        assert "考慮" in recommendation
    
    def test_recommendation_watch(self, dcf_calculator):
        """測試觀望建議 (-10% to 10%)"""
        upside_potential = 0.05  # 5%
        recommendation = dcf_calculator._get_investment_recommendation(upside_potential)
        assert "觀望" in recommendation
    
    def test_recommendation_sell(self, dcf_calculator):
        """測試不推薦建議 (<-10%)"""
        upside_potential = -0.20  # -20%
        recommendation = dcf_calculator._get_investment_recommendation(upside_potential)
        assert "不推薦" in recommendation
    
    def test_recommendation_boundary_50_percent(self, dcf_calculator):
        """測試邊界：剛好 50%"""
        recommendation = dcf_calculator._get_investment_recommendation(0.50)
        assert "推薦" in recommendation or "強烈推薦" in recommendation
    
    def test_recommendation_boundary_30_percent(self, dcf_calculator):
        """測試邊界：剛好 30%"""
        recommendation = dcf_calculator._get_investment_recommendation(0.30)
        assert "推薦" in recommendation or "考慮" in recommendation


# ============================================================================
# Test Class: DCF 價值計算（主要功能）
# ============================================================================

class TestDCFValueCalculation:
    """測試 DCF 價值計算主要功能"""
    
    def test_calculate_dcf_value_basic(self, dcf_calculator):
        """測試基本 DCF 計算"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=100.0,
            current_eps=10.0,
            growth_rates=[0.15, 0.10],
            discount_rate=0.11,
            years=10
        )
        
        assert 'current_price' in result
        assert 'intrinsic_value' in result
        assert 'upside_potential' in result
        assert 'discount_rate' in result
        assert 'cash_flows' in result
        assert 'present_values' in result
        assert 'terminal_value' in result
        assert 'recommendation' in result
    
    def test_calculate_dcf_value_result_types(self, dcf_calculator):
        """測試結果類型正確性"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=100.0,
            current_eps=10.0,
            growth_rates=[0.10, 0.05]
        )
        
        assert isinstance(result['current_price'], float)
        assert isinstance(result['intrinsic_value'], (int, float))
        assert isinstance(result['upside_potential'], (int, float))
        assert isinstance(result['discount_rate'], float)
        assert isinstance(result['cash_flows'], list)
        assert isinstance(result['present_values'], list)
        assert isinstance(result['terminal_value'], (int, float))
        assert isinstance(result['recommendation'], str)
    
    def test_calculate_dcf_value_with_custom_discount_rate(self, dcf_calculator):
        """測試自訂折現率"""
        custom_rate = 0.15
        result = dcf_calculator.calculate_dcf_value(
            current_price=200.0,
            current_eps=20.0,
            growth_rates=[0.12, 0.08],
            discount_rate=custom_rate
        )
        
        assert result['discount_rate'] == custom_rate
    
    def test_calculate_dcf_value_without_discount_rate(self, dcf_calculator):
        """測試使用 CAPM 計算折現率"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=150.0,
            current_eps=15.0,
            growth_rates=[0.10, 0.05],
            discount_rate=None  # 使用 CAPM
        )
        
        # 應該使用 CAPM 計算的折現率
        expected_capm_rate = 0.04 + 0.04 + 0.03  # 0.11
        assert result['discount_rate'] == pytest.approx(expected_capm_rate)
    
    def test_calculate_dcf_value_upside_potential_calculation(self, dcf_calculator):
        """測試潛在獲利率計算"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=100.0,
            current_eps=10.0,
            growth_rates=[0.15, 0.10],
            discount_rate=0.11
        )
        
        # 潛在獲利率 = (內在價值 - 當前價格) / 當前價格
        expected_upside = (result['intrinsic_value'] - 100.0) / 100.0
        assert result['upside_potential'] == pytest.approx(expected_upside)
    
    def test_calculate_dcf_value_realistic_scenario(self, dcf_calculator):
        """測試真實情境（台積電類似數據）"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=973.0,
            current_eps=32.34,
            growth_rates=[0.23, 0.12],
            discount_rate=0.11,
            years=10
        )
        
        # 檢查結果合理性
        assert result['intrinsic_value'] > 0
        assert result['cash_flows'][0] > 32.34  # 第一年 EPS 應大於當前
        assert len(result['cash_flows']) == 10
        assert len(result['present_values']) == 10
        assert result['terminal_value'] > 0


# ============================================================================
# Test Class: 敏感性分析
# ============================================================================

class TestSensitivityAnalysis:
    """測試敏感性分析"""
    
    def test_sensitivity_analysis_structure(self, dcf_calculator):
        """測試敏感性分析結果結構"""
        result = dcf_calculator.sensitivity_analysis(
            current_price=100.0,
            current_eps=10.0,
            base_growth_rates=[0.15, 0.10]
        )
        
        # 檢查三種情境
        assert '悲觀' in result
        assert '基準' in result
        assert '樂觀' in result
        
        # 檢查每個情境有三種折現率
        for scenario in ['悲觀', '基準', '樂觀']:
            assert '折現率8.0%' in result[scenario]
            assert '折現率11.0%' in result[scenario]
            assert '折現率14.0%' in result[scenario]
    
    def test_sensitivity_analysis_values(self, dcf_calculator):
        """測試敏感性分析數值正確性"""
        result = dcf_calculator.sensitivity_analysis(
            current_price=100.0,
            current_eps=10.0,
            base_growth_rates=[0.10, 0.05]
        )
        
        # 檢查每個情境下都有內在價值和潛在獲利率
        for scenario in ['悲觀', '基準', '樂觀']:
            for discount_rate in ['折現率8.0%', '折現率11.0%', '折現率14.0%']:
                assert '內在價值' in result[scenario][discount_rate]
                assert '潛在獲利率' in result[scenario][discount_rate]
                assert result[scenario][discount_rate]['內在價值'] > 0
    
    def test_sensitivity_analysis_growth_rate_scenarios(self, dcf_calculator):
        """測試成長率情境正確性"""
        base_growth_rates = [0.10, 0.05]
        result = dcf_calculator.sensitivity_analysis(
            current_price=100.0,
            current_eps=10.0,
            base_growth_rates=base_growth_rates
        )
        
        # 樂觀情境的內在價值應該最高
        optimistic_value = result['樂觀']['折現率11.0%']['內在價值']
        base_value = result['基準']['折現率11.0%']['內在價值']
        pessimistic_value = result['悲觀']['折現率11.0%']['內在價值']
        
        assert optimistic_value > base_value > pessimistic_value
    
    def test_sensitivity_analysis_discount_rate_effect(self, dcf_calculator):
        """測試折現率對結果的影響"""
        result = dcf_calculator.sensitivity_analysis(
            current_price=100.0,
            current_eps=10.0,
            base_growth_rates=[0.15, 0.10]
        )
        
        # 在同一情境下，較低的折現率應產生較高的內在價值
        base_scenario = result['基準']
        value_8pct = base_scenario['折現率8.0%']['內在價值']
        value_11pct = base_scenario['折現率11.0%']['內在價值']
        value_14pct = base_scenario['折現率14.0%']['內在價值']
        
        assert value_8pct > value_11pct > value_14pct
    
    def test_sensitivity_analysis_with_custom_discount_rate(self, dcf_calculator):
        """測試自訂折現率的敏感性分析"""
        # 即使提供自訂折現率，敏感性分析應該使用預設的三種折現率
        result = dcf_calculator.sensitivity_analysis(
            current_price=150.0,
            current_eps=15.0,
            base_growth_rates=[0.12, 0.08],
            discount_rate=0.09  # 自訂折現率應該被忽略
        )
        
        # 應該仍然有三種標準折現率的結果
        assert '折現率8.0%' in result['基準']
        assert '折現率11.0%' in result['基準']
        assert '折現率14.0%' in result['基準']


# ============================================================================
# Test Class: 邊界條件測試
# ============================================================================

class TestEdgeCases:
    """測試邊界條件與異常情況"""
    
    def test_zero_current_eps(self, dcf_calculator):
        """測試零 EPS"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=100.0,
            current_eps=0.0,
            growth_rates=[0.10, 0.05]
        )
        
        # 零 EPS 應該產生零或接近零的內在價值
        assert result['intrinsic_value'] == pytest.approx(0.0, abs=1.0)
    
    def test_negative_current_eps(self, dcf_calculator):
        """測試負 EPS（虧損公司）"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=50.0,
            current_eps=-5.0,
            growth_rates=[0.10, 0.05]
        )
        
        # 負 EPS 應該能正常計算（即使結果可能為負）
        assert 'intrinsic_value' in result
        assert 'cash_flows' in result
    
    def test_very_high_growth_rates(self, dcf_calculator):
        """測試極高成長率"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=100.0,
            current_eps=10.0,
            growth_rates=[0.50, 0.30]  # 50%, 30% 成長率
        )
        
        # 高成長率應該產生高內在價值
        assert result['intrinsic_value'] > result['current_price'] * 2
    
    def test_zero_growth_rates(self, dcf_calculator):
        """測試零成長率"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=100.0,
            current_eps=10.0,
            growth_rates=[0.0, 0.0]
        )
        
        # 零成長率仍應產生有效結果
        assert result['intrinsic_value'] > 0
        # 所有現金流應該相等
        cash_flows_set = set(result['cash_flows'])
        assert len(cash_flows_set) == 1  # 所有值應該相同
    
    def test_extreme_discount_rate(self, dcf_calculator):
        """測試極端折現率"""
        # 測試非常高的折現率
        result_high = dcf_calculator.calculate_dcf_value(
            current_price=100.0,
            current_eps=10.0,
            growth_rates=[0.10, 0.05],
            discount_rate=0.50  # 50%
        )
        
        # 高折現率應產生低內在價值
        assert result_high['intrinsic_value'] < 100.0
    
    def test_single_year_projection(self, dcf_calculator):
        """測試單年預測"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=100.0,
            current_eps=10.0,
            growth_rates=[0.10, 0.05],
            years=1
        )
        
        assert len(result['cash_flows']) == 1
        assert len(result['present_values']) == 1
        assert result['terminal_value'] > 0
    
    def test_very_long_projection(self, dcf_calculator):
        """測試長期預測（20年）"""
        result = dcf_calculator.calculate_dcf_value(
            current_price=100.0,
            current_eps=10.0,
            growth_rates=[0.10, 0.05],
            years=20
        )
        
        assert len(result['cash_flows']) == 20
        assert len(result['present_values']) == 20
        # 後期現值應該顯著小於前期現值（因為折現效果）
        assert result['present_values'][-1] < result['present_values'][0] * 0.5


# ============================================================================
# Test Class: 整合測試
# ============================================================================

class TestIntegration:
    """整合測試"""
    
    def test_full_workflow(self, dcf_calculator):
        """測試完整工作流程"""
        # 1. 計算 DCF 價值
        dcf_result = dcf_calculator.calculate_dcf_value(
            current_price=500.0,
            current_eps=25.0,
            growth_rates=[0.18, 0.12]
        )
        
        # 2. 檢查所有關鍵欄位存在
        required_fields = [
            'current_price', 'intrinsic_value', 'upside_potential',
            'discount_rate', 'cash_flows', 'present_values',
            'terminal_value', 'recommendation'
        ]
        for field in required_fields:
            assert field in dcf_result
        
        # 3. 進行敏感性分析
        sensitivity_result = dcf_calculator.sensitivity_analysis(
            current_price=500.0,
            current_eps=25.0,
            base_growth_rates=[0.18, 0.12]
        )
        
        # 4. 檢查敏感性分析結果
        assert len(sensitivity_result) == 3  # 三種情境
        
        # 5. 驗證結果一致性
        base_dcf = sensitivity_result['基準']['折現率11.0%']['內在價值']
        # 基準情境在 11% 折現率下的結果應該接近 DCF 計算（如果使用 CAPM）
        # 注意：由於 CAPM 也是 11%，所以應該相同
        if dcf_result['discount_rate'] == pytest.approx(0.11):
            assert dcf_result['intrinsic_value'] == pytest.approx(base_dcf, rel=0.01)
    
    def test_multiple_calculations_consistency(self, dcf_calculator):
        """測試多次計算的一致性"""
        params = {
            'current_price': 200.0,
            'current_eps': 15.0,
            'growth_rates': [0.15, 0.10],
            'discount_rate': 0.12
        }
        
        # 執行多次計算
        result1 = dcf_calculator.calculate_dcf_value(**params)
        result2 = dcf_calculator.calculate_dcf_value(**params)
        result3 = dcf_calculator.calculate_dcf_value(**params)
        
        # 結果應該完全相同
        assert result1['intrinsic_value'] == pytest.approx(result2['intrinsic_value'])
        assert result2['intrinsic_value'] == pytest.approx(result3['intrinsic_value'])
        assert result1['upside_potential'] == pytest.approx(result2['upside_potential'])

class TestScenarioComparison:
    """測試情境比較功能"""
    def test_calculate_scenario_comparison(self, dcf_calculator):
        result = dcf_calculator.calculate_scenario_comparison(
            current_price=100.0,
            current_eps=10.0,
            base_growth_rates=[0.10, 0.05],
            discount_rate=0.10
        )
        assert '保守' in result
        assert '中性' in result
        assert '樂觀' in result
        
        # 內在價值應該 樂觀 > 基準 > 悲觀 
        assert result['樂觀']['intrinsic_value'] > result['中性']['intrinsic_value']
        assert result['中性']['intrinsic_value'] > result['保守']['intrinsic_value']
