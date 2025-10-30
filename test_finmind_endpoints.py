"""
測試 FinMind 的不同 API endpoints
目標：找出能夠獲取失敗股票 EPS 的替代方法
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from FinMind.data import DataLoader
from dotenv import load_dotenv
from datetime import datetime, timedelta

# 載入環境變數
load_dotenv()

def test_finmind_endpoints():
    """
    測試 FinMind 的多個 dataset
    找出哪些可以提供 EPS 數據
    """
    
    # 初始化 FinMind
    api_token = os.getenv("FINMIND_TOKEN")
    if not api_token:
        print("❌ 錯誤：找不到 FINMIND_TOKEN")
        return
    
    dl = DataLoader()
    dl.login_by_token(api_token=api_token)
    print(f"✓ FinMind API Token 已載入\n")
    
    # 選擇測試股票（從失敗清單中選擇代表性股票）
    test_stocks = [
        ("3005", "神基"),
        ("3042", "晶技"),
        ("3481", "群創"),
        ("2732", "六角"),
        ("3443", "創意"),
    ]
    
    # 要測試的 datasets
    datasets_to_test = [
        {
            "name": "TaiwanStockFinancialStatements",
            "description": "綜合損益表（目前使用）",
            "method": "taiwan_stock_financial_statement",
            "date_required": True
        },
        {
            "name": "TaiwanStockBalanceSheet", 
            "description": "資產負債表",
            "method": "taiwan_stock_balance_sheet",
            "date_required": True
        },
        {
            "name": "TaiwanStockCashFlowsStatement",
            "description": "現金流量表",
            "method": "taiwan_stock_cash_flows_statement",
            "date_required": True
        },
        {
            "name": "TaiwanStockPER",
            "description": "本益比（含股價、EPS）",
            "method": "taiwan_stock_per",
            "date_required": True
        },
        {
            "name": "TaiwanStockDividend",
            "description": "股利資料",
            "method": "taiwan_stock_dividend",
            "date_required": False
        },
        {
            "name": "TaiwanStockMonthRevenue",
            "description": "月營收",
            "method": "taiwan_stock_month_revenue",
            "date_required": True
        },
    ]
    
    # 日期設定
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')  # 2年前
    
    print("=" * 80)
    print("FinMind API Endpoints 測試")
    print("=" * 80)
    print(f"測試期間：{start_date} ~ {end_date}\n")
    
    # 統計結果
    results = {stock[0]: {} for stock in test_stocks}
    
    # 測試每個股票
    for stock_code, stock_name in test_stocks:
        print(f"\n{'='*80}")
        print(f"測試股票：{stock_code} {stock_name}")
        print(f"{'='*80}")
        
        for dataset in datasets_to_test:
            dataset_name = dataset["name"]
            description = dataset["description"]
            method_name = dataset["method"]
            
            print(f"\n📊 測試 Dataset: {dataset_name}")
            print(f"   說明: {description}")
            
            try:
                # 根據不同的 dataset 調用不同的方法
                if dataset["date_required"]:
                    method = getattr(dl, method_name)
                    data = method(
                        stock_id=stock_code,
                        start_date=start_date,
                        end_date=end_date
                    )
                else:
                    method = getattr(dl, method_name)
                    data = method(stock_id=stock_code)
                
                if data is not None and len(data) > 0:
                    print(f"   ✓ 成功獲取 {len(data)} 筆資料")
                    print(f"   欄位: {list(data.columns)[:10]}")  # 只顯示前10個欄位
                    
                    # 檢查是否包含 EPS 相關欄位
                    eps_columns = [col for col in data.columns if 'eps' in col.lower() or '每股盈餘' in col.lower()]
                    if eps_columns:
                        print(f"   ⭐ 找到 EPS 欄位: {eps_columns}")
                        
                        # 顯示最新的 EPS 值
                        for col in eps_columns:
                            non_null_values = data[col].dropna()
                            if len(non_null_values) > 0:
                                latest_value = non_null_values.iloc[-1]
                                print(f"      {col} 最新值: {latest_value}")
                                results[stock_code][dataset_name] = {
                                    'success': True,
                                    'eps': float(latest_value),
                                    'column': col
                                }
                    else:
                        print(f"   ⚠️  未找到 EPS 欄位")
                        results[stock_code][dataset_name] = {
                            'success': True,
                            'eps': None,
                            'column': None
                        }
                    
                    # 顯示資料範例（前3筆）
                    print(f"   資料範例（前3筆）:")
                    print(data.head(3).to_string(index=False))
                    
                else:
                    print(f"   ✗ 返回空數據")
                    results[stock_code][dataset_name] = {
                        'success': False,
                        'eps': None,
                        'column': None
                    }
                    
            except AttributeError:
                print(f"   ✗ 方法不存在: {method_name}")
                results[stock_code][dataset_name] = {
                    'success': False,
                    'eps': None,
                    'column': None,
                    'error': 'Method not found'
                }
            except Exception as e:
                print(f"   ✗ 發生錯誤: {str(e)}")
                results[stock_code][dataset_name] = {
                    'success': False,
                    'eps': None,
                    'column': None,
                    'error': str(e)
                }
    
    # 總結報告
    print(f"\n\n{'='*80}")
    print("測試結果總結")
    print(f"{'='*80}\n")
    
    # 按 dataset 統計成功率
    print("📊 各 Dataset 成功率：\n")
    for dataset in datasets_to_test:
        dataset_name = dataset["name"]
        success_count = sum(1 for stock in test_stocks 
                          if results[stock[0]].get(dataset_name, {}).get('success', False))
        total = len(test_stocks)
        success_rate = success_count / total * 100
        
        eps_count = sum(1 for stock in test_stocks 
                       if results[stock[0]].get(dataset_name, {}).get('eps') is not None)
        
        status = "✅" if eps_count > 0 else "⚠️" if success_count > 0 else "❌"
        print(f"{status} {dataset_name:40} | 成功: {success_count}/{total} ({success_rate:.0f}%) | 有EPS: {eps_count}/{total}")
    
    # 按股票統計
    print(f"\n📈 各股票資料可用性：\n")
    for stock_code, stock_name in test_stocks:
        available_datasets = [ds for ds, result in results[stock_code].items() 
                            if result.get('eps') is not None]
        print(f"{stock_code} {stock_name:10} | 可用 datasets: {len(available_datasets)}/{len(datasets_to_test)}")
        if available_datasets:
            for ds in available_datasets:
                eps = results[stock_code][ds]['eps']
                print(f"   → {ds}: EPS = {eps}")
    
    # 建議
    print(f"\n{'='*80}")
    print("💡 建議與結論")
    print(f"{'='*80}\n")
    
    # 找出最有效的 dataset
    best_datasets = []
    for dataset in datasets_to_test:
        dataset_name = dataset["name"]
        eps_count = sum(1 for stock in test_stocks 
                       if results[stock[0]].get(dataset_name, {}).get('eps') is not None)
        if eps_count > 0:
            best_datasets.append((dataset_name, eps_count, dataset["description"]))
    
    if best_datasets:
        best_datasets.sort(key=lambda x: x[1], reverse=True)
        print("✅ 發現可用的替代 Dataset：\n")
        for ds_name, count, desc in best_datasets:
            success_rate = count / len(test_stocks) * 100
            print(f"   {ds_name}")
            print(f"   說明：{desc}")
            print(f"   成功率：{count}/{len(test_stocks)} ({success_rate:.0f}%)")
            print()
        
        print("📝 建議行動：")
        print(f"1. 修改 FinMindSource 優先使用 '{best_datasets[0][0]}'")
        print(f"2. 建立多重備援機制（依序嘗試多個 datasets）")
        print(f"3. 預期可解決 {best_datasets[0][1]}/{len(test_stocks)} 的測試股票問題")
    else:
        print("❌ 所有測試的 FinMind datasets 都無法獲取 EPS")
        print("\n📝 建議行動：")
        print("1. FinMind 免費版無法解決此問題")
        print("2. 需要執行 Phase 2：建立 CSV 資料庫")
        print("3. 或考慮 Phase 3：整合 MOPS 資料源")
    
    return results


if __name__ == "__main__":
    print("\n🔍 開始測試 FinMind 的不同 API endpoints...\n")
    results = test_finmind_endpoints()
    print("\n✓ 測試完成！\n")
