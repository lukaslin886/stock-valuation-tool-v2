"""
測試腳本：查詢 FinLab 正確的欄位名稱
"""

import finlab
from finlab import data
import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 登入 FinLab
token = os.getenv('FINLAB_API_TOKEN')
if not token:
    print("錯誤：未找到 FINLAB_API_TOKEN")
    exit(1)

try:
    finlab.login(token)
    print("✓ FinLab 登入成功\n")
except Exception as e:
    print(f"✗ FinLab 登入失敗: {str(e)}")
    exit(1)

# 查詢各項財務指標
print("=" * 60)
print("查詢財務指標欄位名稱")
print("=" * 60)

keywords = [
    ('eps', 'EPS/每股盈餘'),
    ('每股盈餘', 'EPS'),
    ('營業收入', '營收'),
    ('營收', '營業收入'),
    ('本期淨利', '淨利'),
    ('淨利', '本期淨利'),
    ('股東權益報酬率', 'ROE'),
    ('roe', 'ROE'),
    ('負債比', '負債比率'),
]

for keyword, description in keywords:
    print(f"\n搜尋關鍵字: '{keyword}' ({description})")
    print("-" * 60)
    try:
        results = data.search(keyword=keyword, display_info=['name', 'description', 'items'])
        if results:
            for result in results:
                print(f"資料集: {result['name']}")
                print(f"描述: {result['description']}")
                if 'items' in result and result['items']:
                    print("欄位:")
                    for field_name, field_info in result['items'].items():
                        print(f"  - {field_name}: {field_info.get('description', 'N/A')}")
        else:
            print(f"  未找到包含 '{keyword}' 的欄位")
    except Exception as e:
        print(f"  查詢失敗: {str(e)}")

# 查詢價格相關資料
print("\n" + "=" * 60)
print("查詢價格資料欄位")
print("=" * 60)

price_keywords = ['收盤價', '開盤價', '最高價', '最低價', '成交股數']

for keyword in price_keywords:
    print(f"\n搜尋: '{keyword}'")
    print("-" * 60)
    try:
        results = data.search(keyword=keyword, display_info=['name', 'items'])
        if results:
            for result in results:
                print(f"資料集: {result['name']}")
                if 'items' in result and result['items']:
                    for field_name in result['items'].keys():
                        if keyword in field_name:
                            print(f"  - 完整欄位名: {field_name}")
        else:
            print(f"  未找到")
    except Exception as e:
        print(f"  查詢失敗: {str(e)}")

print("\n" + "=" * 60)
print("測試完成")
print("=" * 60)
