"""
測試 FinLab 價格數據是否可用（免費版測試）
"""

import finlab
from finlab import data
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('FINLAB_API_TOKEN')
finlab.login(token)

print("=" * 60)
print("測試 FinLab 免費版可用資料")
print("=" * 60)

# 測試價格數據
print("\n測試：獲取價格數據 (price:收盤價)")
try:
    close_price = data.get('price:收盤價')
    print(f"✓ 成功獲取價格數據")
    print(f"  類型: {type(close_price)}")
    print(f"  Shape: {close_price.shape}")
    
    if '2330' in close_price.columns:
        print(f"  ✓ 包含 2330 資料")
        stock_2330 = close_price['2330']
        print(f"  最近5筆資料:")
        print(stock_2330.tail())
    else:
        print(f"  ✗ 不包含 2330")
        print(f"  前5個股票: {list(close_price.columns[:5])}")
        
except Exception as e:
    print(f"✗ 失敗: {str(e)}")

# 列出所有可用的資料集
print("\n" + "=" * 60)
print("查詢所有可用資料集")
print("=" * 60)

try:
    # 搜尋所有資料集
    all_datasets = data.search(keyword='.*', display_info=['name', 'description'])
    
    print(f"\n找到 {len(all_datasets)} 個資料集")
    print("\n可用的資料集：")
    for ds in all_datasets[:20]:  # 只顯示前20個
        print(f"  - {ds['name']}: {ds.get('description', 'N/A')}")
        
except Exception as e:
    print(f"查詢失敗: {str(e)}")

print("\n" + "=" * 60)
