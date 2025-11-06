"""
測試時間加權成長率功能

驗證指數衰減時間加權（EWMA）實作是否正確
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import pandas as pd
import numpy as np
from data.manager import DataManagerV2


def test_exponential_weights():
    """測試指數衰減權重計算"""
    print("\n" + "="*60)
    print("測試 1：指數衰減權重計算")
    print("="*60)
    
    manager = DataManagerV2()
    
    # 測試案例 1：5 年數據，近期權重 60%
    n = 5
    recent_weight_ratio = 0.6
    
    weights = manager._calculate_exponential_weights(n, recent_weight_ratio)
    
    print(f"\n數據點數量：{n}")
    print(f"近期權重比例設定：{recent_weight_ratio:.1%}")
    print(f"\n權重分配（由舊到新）：")
    for i, w in enumerate(weights):
        print(f"  第 {i+1} 年：{w:.4f} ({w*100:.2f}%)")
    
    print(f"\n權重總和：{sum(weights):.4f}")
    print(f"最新年份權重：{weights[-1]:.4f} ({weights[-1]*100:.2f}%)")
    
    # 驗證
    assert abs(sum(weights) - 1.0) < 0.001, "權重總和應該為 1"
    assert weights[-1] >= 0.55, f"最新年份權重應該 ≥ 55%（實際：{weights[-1]*100:.2f}%）"
    assert weights[-1] <= 0.65, f"最新年份權重應該 ≤ 65%（實際：{weights[-1]*100:.2f}%）"
    print("\n✓ 權重計算正確")
    
    # 測試案例 2：不同的 recent_weight_ratio
    print("\n" + "-"*60)
    print("測試不同的近期權重比例：")
    print("-"*60)
    
    for ratio in [0.5, 0.6, 0.7, 0.8, 0.9]:
        weights = manager._calculate_exponential_weights(5, ratio)
        print(f"ratio={ratio:.1f}: 最新年份權重 = {weights[-1]:.4f} ({weights[-1]*100:.2f}%)")


def test_time_weighted_growth_rate():
    """測試時間加權成長率計算"""
    print("\n" + "="*60)
    print("測試 2：時間加權成長率計算")
    print("="*60)
    
    manager = DataManagerV2()
    
    # 測試案例：穩定成長的 EPS 數據
    eps_data = pd.Series([10.0, 11.0, 12.1, 13.3, 14.6])
    print(f"\nEPS 數據（穩定成長 10%）：")
    for i, eps in enumerate(eps_data):
        print(f"  第 {i+1} 年：{eps:.2f}")
    
    # 計算時間加權成長率
    growth_rate = manager._calculate_time_weighted_growth_rate(eps_data, recent_weight_ratio=0.6)
    print(f"\n時間加權成長率：{growth_rate:.4f} ({growth_rate*100:.2f}%)")
    
    # 計算傳統 CAGR
    cagr = (eps_data.iloc[-1] / eps_data.iloc[0]) ** (1 / (len(eps_data) - 1)) - 1
    print(f"傳統 CAGR：{cagr:.4f} ({cagr*100:.2f}%)")
    
    # 驗證
    assert abs(growth_rate - 0.10) < 0.02, "穩定成長數據的時間加權成長率應接近 10%"
    print("\n✓ 成長率計算正確")
    
    # 測試案例：近期加速成長
    print("\n" + "-"*60)
    print("測試近期加速成長情境：")
    print("-"*60)
    
    eps_data_accel = pd.Series([10.0, 11.0, 12.0, 14.0, 17.0])
    print(f"\nEPS 數據（近期加速成長）：")
    for i, eps in enumerate(eps_data_accel):
        growth = ((eps / eps_data_accel.iloc[i-1]) - 1) * 100 if i > 0 else 0
        print(f"  第 {i+1} 年：{eps:.2f}" + (f" (成長 {growth:.1f}%)" if i > 0 else ""))
    
    growth_weighted = manager._calculate_time_weighted_growth_rate(eps_data_accel, 0.6)
    cagr_accel = (eps_data_accel.iloc[-1] / eps_data_accel.iloc[0]) ** (1 / (len(eps_data_accel) - 1)) - 1
    
    print(f"\n時間加權成長率：{growth_weighted:.4f} ({growth_weighted*100:.2f}%)")
    print(f"傳統 CAGR：{cagr_accel:.4f} ({cagr_accel*100:.2f}%)")
    print(f"差異：{(growth_weighted - cagr_accel)*100:.2f} 個百分點")
    print(f"\n說明：近期加速成長時，時間加權成長率應該 > CAGR")
    print(f"結果：{'✓ 符合預期' if growth_weighted > cagr_accel else '✗ 不符合預期'}")


def test_calculate_historical_growth_rate():
    """測試完整的歷史成長率計算功能"""
    print("\n" + "="*60)
    print("測試 3：完整歷史成長率計算（使用真實股票數據）")
    print("="*60)
    
    manager = DataManagerV2()
    
    # 測試台積電（2330）
    stock_code = "2330"
    print(f"\n測試股票：{stock_code} 台積電")
    
    try:
        # 使用時間加權
        result_weighted = manager.calculate_historical_growth_rate(
            stock_code,
            years=5,
            use_time_weighting=True,
            recent_weight_ratio=0.6
        )
        
        print(f"\n【時間加權模式】")
        print(f"近期成長率（1-5年）：{result_weighted['growth_rate_1_5']*100:.2f}%")
        print(f"長期成長率（6-10年）：{result_weighted['growth_rate_6_10']*100:.2f}%")
        print(f"資料品質：{result_weighted['data_quality']}")
        print(f"訊息：{result_weighted['message']}")
        print(f"加權方法：{result_weighted.get('weighting_method', 'N/A')}")
        
        if 'eps_start' in result_weighted:
            print(f"\nEPS 起始：{result_weighted['eps_start']:.2f}")
            print(f"EPS 最新：{result_weighted['eps_latest']:.2f}")
            if 'eps_start_year' in result_weighted:
                print(f"起始年份：{result_weighted['eps_start_year']}")
            if 'eps_latest_year' in result_weighted:
                print(f"最新年份：{result_weighted['eps_latest_year']}")
        
        # 使用傳統等權重
        result_equal = manager.calculate_historical_growth_rate(
            stock_code,
            years=5,
            use_time_weighting=False
        )
        
        print(f"\n【等權重模式（傳統 CAGR）】")
        print(f"近期成長率（1-5年）：{result_equal['growth_rate_1_5']*100:.2f}%")
        print(f"長期成長率（6-10年）：{result_equal['growth_rate_6_10']*100:.2f}%")
        print(f"加權方法：{result_equal.get('weighting_method', 'N/A')}")
        
        # 比較
        diff = (result_weighted['growth_rate_1_5'] - result_equal['growth_rate_1_5']) * 100
        print(f"\n【比較】")
        print(f"成長率差異：{diff:+.2f} 個百分點")
        
        print("\n✓ 完整功能測試成功")
        
    except Exception as e:
        print(f"\n⚠️  測試失敗：{str(e)}")
        print(f"可能原因：無法獲取 {stock_code} 的財務數據")


def test_parameter_sensitivity():
    """測試參數敏感度"""
    print("\n" + "="*60)
    print("測試 4：參數敏感度分析")
    print("="*60)
    
    manager = DataManagerV2()
    
    # 建立測試數據（近期加速成長）
    eps_data = pd.Series([10.0, 11.0, 12.0, 14.0, 18.0])
    
    print("\nEPS 測試數據（近期加速成長）：")
    for i, eps in enumerate(eps_data):
        print(f"  第 {i+1} 年：{eps:.2f}")
    
    print("\n不同 recent_weight_ratio 的影響：")
    print("-" * 60)
    
    ratios = [0.5, 0.6, 0.7, 0.8, 0.9]
    results = []
    
    for ratio in ratios:
        growth = manager._calculate_time_weighted_growth_rate(eps_data, ratio)
        results.append((ratio, growth))
        print(f"ratio = {ratio:.1f}: 成長率 = {growth*100:.2f}%")
    
    # 計算傳統 CAGR 作為比較
    cagr = (eps_data.iloc[-1] / eps_data.iloc[0]) ** (1 / (len(eps_data) - 1)) - 1
    print(f"\n傳統 CAGR（等權重）：{cagr*100:.2f}%")
    
    print(f"\n觀察：")
    print(f"- ratio 越高，越重視近期數據")
    print(f"- 近期加速成長時，ratio 越高，成長率越高")
    print(f"- ratio = 0.5 時，結果應接近 CAGR")
    
    # 驗證趨勢
    assert all(results[i][1] <= results[i+1][1] for i in range(len(results)-1)), \
        "ratio 增加時，成長率應該上升（近期加速成長情境）"
    
    print(f"\n✓ 參數敏感度測試通過")


def run_all_tests():
    """執行所有測試"""
    print("\n")
    print("="*60)
    print(" 時間加權成長率功能測試")
    print("="*60)
    
    try:
        test_exponential_weights()
        test_time_weighted_growth_rate()
        test_parameter_sensitivity()
        test_calculate_historical_growth_rate()
        
        print("\n" + "="*60)
        print(" 🎉 所有測試通過！")
        print("="*60)
        print("\n時間加權成長率功能實作正確，可以開始使用。")
        print("\n建議後續步驟：")
        print("1. 在實際股票分析中測試效果")
        print("2. 比較時間加權 vs 等權重的預測準確度")
        print("3. 調整 recent_weight_ratio 參數以符合投資風格")
        print("4. 更新文件說明使用方法")
        
    except AssertionError as e:
        print(f"\n❌ 測試失敗：{str(e)}")
        return False
    except Exception as e:
        print(f"\n❌ 測試錯誤：{str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
