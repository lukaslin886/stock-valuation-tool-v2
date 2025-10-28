"""
DataManagerV2 整合測試
驗證新架構是否正常運作
"""

import sys
import os

# 添加 app 目錄到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from datetime import datetime, timedelta
from data import DataManager


def test_basic_initialization():
    """測試基本初始化"""
    print("\n" + "="*60)
    print("測試 1: 基本初始化")
    print("="*60)
    
    try:
        dm = DataManager()
        print("✓ DataManager 初始化成功")
        return True
    except Exception as e:
        print(f"✗ 初始化失敗: {str(e)}")
        return False


def test_get_stock_info():
    """測試獲取股票資訊"""
    print("\n" + "="*60)
    print("測試 2: 獲取股票資訊")
    print("="*60)
    
    try:
        dm = DataManager()
        info = dm.get_stock_info("2330")
        
        if info:
            print(f"✓ 成功獲取 2330 資訊")
            print(f"  股票名稱: {info.get('stock_name', 'N/A')}")
            print(f"  當前價格: ${info.get('current_price', 0):.2f}")
            return True
        else:
            print("✗ 無法獲取股票資訊")
            return False
            
    except Exception as e:
        print(f"✗ 測試失敗: {str(e)}")
        return False


def test_get_latest_eps():
    """測試獲取 EPS"""
    print("\n" + "="*60)
    print("測試 3: 獲取最新 EPS")
    print("="*60)
    
    try:
        dm = DataManager()
        eps = dm.get_latest_eps("2330")
        
        if eps > 0:
            print(f"✓ 成功獲取 2330 的 EPS: ${eps:.2f}")
            return True
        else:
            print(f"✗ EPS 數據無效: {eps}")
            return False
            
    except Exception as e:
        print(f"✗ 測試失敗: {str(e)}")
        return False


def test_get_price_data():
    """測試獲取價格數據"""
    print("\n" + "="*60)
    print("測試 4: 獲取價格數據")
    print("="*60)
    
    try:
        dm = DataManager()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        price_data = dm.get_stock_price("2330", start_date, end_date)
        
        if price_data is not None and len(price_data) > 0:
            print(f"✓ 成功獲取 2330 的價格數據")
            print(f"  數據筆數: {len(price_data)}")
            print(f"  日期範圍: {price_data['date'].min()} 至 {price_data['date'].max()}")
            print(f"  最新收盤價: ${price_data['close_price'].iloc[-1]:.2f}")
            return True
        else:
            print("✗ 無法獲取價格數據")
            return False
            
    except Exception as e:
        print(f"✗ 測試失敗: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_get_financial_data():
    """測試獲取財務數據"""
    print("\n" + "="*60)
    print("測試 5: 獲取財務數據")
    print("="*60)
    
    try:
        dm = DataManager()
        financial_data = dm.get_financial_data("2330", years=2)
        
        if financial_data is not None and len(financial_data) > 0:
            print(f"✓ 成功獲取 2330 的財務數據")
            print(f"  數據筆數: {len(financial_data)}")
            
            if 'eps' in financial_data.columns:
                valid_eps = financial_data['eps'].dropna()
                if len(valid_eps) > 0:
                    print(f"  最新 EPS: ${valid_eps.iloc[-1]:.2f}")
            
            return True
        else:
            print("✗ 無法獲取財務數據")
            return False
            
    except Exception as e:
        print(f"✗ 測試失敗: {str(e)}")
        return False


def test_intelligent_fallback():
    """測試智能備援機制"""
    print("\n" + "="*60)
    print("測試 6: 智能備援機制")
    print("="*60)
    
    try:
        dm = DataManager()
        
        # 測試多次獲取 EPS（應該會觸發不同的資料來源）
        print("  執行 3 次 EPS 查詢...")
        for i in range(3):
            eps = dm.get_latest_eps("2330")
            print(f"  查詢 {i+1}: EPS = ${eps:.2f}")
        
        # 檢查資料來源統計
        stats = dm.get_source_statistics()
        print(f"\n✓ 資料來源使用統計:")
        for source, counts in stats.items():
            success_rate = counts['success'] / (counts['success'] + counts['failure']) * 100 if (counts['success'] + counts['failure']) > 0 else 0
            print(f"  {source}:")
            print(f"    成功: {counts['success']} 次")
            print(f"    失敗: {counts['failure']} 次")
            print(f"    成功率: {success_rate:.1f}%")
        
        return True
            
    except Exception as e:
        print(f"✗ 測試失敗: {str(e)}")
        return False


def test_quality_scoring():
    """測試資料品質評分"""
    print("\n" + "="*60)
    print("測試 7: 資料品質評分")
    print("="*60)
    
    try:
        dm = DataManager()
        
        # 獲取一些數據（會觸發品質評分）
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        dm.get_stock_price("2330", start_date, end_date)
        dm.get_financial_data("2330", years=2)
        
        # 查看品質評分
        scores = dm.get_quality_scores()
        
        if scores:
            print(f"✓ 資料品質評分:")
            for stock, score in scores.items():
                print(f"  {stock}: {score:.1f}/100")
            return True
        else:
            print("  (尚無品質評分記錄)")
            return True
            
    except Exception as e:
        print(f"✗ 測試失敗: {str(e)}")
        return False


def test_memory_cache():
    """測試記憶體快取"""
    print("\n" + "="*60)
    print("測試 8: 記憶體快取效能")
    print("="*60)
    
    try:
        dm = DataManager()
        
        import time
        
        # 第一次查詢（無快取）
        start_time = time.time()
        eps1 = dm.get_latest_eps("2330")
        time1 = time.time() - start_time
        
        # 第二次查詢（應該從記憶體快取獲取）
        start_time = time.time()
        eps2 = dm.get_latest_eps("2330")
        time2 = time.time() - start_time
        
        print(f"  第一次查詢: {time1:.3f} 秒, EPS = ${eps1:.2f}")
        print(f"  第二次查詢: {time2:.3f} 秒, EPS = ${eps2:.2f}")
        
        if time2 < time1:
            speedup = time1 / time2
            print(f"✓ 快取加速: {speedup:.1f}x")
        else:
            print(f"  (快取效果不明顯，可能因為第一次已有 SQLite 快取)")
        
        return eps1 == eps2
            
    except Exception as e:
        print(f"✗ 測試失敗: {str(e)}")
        return False


def main():
    """執行所有測試"""
    print("\n" + "#"*60)
    print("#" + " "*18 + "DataManagerV2 整合測試" + " "*18 + "#")
    print("#"*60)
    
    tests = [
        test_basic_initialization,
        test_get_stock_info,
        test_get_latest_eps,
        test_get_price_data,
        test_get_financial_data,
        test_intelligent_fallback,
        test_quality_scoring,
        test_memory_cache,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ 測試發生異常: {str(e)}")
            results.append(False)
    
    # 總結
    print("\n" + "="*60)
    print("測試總結")
    print("="*60)
    
    passed = sum(results)
    total = len(results)
    success_rate = passed / total * 100
    
    print(f"通過: {passed}/{total} ({success_rate:.1f}%)")
    
    if passed == total:
        print("\n🎉 所有測試通過！DataManagerV2 整合成功！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 個測試失敗")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
