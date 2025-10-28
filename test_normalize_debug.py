"""
調試 normalize_stock_input 方法
"""

from app.data import DataManager

def test_normalize_debug():
    """調試測試"""
    
    print("=== 調試 normalize_stock_input ===\n")
    
    dm = DataManager()
    
    # 測試輸入
    test_input = "台塑"
    
    print(f"測試輸入: {test_input}")
    print(f"輸入類型: {type(test_input)}")
    print(f"是否為數字: {test_input.isdigit()}")
    
    # 手動獲取股票清單
    print("\n手動獲取股票清單...")
    all_stocks = dm.get_all_stocks()
    
    if all_stocks is None:
        print("✗ all_stocks is None")
    else:
        print(f"✓ 獲取到 {len(all_stocks)} 支股票")
        print(f"  欄位: {list(all_stocks.columns)}")
        
        # 嘗試查找
        if 'stock_name' in all_stocks.columns and 'stock_id' in all_stocks.columns:
            print(f"\n  ✓ 欄位名稱正確")
            matched = all_stocks[all_stocks['stock_name'] == test_input]
            print(f"  完全匹配結果: {len(matched)} 筆")
            
            if len(matched) > 0:
                print(f"  找到: {matched.iloc[0]['stock_id']} - {matched.iloc[0]['stock_name']}")
        else:
            print(f"\n  ✗ 欄位名稱不正確")
            print(f"  實際欄位: {list(all_stocks.columns)}")
    
    # 調用 normalize_stock_input
    print(f"\n調用 normalize_stock_input...")
    result = dm.normalize_stock_input(test_input)
    
    print(f"結果: {result}")

if __name__ == "__main__":
    test_normalize_debug()
