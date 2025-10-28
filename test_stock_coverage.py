"""
測試 50 檔重要股票的資料覆蓋率

測試項目：
- EPS 資料獲取
- 股價資料獲取
- 財務數據獲取
- 資料品質評分
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 添加 app 目錄到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from data.manager import DataManagerV2

# 測試股票清單（前50大市值）
TEST_STOCKS = [
    ('2330', '台積電'),
    ('2317', '鴻海'),
    ('2454', '聯發科'),
    ('2412', '中華電'),
    ('2882', '國泰金'),
    ('2881', '富邦金'),
    ('2886', '兆豐金'),
    ('2892', '第一金'),
    ('2891', '中信金'),
    ('2883', '開發金'),
    ('1301', '台塑'),
    ('1303', '南亞'),
    ('1326', '台化'),
    ('2308', '台達電'),
    ('2002', '中鋼'),
    ('2603', '長榮'),
    ('2609', '陽明'),
    ('2615', '萬海'),
    ('3008', '大立光'),
    ('2357', '華碩'),
    ('2382', '廣達'),
    ('2395', '研華'),
    ('3711', '日月光投控'),
    ('6505', '台塑化'),
    ('2345', '智邦'),
    ('2884', '玉山金'),
    ('5880', '合庫金'),
    ('2890', '永豐金'),
    ('2912', '統一超'),
    ('2887', '台新金'),
    ('1216', '統一'),
    ('2379', '瑞昱'),
    ('2301', '光寶科'),
    ('3045', '台灣大'),
    ('2327', '國巨'),
    ('2303', '聯電'),
    ('6669', '緯穎'),
    ('3034', '聯詠'),
    ('2408', '南亞科'),
    ('2409', '友達'),
    ('2324', '仁寶'),
    ('2049', '上銀'),
    ('2207', '和泰車'),
    ('2885', '元大金'),
    ('2376', '技嘉'),
    ('3231', '緯創'),
    ('2474', '可成'),
    ('2356', '英業達'),
    ('2377', '微星'),
    ('2201', '裕隆'),
]


def test_stock_data_coverage():
    """測試股票資料覆蓋率"""
    
    print("=" * 80)
    print("台股 DCF 估值工具 - 資料覆蓋率測試")
    print("=" * 80)
    print(f"測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"測試股票數量: {len(TEST_STOCKS)} 檔\n")
    
    # 初始化資料管理器
    finmind_token = os.getenv('FINMIND_TOKEN')
    manager = DataManagerV2(finmind_token=finmind_token)
    
    # 測試結果統計
    results = {
        'eps': {'success': 0, 'failed': 0, 'default': 0},
        'price': {'success': 0, 'failed': 0},
        'financial': {'success': 0, 'failed': 0}
    }
    
    # 失敗清單
    failures = {
        'eps': [],
        'price': [],
        'financial': []
    }
    
    # 測試每一檔股票
    for i, (code, name) in enumerate(TEST_STOCKS, 1):
        print(f"\n[{i}/{len(TEST_STOCKS)}] 測試 {code} {name}")
        print("-" * 80)
        
        # 測試 1: EPS 獲取
        try:
            eps = manager.get_latest_eps(code)
            if eps > 0:
                results['eps']['success'] += 1
                # 檢查是否使用預設值
                if code in manager.DEFAULT_EPS and abs(eps - manager.DEFAULT_EPS[code]) < 0.01:
                    results['eps']['default'] += 1
                    print(f"  ✓ EPS: {eps:.2f} (使用預設值)")
                else:
                    print(f"  ✓ EPS: {eps:.2f}")
            else:
                results['eps']['failed'] += 1
                failures['eps'].append((code, name))
                print(f"  ✗ EPS: 無法獲取")
        except Exception as e:
            results['eps']['failed'] += 1
            failures['eps'].append((code, name))
            print(f"  ✗ EPS: 錯誤 - {str(e)}")
        
        # 測試 2: 股價獲取
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            price_data = manager.get_stock_price(code, start_date, end_date)
            
            if price_data is not None and len(price_data) > 0:
                results['price']['success'] += 1
                latest_price = price_data['close_price'].iloc[-1]
                print(f"  ✓ 股價: {latest_price:.2f} ({len(price_data)} 筆資料)")
            else:
                results['price']['failed'] += 1
                failures['price'].append((code, name))
                print(f"  ✗ 股價: 無法獲取")
        except Exception as e:
            results['price']['failed'] += 1
            failures['price'].append((code, name))
            print(f"  ✗ 股價: 錯誤 - {str(e)}")
        
        # 測試 3: 財務數據獲取
        try:
            financial_data = manager.get_financial_data(code, years=2)
            
            if financial_data is not None and len(financial_data) > 0:
                results['financial']['success'] += 1
                print(f"  ✓ 財務數據: {len(financial_data)} 筆資料")
            else:
                results['financial']['failed'] += 1
                failures['financial'].append((code, name))
                print(f"  ✗ 財務數據: 無法獲取")
        except Exception as e:
            results['financial']['failed'] += 1
            failures['financial'].append((code, name))
            print(f"  ✗ 財務數據: 錯誤 - {str(e)}")
    
    # 生成測試報告
    print("\n" + "=" * 80)
    print("測試結果摘要")
    print("=" * 80)
    
    total = len(TEST_STOCKS)
    
    # EPS 測試結果
    eps_rate = (results['eps']['success'] / total) * 100
    eps_default_rate = (results['eps']['default'] / results['eps']['success']) * 100 if results['eps']['success'] > 0 else 0
    print(f"\n1. EPS 資料獲取")
    print(f"   成功: {results['eps']['success']}/{total} ({eps_rate:.1f}%)")
    print(f"   失敗: {results['eps']['failed']}/{total}")
    print(f"   使用預設值: {results['eps']['default']}/{results['eps']['success']} ({eps_default_rate:.1f}%)")
    
    # 股價測試結果
    price_rate = (results['price']['success'] / total) * 100
    print(f"\n2. 股價資料獲取")
    print(f"   成功: {results['price']['success']}/{total} ({price_rate:.1f}%)")
    print(f"   失敗: {results['price']['failed']}/{total}")
    
    # 財務數據測試結果
    financial_rate = (results['financial']['success'] / total) * 100
    print(f"\n3. 財務數據獲取")
    print(f"   成功: {results['financial']['success']}/{total} ({financial_rate:.1f}%)")
    print(f"   失敗: {results['financial']['failed']}/{total}")
    
    # 整體評估
    avg_rate = (eps_rate + price_rate + financial_rate) / 3
    print(f"\n整體成功率: {avg_rate:.1f}%")
    
    # 顯示失敗項目
    if failures['eps']:
        print(f"\nEPS 獲取失敗的股票 ({len(failures['eps'])} 檔):")
        for code, name in failures['eps']:
            print(f"  - {code} {name}")
    
    if failures['price']:
        print(f"\n股價獲取失敗的股票 ({len(failures['price'])} 檔):")
        for code, name in failures['price']:
            print(f"  - {code} {name}")
    
    if failures['financial']:
        print(f"\n財務數據獲取失敗的股票 ({len(failures['financial'])} 檔):")
        for code, name in failures['financial']:
            print(f"  - {code} {name}")
    
    # 資料來源統計
    print("\n" + "=" * 80)
    print("資料來源使用統計")
    print("=" * 80)
    stats = manager.get_source_statistics()
    for source_name, stat in stats.items():
        total_attempts = stat['success'] + stat['failure']
        if total_attempts > 0:
            success_rate = (stat['success'] / total_attempts) * 100
            print(f"\n{source_name}:")
            print(f"  成功: {stat['success']} 次")
            print(f"  失敗: {stat['failure']} 次")
            print(f"  成功率: {success_rate:.1f}%")
    
    # 最終評級
    print("\n" + "=" * 80)
    print("最終評級")
    print("=" * 80)
    if avg_rate >= 90:
        grade = "A+ 優秀"
    elif avg_rate >= 80:
        grade = "A 良好"
    elif avg_rate >= 70:
        grade = "B 尚可"
    elif avg_rate >= 60:
        grade = "C 需改善"
    else:
        grade = "D 不及格"
    
    print(f"評級: {grade}")
    print(f"建議: ", end="")
    if avg_rate >= 90:
        print("資料覆蓋率優秀，系統運作正常。")
    elif avg_rate >= 70:
        print("資料覆蓋率良好，但部分股票可能需要關注。")
    else:
        print("資料覆蓋率需要改善，建議檢查資料來源設定。")
    
    print("\n" + "=" * 80)
    print(f"測試完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    return results


if __name__ == "__main__":
    try:
        test_stock_data_coverage()
    except KeyboardInterrupt:
        print("\n\n測試被用戶中斷")
    except Exception as e:
        print(f"\n\n測試過程發生錯誤: {str(e)}")
        import traceback
        traceback.print_exc()
