import finlab
import os
import pandas as pd
from dotenv import load_dotenv

def test_free_tier_paths():
    load_dotenv()
    token = os.getenv('FINLAB_API_TOKEN')
    finlab.login(token)
    from finlab import data
    
    print("--- Free Tier Path Discovery ---")
    
    # 嘗試不同的存取路徑
    test_paths = [
        'finlab_free_tw_stock_item/price',
        'finlab_free_tw_stock_item/fundamental_features',
        'price:close',  # 嘗試英文別名
        'fundamental_features:pe',
        'fundamental_features:roe'
    ]
    
    for path in test_paths:
        try:
            df = data.get(path)
            print(f"SUCCESS: {path} | Shape: {df.shape}")
        except Exception as e:
            # 擷取詳細錯誤訊息，看是否有暗示正確的 ID
            err_msg = str(e)
            print(f"FAILED: {path} | Error: {err_msg[:100]}")

if __name__ == "__main__":
    test_free_tier_paths()
