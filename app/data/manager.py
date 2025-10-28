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
from .cache.base import CacheBackend
from .cache.sqlite_cache import SQLiteCache


class DataManagerV2:
    """
    新一代資料管理器
    
    特色：
    - 多資料來源智能備援
    - 資料品質追蹤
    - 分層快取（記憶體 + SQLite）
    - 統一的資料介面
    """
    
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
        
        # 1. YFinance (主要來源)
        yfinance_source = YFinanceSource()
        if yfinance_source.is_available:
            self.sources.append(yfinance_source)
            print("✓ YFinance 資料源已就緒")
        
        # 2. FinMind (備援來源)
        finmind_source = FinMindSource(api_token=finmind_token)
        if finmind_source.is_available:
            self.sources.append(finmind_source)
            print("✓ FinMind 資料源已就緒")
        
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
        cached_data = self.cache.get_price_data(stock_code, start_date, end_date)
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
            self.cache.save_price_data(stock_code, data)
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
        
        print(f"✗ 無法獲取 EPS: {stock_code}")
        return 0.0
    
    def get_stock_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        獲取股票基本資訊（智能備援）
        
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
