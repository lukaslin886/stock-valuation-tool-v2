"""
測試 get_all_stocks 功能
"""

from app.data import DataManager

def test_get_all_stocks():
    """測試獲取所有股票清單"""
    
    print("=== 測試獲取股票清單 ===\n")
    
    # 初始化 DataManager
    dm = DataManager()
    
    print("正在獲取股票清單...")
    all_stocks = dm.get_all_stocks()
    
    if all_stocks is None:
        print("✗ 獲取失敗 - 返回 None")
        return
    
    if len(all_stocks) == 0:
        print("✗ 獲取失敗 - 返回空列表")
        return
    
    print(f"✓ 成功獲取 {len(all_stocks)} 支股票")
    print(f"\n欄位名稱: {list(all_stocks.columns)}")
    
    # 顯示前 10 筆
    print("\n前 10 筆資料:")
    print(all_stocks.head(10))
    
    # 測試查找特定股票
    print("\n=== 測試查找特定股票 ===")
    test_names = ["台塑", "台積電", "鴻海"]
    
    for name in test_names:
        print(f"\n查找: {name}")
        if 'stock_name' in all_stocks.columns:
            matched = all_stocks[all_stocks['stock_name'] == name]
            if len(matched) > 0:
                print(f"  ✓ 找到: {matched.iloc[0]['stock_id']} - {matched.iloc[0]['stock_name']}")
            else:
                # 嘗試部分匹配
                matched = all_stocks[all_stocks['stock_name'].str.contains(name, na=False)]
                if len(matched) > 0:
                    print(f"  ✓ 部分匹配找到: {matched.iloc[0]['stock_id']} - {matched.iloc[0]['stock_name']}")
                else:
                    print(f"  ✗ 未找到")
        else:
            print(f"  ✗ 資料中沒有 'stock_name' 欄位")

if __name__ == "__main__":
    test_get_all_stocks()
