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
    
    # 台灣前 50 大市值股票預設 EPS 值（從外部 JSON 載入）
    import json
    from pathlib import Path
    try:
        DEFAULT_EPS = json.loads((Path(__file__).parent / "default_eps.json").read_text(encoding="utf-8"))
    except Exception:
        DEFAULT_EPS = {}
    
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
            print("[OK] YFinance 資料源已就緒")
        
        # 2. FinMind (備援來源 - 股價、財報)
        finmind_source = FinMindSource(api_token=finmind_token)
        if finmind_source.is_available:
            self.sources.append(finmind_source)
            print("[OK] FinMind 資料源已就緒")
        
        # 3. MOPS (輔助來源 - 流通股數、公司資訊)
        mops_source = MOPSSource()
        if mops_source.is_available:
            self.sources.append(mops_source)
            print("[OK] MOPS 資料源已就緒（簡化版 - 流通股數、公司資訊）")
        
        if not self.sources:
            print("[WARN]  警告：沒有可用的資料來源！")
        
        # 初始化快取後端
        self.cache: CacheBackend = SQLiteCache(db_path=db_path)
        print(f"[OK] SQLite 快取已就緒: {db_path}")
        
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
        print("[OK] 資料驗證器已就緒")
        
        # 資料警告記錄
        self.data_warnings: Dict[str, List[str]] = defaultdict(list)
        
        print("[OK] DataManagerV2 初始化完成\n")
    
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
                print(f"[OK] 從記憶體快取獲取價格數據: {stock_code}")
                return cached_data
        
        # 2. 檢查 SQLite 快取
        cached_data = self.cache.get_stock_price(stock_code, start_date, end_date)
        if cached_data is not None and len(cached_data) > 0:
            print(f"[OK] 從 SQLite 快取獲取價格數據: {stock_code}")
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
            validation_res = self._evaluate_data_quality(data, 'price', stock_code)
            quality = validation_res['quality_score']
            self.quality_scores[stock_code].append(quality)
            
            # 記錄警告
            if validation_res['warnings']:
                self.data_warnings[stock_code].extend(validation_res['warnings'])
                print(f"[WARN]  價格數據警告: {', '.join(validation_res['warnings'])}")
            
            print(f"[OK] 價格數據品質評分: {quality:.1f}/100")
            
            return data
        
        print(f"[FAIL] 無法獲取價格數據: {stock_code}")
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
                print(f"[OK] 從記憶體快取獲取財務數據: {stock_code}")
                return cached_data
        
        # 2. 檢查 SQLite 快取
        cached_data = self.cache.get_financial_data(stock_code)
        if cached_data is not None and len(cached_data) > 0:
            print(f"[OK] 從 SQLite 快取獲取財務數據: {stock_code}")
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
            validation_res = self._evaluate_data_quality(data, 'financial', stock_code)
            quality = validation_res['quality_score']
            self.quality_scores[stock_code].append(quality)
            
            # 記錄警告
            if validation_res['warnings']:
                self.data_warnings[stock_code].extend(validation_res['warnings'])
                print(f"[WARN]  財務數據警告: {', '.join(validation_res['warnings'])}")
            
            print(f"[OK] 財務數據品質評分: {quality:.1f}/100")
            
            return data
        
        print(f"[FAIL] 無法獲取財務數據: {stock_code}")
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
                print(f"[OK] 從記憶體快取獲取 EPS: {stock_code}")
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
            print(f"[WARN] 使用預設 EPS 值: {stock_code} = {default_eps}")
            self._save_to_memory_cache(cache_key, default_eps)
            return default_eps
        
        print(f"[FAIL] 無法獲取 EPS: {stock_code}")
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
    
    def get_quality_indicators(self, stock_code: str) -> Dict[str, float]:
        """
        獲取盈餘品質與營運效率指標
        包含 OCF/NI 比例、存貨週轉率等
        """
        df = self.get_financial_data(stock_code, years=2)
        indicators = {
            "earnings_quality": None, # OCF / NI
            "gross_margin": None,
            "operating_margin": None,
            "net_margin": None
        }
        
        if df is not None and not df.empty:
            try:
                latest = df.iloc[0]
                
                # Earnings Quality = Operating Cash Flow / Net Income
                if 'operating_cash_flow' in latest and 'net_income' in latest:
                    ocf = latest['operating_cash_flow']
                    ni = latest['net_income']
                    if ni and ni != 0 and ocf and pd.notna(ocf) and pd.notna(ni):
                        indicators["earnings_quality"] = ocf / ni
                
                # Margins
                if 'gross_profit' in latest and 'revenue' in latest:
                    gp = latest['gross_profit']
                    rev = latest['revenue']
                    if rev and rev != 0 and pd.notna(gp) and pd.notna(rev):
                        indicators["gross_margin"] = gp / rev
                        
                if 'operating_income' in latest and 'revenue' in latest:
                    op = latest['operating_income']
                    rev = latest['revenue']
                    if rev and rev != 0 and pd.notna(op) and pd.notna(rev):
                        indicators["operating_margin"] = op / rev
                        
                if 'net_income' in latest and 'revenue' in latest:
                    ni = latest['net_income']
                    rev = latest['revenue']
                    if rev and rev != 0 and pd.notna(ni) and pd.notna(rev):
                        indicators["net_margin"] = ni / rev
                        
            except Exception as e:
                print(f"[WARN] 計算品質指標失敗: {e}")
                
        return indicators
    
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
                print(f"[OK] 從記憶體快取獲取流通股數: {stock_code}")
                return cached_shares
        
        # 2. 優先使用 MOPS（最準確的流通股數來源）
        for source in self.sources:
            source_class_name = getattr(source, '__class__', type(source)).__name__
            if source_class_name == 'MOPSSource' or 'MOPSSource' in str(type(source)) or 'MOPSSource' in str(source):
                try:
                    print(f"  [INFO] 優先使用 MOPS 獲取流通股數...")
                    shares = source.get_shares_outstanding(stock_code, report_date)
                    if shares is not None and shares > 0:
                        self._save_to_memory_cache(cache_key, shares)
                        return shares
                except Exception as e:
                    print(f"  [WARN] MOPS 獲取流通股數失敗: {str(e)}")
        
        # 3. 備援：嘗試從其他資料來源獲取
        print(f"  [INFO] 使用備援來源獲取流通股數...")
        shares = self._get_with_fallback(
            'get_shares_outstanding', 
            stock_code=stock_code,
            report_date=report_date
        )
        
        if shares is not None and shares > 0:
            self._save_to_memory_cache(cache_key, shares)
            return shares
        
        print(f"  [FAIL] 無法獲取流通股數: {stock_code}")
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
        if cached_stocks is not None and len(cached_stocks) > 1000:  # 確保是完整清單而非個別查詢留下的記錄
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
            name = info.get('name') or info.get('stock_name', '') if info else ''
            if info and name:
                return {
                    'is_valid': True,
                    'stock_code': stock_code,
                    'stock_name': name,
                    'display_name': f"{stock_code} {name}"
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
        years: int = 10,
        use_time_weighting: bool = True,
        recent_weight_ratio: float = 0.6
    ) -> Dict[str, Any]:
        """
        計算歷史成長率建議（支援指數衰減時間加權）
        
        Args:
            stock_code: 股票代碼
            years: 歷史年數
            use_time_weighting: 是否使用時間加權（預設 True）
            recent_weight_ratio: 近期權重比例（預設 0.6 = 60%）
                               - 數值越高，近期數據影響越大
                               - 範圍：0.5-0.9
                               - 0.6 表示最近一年佔總權重的 60%
            
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
            - weighting_method: 使用的加權方法（'time_weighted' 或 'equal_weighted'）
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
        
        # 計算成長率（支援時間加權或等權重）
        if len(recent_data) >= 2:
            if use_time_weighting:
                # 使用指數衰減時間加權
                recent_growth = self._calculate_time_weighted_growth_rate(
                    recent_data, 
                    recent_weight_ratio
                )
                weighting_method = 'time_weighted'
            else:
                # 使用傳統等權重 CAGR
                recent_growth = (recent_data.iloc[-1] / recent_data.iloc[0]) ** (1 / (len(recent_data) - 1)) - 1
                weighting_method = 'equal_weighted'
            
            recent_growth = max(-0.5, min(0.5, recent_growth))  # 限制在 ±50%
        else:
            recent_growth = 0.15
            weighting_method = 'default'
        
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
            'years_count': years_count,
            'weighting_method': weighting_method
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
        print("[OK] 記憶體快取已清除")
    
    def clear_all_cache(self):
        """清除所有快取"""
        self.memory_cache.clear()
        self.cache.clear_cache()
        print("[OK] 所有快取已清除")
    
    # ==================== 時間加權計算方法 ====================
    
    def _calculate_lambda(self, n: int, recent_weight_ratio: float) -> float:
        """
        計算指數衰減參數 lambda
        
        使用指數衰減權重公式：w_i = exp(-λ * (n - 1 - i))
        其中 i 是數據點索引（0 為最舊，n-1 為最新）
        
        Args:
            n: 數據點數量
            recent_weight_ratio: 最近數據點應佔的權重比例（0.5-0.9）
                               例如 0.6 表示最新數據點應佔總權重的 60%
            
        Returns:
            lambda 衰減參數
            
        技術說明：
            求解方程：1 / [Σ exp(-λ * (n-1-i))] = recent_weight_ratio
            即找到 λ 使得最新數據點的標準化權重等於 recent_weight_ratio
        """
        import numpy as np
        from scipy.optimize import brentq
        
        # 限制 recent_weight_ratio 在合理範圍
        recent_weight_ratio = max(0.5, min(0.9, recent_weight_ratio))
        
        # 特殊情況：等權重
        if abs(recent_weight_ratio - 1.0/n) < 0.01:
            return 0.0001  # 接近 0 的 lambda 會產生接近等權重的結果
        
        def weight_sum_equation(lam):
            """
            計算目標方程式的值
            目標：使得 1 / sum(weights) = recent_weight_ratio
            即：sum(weights) = 1 / recent_weight_ratio
            """
            if lam <= 0:
                return float('inf')
            
            # 計算權重總和：Σ exp(-λ * (n-1-i)) for i = 0 to n-1
            # 等價於：Σ exp(-λ * j) for j = n-1 down to 0
            # 這是等比級數：1 + r + r^2 + ... + r^(n-1)，其中 r = exp(-λ)
            
            r = np.exp(-lam)
            if abs(r - 1.0) < 1e-10:
                # r 接近 1 時使用極限公式
                weight_sum = n
            else:
                # 等比級數和：(1 - r^n) / (1 - r)
                weight_sum = (1 - r**n) / (1 - r)
            
            # 目標總和
            target_sum = 1.0 / recent_weight_ratio
            
            return weight_sum - target_sum
        
        # 使用 Brent 方法求根
        try:
            lambda_value = brentq(weight_sum_equation, 0.001, 10.0)
            return lambda_value
        except ValueError:
            # 如果求根失敗，返回保守值
            return 0.5
    
    def _calculate_exponential_weights(
        self, 
        n: int, 
        recent_weight_ratio: float = 0.6
    ) -> List[float]:
        """
        計算指數衰減權重
        
        Args:
            n: 數據點數量
            recent_weight_ratio: 近期權重比例（預設 0.6）
            
        Returns:
            標準化後的權重列表（由舊到新順序，總和為 1）
            
        範例：
            n=5, recent_weight_ratio=0.6
            返回類似 [0.05, 0.08, 0.12, 0.20, 0.55] 的權重
            最新數據（最後一個）佔約 55-60% 權重
        """
        import numpy as np
        
        if n < 2:
            return [1.0]
        
        # 計算 lambda 參數
        lam = self._calculate_lambda(n, recent_weight_ratio)
        
        # 計算指數衰減權重（從舊到新：i=0 最舊，i=n-1 最新）
        indices = np.arange(n)
        weights = np.exp(-lam * (n - 1 - indices))
        
        # 標準化權重（總和為 1）
        weights = weights / np.sum(weights)
        
        return weights.tolist()
    
    def _calculate_time_weighted_growth_rate(
        self,
        eps_series: pd.Series,
        recent_weight_ratio: float = 0.6
    ) -> float:
        """
        使用時間加權計算成長率
        
        Args:
            eps_series: EPS 時間序列（由舊到新排序）
            recent_weight_ratio: 近期權重比例（預設 0.6）
            
        Returns:
            時間加權成長率
            
        計算方法：
            1. 計算各期間的成長率
            2. 使用指數衰減權重計算加權平均
            3. 近期成長率獲得更高權重
        """
        import numpy as np
        
        if len(eps_series) < 2:
            return 0.15  # 預設值
        
        eps_values = eps_series.values
        n = len(eps_values)
        
        # 計算各期間的年化成長率
        growth_rates = []
        for i in range(1, n):
            if eps_values[i-1] > 0 and eps_values[i] > 0:
                # 計算單期成長率（年化）
                growth = (eps_values[i] / eps_values[i-1]) - 1
                growth_rates.append(growth)
            else:
                growth_rates.append(0.0)
        
        if not growth_rates:
            return 0.15
        
        # 計算指數衰減權重（n-1 個成長率對應 n-1 個權重）
        weights = self._calculate_exponential_weights(len(growth_rates), recent_weight_ratio)
        
        # 計算加權平均成長率
        weighted_growth = np.average(growth_rates, weights=weights)
        
        return weighted_growth
    
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
                    print(f"  [FAILED] {source_name} 未就緒，跳過")
                    continue
                
                # 檢查來源是否有此方法
                if not hasattr(source, method_name):
                    continue
                
                # 調用方法
                method = getattr(source, method_name)
                print(f"  [INFO] 嘗試從 {source_name} 獲取...")
                
                result = method(**kwargs)
                
                # 驗證結果
                if result is not None:
                    if isinstance(result, pd.DataFrame) and len(result) == 0:
                        print(f"  [FAIL] {source_name} 返回空數據")
                        self.source_stats[source_name]['failure'] += 1
                        continue
                    
                    # 成功
                    print(f"  [OK] 從 {source_name} 成功獲取")
                    self.source_stats[source_name]['success'] += 1
                    return result
                else:
                    print(f"  [FAIL] {source_name} 返回 None")
                    self.source_stats[source_name]['failure'] += 1
                    
            except Exception as e:
                print(f"  [FAIL] {source_name} 發生錯誤: {str(e)}")
                self.source_stats[source_name]['failure'] += 1
                last_error = e
                continue
        
        # 所有來源都失敗
        print(f"  [FAIL] 所有資料來源都無法獲取數據")
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
        data_type: str,
        stock_code: str = ""
    ) -> Dict[str, Any]:
        """
        評估資料品質
        
        Args:
            data: 數據 DataFrame
            data_type: 數據類型 ('price' 或 'financial')
            stock_code: 股票代碼
            
        Returns:
            驗證結果字典，包含 quality_score, warnings, issues 等
        """
        # 使用 DataValidator 進行深度檢查
        if data_type == 'price':
            validation = self.validator.validate_price_data(data, stock_code)
        else:
            validation = self.validator.validate_financial_data(data, stock_code)
            
        # 額外進行數據量權重計算（保留原有的基礎評分邏輯作為加乘因子）
        base_score = 0.0
        
        # 1. 完整性檢查 (40分)
        required_cols = {
            'price': ['date', 'close_price', 'volume'],
            'financial': ['date', 'eps', 'revenue']
        }
        
        if data_type in required_cols:
            present_cols = sum(1 for col in required_cols[data_type] 
                             if col in data.columns)
            completeness = present_cols / len(required_cols[data_type])
            base_score += completeness * 40
        
        # 2. 數據量檢查 (30分)
        expected_rows = {'price': 100, 'financial': 8}  # 財務資料 8 筆約兩年
        actual_rows = len(data)
        expected = expected_rows.get(data_type, 10)
        
        if actual_rows >= expected:
            base_score += 30
        else:
            base_score += (actual_rows / expected) * 30
            
        # 3. 缺失值檢查 (30分)
        if len(data) > 0:
            non_null_ratio = 1 - (data.isnull().sum().sum() / (len(data) * len(data.columns)))
            base_score += non_null_ratio * 30
            
        # 最終分數結合：平均 DataValidator 的分數與數據量基礎分數
        # 這能同時考量「數值合理性」與「資料充足度」
        final_score = (validation['quality_score'] * 0.7) + (base_score * 0.3)
        
        validation['quality_score'] = min(100, max(0, final_score))
        return validation


# 向下相容：保留舊名稱
DataManager = DataManagerV2
