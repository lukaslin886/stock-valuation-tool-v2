"""
分析失敗股票的 EPS 獲取問題
測試 portfolio_analysis 中失敗的股票
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.data.manager import DataManagerV2
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

def test_failed_stocks():
    """測試失敗股票的 EPS 獲取"""
    
    # 從「未分析清單」中選擇代表性股票測試
    failed_stocks = [
        # ETF
        ("006208", "富邦台50"),
        ("00636", "國泰中國A50"),
        
        # 大型股
        ("3005", "神基"),
        ("3042", "晶技"),
        ("3481", "群創"),
        ("4938", "和碩"),
        
        # 中型股
        ("2732", "六角"),
        ("2758", "路易莎咖啡"),
        ("3030", "德律"),
        ("3443", "創意"),
        
        # 小型股
        ("1259", "安心"),
        ("3033", "威健"),
        ("3090", "日電貿"),
        ("4104", "佳醫"),
    ]
    
    print("=" * 80)
    print("失敗股票 EPS 獲取測試")
    print("=" * 80)
    print(f"\n測試股票數量：{len(failed_stocks)}\n")
    
    # 初始化 DataManager
    finmind_token = os.getenv("FINMIND_TOKEN")
    data_manager = DataManagerV2(
        db_path="data/cache.db",
        finmind_token=finmind_token
    )
    
    results = {
        'success': [],
        'failed': [],
        'etf': []
    }
    
    for stock_code, stock_name in failed_stocks:
        print(f"\n{'='*80}")
        print(f"測試股票：{stock_code} {stock_name}")
        print(f"{'='*80}")
        
        # 判斷是否為 ETF
        is_etf = stock_code.startswith('00')
        if is_etf:
            print(f"⚠️  {stock_code} 是 ETF，不適用 EPS 分析")
            results['etf'].append((stock_code, stock_name))
            continue
        
        # 1. 測試 get_latest_eps
        print(f"\n1️⃣ 測試 get_latest_eps()...")
        eps = data_manager.get_latest_eps(stock_code)
        print(f"   結果：EPS = {eps}")
        
        # 2. 測試 get_financial_data
        print(f"\n2️⃣ 測試 get_financial_data()...")
        financial_data = data_manager.get_financial_data(stock_code, years=2)
        if financial_data is not None and len(financial_data) > 0:
            print(f"   結果：獲取到 {len(financial_data)} 筆財務數據")
            if 'eps' in financial_data.columns:
                eps_values = financial_data['eps'].dropna()
                print(f"   EPS 數據：{list(eps_values.head())}")
            else:
                print(f"   ⚠️  財務數據中沒有 'eps' 欄位")
                print(f"   可用欄位：{list(financial_data.columns)}")
        else:
            print(f"   ✗ 無法獲取財務數據")
        
        # 3. 測試 get_stock_info
        print(f"\n3️⃣ 測試 get_stock_info()...")
        info = data_manager.get_stock_info(stock_code)
        if info:
            print(f"   結果：成功獲取股票資訊")
            print(f"   名稱：{info.get('name', 'N/A')}")
        else:
            print(f"   ✗ 無法獲取股票資訊")
        
        # 4. 統計結果
        if eps and eps > 0:
            print(f"\n✅ {stock_code} {stock_name}：成功獲取 EPS = {eps}")
            results['success'].append((stock_code, stock_name, eps))
        else:
            print(f"\n❌ {stock_code} {stock_name}：失敗（EPS = {eps}）")
            results['failed'].append((stock_code, stock_name))
        
        # 5. 查看資料來源統計
        print(f"\n4️⃣ 資料來源使用統計：")
        stats = data_manager.get_source_statistics()
        for source, stat in stats.items():
            success_rate = stat['success'] / (stat['success'] + stat['failure']) * 100 if (stat['success'] + stat['failure']) > 0 else 0
            print(f"   {source}: 成功 {stat['success']}, 失敗 {stat['failure']}, 成功率 {success_rate:.1f}%")
    
    # 最終統計
    print(f"\n\n{'='*80}")
    print("最終統計結果")
    print(f"{'='*80}")
    print(f"總測試數：{len(failed_stocks)}")
    print(f"ETF（排除）：{len(results['etf'])} 支")
    print(f"有效測試：{len(failed_stocks) - len(results['etf'])} 支")
    print(f"成功獲取：{len(results['success'])} 支")
    print(f"失敗：{len(results['failed'])} 支")
    
    success_rate = len(results['success']) / (len(failed_stocks) - len(results['etf'])) * 100 if (len(failed_stocks) - len(results['etf'])) > 0 else 0
    print(f"成功率：{success_rate:.1f}%")
    
    print(f"\n✅ 成功的股票：")
    for stock_code, stock_name, eps in results['success']:
        print(f"   {stock_code} {stock_name}: EPS = {eps}")
    
    print(f"\n❌ 失敗的股票：")
    for stock_code, stock_name in results['failed']:
        print(f"   {stock_code} {stock_name}")
    
    print(f"\n⚠️  ETF（不適用）：")
    for stock_code, stock_name in results['etf']:
        print(f"   {stock_code} {stock_name}")
    
    # 分析失敗原因
    print(f"\n{'='*80}")
    print("失敗原因分析")
    print(f"{'='*80}")
    
    if len(results['failed']) > 0:
        print("\n可能的失敗原因：")
        print("1. FinMind 免費版限制（最可能）")
        print("   - 部分股票資料不完整")
        print("   - API 請求頻率限制")
        print("   - 某些財報欄位無法存取")
        print("\n2. YFinance 覆蓋不足")
        print("   - 台股小型股資料較少")
        print("   - 特定產業股票缺漏")
        print("\n3. 股票特殊狀況")
        print("   - 新上市/上櫃（歷史數據不足）")
        print("   - 長期虧損（無正 EPS）")
        print("   - 停牌或下市")
    
    # 建議解決方案
    print(f"\n{'='*80}")
    print("建議解決方案")
    print(f"{'='*80}")
    
    failure_rate = len(results['failed']) / (len(failed_stocks) - len(results['etf'])) * 100 if (len(failed_stocks) - len(results['etf'])) > 0 else 0
    
    if failure_rate > 50:
        print("\n🔴 高失敗率（>50%）：建議採用混合策略")
        print("\n推薦方案：**方案 C - JoJoTrading 混合策略**")
        print("理由：")
        print("- 失敗率過高，單純升級 FinMind 可能不足")
        print("- 需要整合多個資料來源")
        print("- 參考 JoJoTrading 成功經驗")
        print("\n實作步驟：")
        print("1. 升級 FinMind 付費版（改善主要資料源）")
        print("2. 保持 YFinance 備援")
        print("3. 整合 MOPS 股本異動表（精確流通股數）")
        print("4. 建立更完善的預設 EPS 字典")
    elif failure_rate > 20:
        print("\n🟡 中等失敗率（20-50%）：建議升級 API 或實作 XBRL")
        print("\n選項 1：**方案 A - 升級 FinMind 付費版**")
        print("- 快速：1天內完成")
        print("- 成本：$300-500/月")
        print("- 預期改善：+15-20%")
        print("\n選項 2：**方案 B - 實作 XBRL 解析**")
        print("- 時間：10-14天")
        print("- 成本：免費")
        print("- 預期改善：+20-25%")
        print("- 100% 覆蓋所有上市櫃公司")
    else:
        print("\n🟢 低失敗率（<20%）：擴充預設值即可")
        print("\n推薦：**擴充 DEFAULT_EPS 字典**")
        print("- 將失敗的股票加入預設 EPS 字典")
        print("- 從財報手動查詢 EPS")
        print("- 快速且免費")

if __name__ == "__main__":
    test_failed_stocks()
