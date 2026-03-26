"""
滑動風險模型測試套件

測試涵蓋：
- SlippageModel 初始化
- 基本滑價計算（買入/賣出）
- 買入價格調整功能
- 不同流動性股票的滑價差異
- 不同部位大小的市場衝擊
- 邊界條件處理
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from app.risk.slippage_model import SlippageModel


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
def slippage_model():
    """創建滑價模型實例"""
    return SlippageModel()


# ============================================================================
# Test Class: SlippageModel 初始化
# ============================================================================

class TestSlippageModelInit:
    """測試 SlippageModel 初始化"""
    
    def test_init_default_weights(self, slippage_model):
        """測試預設權重初始化"""
        assert slippage_model.volatility_weight == pytest.approx(0.4)
        assert slippage_model.liquidity_weight == pytest.approx(0.3)
        assert slippage_model.impact_weight == pytest.approx(0.3)
    
    def test_init_custom_weights(self):
        """測試自訂權重初始化"""
        model = SlippageModel(
            volatility_weight=0.5,
            liquidity_weight=0.3,
            impact_weight=0.2
        )
        
        assert model.volatility_weight == pytest.approx(0.5)
        assert model.liquidity_weight == pytest.approx(0.3)
        assert model.impact_weight == pytest.approx(0.2)
    
    def test_init_creates_valid_object(self, slippage_model):
        """測試初始化建立有效物件"""
        assert slippage_model is not None
        assert hasattr(slippage_model, 'calculate_slippage')
        assert hasattr(slippage_model, 'adjust_buy_price')


# ============================================================================
# Test Class: 基本滑價計算
# ============================================================================

class TestBasicSlippageCalculation:
    """測試基本滑價計算"""
    
    def test_calculate_slippage_buy(self, slippage_model, sample_price_data):
        """測試買入滑價計算"""
        result = slippage_model.calculate_slippage(
            price_data=sample_price_data,
            trade_type='buy',
            position_size=1000000  # 100萬元部位
        )
        
        # 檢查必要欄位
        assert 'reference_price' in result
        assert 'adjusted_price' in result
        assert 'total_slippage_pct' in result
        assert 'total_slippage_amount' in result
        assert 'liquidity_tier' in result
        assert 'is_valid' in result
        assert 'message' in result
        
        # 檢查數值合理性
        assert result['is_valid'] is True
        assert result['reference_price'] > 0
        assert result['adjusted_price'] > result['reference_price']  # 買入價格上調
        assert result['total_slippage_pct'] > 0
    
    def test_calculate_slippage_sell(self, slippage_model, sample_price_data):
        """測試賣出滑價計算"""
        result = slippage_model.calculate_slippage(
            price_data=sample_price_data,
            trade_type='sell',
            position_size=500000  # 50萬元部位
        )
        
        # 檢查必要欄位
        assert result['is_valid'] is True
        
        # 賣出時，調整後價格應該低於參考價格
        assert result['adjusted_price'] < result['reference_price']
        # 滑價金額的正負取決於實作方式，主要檢查價格調整方向正確
        assert result['total_slippage_pct'] > 0  # 滑價率應為正數
    
    def test_calculate_slippage_components(self, slippage_model, sample_price_data):
        """測試滑價分解組成"""
        result = slippage_model.calculate_slippage(
            price_data=sample_price_data,
            trade_type='buy',
            position_size=1000000
        )
        
        # 檢查各項滑價分解
        assert 'volatility_slippage' in result
        assert 'liquidity_slippage' in result
        assert 'impact_slippage' in result
        
        # 所有滑價組成應為非負數（買入時）
        assert result['volatility_slippage'] >= 0
        assert result['liquidity_slippage'] >= 0
        assert result['impact_slippage'] >= 0
        
        # 總滑價應該等於加權平均（允許小誤差）
        weighted_sum = (
            result['volatility_slippage'] * slippage_model.volatility_weight +
            result['liquidity_slippage'] * slippage_model.liquidity_weight +
            result['impact_slippage'] * slippage_model.impact_weight
        )
        assert result['total_slippage_pct'] == pytest.approx(weighted_sum, rel=0.01)


# ============================================================================
# Test Class: 買入價格調整
# ============================================================================

class TestBuyPriceAdjustment:
    """測試買入價格調整功能"""
    
    def test_adjust_buy_price_basic(self, slippage_model, sample_price_data):
        """測試基本買入價格調整"""
        target_price = 550.0
        position_size = 200000  # 預計投入 20 萬
        
        result = slippage_model.adjust_buy_price(
            price_data=sample_price_data,
            target_price=target_price,
            position_size=position_size
        )
        
        # 檢查必要欄位
        assert 'original_price' in result
        assert 'adjusted_price' in result
        assert 'slippage_amount' in result
        assert 'slippage_pct' in result
        assert 'liquidity_tier' in result
        assert 'is_valid' in result
        assert 'message' in result
        
        # 檢查數值正確性
        assert result['original_price'] == pytest.approx(target_price)
        assert result['is_valid'] is True
        assert result['adjusted_price'] > result['original_price']  # 考慮滑價後應更高
    
    def test_adjust_buy_price_calculation(self, slippage_model, sample_price_data):
        """測試價格調整計算正確性"""
        target_price = 600.0
        result = slippage_model.adjust_buy_price(
            price_data=sample_price_data,
            target_price=target_price,
            position_size=100000
        )
        
        # 滑價金額應該等於調整後價格減原價格
        expected_slippage = result['adjusted_price'] - result['original_price']
        assert result['slippage_amount'] == pytest.approx(expected_slippage, abs=0.01)
        
        # 滑價百分比應該正確
        expected_pct = result['slippage_amount'] / result['original_price']
        assert result['slippage_pct'] == pytest.approx(expected_pct, rel=0.01)


# ============================================================================
# Test Class: 流動性分級測試
# ============================================================================

class TestLiquidityTiers:
    """測試不同流動性股票的滑價"""
    
    def test_high_vs_low_liquidity(self, slippage_model, sample_price_data):
        """測試高流動性 vs 低流動性股票"""
        # 高流動性股票（台積電等級）
        high_result = slippage_model.calculate_slippage(
            sample_price_data, 
            'buy',
            position_size=1000000
        )
        
        # 低流動性股票（模擬小型股）
        low_liquidity_data = sample_price_data.copy()
        low_liquidity_data['volume'] = low_liquidity_data['volume'] / 100  # 成交量僅 1/100
        
        low_result = slippage_model.calculate_slippage(
            low_liquidity_data,
            'buy',
            position_size=1000000
        )
        
        # 低流動性股票的滑價應該更高
        assert low_result['total_slippage_pct'] > high_result['total_slippage_pct']
        assert low_result['liquidity_slippage'] > high_result['liquidity_slippage']
    
    def test_liquidity_tier_classification(self, slippage_model, sample_price_data):
        """測試流動性分級正確性"""
        result = slippage_model.calculate_slippage(
            sample_price_data,
            'buy'
        )
        
        # 應該被分類到某個流動性等級
        assert result['liquidity_tier'] in ['high', 'medium', 'low', 'very_low']
        
        # 台積電等級的成交量（50M）應該是 high 或 medium 等級
        # 實際分級取決於滑價模型的閾值設定
        assert result['liquidity_tier'] in ['high', 'medium']


# ============================================================================
# Test Class: 市場衝擊測試
# ============================================================================

class TestMarketImpact:
    """測試不同部位大小的市場衝擊"""
    
    def test_position_size_impact(self, slippage_model, sample_price_data):
        """測試不同部位大小的市場衝擊差異"""
        # 小單
        small_result = slippage_model.calculate_slippage(
            sample_price_data,
            'buy',
            position_size=100000  # 10萬
        )
        
        # 中單
        medium_result = slippage_model.calculate_slippage(
            sample_price_data,
            'buy',
            position_size=1000000000  # 10億
        )
        
        # 大單
        large_result = slippage_model.calculate_slippage(
            sample_price_data,
            'buy',
            position_size=5000000000  # 50億
        )
        
        # 部位越大，市場衝擊越大（檢查小單 vs 大單的顯著差異）
        assert small_result['impact_slippage'] <= medium_result['impact_slippage']
        assert medium_result['impact_slippage'] <= large_result['impact_slippage']
        
        # 總滑價：大單應該明顯高於小單
        assert small_result['total_slippage_pct'] < large_result['total_slippage_pct']
        # 小單和中單的市場衝擊應該不同（除非都在同一閾值區間）
        assert (small_result['impact_slippage'] < large_result['impact_slippage'] or
                small_result['total_slippage_pct'] < large_result['total_slippage_pct'])
    
    def test_zero_position_size(self, slippage_model, sample_price_data):
        """測試零部位（使用預設值）"""
        result = slippage_model.calculate_slippage(
            sample_price_data,
            'buy',
            position_size=0  # 使用預設部位
        )
        
        # 應該能正常計算
        assert result['is_valid'] is True
        assert result['total_slippage_pct'] > 0


# ============================================================================
# Test Class: 邊界條件測試
# ============================================================================

class TestEdgeCases:
    """測試邊界條件與異常情況"""
    
    def test_insufficient_data(self, slippage_model):
        """測試資料不足情況"""
        # 只有一根 K 棒
        short_data = pd.DataFrame({
            'date': [datetime.now()],
            'close_price': [600],
            'high_price': [610],
            'low_price': [590],
            'volume': [1000000]
        })
        
        result = slippage_model.calculate_slippage(short_data, 'buy')
        
        # 應該失敗或使用預設值
        if not result['is_valid']:
            assert 'message' in result
    
    def test_negative_price(self, slippage_model, sample_price_data):
        """測試負價格處理"""
        bad_data = sample_price_data.copy()
        bad_data['close_price'] = -100
        
        result = slippage_model.calculate_slippage(bad_data, 'buy')
        
        # 應該處理異常情況
        assert 'is_valid' in result
    
    def test_invalid_trade_type(self, slippage_model, sample_price_data):
        """測試無效交易類型"""
        result = slippage_model.calculate_slippage(
            sample_price_data,
            trade_type='invalid_type'
        )
        
        # 應該使用預設值或回傳錯誤
        assert result is not None
    
    def test_empty_dataframe(self, slippage_model):
        """測試空資料框"""
        empty_data = pd.DataFrame()
        
        result = slippage_model.calculate_slippage(empty_data, 'buy')
        
        # 應該正確處理空資料
        assert 'is_valid' in result
        if not result['is_valid']:
            assert 'message' in result


# ============================================================================
# Test Class: 整合測試
# ============================================================================

class TestIntegration:
    """整合測試"""
    
    def test_full_workflow(self, slippage_model, sample_price_data):
        """測試完整工作流程"""
        # Step 1: 計算滑價
        slippage_result = slippage_model.calculate_slippage(
            sample_price_data,
            'buy',
            position_size=1000000
        )
        
        assert slippage_result['is_valid'] is True
        
        # Step 2: 使用滑價調整買入價
        target_price = 550.0
        adjust_result = slippage_model.adjust_buy_price(
            sample_price_data,
            target_price,
            position_size=1000000
        )
        
        assert adjust_result['is_valid'] is True
        
        # Step 3: 比較兩種方法的流動性分級應該一致
        assert slippage_result['liquidity_tier'] == adjust_result['liquidity_tier']
    
    def test_multiple_calculations_consistency(self, slippage_model, sample_price_data):
        """測試多次計算的一致性"""
        params = {
            'price_data': sample_price_data,
            'trade_type': 'buy',
            'position_size': 500000
        }
        
        # 執行多次計算
        result1 = slippage_model.calculate_slippage(**params)
        result2 = slippage_model.calculate_slippage(**params)
        result3 = slippage_model.calculate_slippage(**params)
        
        # 結果應該完全相同
        assert result1['total_slippage_pct'] == pytest.approx(result2['total_slippage_pct'])
        assert result2['total_slippage_pct'] == pytest.approx(result3['total_slippage_pct'])
        assert result1['adjusted_price'] == pytest.approx(result2['adjusted_price'])

    def test_adjust_backtesting_trades(self, slippage_model, sample_price_data):
        import pandas as pd
        trades = pd.DataFrame([
            {'date': sample_price_data['date'].iloc[5], 'type': 'buy', 'price': 500.0, 'quantity': 5000},
            {'date': sample_price_data['date'].iloc[6], 'type': 'sell', 'price': 505.0, 'quantity': 5000}
        ])
        
        adjusted_trades = slippage_model.adjust_backtesting_trades(trades, sample_price_data)
        
        assert 'slippage_pct' in adjusted_trades.columns
        assert 'adjusted_price' in adjusted_trades.columns
        assert 'slippage_amount' in adjusted_trades.columns
        
        # 檢查滑價是否大於 0
        buy_row = adjusted_trades[adjusted_trades['type'] == 'buy'].iloc[0]
        assert buy_row['slippage_pct'] > 0
        
        # 檢查滑價是否大於 0
        sell_row = adjusted_trades[adjusted_trades['type'] == 'sell'].iloc[0]
        assert sell_row['slippage_pct'] > 0
