"""
測試 FinLab 資料結構
"""

import finlab
from finlab import data
import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 登入
token = os.getenv('FINLAB_API_TOKEN')
finlab.login(token)

print("=" * 60)
print("測試 FinLab 資料獲取方式")
print("=" * 60)

# 測試 1: 嘗試直接獲取 financial_statement
print("\n測試 1: 嘗試獲取 financial_statement")
try:
    financial_data = data.get('financial_statement')
    print(f"✓ 成功獲取 financial_statement")
    print(f"  類型: {type(financial_data)}")
    print(f"  Shape: {financial_data.shape if hasattr(financial_data, 'shape') else 'N/A'}")
    if hasattr(financial_data, 'columns'):
        print(f"  前5個欄位: {list(financial_data.columns[:5])}")
except Exception as e:
    print(f"✗ 失敗: {str(e)}")

# 測試 2: 嘗試獲取 fundamental_features
print("\n測試 2: 嘗試獲取 fundamental_features")
try:
    fundamental_data = data.get('fundamental_features')
    print(f"✓ 成功獲取 fundamental_features")
    print(f"  類型: {type(fundamental_data)}")
    print(f"  Shape: {fundamental_data.shape if hasattr(fundamental_data, 'shape') else 'N/A'}")
    
    # 檢查 2330 是否存在
    if hasattr(fundamental_data, 'columns'):
        if '2330' in fundamental_data.columns:
            print(f"  ✓ 找到 2330 資料")
            stock_data = fundamental_data['2330']
            print(f"  2330 資料類型: {type(stock_data)}")
            if hasattr(stock_data, 'columns'):
                print(f"  2330 可用欄位:")
                for col in ['每股盈餘', '歸屬母公司淨利', 'ROE稅後', '負債比率', '營收成長率']:
                    if col in stock_data.columns:
                        print(f"    ✓ {col}")
                    else:
                        print(f"    ✗ {col} (不存在)")
        else:
            print(f"  ✗ 2330 不在欄位中")
            print(f"  前5個股票: {list(fundamental_data.columns[:5])}")
except Exception as e:
    print(f"✗ 失敗: {str(e)}")
    import traceback
    traceback.print_exc()

# 測試 3: 搜尋包含 eps 或 每股盈餘 的所有資料集
print("\n測試 3: 搜尋 EPS 相關資料集")
try:
    eps_results = data.search(keyword='每股盈餘', display_info=None)
    if eps_results:
        for result in eps_results:
            if result['name'] not in ['us_fundamental', 'us_fundamental_ART']:  # 跳過美股
                print(f"\n資料集: {result['name']}")
                print(f"  描述: {result.get('description', 'N/A')}")
                
                # 嘗試獲取這個資料集
                try:
                    test_data = data.get(result['name'])
                    print(f"  ✓ 可以獲取")
                    print(f"  類型: {type(test_data)}")
                    if hasattr(test_data, 'shape'):
                        print(f"  Shape: {test_data.shape}")
                    if hasattr(test_data, 'columns') and '2330' in test_data.columns:
                        print(f"  ✓ 包含 2330 資料")
                        stock_2330 = test_data['2330']
                        if hasattr(stock_2330, 'columns'):
                            print(f"  2330 欄位: {list(stock_2330.columns[:10])}")
                except Exception as e:
                    print(f"  ✗ 無法獲取: {str(e)}")
except Exception as e:
    print(f"✗ 搜尋失敗: {str(e)}")

print("\n" + "=" * 60)
print("測試完成")
print("=" * 60)
