"""
FinMind API 權限檢查工具

測試項目：
1. Token 有效性驗證
2. 可用資料集檢查
3. 請求頻率限制測試
4. 歷史資料深度測試
5. 特殊限制檢查
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
import time

# 載入環境變數
load_dotenv()

# 添加 app 目錄到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

try:
    from FinMind.data import DataLoader
except ImportError:
    print("❌ 錯誤：請先安裝 FinMind 套件")
    print("執行：pip install FinMind")
    sys.exit(1)


class FinMindPermissionChecker:
    """FinMind API 權限檢查器"""
    
    def __init__(self, token: str = None):
        """
        初始化檢查器
        
        Args:
            token: FinMind API Token，若未提供則從環境變數讀取
        """
        self.token = token or os.getenv('FINMIND_TOKEN')
        if not self.token:
            print("⚠️  警告：未設定 FINMIND_TOKEN 環境變數")
            print("將使用免費版 API（有較多限制）")
        
        self.api = DataLoader()
        if self.token:
            self.api.login_by_token(api_token=self.token)
        
        self.results = {
            'token_valid': None,
            'available_datasets': [],
            'rate_limits': {},
            'data_depth': {},
            'restrictions': []
        }
    
    def check_token_validity(self) -> bool:
        """
        檢查 Token 是否有效
        
        Returns:
            Token 是否有效
        """
        print("\n" + "="*80)
        print("1. Token 有效性檢查")
        print("="*80)
        
        if not self.token:
            print("❌ 未提供 Token，使用免費版 API")
            self.results['token_valid'] = False
            return False
        
        try:
            # 嘗試獲取一筆簡單的數據來驗證 Token
            test_data = self.api.taiwan_stock_info()
            
            if test_data is not None and len(test_data) > 0:
                print(f"✅ Token 有效")
                print(f"   測試查詢成功，返回 {len(test_data)} 筆股票資訊")
                self.results['token_valid'] = True
                return True
            else:
                print("❌ Token 可能無效（無法獲取數據）")
                self.results['token_valid'] = False
                return False
                
        except Exception as e:
            print(f"❌ Token 驗證失敗: {str(e)}")
            self.results['token_valid'] = False
            return False
    
    def check_available_datasets(self) -> list:
        """
        檢查可用的資料集
        
        Returns:
            可用資料集列表
        """
        print("\n" + "="*80)
        print("2. 可用資料集檢查")
        print("="*80)
        
        # 測試常用的資料集
        datasets_to_test = {
            'taiwan_stock_info': '台股基本資訊',
            'taiwan_stock_price': '台股每日股價',
            'taiwan_stock_financial_statement': '台股財務報表',
            'taiwan_stock_per_pbr': '台股本益比、股價淨值比',
            'taiwan_stock_dividend': '台股股利政策表',
            'taiwan_stock_month_revenue': '台股月營收',
            'taiwan_stock_margin_purchase_short_sale': '台股融資融券',
            'taiwan_stock_holding_shares_per': '台股股權分散表',
        }
        
        available = []
        unavailable = []
        
        for dataset_name, description in datasets_to_test.items():
            try:
                print(f"\n測試：{description} ({dataset_name})")
                
                # 使用台積電(2330)作為測試股票
                if dataset_name == 'taiwan_stock_info':
                    data = self.api.taiwan_stock_info()
                elif dataset_name == 'taiwan_stock_price':
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=7)
                    data = self.api.taiwan_stock_daily(
                        stock_id='2330',
                        start_date=start_date.strftime('%Y-%m-%d'),
                        end_date=end_date.strftime('%Y-%m-%d')
                    )
                elif dataset_name == 'taiwan_stock_financial_statement':
                    data = self.api.taiwan_stock_financial_statement(
                        stock_id='2330',
                        date='2024-Q2'
                    )
                elif dataset_name == 'taiwan_stock_per_pbr':
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=30)
                    data = self.api.taiwan_stock_per_pbr(
                        stock_id='2330',
                        start_date=start_date.strftime('%Y-%m-%d'),
                        end_date=end_date.strftime('%Y-%m-%d')
                    )
                elif dataset_name == 'taiwan_stock_dividend':
                    data = self.api.taiwan_stock_dividend(stock_id='2330')
                elif dataset_name == 'taiwan_stock_month_revenue':
                    data = self.api.taiwan_stock_month_revenue(stock_id='2330')
                elif dataset_name == 'taiwan_stock_margin_purchase_short_sale':
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=30)
                    data = self.api.taiwan_stock_margin_purchase_short_sale(
                        stock_id='2330',
                        start_date=start_date.strftime('%Y-%m-%d'),
                        end_date=end_date.strftime('%Y-%m-%d')
                    )
                elif dataset_name == 'taiwan_stock_holding_shares_per':
                    data = self.api.taiwan_stock_holding_shares_per(
                        stock_id='2330',
                        date='2024-10-01'
                    )
                else:
                    continue
                
                if data is not None and len(data) > 0:
                    print(f"  ✅ 可用 - 返回 {len(data)} 筆資料")
                    available.append({
                        'name': dataset_name,
                        'description': description,
                        'sample_size': len(data)
                    })
                else:
                    print(f"  ⚠️  可能不可用或無資料")
                    unavailable.append({
                        'name': dataset_name,
                        'description': description,
                        'reason': '無資料返回'
                    })
                
                # 避免請求過快
                time.sleep(0.5)
                
            except Exception as e:
                error_msg = str(e)
                print(f"  ❌ 不可用 - {error_msg}")
                unavailable.append({
                    'name': dataset_name,
                    'description': description,
                    'reason': error_msg
                })
        
        self.results['available_datasets'] = available
        self.results['unavailable_datasets'] = unavailable
        
        print(f"\n總結：")
        print(f"  可用資料集: {len(available)}/{len(datasets_to_test)}")
        print(f"  不可用資料集: {len(unavailable)}/{len(datasets_to_test)}")
        
        return available
    
    def check_rate_limits(self) -> dict:
        """
        測試請求頻率限制
        
        Returns:
            頻率限制資訊
        """
        print("\n" + "="*80)
        print("3. 請求頻率限制測試")
        print("="*80)
        
        print("\n測試連續請求...")
        
        request_count = 10
        success_count = 0
        failed_count = 0
        start_time = time.time()
        
        for i in range(request_count):
            try:
                # 簡單的股票資訊查詢
                data = self.api.taiwan_stock_info()
                if data is not None and len(data) > 0:
                    success_count += 1
                    print(f"  請求 {i+1}/{request_count}: ✅ 成功")
                else:
                    failed_count += 1
                    print(f"  請求 {i+1}/{request_count}: ❌ 失敗（無資料）")
                
                # 短暫延遲
                time.sleep(0.2)
                
            except Exception as e:
                failed_count += 1
                print(f"  請求 {i+1}/{request_count}: ❌ 失敗 - {str(e)}")
                
                # 檢查是否為頻率限制錯誤
                if 'rate limit' in str(e).lower() or '429' in str(e):
                    print("  ⚠️  偵測到頻率限制錯誤")
                    break
        
        elapsed_time = time.time() - start_time
        
        rate_limits = {
            'test_requests': request_count,
            'successful': success_count,
            'failed': failed_count,
            'elapsed_time': f"{elapsed_time:.2f}秒",
            'avg_time_per_request': f"{elapsed_time/request_count:.2f}秒"
        }
        
        self.results['rate_limits'] = rate_limits
        
        print(f"\n測試結果：")
        print(f"  總請求數: {request_count}")
        print(f"  成功: {success_count}")
        print(f"  失敗: {failed_count}")
        print(f"  總耗時: {elapsed_time:.2f}秒")
        print(f"  平均每次請求: {elapsed_time/request_count:.2f}秒")
        
        if failed_count == 0:
            print("  ✅ 未遇到明顯的頻率限制")
        else:
            print("  ⚠️  可能存在頻率限制或其他問題")
        
        return rate_limits
    
    def check_historical_data_depth(self) -> dict:
        """
        測試歷史資料可追溯深度
        
        Returns:
            歷史資料深度資訊
        """
        print("\n" + "="*80)
        print("4. 歷史資料深度測試")
        print("="*80)
        
        test_stock = '2330'  # 台積電
        depth_results = {}
        
        # 測試不同年份的資料
        test_years = [1, 3, 5, 10]
        
        for years in test_years:
            try:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=years*365)
                
                print(f"\n測試 {years} 年歷史資料...")
                print(f"  期間: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
                
                data = self.api.taiwan_stock_daily(
                    stock_id=test_stock,
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d')
                )
                
                if data is not None and len(data) > 0:
                    actual_start = data['date'].min()
                    actual_end = data['date'].max()
                    print(f"  ✅ 成功獲取 {len(data)} 筆資料")
                    print(f"  實際範圍: {actual_start} ~ {actual_end}")
                    
                    depth_results[f'{years}年'] = {
                        'available': True,
                        'records': len(data),
                        'actual_start': str(actual_start),
                        'actual_end': str(actual_end)
                    }
                else:
                    print(f"  ❌ 無法獲取資料")
                    depth_results[f'{years}年'] = {
                        'available': False,
                        'records': 0
                    }
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"  ❌ 錯誤: {str(e)}")
                depth_results[f'{years}年'] = {
                    'available': False,
                    'error': str(e)
                }
        
        self.results['data_depth'] = depth_results
        
        return depth_results
    
    def generate_report(self) -> str:
        """
        生成完整的權限檢查報告
        
        Returns:
            Markdown 格式的報告
        """
        print("\n" + "="*80)
        print("生成權限報告")
        print("="*80)
        
        report = f"""# FinMind API 權限檢查報告

**檢查日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Token 狀態**: {'✅ 已設定' if self.token else '❌ 未設定（使用免費版）'}

---

## 1. Token 有效性

"""
        
        if self.results['token_valid']:
            report += "✅ **Token 有效且可正常使用**\n\n"
        elif self.results['token_valid'] is False:
            report += "❌ **Token 無效或未設定**\n\n"
            report += "建議：請檢查 `.env` 檔案中的 `FINMIND_TOKEN` 設定\n\n"
        else:
            report += "⚠️  **未進行測試**\n\n"
        
        report += "---\n\n## 2. 可用資料集\n\n"
        
        if self.results['available_datasets']:
            report += f"**可用**: {len(self.results['available_datasets'])} 個資料集\n\n"
            report += "| 資料集 | 說明 | 測試結果 |\n"
            report += "|--------|------|----------|\n"
            for ds in self.results['available_datasets']:
                report += f"| `{ds['name']}` | {ds['description']} | ✅ {ds['sample_size']} 筆 |\n"
            report += "\n"
        
        if self.results.get('unavailable_datasets'):
            report += f"\n**不可用**: {len(self.results['unavailable_datasets'])} 個資料集\n\n"
            report += "| 資料集 | 說明 | 原因 |\n"
            report += "|--------|------|------|\n"
            for ds in self.results['unavailable_datasets']:
                report += f"| `{ds['name']}` | {ds['description']} | ❌ {ds['reason']} |\n"
            report += "\n"
        
        report += "---\n\n## 3. 請求頻率限制\n\n"
        
        if self.results['rate_limits']:
            rl = self.results['rate_limits']
            report += f"**測試結果**:\n"
            report += f"- 總請求數: {rl['test_requests']}\n"
            report += f"- 成功: {rl['successful']}\n"
            report += f"- 失敗: {rl['failed']}\n"
            report += f"- 總耗時: {rl['elapsed_time']}\n"
            report += f"- 平均每次: {rl['avg_time_per_request']}\n\n"
            
            if rl['failed'] == 0:
                report += "✅ **未遇到明顯的頻率限制**\n\n"
            else:
                report += "⚠️  **可能存在頻率限制**\n\n"
                report += "建議：請求之間適當延遲（建議 0.5-1 秒）\n\n"
        
        report += "---\n\n## 4. 歷史資料深度\n\n"
        
        if self.results['data_depth']:
            report += "| 時間範圍 | 狀態 | 筆數 | 實際範圍 |\n"
            report += "|----------|------|------|----------|\n"
            for period, info in self.results['data_depth'].items():
                if info['available']:
                    start = info.get('actual_start', 'N/A')
                    end = info.get('actual_end', 'N/A')
                    report += f"| {period} | ✅ 可用 | {info['records']} | {start} ~ {end} |\n"
                else:
                    error = info.get('error', '無資料')
                    report += f"| {period} | ❌ 不可用 | 0 | {error} |\n"
            report += "\n"
        
        report += "---\n\n## 5. 限制與建議\n\n"
        
        if not self.token:
            report += "### ⚠️  免費版限制\n\n"
            report += "- 請求頻率限制較嚴格\n"
            report += "- 某些進階資料集可能不可用\n"
            report += "- 歷史資料深度可能受限\n\n"
            report += "**建議**: 考慮升級到付費版以獲得更好的使用體驗\n\n"
        else:
            report += "### ✅ 付費版優勢\n\n"
            report += "- 更高的請求頻率限制\n"
            report += "- 完整的資料集存取\n"
            report += "- 更深的歷史資料\n\n"
        
        report += "### 💡 使用建議\n\n"
        report += "1. **快取策略**: 使用本地快取減少 API 請求\n"
        report += "2. **請求延遲**: 請求之間加入適當延遲（0.5-1秒）\n"
        report += "3. **錯誤處理**: 實作完整的錯誤處理與重試機制\n"
        report += "4. **備援方案**: 考慮整合其他資料源（如 yfinance）\n\n"
        
        report += "---\n\n"
        report += f"**報告生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        return report
    
    def run_all_checks(self) -> str:
        """
        執行所有檢查並生成報告
        
        Returns:
            完整報告（Markdown 格式）
        """
        print("\n" + "="*80)
        print("FinMind API 權限完整檢查")
        print("="*80)
        print(f"開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. Token 有效性
        self.check_token_validity()
        
        # 2. 可用資料集
        self.check_available_datasets()
        
        # 3. 頻率限制
        self.check_rate_limits()
        
        # 4. 歷史資料深度
        self.check_historical_data_depth()
        
        # 5. 生成報告
        report = self.generate_report()
        
        print("\n" + "="*80)
        print("檢查完成！")
        print("="*80)
        
        return report


def main():
    """主程式"""
    
    # 建立檢查器
    checker = FinMindPermissionChecker()
    
    # 執行所有檢查
    report = checker.run_all_checks()
    
    # 儲存報告
    report_file = 'finmind_api_permissions_report.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ 報告已儲存至: {report_file}")
    print("\n" + "="*80)
    print("報告預覽:")
    print("="*80)
    print(report)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  檢查被使用者中斷")
    except Exception as e:
        print(f"\n\n❌ 檢查過程發生錯誤: {str(e)}")
        import traceback
        traceback.print_exc()
