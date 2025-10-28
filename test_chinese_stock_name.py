"""
測試中文股票名稱查詢功能
"""

from app.data import DataManager

def test_chinese_stock_name():
    """測試中文股票名稱輸入"""
    
    print("=== 測試中文股票名稱查詢 ===\n")
    
    # 初始化 DataManager
    dm = DataManager()
    
    # 測試案例
    test_cases = [
        "台塑",      # 1301
        "台積電",    # 2330
        "鴻海",      # 2317
        "2330",      # 直接輸入代碼
        "1301",      # 直接輸入代碼
    ]
    
    for test_input in test_cases:
        print(f"測試輸入: {test_input}")
        result = dm.normalize_stock_input(test_input)
        
        if result['is_valid']:
            print(f"  ✓ 成功")
            print(f"    股票代碼: {result['stock_code']}")
            print(f"    股票名稱: {result['stock_name']}")
            print(f"    顯示名稱: {result['display_name']}")
        else:
            print(f"  ✗ 失敗 - 無法識別")
        
        print()

if __name__ == "__main__":
    test_chinese_stock_name()
