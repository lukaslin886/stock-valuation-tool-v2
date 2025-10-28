"""
測試模組化資料層架構
驗證新的資料來源和快取系統
"""

import sys
import os

# 加入 app 目錄到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from data import YFinanceSource, FinMindSource, SQLiteCache


def test_yfinance_source():
    """測試 YFinance 資料來源"""
    print("\n" + "="*60)
    print("測試 YFinance 資料來源")
    print("="*60)
    
    try:
        source = YFinanceSource()
        print(f"✓ YFinance 初始化: {source}")
        print(f"  狀態: {'可用' if source.is_ready() else '不可用'}")
        
        if source.is_ready():
            # 測試獲取 EPS
            print("\n測試獲取台積電 (2330) 的 EPS...")
            eps = source.get_latest_eps('2330')
            if eps:
                print(f"✓ EPS: {eps}")
            else:
                print("✗ 無法獲取 EPS")
            
            # 測試獲取股票資訊
            print("\n測試獲取股票資訊...")
            info = source.get_stock_info('2330')
            if info:
                print(f"✓ 股票資訊:")
                print(f"  代碼: {info['stock_code']}")
                print(f"  名稱: {info['stock_name']}")
                print(f"  產業: {info['industry']}")
            else:
                print("✗ 無法獲取股票資訊")
        
        return True
        
    except Exception as e:
        print(f"✗ YFinance 測試失敗: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_finmind_source():
    """測試 FinMind 資料來源"""
    print("\n" + "="*60)
    print("測試 FinMind 資料來源")
    print("="*60)
    
    try:
        source = FinMindSource()
        print(f"✓ FinMind 初始化: {source}")
        print(f"  狀態: {'可用' if source.is_ready() else '不可用'}")
        
        if source.is_ready():
            # 測試獲取股票資訊
            print("\n測試獲取股票資訊...")
            info = source.get_stock_info('2330')
            if info:
                print(f"✓ 股票資訊:")
                print(f"  代碼: {info['stock_code']}")
                print(f"  名稱: {info['stock_name']}")
            else:
                print("✗ 無法獲取股票資訊")
        
        return True
        
    except Exception as e:
        print(f"✗ FinMind 測試失敗: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_sqlite_cache():
    """測試 SQLite 快取"""
    print("\n" + "="*60)
    print("測試 SQLite 快取")
    print("="*60)
    
    try:
        cache = SQLiteCache('data/test_cache.db')
        print(f"✓ SQLite 快取初始化: {cache}")
        print(f"  狀態: {'可用' if cache.is_ready() else '不可用'}")
        
        if cache.is_ready():
            # 測試儲存股票資訊
            print("\n測試儲存股票資訊...")
            test_info = {
                'stock_code': '2330',
                'stock_name': '台積電',
                'industry': '半導體',
                'market': '上市'
            }
            result = cache.save_stock_info('2330', test_info)
            print(f"{'✓' if result else '✗'} 儲存結果: {result}")
            
            # 測試讀取股票資訊
            print("\n測試讀取股票資訊...")
            info = cache.get_stock_info('2330')
            if info:
                print(f"✓ 讀取成功:")
                print(f"  代碼: {info['stock_code']}")
                print(f"  名稱: {info['stock_name']}")
            else:
                print("✗ 無法讀取")
        
        return True
        
    except Exception as e:
        print(f"✗ SQLite 快取測試失敗: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """執行所有測試"""
    print("="*60)
    print("模組化資料層架構測試")
    print("="*60)
    
    results = {
        'YFinance': test_yfinance_source(),
        'FinMind': test_finmind_source(),
        'SQLite Cache': test_sqlite_cache()
    }
    
    print("\n" + "="*60)
    print("測試結果摘要")
    print("="*60)
    for name, result in results.items():
        status = "✓ 通過" if result else "✗ 失敗"
        print(f"{name}: {status}")
    
    all_passed = all(results.values())
    print(f"\n總體結果: {'✓ 全部通過' if all_passed else '✗ 部分失敗'}")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
