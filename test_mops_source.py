"""
測試 MOPS 資料源功能

測試項目：
1. MOPSSource 初始化
2. get_shares_outstanding() 獲取流通股數
3. get_stock_info() 獲取公司資訊
4. 快取機制測試
5. DataManagerV2 整合測試
"""

import sys
import os
from datetime import datetime
from pathlib import Path

# 添加專案根目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.data.sources.mops_source import MOPSSource
from app.data.manager import DataManagerV2


def test_mops_initialization():
    """測試 MOPS 初始化"""
    print("\n" + "="*60)
    print("測試 1: MOPS 初始化")
    print("="*60)
    
    try:
        mops = MOPSSource()
        print(f"✓ MOPS 初始化成功")
        print(f"  - 可用性: {mops.is_available}")
        print(f"  - 就緒狀態: {mops.is_ready()}")
        print(f"  - 快取目錄: {mops.cache_dir}")
        return True
    except Exception as e:
        print(f"✗ MOPS 初始化失敗: {str(e)}")
        return False


def test_get_shares_outstanding():
    """測試獲取流通股數"""
    print("\n" + "="*60)
    print("測試 2: 獲取流通股數")
    print("="*60)
    
    test_stocks = [
        ('2330', '台積電'),
        ('2317', '鴻海'),
        ('2454', '聯發科'),
    ]
    
    mops = MOPSSource()
    results = []
    
    for stock_code, stock_name in test_stocks:
        print(f"\n測試股票: {stock_code} {stock_name}")
        try:
            # 使用當前日期
            report_date = datetime.now().strftime('%Y-%m-%d')
            shares = mops.get_shares_outstanding(stock_code, report_date)
            
            if shares and shares > 0:
                print(f"  ✓ 成功獲取流通股數: {shares:,} 股")
                results.append(True)
            else:
                print(f"  ⚠️ 未獲取到流通股數")
                results.append(False)
                
        except Exception as e:
            print(f"  ✗ 獲取失敗: {str(e)}")
            results.append(False)
    
    success_rate = sum(results) / len(results) * 100
    print(f"\n成功率: {success_rate:.1f}% ({sum(results)}/{len(results)})")
    return success_rate >= 66.7  # 至少2/3成功


def test_get_stock_info():
    """測試獲取公司資訊"""
    print("\n" + "="*60)
    print("測試 3: 獲取公司資訊")
    print("="*60)
    
    test_stocks = [
        ('2330', '台積電'),
        ('2317', '鴻海'),
    ]
    
    mops = MOPSSource()
    results = []
    
    for stock_code, expected_name in test_stocks:
        print(f"\n測試股票: {stock_code}")
        try:
            info = mops.get_stock_info(stock_code)
            
            if info:
                print(f"  ✓ 成功獲取公司資訊:")
                print(f"    - 代碼: {info.get('stock_code', 'N/A')}")
                print(f"    - 名稱: {info.get('stock_name', 'N/A')}")
                print(f"    - 產業: {info.get('industry', 'N/A')}")
                print(f"    - 市場: {info.get('market', 'N/A')}")
                results.append(True)
            else:
                print(f"  ⚠️ 未獲取到公司資訊")
                results.append(False)
                
        except Exception as e:
            print(f"  ✗ 獲取失敗: {str(e)}")
            results.append(False)
    
    success_rate = sum(results) / len(results) * 100
    print(f"\n成功率: {success_rate:.1f}% ({sum(results)}/{len(results)})")
    return success_rate >= 50  # 至少一半成功


def test_cache_mechanism():
    """測試快取機制"""
    print("\n" + "="*60)
    print("測試 4: 快取機制")
    print("="*60)
    
    mops = MOPSSource()
    stock_code = '2330'
    report_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"第一次獲取 {stock_code} 流通股數...")
    import time
    start_time = time.time()
    shares_1 = mops.get_shares_outstanding(stock_code, report_date)
    time_1 = time.time() - start_time
    print(f"  - 耗時: {time_1:.2f} 秒")
    print(f"  - 結果: {shares_1:,} 股" if shares_1 else "  - 結果: None")
    
    print(f"\n第二次獲取 {stock_code} 流通股數（應使用快取）...")
    start_time = time.time()
    shares_2 = mops.get_shares_outstanding(stock_code, report_date)
    time_2 = time.time() - start_time
    print(f"  - 耗時: {time_2:.2f} 秒")
    print(f"  - 結果: {shares_2:,} 股" if shares_2 else "  - 結果: None")
    
    if shares_1 and shares_2:
        print(f"\n快取效果:")
        print(f"  - 數據一致性: {'✓ 相同' if shares_1 == shares_2 else '✗ 不同'}")
        print(f"  - 速度提升: {time_1/time_2:.1f}x" if time_2 > 0 else "  - 速度提升: N/A")
        return shares_1 == shares_2
    else:
        print(f"\n⚠️ 無法測試快取（未獲取到數據）")
        return False


def test_datamanager_integration():
    """測試 DataManagerV2 整合"""
    print("\n" + "="*60)
    print("測試 5: DataManagerV2 整合")
    print("="*60)
    
    try:
        # 初始化 DataManager（不需要 FinMind Token）
        print("初始化 DataManagerV2...")
        dm = DataManagerV2()
        
        # 檢查 MOPS 是否已載入
        mops_loaded = any(
            source.__class__.__name__ == 'MOPSSource' 
            for source in dm.sources
        )
        print(f"  - MOPS 資料源已載入: {'✓' if mops_loaded else '✗'}")
        
        if not mops_loaded:
            print("  ⚠️ MOPS 未載入到 DataManagerV2")
            return False
        
        # 測試透過 DataManager 獲取流通股數
        stock_code = '2330'
        print(f"\n透過 DataManager 獲取 {stock_code} 流通股數...")
        shares = dm.get_shares_outstanding(stock_code)
        
        if shares and shares > 0:
            print(f"  ✓ 成功獲取: {shares:,} 股")
            print(f"  ✓ DataManagerV2 整合測試通過")
            return True
        else:
            print(f"  ⚠️ 未獲取到流通股數")
            return False
            
    except Exception as e:
        print(f"  ✗ 整合測試失敗: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_data_accuracy():
    """測試數據準確性（與 FinMind 比對）"""
    print("\n" + "="*60)
    print("測試 6: 數據準確性驗證")
    print("="*60)
    
    try:
        from app.data.sources.finmind_source import FinMindSource
        
        stock_code = '2330'
        report_date = datetime.now().strftime('%Y-%m-%d')
        
        # MOPS 數據
        mops = MOPSSource()
        shares_mops = mops.get_shares_outstanding(stock_code, report_date)
        
        # FinMind 數據
        finmind = FinMindSource()
        shares_finmind = finmind.get_shares_outstanding(stock_code, report_date) if finmind.is_available else None
        
        print(f"股票: {stock_code}")
        print(f"  - MOPS 流通股數: {shares_mops:,} 股" if shares_mops else "  - MOPS: None")
        print(f"  - FinMind 流通股數: {shares_finmind:,} 股" if shares_finmind else "  - FinMind: None")
        
        if shares_mops and shares_finmind:
            diff_pct = abs(shares_mops - shares_finmind) / shares_finmind * 100
            print(f"  - 差異: {diff_pct:.2f}%")
            
            if diff_pct < 5:
                print(f"  ✓ 數據一致性良好（差異 < 5%）")
                return True
            else:
                print(f"  ⚠️ 數據差異較大（差異 > 5%）")
                return False
        else:
            print(f"  ⚠️ 無法比對（缺少其中一個來源的數據）")
            return shares_mops is not None
            
    except Exception as e:
        print(f"  ✗ 準確性測試失敗: {str(e)}")
        return False


def run_all_tests():
    """執行所有測試"""
    print("\n" + "="*80)
    print("MOPS 資料源完整測試")
    print("="*80)
    
    tests = [
        ("MOPS 初始化", test_mops_initialization),
        ("獲取流通股數", test_get_shares_outstanding),
        ("獲取公司資訊", test_get_stock_info),
        ("快取機制", test_cache_mechanism),
        ("DataManagerV2 整合", test_datamanager_integration),
        ("數據準確性", test_data_accuracy),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ 測試 '{test_name}' 發生異常: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # 測試結果摘要
    print("\n" + "="*80)
    print("測試結果摘要")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ 通過" if result else "✗ 失敗"
        print(f"{status} - {test_name}")
    
    print(f"\n總結: {passed}/{total} 測試通過 ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 所有測試通過！MOPS 整合成功！")
    elif passed >= total * 0.7:
        print("⚠️ 大部分測試通過，但仍需注意失敗項目")
    else:
        print("❌ 多項測試失敗，需要檢查問題")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
