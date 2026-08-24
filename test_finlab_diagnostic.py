import os
import pandas as pd
import finlab
from finlab import data
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any
from datetime import datetime

# 依照 _AI_Rules 規範，使用 Type Hints 與 Google Style Docstrings

def run_diagnostic(token: Optional[str] = None) -> None:
    """執行 FinLab 數據源深度診斷。
    ... (docstring truncated for brevity)
    """
    print("=" * 60)
    print(f"FinLab Deep Diagnostic Tool - Start Time: {datetime.now()}")
    print("=" * 60)

    # 1. 環境與配置檢查
    load_dotenv()
    api_token = token or os.getenv("FINLAB_API_TOKEN")
    
    if not api_token:
        print("ERROR: Cannot find FINLAB_API_TOKEN in .env file.")
        return

    print(f"Status: Logging into FinLab (Token prefix: {api_token[:10]}...)")

    try:
        finlab.login(api_token)
        print("Login Success!")
    except Exception as e:
        print(f"Login Failed: {e}")
        return

    # 2. 核心數據可用性檢查
    target_keys = [
        'price:收盤價',
        'fundamental_features:本益比',
        'fundamental_features:股價淨值比',
        'price:殖利率',
        'fundamental_features:股東權益報酬率',
        'internal:市值'
    ]

    print("\nData Table Access Test:")
    available_data = {}
    
    for key in target_keys:
        try:
            df = data.get(key)
            last_date = df.index[-1] if not df.empty else "N/A"
            cols_count = len(df.columns)
            print(f"  OK - [{key}]: Last Date={last_date}, Stocks={cols_count}")
            available_data[key] = df
        except Exception as e:
            print(f"  FAIL - [{key}]: {e}")

    # 3. 數據對齊分析 (Alignment Analysis)
    if 'price:收盤價' in available_data:
        print("\nAlignment Diagnosis:")
        close_df = available_data['price:收盤價']
        # 取得最後一筆有資料的收盤價
        last_prices = close_df.dropna(how='all').iloc[-1]
        master_index = last_prices.dropna().index
        print(f"  Master Index: {len(master_index)} stocks with price data")

        for key, df in available_data.items():
            if key == 'price:收盤價':
                continue
            
            # 取得該數據表的最後一行
            try:
                raw_series = df.dropna(how='all').iloc[-1]
                # 測試 reindex
                aligned = raw_series.reindex(master_index)
                valid_count = aligned.count() # 非 NaN 數量
                zero_count = (aligned == 0).sum()
                
                print(f"  Alignment Test [{key}]:")
                print(f"    - Raw Valid Data: {raw_series.count()} items")
                print(f"    - Aligned Valid Data: {valid_count} items (Overlap)")
                print(f"    - Aligned 0.0 Data: {zero_count} items")
                
                if valid_count == 0:
                    print(f"    WARNING: [{key}] does not match Price index!")
                    print(f"    - Raw Index Example: {raw_series.index[:3].tolist()}")
                    print(f"    - Master Index Example: {master_index[:3].tolist()}")
            except Exception as e:
                print(f"  Alignment Test [{key}] failed: {e}")

    # 4. 系統建議
    print("\nConclusion and Suggestions:")
    if len(available_data) < len(target_keys):
        print("  - Some fundamental tables are inaccessible. Check account tier.")
    else:
        print("  - Tables are accessible, but alignment might be failed if index dates differ too much.")
        print("  - Check if DataManager incorrectly fills NaN with 0.0.")

    print("\n" + "=" * 60)
    print("Diagnosis Finished")
    print("=" * 60)

if __name__ == "__main__":
    run_diagnostic()
