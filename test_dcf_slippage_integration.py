"""
測試 DCF Calculator 與滑動風險模型整合

驗證 calculate_buy_recommendation() 方法
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import pandas as pd
from datetime import datetime, timedelta
from dcf_calculator import DCFCalculator


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


def test_basic_dcf_calculation():
    """測試基本 DCF 計算"""
    print("=" * 60)
    print("測試 1: 基本 DCF 計算（不含滑價）")
    print("=" * 60)
    
    # 創建計算器（停用滑價）
    calculator = DCFCalculator(enable_slippage=False)
    
    # 台積電假設數據
    test_data = {
        'current_price': 593.0,
        'current_eps': 32.0,
        'growth_rates': [0.15, 0.08],  # 1-5年 15%, 6-10年 8%
    }
    
    result = calculator.calculate_dcf_value(**test_data)
    
    print(f"\n目前股價: ${result['current_price']:.2f}")
    print(f"內在價值: ${result['intrinsic_value']:.2f}")
    print(f"潛在獲利率: {result['upside_potential']:.2%}")
    print(f"投資建議: {result['recommendation']}")
    
    assert result['intrinsic_value'] > 0, "內在價值應該大於 0"
    print("\n✓ 測試通過！")
    
    return result


def test_buy_recommendation_without_slippage():
    """測試買入建議（不含滑價）"""
    print("\n" + "=" * 60)
    print("測試 2: 買入建議計算（不含滑價）")
    print("=" * 60)
    
    calculator = DCFCalculator(enable_slippage=False)
    
    # 假設內在價值為 700，目前股價 593
    intrinsic_value = 700.0
    current_price = 593.0
    
    result = calculator.calculate_buy_recommendation(
        intrinsic_value=intrinsic_value,
        current_price=current_price,
        safety_margin=0.85
    )
    
    print(f"\n內在價值: ${result['intrinsic_value']:.2f}")
    print(f"目前股價: ${result['current_price']:.2f}")
    print(f"安全邊際: {result['safety_margin']:.0%}")
    print(f"基礎建議價: ${result['base_buy_price']:.2f}")
    print(f"最終建議價: ${result['recommended_buy_price']:.2f}")
    print(f"是否低估: {result['is_undervalued']}")
    print(f"折價率: {result['discount_pct']:.2%}")
    print(f"建議: {result['recommendation']}")
    
    assert result['base_buy_price'] == result['recommended_buy_price'], \
        "停用滑價時，建議價應等於基礎價"
    assert not result['slippage_adjusted'], "應該沒有滑價調整"
    print("\n✓ 測試通過！")
    
    return result


def test_buy_recommendation_with_slippage():
    """測試買入建議（含滑價）"""
    print("\n" + "=" * 60)
    print("測試 3: 買入建議計算（含滑價）")
    print("=" * 60)
    
    calculator = DCFCalculator(enable_slippage=True)
    price_data = create_sample_price_data()
    
    # 假設內在價值為 700，目前股價 593
    intrinsic_value = 700.0
    current_price = 593.0
    position_size = 500000  # 預計投入 50 萬
    
    result = calculator.calculate_buy_recommendation(
        intrinsic_value=intrinsic_value,
        current_price=current_price,
        price_data=price_data,
        position_size=position_size,
        safety_margin=0.85
    )
    
    print(f"\n內在價值: ${result['intrinsic_value']:.2f}")
    print(f"目前股價: ${result['current_price']:.2f}")
    print(f"安全邊際: {result['safety_margin']:.0%}")
    print(f"基礎建議價: ${result['base_buy_price']:.2f}")
    print(f"最終建議價: ${result['recommended_buy_price']:.2f}")
    print(f"是否低估: {result['is_undervalued']}")
    print(f"折價率: {result['discount_pct']:.2%}")
    
    if result['slippage_adjusted']:
        print(f"\n✓ 滑價調整: 已啟用")
        print(f"  滑價金額: ${result['slippage_info']['slippage_amount']:.2f}")
        print(f"  滑價比例: {result['slippage_info']['slippage_pct']:.3%}")
        print(f"  流動性: {result['slippage_info']['liquidity_tier']}")
        print(f"  訊息: {result['slippage_info']['message']}")
    
    print(f"\n建議: {result['recommendation']}")
    
    # 驗證滑價調整
    if result['slippage_adjusted']:
        assert result['recommended_buy_price'] > result['base_buy_price'], \
            "考慮滑價後，建議買入價應該更高"
    
    print("\n✓ 測試通過！")
    
    return result


def test_full_workflow():
    """測試完整工作流程"""
    print("\n" + "=" * 60)
    print("測試 4: 完整工作流程（DCF + 買入建議 + 滑價）")
    print("=" * 60)
    
    calculator = DCFCalculator(enable_slippage=True)
    price_data = create_sample_price_data()
    
    # Step 1: DCF 計算
    current_price = 593.0
    current_eps = 32.0
    growth_rates = [0.15, 0.08]
    
    dcf_result = calculator.calculate_dcf_value(
        current_price=current_price,
        current_eps=current_eps,
        growth_rates=growth_rates
    )
    
    print("\n【Step 1: DCF 估值】")
    print(f"內在價值: ${dcf_result['intrinsic_value']:.2f}")
    print(f"潛在獲利率: {dcf_result['upside_potential']:.2%}")
    
    # Step 2: 買入建議（含滑價）
    buy_rec = calculator.calculate_buy_recommendation(
        intrinsic_value=dcf_result['intrinsic_value'],
        current_price=current_price,
        price_data=price_data,
        position_size=1000000  # 100 萬
    )
    
    print("\n【Step 2: 買入建議（含滑價）】")
    print(f"建議買入價: ${buy_rec['recommended_buy_price']:.2f}")
    print(f"  └─ 基礎價: ${buy_rec['base_buy_price']:.2f}")
    
    if buy_rec['slippage_adjusted']:
        print(f"  └─ 滑價調整: +${buy_rec['slippage_info']['slippage_amount']:.2f} " +
              f"({buy_rec['slippage_info']['slippage_pct']:.2%})")
    
    print(f"\n投資決策: {buy_rec['recommendation']}")
    
    # Step 3: 比較不同部位大小
    print("\n【Step 3: 不同部位大小比較】")
    position_sizes = [
        (100000, "小額投資 (10萬)"),
        (1000000, "中額投資 (100萬)"),
        (10000000, "大額投資 (1000萬)")
    ]
    
    for size, label in position_sizes:
        rec = calculator.calculate_buy_recommendation(
            intrinsic_value=dcf_result['intrinsic_value'],
            current_price=current_price,
            price_data=price_data,
            position_size=size
        )
        print(f"\n{label}:")
        print(f"  建議價: ${rec['recommended_buy_price']:.2f}")
        if rec['slippage_adjusted']:
            print(f"  滑價: {rec['slippage_info']['slippage_pct']:.3%}")
    
    print("\n✓ 完整流程測試通過！")


def main():
    """執行所有測試"""
    print("\n" + "=" * 60)
    print("DCF Calculator + 滑動風險整合測試")
    print("=" * 60 + "\n")
    
    try:
        test_basic_dcf_calculation()
        test_buy_recommendation_without_slippage()
        test_buy_recommendation_with_slippage()
        test_full_workflow()
        
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
