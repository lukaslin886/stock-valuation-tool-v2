"""
DataManagerV2 - 新一代統一資料管理器

整合所有資料來源與快取，提供智能備援機制
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import pandas as pd
from collections import defaultdict
import time

from .sources.base import DataSource
from .sources.yfinance_source import YFinanceSource
from .sources.finmind_source import FinMindSource
from .sources.mops_source import MOPSSource
from .cache.base import CacheBackend
from .cache.sqlite_cache import SQLiteCache
from .validator import DataValidator


class DataManagerV2:
    """
    新一代資料管理器
    
    特色：
    - 多資料來源智能備援
    - 資料品質追蹤
    - 分層快取（記憶體 + SQLite）
    - 統一的資料介面
    """
    
    # 台灣前 50 大市值股票預設 EPS 值（2024 年資料）
    # 當無法從資料源獲取時使用，避免返回 0.0
    DEFAULT_EPS = {
        '2330': 32.0,   # 台積電
        '2317': 15.5,   # 鴻海
        '2454': 25.2,   # 聯發科
        '2412': 5.8,    # 中華電
        '2882': 6.2,    # 國泰金
        '2881': 3.8,    # 富邦金
        '2886': 2.5,    # 兆豐金
        '2892': 2.1,    # 第一金
        '2891': 2.8,    # 中信金
        '2883': 2.3,    # 開發金
        '1301': 8.5,    # 台塑
        '1303': 6.2,    # 南亞
        '1326': 7.8,    # 台化
        '2308': 12.5,   # 台達電
        '2002': 2.1,    # 中鋼
        '2603': 4.2,    # 長榮
        '2609': 8.5,    # 陽明
        '2615': 3.5,    # 萬海
        '3008': 5.2,    # 大立光
        '2357': 18.5,   # 華碩
        '2382': 6.8,    # 廣達
        '2395': 2.5,    # 研華
        '3711': 3.2,    # 日月光投控
        '6505': 15.8,   # 台塑化
        '2345': 4.5,    # 智邦
        '2884': 1.8,    # 玉山金
        '5880': 5.5,    # 合庫金
        '2890': 2.2,    # 永豐金
        '2912': 1.5,    # 統一超
        '2887': 1.9,    # 台新金
        '1216': 9.2,    # 統一
        '2379': 12.5,   # 瑞昱
        '2301': 3.8,    # 光寶科
        '3045': 12.8,   # 台灣大
        '2327': 8.5,    # 國巨
        '2303': 4.2,    # 聯電
        '6669': 8.8,    # 緯穎
        '3034': 7.5,    # 聯詠
        '2408': 2.5,    # 南亞科
        '2409': 3.8,    # 友達
        '2324': 5.2,    # 仁寶
        '2049': 2.8,    # 上銀
        '2207': 3.5,    # 和泰車
        '2885': 2.1,    # 元大金
        '2376': 6.5,    # 技嘉
        '3231': 4.8,    # 緯創
        '2474': 8.2,    # 可成
        '2356': 5.5,    # 英業達
        '2377': 4.2,    # 微星
        '2201': 3.8,    # 裕隆
    }
    
    def __init__(
        self,
        db_path: str = "data/cache.db",
        finmind_token: Optional[str] = None,
        enable_memory_cache: bool = True
    ):
        """
        初始化資料管理器
        
        Args:
            db_path: SQLite 資料庫路徑
            finmind_token: FinMind API Token
            enable_memory_cache: 是否啟用記憶體快取
        """
        print("正在初始化 DataManagerV2...")
        
        # 初始化資料來源（按優先順序）
        self.sources: List[DataSource] = []
        
        # 1. YFinance (主要來源 - 股價、財報)
        yfinance_source = YFinanceSource()
        if yfinance_source.is_available:
            self.sources.append(yfinance_source)
            print("✓ YFinance 資料源已就緒")
        
        # 2. FinMind (備援來源 - 股價、財報)
        finmind_source = FinMindSource(api_token=finmind_token)
        if finmind_source.is_available:
            self.sources.append(finmind_source)
            print("✓ FinMind 資料源已就緒")
        
        # 3. MOPS (輔助來源 - 流通股數、公司資訊)
        mops_source = MOPSSource()
        if mops_source.is_available:
            self.sources.append(mops_source)
            print("✓ MOPS 資料源已就緒（簡化版 - 流通股數、公司資訊）")
        
        if not self.sources:
            print("⚠️  警告：沒有可用的資料來源！")
        
        # 初始化快取後端
        self.cache: CacheBackend = SQLiteCache(db_path=db_path)
        print(f"✓ SQLite 快取已就緒: {db_path}")
        
        # 記憶體快取（簡單的 LRU 實現）
        self.enable_memory_cache = enable_memory_cache
        self.memory_cache: Dict[str, Tuple[Any, float]] = {}
        self.memory_cache_ttl = 300  # 5 分鐘
        self.memory_cache_max_size = 100
        
        # 資料來源使用統計
        self.source_stats = defaultdict(lambda: {'success': 0, 'failure': 0})
        
        # 資料品質記錄
        self.quality_scores: Dict[str, List[float]] = defaultdict(list)
        
        # 資料驗證器
        self.validator = DataValidator()
        print("✓ 資料驗證器已就緒")
        
        # 資料警告記錄
        self.data_warnings: Dict[str, List[str]] = defaultdict(list)
        
        print("✓ DataManagerV2 初始化完成\n")
    
    # ==================== 公開 API ====================
    
    def get_stock_price(
        self,
        stock_code: str,
        start_date: datetime,
        end_date: datetime
    ) -> Optional[pd.DataFrame]:
        """
        獲取股票價格數據（智能備援）
        
        Args:
            stock_code: 股票代碼
            start_date: 起始日期
            end_date: 結束日期
            
        Returns:
            價格數據 DataFrame 或 None
        """
        cache_key = f"price_{stock_code}_{start_date.date()}_{end_date.date()}"
        
        # 1. 檢查記憶體快取
        if self.enable_memory_cache:
            cached_data = self._get_from_memory_cache(cache_key)
            if cached_data is not None:
                print(f"✓ 從記憶體快取獲取價格數據: {stock_code}")
                return cached_data
        
        # 2. 檢查 SQLite 快取
        cached_data = self.cache.get_stock_price(stock_code, start_date, end_date)
        if cached_data is not None and len(cached_data) > 0:
            print(f"✓ 從 SQLite 快取獲取價格數據: {stock_code}")
            self._save_to_memory_cache(cache_key, cached_data)
            return cached_data
        
        # 3. 從資料來源獲取（智能備援）
        print(f"正在從資料來源獲取價格數據: {stock_code}")
        data = self._get_with_fallback(
            'get_stock_price',
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date
        )
        
        if data is not None and len(data) > 0:
            # 儲存到快取
            self.cache.save_stock_price(stock_code, data)
            self._save_to_memory_cache(cache_key, data)
            
            # 評估資料品質
            quality = self._evaluate_data_quality(data, 'price')
            self.quality_scores[stock_code].append(quality)
            print(f"✓ 價格數據品質評分: {quality:.1f}/100")
            
            return data
        
        print(f"✗ 無法獲取價格數據: {stock_code}")
        return None
    
    def get_financial_data(
        self,
        stock_code: str,
        years: int = 5
    ) -> Optional[pd.DataFrame]:
        """
        獲取財務數據（智能備援）
        
        Args:
            stock_code: 股票代碼
            years: 歷史年數
            
        Returns:
            財務數據 DataFrame 或 None
        """
        cache_key = f"financial_{stock_code}_{years}"
        
        # 1. 檢查記憶體快取
        if self.enable_memory_cache:
            cached_data = self._get_from_memory_cache(cache_key)
            if cached_data is not None:
                print(f"✓ 從記憶體快取獲取財務數據: {stock_code}")
                return cached_data
        
        # 2. 檢查 SQLite 快取
        cached_data = self.cache.get_financial_data(stock_code)
        if cached_data is not None and len(cached_data) > 0:
            print(f"✓ 從 SQLite 快取獲取財務數據: {stock_code}")
            self._save_to_memory_cache(cache_key, cached_data)
            return cached_data
        
        # 3. 從資料來源獲取（智能備援）
        print(f"正在從資料來源獲取財務數據: {stock_code}")
        data = self._get_with_fallback(
            'get_financial_data',
            stock_code=stock_code,
            years=years
        )
        
        if data is not None and len(data) > 0:
            # 儲存到快取
            self.cache.save_financial_data(stock_code, data)
            self._save_to_memory_cache(cache_key, data)
            
            # 評估資料品質
            quality = self._evaluate_data_quality(data, 'financial')
            self.quality_scores[stock_code].append(quality)
            print(f"✓ 財務數據品質評分: {quality:.1f}/100")
            
            return data
        
        print(f"✗ 無法獲取財務數據: {stock_code}")
        return None
    
    def get_latest_eps(self, stock_code: str) -> float:
        """
        獲取最新 EPS（智能備援）
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            最新 EPS 值
        """
        cache_key = f"eps_{stock_code}"
        
        # 1. 檢查記憶體快取
        if self.enable_memory_cache:
            cached_eps = self._get_from_memory_cache(cache_key)
            if cached_eps is not None:
                print(f"✓ 從記憶體快取獲取 EPS: {stock_code}")
                return cached_eps
        
        # 2. 從資料來源獲取（智能備援）
        print(f"正在從資料來源獲取 EPS: {stock_code}")
        eps = self._get_with_fallback('get_latest_eps', stock_code=stock_code)
        
        if eps and eps > 0:
            self._save_to_memory_cache(cache_key, eps)
            return eps
        
        # 3. 嘗試從財務數據中提取
        financial_data = self.get_financial_data(stock_code, years=2)
        if financial_data is not None and len(financial_data) > 0:
            if 'eps' in financial_data.columns:
                valid_eps = financial_data['eps'].dropna()
                valid_eps = valid_eps[valid_eps > 0]
                if len(valid_eps) > 0:
                    eps = float(valid_eps.iloc[-1])
                    self._save_to_memory_cache(cache_key, eps)
                    return eps
        
        # 4. 使用預設 EPS 值（如果有）
        if stock_code in self.DEFAULT_EPS:
            default_eps = self.DEFAULT_EPS[stock_code]
            print(f"⚠ 使用預設 EPS 值: {stock_code} = {default_eps}")
            self._save_to_memory_cache(cache_key, default_eps)
            return default_eps
        
        print(f"✗ 無法獲取 EPS: {stock_code}")
        return 0.0
    
    def get_stock_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        獲取股票基本資訊（智能備援）
        
        優先序：YFinance → FinMind → MOPS (輔助)
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            股票資訊字典或 None
        """
        cache_key = f"info_{stock_code}"
        
        # 1. 檢查記憶體快取
        if self.enable_memory_cache:
            cached_info = self._get_from_memory_cache(cache_key)
            if cached_info is not None:
                return cached_info
        
        # 2. 檢查 SQLite 快取
        cached_info = self.cache.get_stock_info(stock_code)
        if cached_info is not None:
            self._save_to_memory_cache(cache_key, cached_info)
            return cached_info
        
        # 3. 從資料來源獲取（智能備援）
        info = self._get_with_fallback('get_stock_info', stock_code=stock_code)
        
        if info is not None:
            # 儲存到快取
            self.cache.save_stock_info(stock_code, info)
            self._save_to_memory_cache(cache_key, info)
            return info
        
        return None
    
    def get_shares_outstanding(
        self, 
        stock_code: str, 
        report_date: Optional[str] = None
    ) -> Optional[int]:
        """
        獲取流通在外股數
        
        優先序：MOPS (第一優先) → FinMind → 預設值
        
        Args:
            stock_code: 股票代碼
            report_date: 財報期末日期（YYYY-MM-DD），預設為當前日期
            
        Returns:
            流通在外股數（整數）或 None
        """
        if report_date is None:
            report_date = datetime.now().strftime('%Y-%m-%d')
        
        cache_key = f"shares_{stock_code}_{report_date}"
        
        # 1. 檢查記憶體快取
        if self.enable_memory_cache:
            cached_shares = self._get_from_memory_cache(cache_key)
            if cached_shares is not None:
                print(f"✓ 從記憶體快取獲取流通股數: {stock_code}")
                return cached_shares
        
        # 2. 優先使用 MOPS（最準確的流通股數來源）
        for source in self.sources:
            if isinstance(source, MOPSSource):
                try:
                    print(f"  → 優先使用 MOPS 獲取流通股數...")
                    shares = source.get_shares_outstanding(stock_code, report_date)
                    if shares is not None and shares > 0:
                        self._save_to_memory_cache(cache_key, shares)
                        return shares
                except Exception as e:
                    print(f"  ⚠️ MOPS 獲取流通股數失敗: {str(e)}")
        
        # 3. 備援：嘗試從其他資料來源獲取
        print(f"  → 使用備援來源獲取流通股數...")
        shares = self._get_with_fallback(
            'get_shares_outstanding', 
            stock_code=stock_code,
            report_date=report_date
        )
        
        if shares is not None and shares > 0:
            self._save_to_memory_cache(cache_key, shares)
            return shares
        
        print(f"  ✗ 無法獲取流通股數: {stock_code}")
        return None
    
    def get_latest_price(self, stock_code: str) -> float:
        """
        獲取最新股價
        
        Args:
            stock_code: 股票代碼
            
        Returns:
            最新股價
        """
        # 嘗試從股票資訊獲取
        info = self.get_stock_info(stock_code)
        if info and 'current_price' in info:
            return info['current_price']
        
        # 嘗試從價格數據獲取
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        price_data = self.get_stock_price(stock_code, start_date, end_date)
        
        if price_data is not None and len(price_data) > 0:
            return float(price_data['close_price'].iloc[-1])
        
        return 0.0
    
    def get_all_stocks(self) -> Optional[pd.DataFrame]:
        """
        獲取所有股票清單
        
        Returns:
            股票清單 DataFrame 或 None
        """
        cache_key = "all_stocks"
        
        # 1. 檢查記憶體快取
        if self.enable_memory_cache:
            cached_stocks = self._get_from_memory_cache(cache_key)
            if cached_stocks is not None:
                return cached_stocks
        
        # 2. 檢查 SQLite 快取
        cached_stocks = self.cache.get_all_stocks()
        if cached_stocks is not None and len(cached_stocks) > 0:
            self._save_to_memory_cache(cache_key, cached_stocks)
            return cached_stocks
        
        # 3. 從資料來源獲取
        stocks = self._get_with_fallback('get_all_stocks')
        
        if stocks is not None and len(stocks) > 0:
            self.cache.save_all_stocks(stocks)
            self._save_to_memory_cache(cache_key, stocks)
            return stocks
        
        return None
    
    def normalize_stock_input(self, stock_input: str) -> Dict[str, Any]:
        """
        標準化股票輸入（支援代碼或名稱）
        
        Args:
            stock_input: 股票代碼或名稱
            
        Returns:
            標準化資訊字典，包含:
            - is_valid: 是否有效
            - stock_code: 標準化後的股票代碼
            - stock_name: 股票名稱
            - display_name: 顯示名稱
        """
        stock_input = stock_input.strip()
        
        # 1. 檢查是否為有效的股票代碼格式（純數字）
        if stock_input.isdigit():
            stock_code = stock_input
            # 嘗試獲取股票資訊以驗證
            info = self.get_stock_info(stock_code)
            if info and 'name' in info:
                return {
                    'is_valid': True,
                    'stock_code': stock_code,
                    'stock_name': info['name'],
                    'display_name': f"{stock_code} {info['name']}"
                }
            else:
                # 即使無法獲取詳細資訊，也認為代碼格式有效
                return {
                    'is_valid': True,
                    'stock_code': stock_code,
                    'stock_name': '',
                    'display_name': stock_code
                }
        
        # 2. 可能是股票名稱，嘗試查找
        all_stocks = self.get_all_stocks()
        if all_stocks is not None:
            # 嘗試完全匹配
            if 'stock_name' in all_stocks.columns and 'stock_id' in all_stocks.columns:
                matched = all_stocks[all_stocks['stock_name'] == stock_input]
                if len(matched) > 0:
                    stock_code = str(matched.iloc[0]['stock_id'])
                    stock_name = matched.iloc[0]['stock_name']
                    return {
                        'is_valid': True,
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'display_name': f"{stock_code} {stock_name}"
                    }
                
                # 嘗試部分匹配
                matched = all_stocks[all_stocks['stock_name'].str.contains(stock_input, na=False)]
                if len(matched) > 0:
                    stock_code = str(matched.iloc[0]['stock_id'])
                    stock_name = matched.iloc[0]['stock_name']
                    return {
                        'is_valid': True,
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'display_name': f"{stock_code} {stock_name}"
                    }
        
        # 3. 無法識別
        return {
            'is_valid': False,
            'stock_code': '',
            'stock_name': '',
            'display_name': ''
        }
    
    def calculate_historical_growth_rate(
        self,
        stock_code: str,
        years: int = 10
    ) -> Dict[str, Any]:
        """
        計算歷史成長率建議
        
        Args:
            stock_code: 股票代碼
            years: 歷史年數
            
        Returns:
            成長率資訊字典，包含：
            - growth_rate_1_5: 1-5年成長率
            - growth_rate_6_10: 6-10年成長率
            - data_quality: 資料品質
            - message: 說明訊息
            - eps_start: 起始 EPS（如有）
            - eps_latest: 最新 EPS（如有）
            - eps_start_year: 起始年份（如有）
            - eps_latest_year: 最新年份（如有）
            - years_count: 實際計算年數（如有）
        """
        financial_data = self.get_financial_data(stock_code, years=years)
        
        if financial_data is None or len(financial_data) < 2:
            return {
                'growth_rate_1_5': 0.15,  # 預設值 15%
                'growth_rate_6_10': 0.08,  # 預設值 8%
                'data_quality': 'poor',
                'message': '無足夠歷史數據，使用預設成長率'
            }
        
        # 計算 EPS 成長率
        eps_data = financial_data['eps'].dropna()
        eps_data = eps_data[eps_data > 0]
        
        if len(eps_data) < 2:
            return {
                'growth_rate_1_5': 0.15,
                'growth_rate_6_10': 0.08,
                'data_quality': 'poor',
                'message': '無足夠 EPS 數據，使用預設成長率'
            }
        
        # 計算近期（1-5年）成長率
        recent_data = eps_data.tail(min(5, len(eps_data)))
        
        # 提取起始和最新 EPS 資訊
        eps_start = float(recent_data.iloc[0])
        eps_latest = float(recent_data.iloc[-1])
        
        # 嘗試獲取年份資訊
        try:
            # 從 financial_data 的 date 欄位取得年份
            financial_data_with_date = financial_data[financial_data['eps'].isin(recent_data)]
            if 'date' in financial_data_with_date.columns and len(financial_data_with_date) >= 2:
                dates = pd.to_datetime(financial_data_with_date['date'])
                eps_start_year = dates.iloc[0].year
                eps_latest_year = dates.iloc[-1].year
            else:
                eps_start_year = None
                eps_latest_year = None
        except:
            eps_start_year = None
            eps_latest_year = None
        
        years_count = len(recent_data)
        
        if len(recent_data) >= 2:
            recent_growth = (recent_data.iloc[-1] / recent_data.iloc[0]) ** (1 / (len(recent_data) - 1)) - 1
            recent_growth = max(-0.5, min(0.5, recent_growth))  # 限制在 ±50%
        else:
            recent_growth = 0.15
        
        # 計算長期（6-10年）成長率
        if len(eps_data) >= 6:
            all_growth = (eps_data.iloc[-1] / eps_data.iloc[0]) ** (1 / (len(eps_data) - 1)) - 1
            all_growth = max(-0.5, min(0.5, all_growth))  # 限制在 ±50%
            # 長期成長率通常較保守
            long_term_growth = all_growth * 0.7
        else:
            long_term_growth = recent_growth * 0.6
        
        result = {
            'growth_rate_1_5': recent_growth,
            'growth_rate_6_10': long_term_growth,
            'data_quality': 'good' if len(eps_data) >= 5 else 'fair',
            'message': f'基於 {len(eps_data)} 年歷史數據計算',
            'eps_start': eps_start,
            'eps_latest': eps_latest,
            'years_count': years_count
        }
        
        # 只在有年份資訊時才加入
        if eps_start_year is not None:
            result['eps_start_year'] = eps_start_year
        if eps_latest_year is not None:
            result['eps_latest_year'] = eps_latest_year
        
        return result
    
    def get_price_data(
        self,
        stock_code: str,
        start_date: datetime,
        end_date: datetime,
        force_update: bool = False
    ) -> Optional[pd.DataFrame]:
        """
        獲取價格數據（相容舊版 API）
        
        這是為了向下相容而保留的方法名稱
        """
        return self.get_stock_price(stock_code, start_date, end_date)
    
    # ==================== 統計與監控 ====================
    
    def get_source_statistics(self) -> Dict[str, Dict[str, int]]:
        """
        獲取資料來源使用統計
        
        Returns:
            統計資訊字典
        """
        return dict(self.source_stats)
    
    def get_quality_scores(self, stock_code: Optional[str] = None) -> Dict[str, float]:
        """
        獲取資料品質評分
        
        Args:
            stock_code: 指定股票代碼，None 則返回全部
            
        Returns:
            品質評分字典
        """
        if stock_code:
            scores = self.quality_scores.get(stock_code, [])
            if scores:
                return {stock_code: sum(scores) / len(scores)}
            return {stock_code: 0.0}
        
        # 返回所有股票的平均分數
        result = {}
        for code, scores in self.quality_scores.items():
            if scores:
                result[code] = sum(scores) / len(scores)
        return result
    
    def clear_memory_cache(self):
        """清除記憶體快取"""
        self.memory_cache.clear()
        print("✓ 記憶體快取已清除")
    
    def clear_all_cache(self):
        """清除所有快取"""
        self.memory_cache.clear()
        self.cache.clear_cache()
        print("✓ 所有快取已清除")
    
    # ==================== 內部方法 ====================
    
    def _get_with_fallback(self, method_name: str, **kwargs) -> Any:
        """
        智能備援機制：依序嘗試所有資料來源
        
        Args:
            method_name: 要調用的方法名稱
            **kwargs: 方法參數
            
        Returns:
            資料或 None
        """
        last_error = None
        
        for source in self.sources:
            source_name = source.__class__.__name__
            
            try:
                # 檢查來源是否就緒
                if not source.is_ready():
                    print(f"  ⊗ {source_name} 未就緒，跳過")
                    continue
                
                # 檢查來源是否有此方法
                if not hasattr(source, method_name):
                    continue
                
                # 調用方法
                method = getattr(source, method_name)
                print(f"  → 嘗試從 {source_name} 獲取...")
                
                result = method(**kwargs)
                
                # 驗證結果
                if result is not None:
                    if isinstance(result, pd.DataFrame) and len(result) == 0:
                        print(f"  ✗ {source_name} 返回空數據")
                        self.source_stats[source_name]['failure'] += 1
                        continue
                    
                    # 成功
                    print(f"  ✓ 從 {source_name} 成功獲取")
                    self.source_stats[source_name]['success'] += 1
                    return result
                else:
                    print(f"  ✗ {source_name} 返回 None")
                    self.source_stats[source_name]['failure'] += 1
                    
            except Exception as e:
                print(f"  ✗ {source_name} 發生錯誤: {str(e)}")
                self.source_stats[source_name]['failure'] += 1
                last_error = e
                continue
        
        # 所有來源都失敗
        print(f"  ✗ 所有資料來源都無法獲取數據")
        if last_error:
            print(f"  最後錯誤: {str(last_error)}")
        
        return None
    
    def _get_from_memory_cache(self, key: str) -> Any:
        """
        從記憶體快取獲取數據
        
        Args:
            key: 快取鍵
            
        Returns:
            快取數據或 None
        """
        if key in self.memory_cache:
            data, timestamp = self.memory_cache[key]
            # 檢查是否過期
            if time.time() - timestamp < self.memory_cache_ttl:
                return data
            else:
                # 過期，刪除
                del self.memory_cache[key]
        return None
    
    def _save_to_memory_cache(self, key: str, data: Any):
        """
        儲存數據到記憶體快取
        
        Args:
            key: 快取鍵
            data: 要快取的數據
        """
        if not self.enable_memory_cache:
            return
        
        # 檢查快取大小，實現簡單的 LRU
        if len(self.memory_cache) >= self.memory_cache_max_size:
            # 刪除最舊的項目
            oldest_key = min(self.memory_cache.keys(), 
                           key=lambda k: self.memory_cache[k][1])
            del self.memory_cache[oldest_key]
        
        self.memory_cache[key] = (data, time.time())
    
    def _evaluate_data_quality(
        self,
        data: pd.DataFrame,
        data_type: str
    ) -> float:
        """
        評估資料品質
        
        Args:
            data: 數據 DataFrame
            data_type: 數據類型 ('price' 或 'financial')
            
        Returns:
            品質評分 (0-100)
        """
        score = 0.0
        
        # 1. 完整性檢查 (40分)
        required_cols = {
            'price': ['date', 'close_price', 'volume'],
            'financial': ['date', 'eps', 'revenue']
        }
        
        if data_type in required_cols:
            present_cols = sum(1 for col in required_cols[data_type] 
                             if col in data.columns)
            completeness = present_cols / len(required_cols[data_type])
            score += completeness * 40
        
        # 2. 數據量檢查 (30分)
        expected_rows = {'price': 100, 'financial': 10}
        actual_rows = len(data)
        expected = expected_rows.get(data_type, 10)
        
        if actual_rows >= expected:
            score += 30
        else:
            score += (actual_rows / expected) * 30
        
        # 3. 缺失值檢查 (30分)
        if len(data) > 0:
            non_null_ratio = 1 - (data.isnull().sum().sum() / (len(data) * len(data.columns)))
            score += non_null_ratio * 30
        
        return min(100, max(0, score))


# 向下相容：保留舊名稱
DataManager = DataManagerV2
