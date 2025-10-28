"""
持股分析工具 - 主程式
自動分析持股並生成賣出建議報告
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from typing import Optional, Dict, List

# 確保可以導入 app 模組（從專案根目錄）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 從當前目錄導入重新命名的模組
from analyzer import StockAnalyzer
from report_generator import PortfolioReportGenerator


def find_latest_csv(folder_path: str = "MY_STOCK") -> Optional[Path]:
    """
    在指定資料夾中尋找最新的 CSV 檔案
    
    Args:
        folder_path: CSV 檔案所在資料夾路徑
        
    Returns:
        最新 CSV 檔案的 Path 物件，若找不到則返回 None
    """
    folder = Path(folder_path)
    
    if not folder.exists():
        print(f"[錯誤] 資料夾不存在: {folder_path}")
        print(f"[提示] 請建立 {folder_path} 資料夾並放入持股 CSV 檔案")
        return None
    
    # 尋找所有 CSV 檔案
    csv_files = list(folder.glob("*.csv"))
    
    if not csv_files:
        print(f"[錯誤] 在 {folder_path} 資料夾中找不到 CSV 檔案")
        print(f"[提示] 請將持股 CSV 檔案放入 {folder_path} 資料夾")
        return None
    
    # 按修改時間排序，取最新的
    latest_file = max(csv_files, key=lambda f: f.stat().st_mtime)
    
    return latest_file


def validate_csv_file(file_path: Path) -> bool:
    """
    驗證 CSV 檔案格式是否正確
    
    Args:
        file_path: CSV 檔案路徑
        
    Returns:
        True 表示格式正確，False 表示格式錯誤
    """
    try:
        # 讀取 CSV（指定編碼為 big5 或 utf-8-sig）
        try:
            df = pd.read_csv(file_path, encoding='big5')
        except:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
        
        # 檢查必要欄位
        required_columns = ['股票名稱', '股數', '成交均價', '市價', '報酬率']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"[錯誤] CSV 檔案缺少必要欄位: {', '.join(missing_columns)}")
            print(f"[提示] 請確認檔案格式是否正確")
            return False
        
        # 檢查是否有資料
        if len(df) == 0:
            print(f"[錯誤] CSV 檔案沒有資料")
            return False
        
        return True
        
    except Exception as e:
        print(f"[錯誤] 無法讀取 CSV 檔案: {str(e)}")
        return False


def check_data_freshness(file_path: Path) -> None:
    """
    檢查資料新鮮度並顯示警告
    
    Args:
        file_path: CSV 檔案路徑
    """
    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
    age_days = (datetime.now() - file_time).days
    
    if age_days > 7:
        print(f"[警告] 資料已有 {age_days} 天，可能不是最新的持股資訊")
        print(f"[提示] 建議從券商系統重新匯出最新的持股資料")
    elif age_days > 1:
        print(f"[提示] 資料更新時間：{age_days} 天前")


def load_holdings_data(file_path: Path) -> Optional[pd.DataFrame]:
    """
    載入持股資料
    
    Args:
        file_path: CSV 檔案路徑
        
    Returns:
        持股資料 DataFrame，若載入失敗則返回 None
    """
    try:
        # 嘗試不同編碼讀取
        try:
            df = pd.read_csv(file_path, encoding='big5')
        except:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
        
        # 清理報酬率欄位（移除百分比符號並轉換為數值）
        if '報酬率' in df.columns:
            df['報酬率'] = df['報酬率'].astype(str).str.replace('%', '').astype(float)
        
        # 清理數值欄位中的逗號
        numeric_columns = ['股數', '總損益', '成交均價', '市價', '現值', '付出成本', '預估損益']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '').astype(float)
        
        return df
        
    except Exception as e:
        print(f"[錯誤] 載入資料失敗: {str(e)}")
        return None


def print_statistics(stats: Dict) -> None:
    """
    顯示分析統計資訊
    
    Args:
        stats: 統計資料字典
    """
    print(f"\n[統計] 分析結果摘要：")
    print(f"  ├─ 總持股數：{stats.get('total_holdings', 0)} 支")
    print(f"  ├─ ETF（已排除）：{stats.get('etf_count', 0)} 支")
    print(f"  ├─ 保護名單：{stats.get('protected_count', 0)} 支")
    print(f"  ├─ 已分析：{stats.get('analyzed_count', 0)} 支")
    print(f"  ├─ 未分析：{stats.get('skipped_count', 0)} 支")
    print(f"  │")
    print(f"  ├─ 強烈建議賣出：{stats.get('strong_sell_count', 0)} 支")
    print(f"  ├─ 考慮賣出：{stats.get('consider_sell_count', 0)} 支")
    print(f"  └─ 建議續抱：{stats.get('hold_count', 0)} 支")


def main():
    """主程式入口"""
    
    print("\n" + "="*50)
    print("           持股分析工具 v1.0")
    print("="*50)
    
    # 步驟1：偵測 CSV 檔案
    print(f"\n[1/5] 正在偵測 CSV 檔案...")
    csv_file = find_latest_csv()
    
    if csv_file is None:
        print(f"\n[失敗] 無法找到 CSV 檔案")
        return 1
    
    print(f"✓ 找到檔案：{csv_file.name}")
    
    file_time = datetime.fromtimestamp(csv_file.stat().st_mtime)
    print(f"✓ 檔案時間：{file_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 檢查資料新鮮度
    check_data_freshness(csv_file)
    
    # 步驟2：驗證檔案格式
    print(f"\n[2/5] 正在驗證檔案格式...")
    if not validate_csv_file(csv_file):
        return 1
    print(f"✓ 檔案格式正確")
    
    # 步驟3：載入持股資料
    print(f"\n[3/5] 正在載入持股資料...")
    holdings_df = load_holdings_data(csv_file)
    
    if holdings_df is None:
        return 1
    
    print(f"✓ 成功載入 {len(holdings_df)} 筆持股資料")
    
    # 步驟4：執行分析
    print(f"\n[4/5] 正在執行持股分析...")
    print(f"[提示] 這可能需要 3-8 分鐘，請耐心等候...")
    print()
    
    try:
        analyzer = StockAnalyzer()
        analysis_results = analyzer.analyze_portfolio(holdings_df)
        
        if analysis_results is None:
            print(f"\n[錯誤] 分析過程失敗")
            return 1
        
        print(f"\n✓ 分析完成")
        
    except Exception as e:
        print(f"\n[錯誤] 分析過程發生錯誤: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 步驟5：生成報告
    print(f"\n[5/5] 正在生成 Excel 報告...")
    
    try:
        # 確保 reports 資料夾存在
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        
        # 生成報告
        report_gen = PortfolioReportGenerator()
        report_path = report_gen.generate_report(analysis_results, holdings_df)
        
        if report_path:
            print(f"✓ 報告已儲存：{report_path}")
        else:
            print(f"[錯誤] 報告生成失敗")
            return 1
        
    except Exception as e:
        print(f"\n[錯誤] 報告生成失敗: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 顯示統計資訊
    print_statistics(analysis_results.get('statistics', {}))
    
    print("\n" + "="*50)
    print("           分析完成！")
    print("="*50)
    print(f"\n[提示] 請開啟 {report_path} 查看詳細報告")
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
