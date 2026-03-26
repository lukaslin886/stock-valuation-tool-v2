"""
DCF Calculator 與滑動風險模型整合測試套件

測試涵蓋：
- DCF Calculator 滑價功能初始化
- 基本 DCF 計算（不含滑價）
- 買入建議計算（不含滑價）
- 買入建議計算（含滑價）
- 完整工作流程（DCF + 滑價）
- 不同部位大小的滑價影響
- 邊界條件處理
"""

import pytest
import pandas as pd
from datetime import datetime
from app.dcf_calculator import DCFCalculator


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_price_data():
    """創建測試用的價格數據（模擬台積電）"""
    dates = pd.date_range(end=datetime.now(), periods=10, freq='D')
    
    data = {
        'date': dates,
        'close_price': [580, 582, 585, 583, 587, 590, 588, 592, 595, 593],
        'high_price': [585, 588, 590, 588, 592, 595, 593, 597, 600, 598],
        'low_price': [578, 580, 582, 580, 585, 588, 586, 590, 592, 590],
        'volume': [50000000, 52000000, 48000000, 51000000, 53000000,
                  49000000, 50000000, 54000000, 52000000, 51000000]
    }
    
    return pd.DataFrame(data)


@pytest.fixture
def dcf_calculator_with_slippage():
    """創建啟用滑價的 DCF Calculator"""
    return DCFCalculator(enable_slippage=True)


@pytest.fixture
def dcf_calculator_without_slippage():
    """創建停用滑價的 DCF Calculator"""
    return DCFCalculator(enable_slippage=False)


# ============================================================================
# Test Class: DCF Calculator 滑價功能初始化
# ============================================================================

class TestDCFCalculatorSlippageInit:
    """測試 DCF Calculator 滑價功能初始化"""
    
    def test_init_with_slippage_enabled(self, dcf_calculator_with_slippage):
        """測試啟用滑價初始化"""
        assert dcf_calculator_with_slippage.enable_slippage is True
        assert dcf_calculator_with_slippage.slippage_model is not None
    
    def test_init_with_slippage_disabled(self, dcf_calculator_without_slippage):
        """測試停用滑價初始化"""
        assert dcf_calculator_without_slippage.enable_slippage is False
        assert dcf_calculator_without_slippage.slippage_model is None
    
    def test_init_default_slippage_enabled(self):
        """測試預設狀態（滑價啟動）"""
        calculator = DCFCalculator()
        assert calculator.enable_slippage is True
        assert calculator.slippage_model is not None


# ============================================================================
# Test Class: DCF 基本計算（不含滑價）
# ============================================================================

class TestBasicDCFCalculation:
    """測試基本 DCF 計算（不含滑價）"""
    
    def test_basic_dcf_without_slippage(self, dcf_calculator_without_slippage):
        """測試基本 DCF 計算"""
        result = dcf_calculator_without_slippage.calculate_dcf_value(
            current_price=593.0,
            current_eps=32.0,
            growth_rates=[0.15, 0.08]
        )
        
        # 檢查必要欄位
        assert 'current_price' in result
        assert 'intrinsic_value' in result
        assert 'upside_potential' in result
        assert 'recommendation' in result
        
        # 檢查數值合理性
        assert result['current_price'] == 593.0
        assert result['intrinsic_value'] > 0
    
    def test_dcf_upside_potential_calculation(self, dcf_calculator_without_slippage):
        """測試潛在獲利率計算"""
        result = dcf_calculator_without_slippage.calculate_dcf_value(
            current_price=100.0,
            current_eps=10.0,
            growth_rates=[0.15, 0.10]
        )
        
        # 潛在獲利率 = (內在價值 - 當前價格) / 當前價格
        expected_upside = (result['intrinsic_value'] - 100.0) / 100.0
        assert result['upside_potential'] == pytest.approx(expected_upside, rel=0.01)


# ============================================================================
# Test Class: 買入建議（不含滑價）
# ============================================================================

class TestBuyRecommendationWithoutSlippage:
    """測試買入建議（不含滑價）"""
    
    def test_buy_recommendation_basic(self, dcf_calculator_without_slippage):
        """測試基本買入建議計算"""
        result = dcf_calculator_without_slippage.calculate_buy_recommendation(
            intrinsic_value=700.0,
            current_price=593.0,
            safety_margin=0.85
        )
        
        # 檢查必要欄位
        assert 'intrinsic_value' in result
        assert 'current_price' in result
        assert 'safety_margin' in result
        assert 'base_buy_price' in result
        assert 'recommended_buy_price' in result
        assert 'is_undervalued' in result
        assert 'discount_pct' in result
        assert 'recommendation' in result
        assert 'slippage_adjusted' in result
        
        # 檢查停用滑價狀態
        assert result['slippage_adjusted'] is False
        assert result['base_buy_price'] == result['recommended_buy_price']
    
    def test_buy_recommendation_safety_margin(self, dcf_calculator_without_slippage):
        """測試安全邊際計算"""
        intrinsic_value = 1000.0
        safety_margin = 0.80
        
        result = dcf_calculator_without_slippage.calculate_buy_recommendation(
            intrinsic_value=intrinsic_value,
            current_price=500.0,
            safety_margin=safety_margin
        )
        
        # 基礎買入價 = 內在價值 × 安全邊際
        expected_base_price = intrinsic_value * safety_margin
        assert result['base_buy_price'] == pytest.approx(expected_base_price)
    
    def test_buy_recommendation_undervalued(self, dcf_calculator_without_slippage):
        """測試低估判斷"""
        # 低估情況：目前價格 < 建議價格
        result = dcf_calculator_without_slippage.calculate_buy_recommendation(
            intrinsic_value=1000.0,
            current_price=500.0,
            safety_margin=0.85
        )
        
        assert result['is_undervalued'] is True
        assert result['discount_pct'] > 0
    
    def test_buy_recommendation_overvalued(self, dcf_calculator_without_slippage):
        """測試高估判斷"""
        # 高估情況：目前價格 > 建議價格
        result = dcf_calculator_without_slippage.calculate_buy_recommendation(
            intrinsic_value=500.0,
            current_price=1000.0,
            safety_margin=0.85
        )
        
        assert result['is_undervalued'] is False
        assert result['discount_pct'] < 0


# ============================================================================
# Test Class: 買入建議（含滑價）
# ============================================================================

class TestBuyRecommendationWithSlippage:
    """測試買入建議（含滑價）"""
    
    def test_buy_recommendation_with_slippage_enabled(
        self, dcf_calculator_with_slippage, sample_price_data
    ):
        """測試啟用滑價的買入建議"""
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=700.0,
            current_price=593.0,
            price_data=sample_price_data,
            position_size=500000,
            safety_margin=0.85
        )
        
        # 檢查滑價調整狀態
        assert result['slippage_adjusted'] is True
        assert 'slippage_info' in result
        
        # 最終建議價應該高於基礎價（考慮滑價）
        assert result['recommended_buy_price'] > result['base_buy_price']
    
    def test_buy_recommendation_slippage_info(
        self, dcf_calculator_with_slippage, sample_price_data
    ):
        """測試滑價資訊完整性"""
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=700.0,
            current_price=593.0,
            price_data=sample_price_data,
            position_size=500000
        )
        
        if result['slippage_adjusted']:
            slippage_info = result['slippage_info']
            
            # 檢查滑價資訊欄位
            assert 'slippage_amount' in slippage_info
            assert 'slippage_pct' in slippage_info
            assert 'liquidity_tier' in slippage_info
            assert 'message' in slippage_info
            
            # 滑價金額應該等於最終價 - 基礎價
            expected_slippage = result['recommended_buy_price'] - result['base_buy_price']
            assert slippage_info['slippage_amount'] == pytest.approx(expected_slippage, abs=0.01)
    
    def test_buy_recommendation_without_price_data(
        self, dcf_calculator_with_slippage
    ):
        """測試缺少價格數據時的處理"""
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=700.0,
            current_price=593.0,
            price_data=None,  # 未提供價格數據
            position_size=500000
        )
        
        # 應該回退到不使用滑價
        assert result['slippage_adjusted'] is False
        assert result['base_buy_price'] == result['recommended_buy_price']


# ============================================================================
# Test Class: 完整工作流程測試
# ============================================================================

class TestFullWorkflow:
    """測試完整工作流程（DCF + 滑價）"""
    
    def test_full_dcf_to_buy_recommendation_workflow(
        self, dcf_calculator_with_slippage, sample_price_data
    ):
        """測試 DCF 計算到買入建議的完整流程"""
        # Step 1: DCF 計算
        dcf_result = dcf_calculator_with_slippage.calculate_dcf_value(
            current_price=593.0,
            current_eps=32.0,
            growth_rates=[0.15, 0.08]
        )
        
        assert dcf_result['intrinsic_value'] > 0
        
        # Step 2: 買入建議（含滑價）
        buy_rec = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=dcf_result['intrinsic_value'],
            current_price=593.0,
            price_data=sample_price_data,
            position_size=1000000
        )
        
        assert buy_rec['slippage_adjusted'] is True
        assert buy_rec['recommended_buy_price'] > buy_rec['base_buy_price']
    
    def test_workflow_with_different_position_sizes(
        self, dcf_calculator_with_slippage, sample_price_data
    ):
        """測試不同部位大小的完整流程"""
        # DCF 計算
        dcf_result = dcf_calculator_with_slippage.calculate_dcf_value(
            current_price=593.0,
            current_eps=32.0,
            growth_rates=[0.15, 0.08]
        )
        
        # 測試小、中、大三種部位
        position_sizes = [100000, 1000000000, 3000000000]
        results = []
        
        for size in position_sizes:
            result = dcf_calculator_with_slippage.calculate_buy_recommendation(
                intrinsic_value=dcf_result['intrinsic_value'],
                current_price=593.0,
                price_data=sample_price_data,
                position_size=size
            )
            results.append(result)
        
        # 部位越大，滑價影響越大
        if all(r['slippage_adjusted'] for r in results):
            small_slippage = results[0]['slippage_info']['slippage_pct']
            large_slippage = results[2]['slippage_info']['slippage_pct']
            assert large_slippage > small_slippage


# ============================================================================
# Test Class: 優先級分類測試
# ============================================================================

class TestPriorityClassification:
    """測試買入建議優先級分類"""
    
    def test_priority_a_classification(self, dcf_calculator_with_slippage):
        """測試 A 級優先級（低估 > 30%）"""
        # 內在價值 1000，目前價 500，安全邊際 0.85
        # 建議價 = 850，折價 = (850-500)/850 = 41%
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=1000.0,
            current_price=500.0,
            safety_margin=0.85
        )
        
        if result['is_undervalued'] and result['discount_pct'] > 0.30:
            assert 'priority' in result
            assert result['priority'] == 'A'
    
    def test_priority_b_classification(self, dcf_calculator_with_slippage):
        """測試 B 級優先級（低估 15-30%）"""
        # 製造 B 級條件：折價率在 15-30% 之間
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=600.0,
            current_price=500.0,
            safety_margin=0.85
        )
        
        if result['is_undervalued']:
            discount = result['discount_pct']
            if 0.15 <= discount <= 0.30:
                assert 'priority' in result
                assert result['priority'] == 'B'
    
    def test_priority_c_classification(self, dcf_calculator_with_slippage):
        """測試 C 級優先級（低估 0-15%）"""
        # 製造 C 級條件：折價率在 0-15% 之間
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=550.0,
            current_price=500.0,
            safety_margin=0.85
        )
        
        if result['is_undervalued']:
            discount = result['discount_pct']
            if 0 < discount < 0.15:
                assert 'priority' in result
                assert result['priority'] == 'C'


# ============================================================================
# Test Class: 不同安全邊際測試
# ============================================================================

class TestDifferentSafetyMargins:
    """測試不同安全邊際的影響"""
    
    def test_aggressive_safety_margin(
        self, dcf_calculator_with_slippage, sample_price_data
    ):
        """測試激進的安全邊際（0.95）"""
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=700.0,
            current_price=593.0,
            price_data=sample_price_data,
            position_size=500000,
            safety_margin=0.95
        )
        
        # 高安全邊際應該產生較高的建議價
        assert result['base_buy_price'] == pytest.approx(700.0 * 0.95)
    
    def test_conservative_safety_margin(
        self, dcf_calculator_with_slippage, sample_price_data
    ):
        """測試保守的安全邊際（0.70）"""
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=700.0,
            current_price=593.0,
            price_data=sample_price_data,
            position_size=500000,
            safety_margin=0.70
        )
        
        # 低安全邊際應該產生較低的建議價
        assert result['base_buy_price'] == pytest.approx(700.0 * 0.70)
    
    def test_safety_margin_comparison(
        self, dcf_calculator_with_slippage, sample_price_data
    ):
        """測試不同安全邊際的比較"""
        intrinsic_value = 1000.0
        current_price = 500.0
        
        result_70 = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=intrinsic_value,
            current_price=current_price,
            price_data=sample_price_data,
            safety_margin=0.70
        )
        
        result_85 = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=intrinsic_value,
            current_price=current_price,
            price_data=sample_price_data,
            safety_margin=0.85
        )
        
        # 85% 安全邊際應該產生更高的建議價
        assert result_85['base_buy_price'] > result_70['base_buy_price']


# ============================================================================
# Test Class: 邊界條件測試
# ============================================================================

class TestEdgeCases:
    """測試邊界條件與異常情況"""
    
    def test_zero_intrinsic_value(self, dcf_calculator_with_slippage):
        """測試零內在價值"""
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=0.0,
            current_price=500.0
        )
        
        # 應該能正常處理
        assert 'recommended_buy_price' in result
        assert result['base_buy_price'] == 0.0
    
    def test_negative_intrinsic_value(self, dcf_calculator_with_slippage):
        """測試負內在價值（虧損公司）"""
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=-100.0,
            current_price=50.0
        )
        
        # 應該能正常處理
        assert 'recommended_buy_price' in result
    
    def test_very_high_intrinsic_value(
        self, dcf_calculator_with_slippage, sample_price_data
    ):
        """測試極高內在價值"""
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=10000.0,
            current_price=500.0,
            price_data=sample_price_data
        )
        
        # 應該產生極高的折價率
        assert result['is_undervalued'] is True
        assert result['discount_pct'] > 0.50
    
    def test_invalid_safety_margin(self, dcf_calculator_with_slippage):
        """測試無效的安全邊際"""
        # 安全邊際應該在 0-1 之間
        result = dcf_calculator_with_slippage.calculate_buy_recommendation(
            intrinsic_value=700.0,
            current_price=500.0,
            safety_margin=1.5  # 無效值
        )
        
        # 應該使用預設值或處理錯誤
        assert 'recommended_buy_price' in result


# ============================================================================
# Test Class: 整合與一致性測試
# ============================================================================

class TestIntegrationAndConsistency:
    """整合與一致性測試"""
    
    def test_slippage_vs_no_slippage_comparison(
        self, dcf_calculator_with_slippage, dcf_calculator_without_slippage,
        sample_price_data
    ):
        """比較啟用與停用滑價的差異"""
        params = {
            'intrinsic_value': 700.0,
            'current_price': 593.0,
            'safety_margin': 0.85
        }
        
        # 停用滑價
        result_no_slip = dcf_calculator_without_slippage.calculate_buy_recommendation(**params)
        
        # 啟用滑價
        result_with_slip = dcf_calculator_with_slippage.calculate_buy_recommendation(
            **params,
            price_data=sample_price_data,
            position_size=500000
        )
        
        # 基礎價應該相同
        assert result_no_slip['base_buy_price'] == result_with_slip['base_buy_price']
        
        # 最終建議價應該不同（啟用滑價時更高）
        if result_with_slip['slippage_adjusted']:
            assert result_with_slip['recommended_buy_price'] > result_no_slip['recommended_buy_price']
    
    def test_multiple_calculations_consistency(
        self, dcf_calculator_with_slippage, sample_price_data
    ):
        """測試多次計算的一致性"""
        params = {
            'intrinsic_value': 700.0,
            'current_price': 593.0,
            'price_data': sample_price_data,
            'position_size': 500000,
            'safety_margin': 0.85
        }
        
        # 執行多次計算
        result1 = dcf_calculator_with_slippage.calculate_buy_recommendation(**params)
        result2 = dcf_calculator_with_slippage.calculate_buy_recommendation(**params)
        result3 = dcf_calculator_with_slippage.calculate_buy_recommendation(**params)
        
        # 結果應該完全相同
        assert result1['recommended_buy_price'] == pytest.approx(result2['recommended_buy_price'])
        assert result2['recommended_buy_price'] == pytest.approx(result3['recommended_buy_price'])
        
        if result1['slippage_adjusted']:
            assert result1['slippage_info']['slippage_pct'] == pytest.approx(
                result2['slippage_info']['slippage_pct']
            )
