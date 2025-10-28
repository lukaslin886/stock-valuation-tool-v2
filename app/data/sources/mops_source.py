"""
MOPS (公開資訊觀測站) 資料來源 - 簡化版
僅提供輔助資料：股本異動、公司基本資料
財報數據交由 FinMind 處理

參考：JoJoTrading-main/data_fetching.py
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict
from io import StringIO
import time
import os
from pathlib import Path

from .base import DataSource


class MOPSSource(DataSource):
    """MOPS 資料來源實作（簡化版 - 僅提供輔助資料）"""
    
    # MOPS 網站 URL
    BASE_URL = "https://mops.twse.com.tw"
    
    def __init__(self, cache_dir: str = "data/cache/mops"):
        """初始化 MOPS 資料來源
        
        Args:
            cache_dir: 快取目錄路徑
        """
        super().__init__("MOPS")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    def _init_source(self) -> None:
        """初始化資料來源"""
        try:
            # 測試連線
            response = requests.get(
                self.BASE_URL,
                timeout=10,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            
            if response.status_code == 200:
                self.is_available = True
                print(f"✓ {self.name} 資料來源初始化成功")
            else:
                self.is_available = False
                print(f"✗ {self.name} 資料來源初始化失敗：HTTP {response.status_code}")
                
        except Exception as e:
            self.is_available = False
            print(f"✗ {self.name} 資料來源初始化失敗：{str(e)}")
    
    def _convert_roc_to_ad(self, roc_year: int, month: int = 1, day: int = 1) -> datetime:
        """
        將民國年轉換為西元年日期
        
        Args:
            roc_year: 民國年
            month: 月份
            day: 日
            
        Returns:
            datetime 物件
        """
        ad_year = roc_year + 1911
        return datetime(ad_year, month, day)
    
    def _convert_ad_to_roc(self, date: datetime) -> int:
        """
        將西元年轉換為民國年
        
        Args:
            date: datetime 物件
            
        Returns:
            民國年
        """
        return date.year - 1911
    
    def get_stock_price(
        self, 
        stock_code: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Optional[pd.DataFrame]:
        """
        獲取股價資料
        
        MOPS 不提供歷史股價 API
        
        Args:
            stock_code: 股票代碼
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            None（不支援此功能）
        """
        return None
    
    def get_financial_data(
        self,
        stock_code: str,
        years: int = 5
    ) -> Optional[pd.DataFrame]:
        """
        獲取財務報表資料
        
        簡化版 MOPS 不提供財報數據，交由 FinMind 處理
        
        Args:
            stock_code: 股票代碼
            years: 獲取最近幾年的資料
            
        Returns:
            None（不支援此功能，請使用 FinMind）
        """
        return None
    
    def get_latest_eps(self, stock_code: str) -> Optional[float]:
        """
        獲取最新 EPS
        
        簡化版 MOPS 不提供 EPS 數據
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            None（不支援此功能）
        """
        return None
    
    def get_shares_outstanding(
        self, 
        stock_code: str, 
        report_date: str
    ) -> Optional[int]:
        """
        獲取流通在外股數（從股本異動表）
        
        參考 JoJoTrading 的 get_shares_outstanding_from_twse_csv 實作
        
        Args:
            stock_code: 股票代碼
            report_date: 財報期末日期（YYYY-MM-DD）
            
        Returns:
            流通在外股數（整數）或 None
        """
        try:
            print(f"正在從 {self.name} 獲取 {stock_code} 的流通股數...")
            
            # 轉換日期
            dt = pd.to_datetime(report_date)
            
            # 下載股本異動表
            df = self._download_capital_change_csv(dt)
            
            if df is not None:
                # 尋找欄位
                code_col = None
                shares_col = None
                
                for col in df.columns:
                    if "公司代號" in col:
                        code_col = col
                    if "普通股股數" in col or "流通在外" in col:
                        shares_col = col
                
                if code_col and shares_col:
                    # 查找股票
                    row = df[df[code_col].astype(str) == str(stock_code)]
                    
                    if not row.empty:
                        so_str = str(row.iloc[0][shares_col]).replace(",", "")
                        so = int(float(so_str))
                        print(f"  ✓ {self.name} 獲取流通股數: {so:,}")
                        return so
            
            print(f"  ✗ 未找到 {stock_code} 的流通股數")
            return None
            
        except Exception as e:
            print(f"  ✗ {self.name} 獲取流通股數失敗：{str(e)}")
            return None
    
    def _download_capital_change_csv(
        self, 
        target_date: datetime
    ) -> Optional[pd.DataFrame]:
        """
        下載指定年月的股本異動彙總表（參考 JoJoTrading 實作）
        
        Args:
            target_date: 財報期末日期
            
        Returns:
            股本異動表 DataFrame 或 None
        """
        try:
            # 轉換為民國年
            minguo_year = target_date.year - 1911
            month = target_date.month
            
            # 檢查快取
            cache_file = self.cache_dir / f"capital_change_{minguo_year}_{month:02d}.csv"
            
            if cache_file.exists():
                try:
                    df = pd.read_csv(cache_file, encoding='utf-8')
                    if not df.empty:
                        print(f"  ✓ 從快取讀取股本異動表")
                        return df
                except Exception:
                    pass
            
            # 從 MOPS 下載
            url = f"{self.BASE_URL}/server-java/t05st10_ifrs"
            params = {
                'step': '1',
                'TYPEK': 'sii',  # sii=上市
                'year': str(minguo_year),
                'month': f"{month:02d}",
                'firstin': '1'
            }
            
            print(f"  正在下載 {minguo_year}年{month}月 股本異動表...")
            
            response = requests.get(
                url,
                params=params,
                timeout=20,
                verify=False,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            
            # 處理編碼（參考 JoJoTrading）
            response.encoding = 'utf-8'
            content = response.content.decode('utf-8', errors='ignore')
            
            # 自動偵測資料起始行（參考 JoJoTrading）
            lines = content.splitlines()
            header_idx = None
            
            for idx, line in enumerate(lines):
                if "公司代號" in line and "普通股股數" in line:
                    header_idx = idx
                    break
            
            if header_idx is not None:
                # 從標題行開始解析 CSV
                csv_content = "\n".join(lines[header_idx:])
                df = pd.read_csv(StringIO(csv_content), encoding='utf-8')
                
                # 儲存到快取
                df.to_csv(cache_file, index=False, encoding='utf-8')
                print(f"  ✓ 成功下載並快取股本異動表")
                
                return df
            else:
                print(f"  ✗ 無法在回應中找到股本異動表標題")
                return None
                
        except Exception as e:
            print(f"  ✗ 下載股本異動表失敗：{str(e)}")
            return None
    
    def get_stock_info(self, stock_code: str) -> Optional[Dict]:
        """
        獲取股票基本資訊
        
        從 MOPS 獲取公司基本資料
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            包含股票資訊的字典或 None
        """
        try:
            print(f"正在從 {self.name} 獲取 {stock_code} 的基本資訊...")
            
            # 檢查快取
            cache_file = self.cache_dir / f"info_{stock_code}.csv"
            
            if cache_file.exists():
                try:
                    # 檢查快取是否過期（7天）
                    file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
                    if datetime.now() - file_time < timedelta(days=7):
                        df = pd.read_csv(cache_file, encoding='utf-8')
                        if not df.empty:
                            print(f"  ✓ 從快取讀取公司資訊")
                            return df.iloc[0].to_dict()
                except Exception:
                    pass
            
            # MOPS 公司基本資料 API
            url = f"{self.BASE_URL}/server-java/t05st03"
            
            params = {
                'step': '1',
                'firstin': '1',
                'co_id': stock_code
            }
            
            response = requests.post(
                url,
                data=params,
                timeout=15,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                verify=False
            )
            
            # 處理編碼
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                print(f"  ✗ 請求失敗：HTTP {response.status_code}")
                return None
            
            # 解析 HTML 回應
            content = response.content.decode('utf-8', errors='ignore')
            info = self._parse_company_info_html(content, stock_code)
            
            if info:
                # 儲存到快取
                df_info = pd.DataFrame([info])
                df_info.to_csv(cache_file, index=False, encoding='utf-8')
                
                print(f"  ✓ 成功獲取公司資訊")
                return info
            else:
                print(f"  ✗ 解析公司資訊失敗")
                return None
                
        except Exception as e:
            print(f"  ✗ 獲取公司資訊失敗：{str(e)}")
            return None
    
    def _parse_company_info_html(self, html: str, stock_code: str) -> Optional[Dict]:
        """
        解析公司基本資訊 HTML
        
        Args:
            html: HTML 內容
            stock_code: 股票代碼
            
        Returns:
            公司資訊字典或 None
        """
        try:
            # 使用自動偵測標題行的方式
            lines = html.splitlines()
            header_idx = None
            
            # 尋找包含「公司代號」或「公司名稱」的標題行
            for idx, line in enumerate(lines):
                if "公司代號" in line and "公司名稱" in line:
                    header_idx = idx
                    break
            
            if header_idx is not None:
                csv_content = "\n".join(lines[header_idx:])
                
                try:
                    df = pd.read_csv(StringIO(csv_content), encoding='utf-8')
                    
                    if not df.empty:
                        # 嘗試從 DataFrame 提取資訊
                        row = df[df['公司代號'].astype(str) == str(stock_code)]
                        
                        if not row.empty:
                            info = {
                                'stock_code': stock_code,
                                'stock_name': str(row.iloc[0].get('公司名稱', '')) if '公司名稱' in row.columns else '',
                                'industry': str(row.iloc[0].get('產業別', '')) if '產業別' in row.columns else '',
                                'market': 'TWSE'
                            }
                            return info
                            
                except Exception as e:
                    print(f"  ⚠️ 解析公司資訊 CSV 失敗: {str(e)}")
            
            # 如果上述方法失敗，嘗試使用 pd.read_html
            try:
                tables = pd.read_html(StringIO(html))
                if tables:
                    for table in tables:
                        if '公司代號' in table.columns:
                            row = table[table['公司代號'].astype(str) == str(stock_code)]
                            if not row.empty:
                                info = {
                                    'stock_code': stock_code,
                                    'stock_name': str(row.iloc[0].get('公司名稱', '')) if '公司名稱' in row.columns else '',
                                    'industry': str(row.iloc[0].get('產業別', '')) if '產業別' in row.columns else '',
                                    'market': 'TWSE'
                                }
                                return info
            except Exception:
                pass
            
            # 返回基本結構
            return {
                'stock_code': stock_code,
                'stock_name': '',
                'industry': '',
                'market': 'TWSE'
            }
            
        except Exception as e:
            print(f"  ⚠️ 解析公司資訊失敗：{str(e)}")
            return None
    
    def get_all_stocks(self) -> Optional[pd.DataFrame]:
        """
        獲取所有股票清單
        
        簡化版 MOPS 不提供此功能
        
        Returns:
            None（不支援此功能）
        """
        print(f"⚠️ {self.name} 簡化版不提供股票清單功能")
        return None
