"""
FinMind API 新手教學 Demo 程式
參考 stock-valuation-tool 專案的使用方式，展示如何使用 FinMind 獲取台股資料。

執行前請先確保已安裝 FinMind 套件:
pip install FinMind pandas

如果需要突破呼叫次數限制，可以去 FinMind 官網註冊並取得 API Token，
並設定環境變數 FINMIND_TOKEN。
"""

import os
from datetime import datetime, timedelta
import pandas as pd
from FinMind.data import DataLoader
from dotenv import load_dotenv

# 載入 .env 檔案中的環境變數
load_dotenv()

def main():
    print("=== FinMind API 新手教學 Demo ===\n")

    # 1. 初始化 DataLoader
    print("1. 初始化 DataLoader...")
    data_loader = DataLoader()
    
    # Optional: 如果有註冊 FinMind，可以使用 API Token 來提高呼叫限制
    api_token = os.getenv('FINMIND_TOKEN') #把相關的資料設定在.env檔案中，就可以不用每次輸入
    if api_token:
        print("   偵測到 FINMIND_TOKEN，正在登入...")
        data_loader.login_by_token(api_token=api_token)
    else:
        print("   未設定 FINMIND_TOKEN，使用未登入模式 (會有較低的使用次數限制)")
    
    # 測試用的股票代碼和日期範圍
    target_stock = "2330"  # 台積電
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)  # 取最近 30 天
    
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    print("\n------------------------------------------------------------\n")

    # 2. 獲取台股所有股票清單 (taiwan_stock_info)
    print(f"2. 獲取台股所有股票基本資訊...")
    try:
        stock_info_df = data_loader.taiwan_stock_info()
        print(f"   總共抓取到 {len(stock_info_df)} 筆股票資料。")
        
        # 尋找特定股票
        target_info = stock_info_df[stock_info_df['stock_id'] == target_stock]
        if not target_info.empty:
            name = target_info.iloc[0].get('stock_name', '未知')
            industry = target_info.iloc[0].get('industry', '未知')
            print(f"   找到股票 [{target_stock}] 的資訊:")
            print(f"    - 名稱: {name}")
            print(f"    - 產業別: {industry}")
    except Exception as e:
        print(f"   獲取股票清單失敗: {e}")

    print("\n------------------------------------------------------------\n")

    # 3. 獲取台股每日交易資料/股價 (taiwan_stock_daily)
    print(f"3. 獲取 [{target_stock}] 從 {start_date_str} 到 {end_date_str} 的每日股價...")
    try:
        price_df = data_loader.taiwan_stock_daily(
            stock_id=target_stock,
            start_date=start_date_str,
            end_date=end_date_str
        )
        if price_df is not None and not price_df.empty:
            print("   成功獲取股價資料，前 3 筆資料如下:")
            print(price_df[['date', 'open', 'max', 'min', 'close', 'Trading_Volume']].head(3).to_string(index=False))
            
            # 在 stock-valuation-tool 中，會將這些欄位標準化，例如：
            # df = pd.DataFrame({
            #     'date': pd.to_datetime(price_df['date']),
            #     'open_price': price_df['open'], ...
            # })
        else:
            print("   查無股價資料。")
    except Exception as e:
        print(f"   獲取股價失敗: {e}")

    print("\n------------------------------------------------------------\n")

    # 4. 獲取台股財務報表 (taiwan_stock_financial_statement)
    # 財報通常是一季一期，所以我們抓過去 2 年的資料
    financial_start_date = (end_date - timedelta(days=2 * 365)).strftime('%Y-%m-%d')
    print(f"4. 獲取 [{target_stock}] 從 {financial_start_date} 到 {end_date_str} 的財務報表...")
    try:
        financial_df = data_loader.taiwan_stock_financial_statement(
            stock_id=target_stock,
            start_date=financial_start_date,
            end_date=end_date_str
        )
        if financial_df is not None and not financial_df.empty:
            print(f"   成功獲取財報資料，總共 {len(financial_df)} 筆數據。")
            print("   注意：FinMind 返回的是「長格式」(type, value)，也就是每個指標獨立一行。")
            
            # 示範如何解析長格式資料（參考 stock-valuation-tool 專案的做法）
            print("\n   [進階解析] 示範將長格式轉為有用的寬格式 (例如提取 EPS, 營收, 淨利):")
            eps_types = ['EPS', 'BasicEarningsPerShare', '基本每股盈餘']
            revenue_types = ['Revenue', 'OperatingRevenue', '營業收入']
            
            # 以季為單位分組查看
            unique_dates = financial_df['date'].unique()
            print(f"   解析最近 3 季的重點財報指標:")
            for date in sorted(unique_dates, reverse=True)[:3]:
                date_data = financial_df[financial_df['date'] == date]
                
                # 抓取 EPS
                eps_data = date_data[date_data['type'].isin(eps_types)]
                eps_value = float(eps_data.iloc[0]['value']) if not eps_data.empty else 0.0
                
                # 抓取營收
                rev_data = date_data[date_data['type'].isin(revenue_types)]
                rev_value = float(rev_data.iloc[0]['value']) if not rev_data.empty else 0.0
                
                print(f"    - 財報日期: {date} | EPS: {eps_value:.2f} | 營收: {rev_value:,.0f}")
        else:
            print("   查無財報資料。")
    except Exception as e:
        print(f"   獲取財報失敗: {e}")

    print("\n------------------------------------------------------------\n")

    # 5. 其他實用功能：法人買賣超 (taiwan_stock_institutional_investors)
    print(f"5. 獲取 [{target_stock}] 從 {start_date_str} 到 {end_date_str} 的三大法人買賣超...")
    try:
        inst_df = data_loader.taiwan_stock_institutional_investors(
            stock_id=target_stock,
            start_date=start_date_str,
            end_date=end_date_str
        )
        if inst_df is not None and not inst_df.empty:
            print("   成功獲取三大法人資料返回結果:")
            print(inst_df[['date', 'name', 'buy', 'sell']].head(3).to_string(index=False))
        else:
            print("   查無三大法人資料。")
    except Exception as e:
        print(f"   獲取三大法人買賣超失敗: {e}")

    print("\n=== Demo 結束 ===")

if __name__ == "__main__":
    main()
