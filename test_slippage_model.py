"""
測試滑動風險模型

驗證 SlippageModel 類別的基本功能
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import pandas as pd
from datetime import datetime, timedelta
from risk.slippage_model import SlippageModel


def create_sample_price_data():
    """創建測試用的價格數據"""
    dates = pd.date_range(end=datetime.now(), periods=10, freq='D')
    
    # 模擬台積電的價格數據
    data = {
        'date': dates,
        'close_price': [580, 582, 585, 583, 587, 590, 588, 592, 595, 593],
        'high_price': [585, 588, 590, 588, 592, 595, 593, 597, 600, 598],
        'low_price': [578, 580, 582, 580, 585, 588, 586, 590, 592, 590],
        'volume': [50000000, 52000000, 48000000, 51000000, 53000000,
                  49000000, 50000000, 54000000, 52000000, 51000000]
    }
    
    return pd.DataFrame(data)


def test_basic_slippage():
    """測試基本滑價計算"""
    print("=" * 60)
    print("測試 1: 基本滑價計算（買入）")
    print("=" * 60)
    
    # 創建模型
    model = SlippageModel()
    print(f"✓ 模型初始化成功")
    print(f"  波動性權重: {model.volatility_weight:.2f}")
    print(f"  流動性權重: {model.liquidity_weight:.2f}")
    print(f"  市場衝擊權重: {model.impact_weight:.2f}")
    
    # 創建測試數據
    price_data = create_sample_price_data()
    print(f"✓ 測試數據創建成功（{len(price_data)} 根 K 棒）")
    
    # 計算滑價
    result = model.calculate_slippage(
        price_data=price_data,
        trade_type='buy',
        position_size=1000000  # 100萬元部位
    )
    
    print("\n滑價計算結果：")
    print(f"  參考價格: {result['reference_price']:.2f} 元")
    print(f"  調整後價格: {result['adjusted_price']:.2f} 元")
    print(f"  總滑價: {result['total_slippage_pct']*100:.3f}%")
    print(f"  滑價金額: {result['total_slippage_amount']:.2f} 元")
    print(f"  流動性分級: {result['liquidity_tier']}")
    print(f"  是否有效: {result['is_valid']}")
    print(f"  訊息: {result['message']}")
    
    print("\n各項滑價分解：")
    print(f"  波動性滑價: {result['volatility_slippage']*100:.3f}%")
    print(f"  流動性滑價: {result['liquidity_slippage']*100:.3f}%")
    print(f"  市場衝擊滑價: {result['impact_slippage']*100:.3f}%")
    
    assert result['is_valid'], "滑價計算應該成功"
    print("\n✓ 測試通過！")


def test_sell_slippage():
    """測試賣出滑價計算"""
    print("\n" + "=" * 60)
    print("測試 2: 賣出滑價計算")
    print("=" * 60)
    
    model = SlippageModel()
    price_data = create_sample_price_data()
    
    result = model.calculate_slippage(
        price_data=price_data,
        trade_type='sell',
        position_size=500000  # 50萬元部位
    )
    
    print("\n滑價計算結果：")
    print(f"  參考價格: {result['reference_price']:.2f} 元")
    print(f"  調整後價格: {result['adjusted_price']:.2f} 元")
    print(f"  總滑價: {result['total_slippage_pct']*100:.3f}%")
    print(f"  滑價金額: {result['total_slippage_amount']:.2f} 元")
    
    # 賣出時，調整後價格應該低於參考價格
    assert result['adjusted_price'] < result['reference_price'], \
        "賣出時調整後價格應該更低"
    print("\n✓ 測試通過！")


def test_adjust_buy_price():
    """測試買入價格調整功能"""
    print("\n" + "=" * 60)
    print("測試 3: 買入價格調整（DCF 應用）")
    print("=" * 60)
    
    model = SlippageModel()
    price_data = create_sample_price_data()
    
    # 假設 DCF 計算的建議買入價為 550 元
    target_price = 550.0
    position_size = 200000  # 預計投入 20 萬
    
    result = model.adjust_buy_price(
        price_data=price_data,
        target_price=target_price,
        position_size=position_size
    )
    
    print(f"\nDCF 建議價格: {result['original_price']:.2f} 元")
    print(f"考慮滑價後: {result['adjusted_price']:.2f} 元")
    print(f"滑價影響: {result['slippage_amount']:.2f} 元 ({result['slippage_pct']*100:.2f}%)")
    print(f"流動性分級: {result['liquidity_tier']}")
    print(f"建議訊息: {result['message']}")
    
    assert result['is_valid'], "價格調整應該成功"
    assert result['adjusted_price'] > result['original_price'], \
        "考慮滑價後的買入價應該更高"
    print("\n✓ 測試通過！")


def test_different_liquidity():
    """測試不同流動性股票的滑價"""
    print("\n" + "=" * 60)
    print("測試 4: 不同流動性股票比較")
    print("=" * 60)
    
    model = SlippageModel()
    
    # 高流動性股票（如台積電）
    high_liquidity_data = create_sample_price_data()
    high_result = model.calculate_slippage(high_liquidity_data, 'buy')
    
    # 低流動性股票（模擬小型股）
    low_liquidity_data = high_liquidity_data.copy()
    low_liquidity_data['volume'] = low_liquidity_data['volume'] / 100  # 成交量僅 1/100
    low_result = model.calculate_slippage(low_liquidity_data, 'buy')
    
    print("\n高流動性股票：")
    print(f"  流動性分級: {high_result['liquidity_tier']}")
    print(f"  總滑價: {high_result['total_slippage_pct']*100:.3f}%")
    
    print("\n低流動性股票：")
    print(f"  流動性分級: {low_result['liquidity_tier']}")
    print(f"  總滑價: {low_result['total_slippage_pct']*100:.3f}%")
    
    assert low_result['total_slippage_pct'] > high_result['total_slippage_pct'], \
        "低流動性股票的滑價應該更高"
    print("\n✓ 測試通過！低流動性股票確實有更高的滑價")


def test_position_size_impact():
    """測試不同部位大小的市場衝擊"""
    print("\n" + "=" * 60)
    print("測試 5: 不同部位大小的市場衝擊")
    print("=" * 60)
    
    model = SlippageModel()
    price_data = create_sample_price_data()
    
    # 測試小單、中單、大單
    position_sizes = [
        (100000, "小單（10萬）"),
        (5000000, "中單（500萬）"),
        (50000000, "大單（5000萬）")
    ]
    
    for size, label in position_sizes:
        result = model.calculate_slippage(
            price_data=price_data,
            trade_type='buy',
            position_size=size
        )
        print(f"\n{label}:")
        print(f"  市場衝擊: {result['impact_slippage']*100:.3f}%")
        print(f"  總滑價: {result['total_slippage_pct']*100:.3f}%")
    
    print("\n✓ 測試通過！")


def main():
    """執行所有測試"""
    print("\n" + "=" * 60)
    print("滑動風險模型測試")
    print("=" * 60 + "\n")
    
    try:
        test_basic_slippage()
        test_sell_slippage()
        test_adjust_buy_price()
        test_different_liquidity()
        test_position_size_impact()
        
        print("\n" + "=" * 60)
        print("所有測試通過！✓")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n✗ 測試失敗: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
