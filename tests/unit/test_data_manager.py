"""
DataManagerV2 單元測試

測試 DataManagerV2 類別的所有功能
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch, call
from app.data.manager import DataManagerV2


class TestDataManagerInit:
    """測試 DataManagerV2 初始化"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_init_creates_instance(
        self, 
        mock_cache, 
        mock_mops, 
        mock_finmind, 
        mock_yfinance
    ):
        """測試建立 DataManagerV2 實例"""
        # 設定 Mock 回傳值
        mock_yfinance.return_value.is_available = True
        mock_finmind.return_value.is_available = True
        mock_mops.return_value.is_available = True
        
        manager = DataManagerV2(db_path="test.db")
        
        assert manager is not None
        assert isinstance(manager, DataManagerV2)
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_init_with_memory_cache_enabled(
        self,
        mock_cache,
        mock_mops,
        mock_finmind,
        mock_yfinance
    ):
        """測試啟用記憶體快取的初始化"""
        mock_yfinance.return_value.is_available = True
        
        manager = DataManagerV2(enable_memory_cache=True)
        
        assert manager.enable_memory_cache is True
        assert isinstance(manager.memory_cache, dict)
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_init_with_finmind_token(
        self,
        mock_cache,
        mock_mops,
        mock_finmind,
        mock_yfinance
    ):
        """測試使用 FinMind Token 初始化"""
        mock_yfinance.return_value.is_available = True
        
        manager = DataManagerV2(finmind_token="test_token")
        
        # 驗證 FinMindSource 被呼叫時有傳入 token
        mock_finmind.assert_called_once_with(api_token="test_token")


class TestGetStockPrice:
    """測試獲取股價數據功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_stock_price_from_cache(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance,
        sample_price_data
    ):
        """測試從快取獲取股價數據"""
        mock_yfinance.return_value.is_available = True
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_stock_price.return_value = sample_price_data
        
        manager = DataManagerV2()
        
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)
        result = manager.get_stock_price("2330", start_date, end_date)
        
        assert result is not None
        assert len(result) > 0
        mock_cache_instance.get_stock_price.assert_called_once()
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_stock_price_from_source(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class,
        sample_price_data
    ):
        """測試從資料來源獲取股價數據"""
        # 設定 Mock
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_stock_price.return_value = sample_price_data
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_stock_price.return_value = None  # 快取未命中
        
        manager = DataManagerV2()
        
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)
        result = manager.get_stock_price("2330", start_date, end_date)
        
        assert result is not None
        assert len(result) > 0
        # 驗證有呼叫資料來源
        mock_yfinance_instance.get_stock_price.assert_called_once()
        # 驗證有儲存到快取
        mock_cache_instance.save_stock_price.assert_called_once()


class TestGetFinancialData:
    """測試獲取財務數據功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_financial_data_from_cache(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance,
        sample_financial_data
    ):
        """測試從快取獲取財務數據"""
        mock_yfinance.return_value.is_available = True
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_financial_data.return_value = sample_financial_data
        
        manager = DataManagerV2()
        result = manager.get_financial_data("2330", years=5)
        
        assert result is not None
        assert len(result) > 0
        assert 'eps' in result.columns
        assert 'revenue' in result.columns
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_financial_data_from_source(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class,
        sample_financial_data
    ):
        """測試從資料來源獲取財務數據"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_financial_data.return_value = sample_financial_data
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_financial_data.return_value = None
        
        manager = DataManagerV2()
        result = manager.get_financial_data("2330", years=5)
        
        assert result is not None
        mock_yfinance_instance.get_financial_data.assert_called_once()
        mock_cache_instance.save_financial_data.assert_called_once()


class TestGetLatestEPS:
    """測試獲取最新 EPS 功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_latest_eps_from_source(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class
    ):
        """測試從資料來源獲取 EPS"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_latest_eps.return_value = 15.5
        
        manager = DataManagerV2()
        result = manager.get_latest_eps("2330")
        
        assert result == 15.5
        mock_yfinance_instance.get_latest_eps.assert_called_once()
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_latest_eps_from_default(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class
    ):
        """測試使用預設 EPS 值"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_latest_eps.return_value = 0.0  # 無法獲取
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_financial_data.return_value = None
        
        manager = DataManagerV2()
        result = manager.get_latest_eps("2330")  # 台積電有預設值
        
        # 應該返回預設值 32.0
        assert result == 32.0
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_latest_eps_no_data(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class
    ):
        """測試無法獲取 EPS 時返回 0"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_latest_eps.return_value = 0.0
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_financial_data.return_value = None
        
        manager = DataManagerV2()
        result = manager.get_latest_eps("9999")  # 不存在的股票
        
        assert result == 0.0


class TestGetStockInfo:
    """測試獲取股票資訊功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_stock_info_success(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class,
        sample_stock_info
    ):
        """測試成功獲取股票資訊"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_stock_info.return_value = sample_stock_info
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_stock_info.return_value = None
        
        manager = DataManagerV2()
        result = manager.get_stock_info("2330")
        
        assert result is not None
        assert result['stock_code'] == '2330'
        assert result['stock_name'] == '台積電'


class TestGetSharesOutstanding:
    """測試獲取流通股數功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_shares_outstanding_from_mops(
        self,
        mock_cache_class,
        mock_mops_class,
        mock_finmind,
        mock_yfinance
    ):
        """測試從 MOPS 獲取流通股數"""
        # MOPS 應該是第一優先
        mock_mops_instance = mock_mops_class.return_value
        mock_mops_instance.is_available = True
        mock_mops_instance.get_shares_outstanding.return_value = 25930380458
        
        mock_yfinance.return_value.is_available = True
        
        manager = DataManagerV2()
        result = manager.get_shares_outstanding("2330")
        
        assert result == 25930380458
        mock_mops_instance.get_shares_outstanding.assert_called_once()


class TestIntelligentFallback:
    """測試智能備援機制"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_fallback_to_secondary_source(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind_class,
        mock_yfinance_class,
        sample_price_data
    ):
        """測試主要來源失敗時切換到備援來源"""
        # YFinance 失敗
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_stock_price.side_effect = Exception("API Error")
        
        # FinMind 成功
        mock_finmind_instance = mock_finmind_class.return_value
        mock_finmind_instance.is_available = True
        mock_finmind_instance.is_ready.return_value = True
        mock_finmind_instance.get_stock_price.return_value = sample_price_data
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_stock_price.return_value = None
        
        manager = DataManagerV2()
        
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)
        result = manager.get_stock_price("2330", start_date, end_date)
        
        # 應該從 FinMind 獲取成功
        assert result is not None
        assert len(result) > 0
        
        # 驗證有嘗試 YFinance
        mock_yfinance_instance.get_stock_price.assert_called_once()
        # 驗證有嘗試 FinMind
        mock_finmind_instance.get_stock_price.assert_called_once()


class TestMemoryCache:
    """測試記憶體快取功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_memory_cache_hit(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class
    ):
        """測試記憶體快取命中"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_latest_eps.return_value = 15.5
        
        manager = DataManagerV2(enable_memory_cache=True)
        
        # 第一次調用 - 從資料來源
        result1 = manager.get_latest_eps("2330")
        assert result1 == 15.5
        
        # 第二次調用 - 應該從記憶體快取
        result2 = manager.get_latest_eps("2330")
        assert result2 == 15.5
        
        # 只應該呼叫一次資料來源（第二次是快取命中）
        assert mock_yfinance_instance.get_latest_eps.call_count == 1
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_clear_memory_cache(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance
    ):
        """測試清除記憶體快取"""
        mock_yfinance.return_value.is_available = True
        
        manager = DataManagerV2(enable_memory_cache=True)
        manager.memory_cache['test_key'] = ('test_data', 1234567890)
        
        assert len(manager.memory_cache) > 0
        
        manager.clear_memory_cache()
        
        assert len(manager.memory_cache) == 0


class TestNormalizeStockInput:
    """測試股票輸入標準化功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_normalize_stock_code(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class,
        sample_stock_info
    ):
        """測試標準化股票代碼"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_stock_info.return_value = sample_stock_info
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_stock_info.return_value = None
        
        manager = DataManagerV2()
        result = manager.normalize_stock_input("2330")
        
        assert result['is_valid'] is True
        assert result['stock_code'] == "2330"
        assert result['stock_name'] == '台積電'
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_normalize_invalid_input(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class
    ):
        """測試無效輸入"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_all_stocks.return_value = None
        mock_cache_instance.get_stock_info.return_value = None
        
        manager = DataManagerV2()
        result = manager.normalize_stock_input("不存在的股票")
        
        assert result['is_valid'] is False


class TestCalculateHistoricalGrowthRate:
    """測試計算歷史成長率功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_calculate_growth_rate_with_data(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class,
        sample_financial_data
    ):
        """測試使用歷史數據計算成長率"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_financial_data.return_value = sample_financial_data
        
        manager = DataManagerV2()
        result = manager.calculate_historical_growth_rate("2330", years=10)
        
        assert 'growth_rate_1_5' in result
        assert 'growth_rate_6_10' in result
        assert 'data_quality' in result
        assert result['data_quality'] in ['good', 'fair', 'poor']
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_calculate_growth_rate_no_data(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance
    ):
        """測試無歷史數據時使用預設值"""
        mock_yfinance.return_value.is_available = True
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_financial_data.return_value = None
        
        manager = DataManagerV2()
        result = manager.calculate_historical_growth_rate("9999", years=10)
        
        assert result['growth_rate_1_5'] == 0.15  # 預設值
        assert result['growth_rate_6_10'] == 0.08  # 預設值
        assert result['data_quality'] == 'poor'


class TestStatisticsAndMonitoring:
    """測試統計與監控功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_source_statistics(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class
    ):
        """測試獲取資料來源統計"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_latest_eps.return_value = 15.5
        
        manager = DataManagerV2()
        
        # 執行一些操作
        manager.get_latest_eps("2330")
        
        stats = manager.get_source_statistics()
        
        assert isinstance(stats, dict)
        assert 'YFinanceSource' in stats
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_quality_scores(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class,
        sample_price_data
    ):
        """測試獲取資料品質評分"""
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_stock_price.return_value = sample_price_data
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_stock_price.return_value = None
        
        manager = DataManagerV2()
        
        # 執行一些操作
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)
        manager.get_stock_price("2330", start_date, end_date)
        
        scores = manager.get_quality_scores("2330")
        
        assert isinstance(scores, dict)
        assert "2330" in scores


class TestDefaultEPS:
    """測試預設 EPS 值"""
    
    def test_default_eps_exists(self):
        """測試預設 EPS 字典存在"""
        assert hasattr(DataManagerV2, 'DEFAULT_EPS')
        assert isinstance(DataManagerV2.DEFAULT_EPS, dict)
    
    def test_default_eps_tsmc(self):
        """測試台積電的預設 EPS"""
        assert '2330' in DataManagerV2.DEFAULT_EPS
        assert DataManagerV2.DEFAULT_EPS['2330'] == 32.0
    
    def test_default_eps_coverage(self):
        """測試預設 EPS 涵蓋前50大股票"""
        assert len(DataManagerV2.DEFAULT_EPS) == 50


class TestGetLatestPrice:
    """測試獲取最新股價功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_latest_price_from_info(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class
    ):
        """測試從股票資訊獲取最新股價"""
        stock_info = {
            'stock_code': '2330',
            'stock_name': '台積電',
            'current_price': 500.0
        }
        
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_stock_info.return_value = stock_info
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_stock_info.return_value = None
        
        manager = DataManagerV2()
        result = manager.get_latest_price("2330")
        
        assert result == 500.0


class TestGetAllStocks:
    """測試獲取所有股票清單功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_get_all_stocks_from_cache(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance
    ):
        """測試從快取獲取股票清單"""
        stocks_df = pd.DataFrame({
            'stock_id': ['2330', '2317', '2454'],
            'stock_name': ['台積電', '鴻海', '聯發科']
        })
        
        mock_yfinance.return_value.is_available = True
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_all_stocks.return_value = stocks_df
        
        manager = DataManagerV2()
        result = manager.get_all_stocks()
        
        assert result is not None
        assert len(result) == 3
        assert '2330' in result['stock_id'].values


class TestClearCache:
    """測試清除快取功能"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_clear_all_cache(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance
    ):
        """測試清除所有快取"""
        mock_yfinance.return_value.is_available = True
        mock_cache_instance = mock_cache_class.return_value
        
        manager = DataManagerV2()
        manager.memory_cache['test'] = ('data', 1234567890)
        
        manager.clear_all_cache()
        
        # 驗證記憶體快取已清除
        assert len(manager.memory_cache) == 0
        # 驗證 SQLite 快取清除方法被呼叫
        mock_cache_instance.clear_cache.assert_called_once()


# ============================================================================
# 整合測試
# ============================================================================

@pytest.mark.integration
class TestDataManagerIntegration:
    """DataManager 整合測試"""
    
    @patch('app.data.manager.YFinanceSource')
    @patch('app.data.manager.FinMindSource')
    @patch('app.data.manager.MOPSSource')
    @patch('app.data.manager.SQLiteCache')
    def test_complete_workflow(
        self,
        mock_cache_class,
        mock_mops,
        mock_finmind,
        mock_yfinance_class,
        sample_financial_data,
        sample_price_data
    ):
        """測試完整的數據獲取工作流程"""
        # 設定 Mock
        mock_yfinance_instance = mock_yfinance_class.return_value
        mock_yfinance_instance.is_available = True
        mock_yfinance_instance.is_ready.return_value = True
        mock_yfinance_instance.get_latest_eps.return_value = 15.5
        mock_yfinance_instance.get_stock_price.return_value = sample_price_data
        mock_yfinance_instance.get_financial_data.return_value = sample_financial_data
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.get_stock_price.return_value = None
        mock_cache_instance.get_financial_data.return_value = None
        
        manager = DataManagerV2()
        
        # 1. 獲取 EPS
        eps = manager.get_latest_eps("2330")
        assert eps == 15.5
        
        # 2. 獲取價格數據
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)
        price_data = manager.get_stock_price("2330", start_date, end_date)
        assert price_data is not None
        
        # 3. 獲取財務數據
        financial_data = manager.get_financial_data("2330", years=5)
        assert financial_data is not None
        
        # 4. 檢查統計資訊
        stats = manager.get_source_statistics()
        assert len(stats) > 0
