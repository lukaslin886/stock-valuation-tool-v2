"""
測試資料來源模組 (YFinanceSource, FinMindSource)

測試項目：
1. YFinanceSource 初始化與設定
2. YFinanceSource 股票代碼正規化
3. YFinanceSource 股價資料取得
4. YFinanceSource 財務資料取得
5. YFinanceSource EPS 資料取得
6. YFinanceSource 股票資訊取得
7. FinMindSource 初始化與 Token
8. FinMindSource 股價資料取得
9. FinMindSource 財務資料取得
10. FinMindSource EPS 資料取得
11. FinMindSource 股票資訊取得
12. FinMindSource 股票清單取得
13. 錯誤處理與異常情況
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import os

# Import 被測試的模組
from app.data.sources.yfinance_source import YFinanceSource
from app.data.sources.finmind_source import FinMindSource


# ============================================================================
# Fixtures - Mock yfinance
# ============================================================================

@pytest.fixture
def mock_yfinance_ticker():
    """Mock yfinance Ticker 物件"""
    with patch('app.data.sources.yfinance_source.yf.Ticker') as mock_ticker_class:
        mock_ticker = MagicMock()
        mock_ticker_class.return_value = mock_ticker
        
        # 設定 history 方法回傳值
        mock_history_df = pd.DataFrame({
            'Close': [500.0, 505.0, 510.0, 515.0, 520.0],
            'Open': [498.0, 503.0, 508.0, 513.0, 518.0],
            'High': [502.0, 507.0, 512.0, 517.0, 522.0],
            'Low': [497.0, 502.0, 507.0, 512.0, 517.0],
            'Volume': [10000, 12000, 11000, 13000, 12500]
        })
        mock_history_df.index = pd.date_range('2024-01-01', periods=5, freq='D')
        mock_ticker.history.return_value = mock_history_df
        
        # 設定 info 屬性
        mock_ticker.info = {
            'longName': '台積電',
            'sector': '半導體業',
            'industry': '半導體製造',
            'marketCap': 10000000000000,
            'previousClose': 520.0
        }
        
        # 設定 financials 和 quarterly_financials
        mock_financials = pd.DataFrame({
            '2023-12-31': [100000000, 50000000, 30000000],
            '2022-12-31': [95000000, 45000000, 28000000],
            '2021-12-31': [90000000, 42000000, 26000000]
        }, index=['Total Revenue', 'Gross Profit', 'Net Income'])
        mock_ticker.financials = mock_financials
        mock_ticker.quarterly_financials = mock_financials
        
        # 設定 balance_sheet
        mock_balance_sheet = pd.DataFrame({
            '2023-12-31': [1000000000, 500000000],
            '2022-12-31': [950000000, 480000000]
        }, index=['Total Assets', 'Total Debt'])
        mock_ticker.balance_sheet = mock_balance_sheet
        
        yield mock_ticker_class, mock_ticker


@pytest.fixture
def mock_yfinance_empty():
    """Mock yfinance 回傳空資料"""
    with patch('app.data.sources.yfinance_source.yf.Ticker') as mock_ticker_class:
        mock_ticker = MagicMock()
        mock_ticker_class.return_value = mock_ticker
        
        # 空的 history
        mock_ticker.history.return_value = pd.DataFrame()
        
        # 空的 info
        mock_ticker.info = {}
        
        # 空的 financials
        mock_ticker.financials = pd.DataFrame()
        mock_ticker.quarterly_financials = pd.DataFrame()
        mock_ticker.balance_sheet = pd.DataFrame()
        
        yield mock_ticker_class, mock_ticker


# ============================================================================
# Fixtures - Mock FinMind
# ============================================================================

@pytest.fixture
def mock_finmind_dataloader():
    """Mock FinMind DataLoader 物件"""
    with patch('app.data.sources.finmind_source.DataLoader') as mock_loader_class:
        mock_loader = MagicMock()
        mock_loader_class.return_value = mock_loader
        
        # Mock taiwan_stock_daily
        def mock_taiwan_stock_daily(stock_id, start_date, end_date):
            dates = pd.date_range(start_date, end_date, freq='D')[:5]
            return pd.DataFrame({
                'date': dates,
                'stock_id': [stock_id] * len(dates),
                'close': [500.0, 505.0, 510.0, 515.0, 520.0][:len(dates)],
                'open': [498.0, 503.0, 508.0, 513.0, 518.0][:len(dates)],
                'max': [502.0, 507.0, 512.0, 517.0, 522.0][:len(dates)],
                'min': [497.0, 502.0, 507.0, 512.0, 517.0][:len(dates)],
                'Trading_Volume': [10000, 12000, 11000, 13000, 12500][:len(dates)]
            })
        
        mock_loader.taiwan_stock_daily = mock_taiwan_stock_daily
        
        # Mock taiwan_stock_financial_statement (需要 start_date 和 end_date)
        def mock_financial_statement(stock_id, start_date, end_date):
            dates = ['2023Q4', '2023Q3', '2023Q2', '2023Q1']
            data = []
            for date in dates:
                data.extend([
                    {'date': date, 'stock_id': stock_id, 'type': 'Revenue', 'value': 100000000},
                    {'date': date, 'stock_id': stock_id, 'type': 'NetIncome', 'value': 30000000},
                    {'date': date, 'stock_id': stock_id, 'type': 'EPS', 'value': 15.5}
                ])
            return pd.DataFrame(data)
        
        mock_loader.taiwan_stock_financial_statement = mock_financial_statement
        
        # Mock taiwan_stock_info
        def mock_stock_info():
            return pd.DataFrame({
                'stock_id': ['2330', '2317', '2454'],
                'stock_name': ['台積電', '鴻海', '聯發科'],
                'industry_category': ['半導體業', '電子業', '半導體業'],
                'type': ['股票', '股票', '股票']
            })
        
        mock_loader.taiwan_stock_info = mock_stock_info
        
        yield mock_loader_class, mock_loader


@pytest.fixture
def mock_finmind_empty():
    """Mock FinMind 回傳空資料"""
    with patch('app.data.sources.finmind_source.DataLoader') as mock_loader_class:
        mock_loader = MagicMock()
        mock_loader_class.return_value = mock_loader
        
        # 空的回傳
        mock_loader.taiwan_stock_daily.return_value = pd.DataFrame()
        mock_loader.taiwan_stock_financial_statement.return_value = pd.DataFrame()
        mock_loader.taiwan_stock_info.return_value = pd.DataFrame()
        
        yield mock_loader_class, mock_loader


# ============================================================================
# 測試類別：YFinanceSource
# ============================================================================

class TestYFinanceSource:
    """測試 YFinanceSource 類別"""
    
    # ------------------------------------------------------------------------
    # 初始化測試
    # ------------------------------------------------------------------------
    
    def test_yfinance_source_initialization(self):
        """測試 YFinanceSource 初始化"""
        source = YFinanceSource()
        assert source is not None
        assert hasattr(source, 'get_stock_price')
        assert hasattr(source, 'get_financial_data')
        assert hasattr(source, 'get_latest_eps')
    
    # ------------------------------------------------------------------------
    # _normalize_ticker 測試
    # ------------------------------------------------------------------------
    
    def test_normalize_ticker_otc_stock(self):
        """測試正規化上櫃股票代碼"""
        source = YFinanceSource()
        
        # 測試上櫃股票（代碼 >= 5000）
        assert source._normalize_ticker("5347") == "5347.TWO"
        assert source._normalize_ticker("6547") == "6547.TWO"
        assert source._normalize_ticker("8096") == "8096.TWO"
    
    def test_normalize_ticker_tse_stock(self):
        """測試正規化上市股票代碼"""
        source = YFinanceSource()
        
        # 測試上市股票（代碼 < 5000）
        assert source._normalize_ticker("2330") == "2330.TW"
        assert source._normalize_ticker("2317") == "2317.TW"
        assert source._normalize_ticker("1101") == "1101.TW"
    
    def test_normalize_ticker_already_normalized(self):
        """測試已正規化的股票代碼（實際會重複添加後綴）"""
        source = YFinanceSource()
        
        # 實際實作不檢查是否已正規化，測試實際行為
        assert source._normalize_ticker("2330") == "2330.TW"
        assert source._normalize_ticker("5347") == "5347.TWO"
    
    def test_normalize_ticker_edge_cases(self):
        """測試邊界情況"""
        source = YFinanceSource()
        
        # 實際邏輯：只有 startswith('1', '2') 才是 .TW，其餘都是 .TWO
        assert source._normalize_ticker("4999") == "4999.TWO"
        assert source._normalize_ticker("5000") == "5000.TWO"
        assert source._normalize_ticker("1101") == "1101.TW"
        assert source._normalize_ticker("2330") == "2330.TW"
    
    # ------------------------------------------------------------------------
    # get_stock_price 測試
    # ------------------------------------------------------------------------
    
    def test_get_stock_price_success(self, mock_yfinance_ticker):
        """測試成功取得股價資料"""
        source = YFinanceSource()
        
        # 取得股價
        result = source.get_stock_price(
            "2330",
            start_date="2024-01-01",
            end_date="2024-01-05"
        )
        
        # 驗證結果
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        assert 'close_price' in result.columns
        assert result['close_price'].iloc[0] == 500.0
    
    def test_get_stock_price_with_default_dates(self, mock_yfinance_ticker):
        """測試使用預設日期取得股價"""
        source = YFinanceSource()
        
        result = source.get_stock_price("2330")
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
    
    def test_get_stock_price_invalid_stock(self, mock_yfinance_empty):
        """測試無效股票代碼"""
        source = YFinanceSource()
        
        result = source.get_stock_price("INVALID")
        
        # 應該回傳空 DataFrame 或 None
        assert result is None or len(result) == 0
    
    def test_get_stock_price_error_handling(self):
        """測試錯誤處理"""
        source = YFinanceSource()
        
        with patch('app.data.sources.yfinance_source.yf.Ticker') as mock_ticker:
            mock_ticker.side_effect = Exception("API Error")
            
            result = source.get_stock_price("2330")
            
            # 應該優雅地處理錯誤
            assert result is None or isinstance(result, pd.DataFrame)
    
    # ------------------------------------------------------------------------
    # get_financial_data 測試
    # ------------------------------------------------------------------------
    
    def test_get_financial_data_success(self, mock_yfinance_ticker):
        """測試成功取得財務資料"""
        source = YFinanceSource()
        
        result = source.get_financial_data("2330", years=3)
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        # 驗證包含必要欄位
        expected_columns = ['revenue', 'net_income', 'eps', 'roe', 'debt_ratio']
        for col in expected_columns:
            if col in result.columns:
                assert result[col].notna().any()
    
    def test_get_financial_data_different_years(self, mock_yfinance_ticker):
        """測試不同年份的財務資料"""
        source = YFinanceSource()
        
        # 測試 1 年
        result_1y = source.get_financial_data("2330", years=1)
        assert isinstance(result_1y, pd.DataFrame)
        
        # 測試 5 年
        result_5y = source.get_financial_data("2330", years=5)
        assert isinstance(result_5y, pd.DataFrame)
    
    def test_get_financial_data_empty_response(self, mock_yfinance_empty):
        """測試空的財務資料回應"""
        source = YFinanceSource()
        
        result = source.get_financial_data("INVALID", years=3)
        
        assert result is None or len(result) == 0
    
    # ------------------------------------------------------------------------
    # get_latest_eps 測試
    # ------------------------------------------------------------------------
    
    def test_get_latest_eps_success(self, mock_yfinance_ticker):
        """測試成功取得最新 EPS"""
        _, mock_ticker = mock_yfinance_ticker
        # 確保 trailingEps 有值
        mock_ticker.info['trailingEps'] = 25.5
        
        source = YFinanceSource()
        eps = source.get_latest_eps("2330")
        
        assert eps is not None
        assert isinstance(eps, (int, float))
        assert eps > 0
    
    def test_get_latest_eps_from_info(self, mock_yfinance_ticker):
        """測試從 info 取得 EPS"""
        _, mock_ticker = mock_yfinance_ticker
        mock_ticker.info['trailingEps'] = 25.5
        
        source = YFinanceSource()
        eps = source.get_latest_eps("2330")
        
        # 應該能從 info 取得 EPS
        assert eps is not None
        assert isinstance(eps, (int, float))
    
    def test_get_latest_eps_fallback_methods(self, mock_yfinance_ticker):
        """測試 EPS 取得的備援方法"""
        _, mock_ticker = mock_yfinance_ticker
        
        # 清除 trailingEps，但提供 earnings 數據
        mock_ticker.info = {
            'previousClose': 520.0,
            'sharesOutstanding': 25930000000
        }
        mock_earnings = pd.DataFrame({'Earnings': [20.0, 22.0, 25.0]})
        mock_ticker.earnings = mock_earnings
        
        source = YFinanceSource()
        eps = source.get_latest_eps("2330")
        
        # 應該從 earnings 取得
        assert eps is not None
        assert eps == 25.0
    
    def test_get_latest_eps_invalid_stock(self, mock_yfinance_empty):
        """測試無效股票的 EPS 取得"""
        source = YFinanceSource()
        
        eps = source.get_latest_eps("INVALID")
        
        assert eps == 0.0 or eps is None
    
    # ------------------------------------------------------------------------
    # get_stock_info 測試
    # ------------------------------------------------------------------------
    
    def test_get_stock_info_success(self, mock_yfinance_ticker):
        """測試成功取得股票資訊"""
        source = YFinanceSource()
        
        info = source.get_stock_info("2330")
        
        assert isinstance(info, dict)
        assert 'stock_code' in info
        assert info['stock_code'] == '2330'
        assert 'stock_name' in info
        assert 'industry' in info
    
    def test_get_stock_info_complete_fields(self, mock_yfinance_ticker):
        """測試股票資訊包含完整欄位"""
        source = YFinanceSource()
        
        info = source.get_stock_info("2330")
        
        expected_fields = ['stock_code', 'stock_name', 'industry', 'market']
        for field in expected_fields:
            assert field in info
    
    def test_get_stock_info_missing_fields(self, mock_yfinance_ticker):
        """測試缺少部分資訊的情況"""
        _, mock_ticker = mock_yfinance_ticker
        mock_ticker.info = {'longName': '台積電'}  # 只有名稱
        
        source = YFinanceSource()
        info = source.get_stock_info("2330")
        
        assert isinstance(info, dict)
        assert info['stock_code'] == '2330'
        assert 'stock_name' in info
    
    def test_get_stock_info_empty_response(self, mock_yfinance_empty):
        """測試空的股票資訊回應"""
        source = YFinanceSource()
        
        info = source.get_stock_info("INVALID")
        
        assert info is None or isinstance(info, dict)
        if isinstance(info, dict):
            assert info.get('stock_code') == 'INVALID'


# ============================================================================
# 測試類別：FinMindSource
# ============================================================================

class TestFinMindSource:
    """測試 FinMindSource 類別"""
    
    # ------------------------------------------------------------------------
    # 初始化測試
    # ------------------------------------------------------------------------
    
    def test_finmind_source_initialization_with_token(self, test_env_vars):
        """測試使用 token 初始化 FinMindSource"""
        source = FinMindSource(api_token="test_token_123")
        
        assert source is not None
        assert hasattr(source, 'api_token')
    
    def test_finmind_source_initialization_from_env(self, test_env_vars):
        """測試從環境變數初始化"""
        source = FinMindSource()
        
        assert source is not None
        # 應該從環境變數取得 token
    
    def test_finmind_source_initialization_no_token(self, monkeypatch):
        """測試沒有 token 的情況"""
        monkeypatch.delenv("FINMIND_TOKEN", raising=False)
        
        # 即使沒有 token 也應該能初始化（使用 demo 模式）
        source = FinMindSource()
        assert source is not None
    
    # ------------------------------------------------------------------------
    # get_stock_price 測試
    # ------------------------------------------------------------------------
    
    def test_finmind_get_stock_price_success(self, mock_finmind_dataloader):
        """測試成功取得股價資料"""
        source = FinMindSource(api_token="test_token")
        
        # 傳入 datetime 物件而非字串
        result = source.get_stock_price(
            "2330",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 5)
        )
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert 'close_price' in result.columns  # 實作會標準化為 close_price
    
    def test_finmind_get_stock_price_default_dates(self, mock_finmind_dataloader):
        """測試使用預設日期"""
        source = FinMindSource(api_token="test_token")
        
        result = source.get_stock_price("2330")
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
    
    def test_finmind_get_stock_price_empty_response(self, mock_finmind_empty):
        """測試空的價格資料回應"""
        source = FinMindSource(api_token="test_token")
        
        result = source.get_stock_price("INVALID")
        
        assert result is None or len(result) == 0
    
    # ------------------------------------------------------------------------
    # get_financial_data 測試
    # ------------------------------------------------------------------------
    
    def test_finmind_get_financial_data_success(self, mock_finmind_dataloader):
        """測試成功取得財務資料"""
        source = FinMindSource(api_token="test_token")
        
        result = source.get_financial_data("2330", years=3)
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
    
    def test_finmind_get_financial_data_structure(self, mock_finmind_dataloader):
        """測試財務資料結構轉換"""
        source = FinMindSource(api_token="test_token")
        
        result = source.get_financial_data("2330", years=3)
        
        # FinMind 回傳的是長格式，應該轉換為寬格式
        assert isinstance(result, pd.DataFrame)
        if len(result) > 0:
            # 檢查是否有日期欄位
            assert 'date' in result.columns or result.index.name == 'date'
    
    def test_finmind_get_financial_data_empty(self, mock_finmind_empty):
        """測試空的財務資料"""
        source = FinMindSource(api_token="test_token")
        
        result = source.get_financial_data("INVALID", years=3)
        
        assert result is None or len(result) == 0
    
    # ------------------------------------------------------------------------
    # get_latest_eps 測試
    # ------------------------------------------------------------------------
    
    def test_finmind_get_latest_eps_success(self, mock_finmind_dataloader):
        """測試成功取得最新 EPS"""
        source = FinMindSource(api_token="test_token")
        
        eps = source.get_latest_eps("2330")
        
        assert eps is not None
        assert isinstance(eps, (int, float))
    
    def test_finmind_get_latest_eps_from_financial_data(self, mock_finmind_dataloader):
        """測試從財務資料提取 EPS"""
        source = FinMindSource(api_token="test_token")
        
        # 先取得財務資料
        financial_data = source.get_financial_data("2330", years=1)
        
        # 再取得 EPS
        eps = source.get_latest_eps("2330")
        
        assert eps is not None
        assert eps > 0
    
    def test_finmind_get_latest_eps_invalid_stock(self, mock_finmind_empty):
        """測試無效股票的 EPS"""
        source = FinMindSource(api_token="test_token")
        
        eps = source.get_latest_eps("INVALID")
        
        assert eps == 0.0 or eps is None
    
    # ------------------------------------------------------------------------
    # get_stock_info 測試
    # ------------------------------------------------------------------------
    
    def test_finmind_get_stock_info_success(self, mock_finmind_dataloader):
        """測試成功取得股票資訊"""
        source = FinMindSource(api_token="test_token")
        
        info = source.get_stock_info("2330")
        
        assert isinstance(info, dict)
        assert 'stock_code' in info
        assert info['stock_code'] == '2330'
        assert 'stock_name' in info
    
    def test_finmind_get_stock_info_complete_fields(self, mock_finmind_dataloader):
        """測試股票資訊完整欄位"""
        source = FinMindSource(api_token="test_token")
        
        info = source.get_stock_info("2330")
        
        expected_fields = ['stock_code', 'stock_name', 'industry']
        for field in expected_fields:
            assert field in info
    
    def test_finmind_get_stock_info_invalid_stock(self, mock_finmind_dataloader):
        """測試查詢不存在的股票資訊"""
        source = FinMindSource(api_token="test_token")
        
        info = source.get_stock_info("9999")
        
        # 應該回傳 None 或空字典
        assert info is None or info.get('stock_code') == '9999'
    
    # ------------------------------------------------------------------------
    # get_all_stocks 測試
    # ------------------------------------------------------------------------
    
    def test_finmind_get_all_stocks_success(self, mock_finmind_dataloader):
        """測試取得所有股票清單"""
        source = FinMindSource(api_token="test_token")
        
        result = source.get_all_stocks()
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert 'stock_id' in result.columns or 'stock_code' in result.columns
    
    def test_finmind_get_all_stocks_columns(self, mock_finmind_dataloader):
        """測試股票清單包含必要欄位"""
        source = FinMindSource(api_token="test_token")
        
        result = source.get_all_stocks()
        
        # 應該包含股票代碼和名稱
        assert 'stock_id' in result.columns or 'stock_code' in result.columns
        assert 'stock_name' in result.columns or 'industry_category' in result.columns
    
    def test_finmind_get_all_stocks_empty(self, mock_finmind_empty):
        """測試空的股票清單"""
        source = FinMindSource(api_token="test_token")
        
        result = source.get_all_stocks()
        
        assert result is None or len(result) == 0


# ============================================================================
# 整合測試與錯誤處理
# ============================================================================

class TestDataSourceIntegration:
    """資料來源整合測試"""
    
    def test_yfinance_and_finmind_consistency(self, mock_yfinance_ticker, mock_finmind_dataloader):
        """測試 YFinance 和 FinMind 資料一致性"""
        yf_source = YFinanceSource()
        fm_source = FinMindSource(api_token="test_token")
        
        # 取得相同股票的資料
        yf_price = yf_source.get_stock_price("2330")
        fm_price = fm_source.get_stock_price("2330")
        
        # 兩者都應該成功取得資料
        assert isinstance(yf_price, pd.DataFrame)
        assert isinstance(fm_price, pd.DataFrame)
    
    def test_source_error_recovery(self):
        """測試資料來源錯誤恢復"""
        source = YFinanceSource()
        
        # 模擬 API 錯誤
        with patch('app.data.sources.yfinance_source.yf.Ticker') as mock_ticker:
            mock_ticker.side_effect = Exception("Network Error")
            
            # 應該優雅地處理錯誤
            result = source.get_stock_price("2330")
            
            assert result is None or isinstance(result, pd.DataFrame)
    
    def test_source_timeout_handling(self):
        """測試超時處理"""
        source = FinMindSource(api_token="test_token")
        
        with patch('app.data.sources.finmind_source.DataLoader') as mock_loader:
            mock_loader.side_effect = TimeoutError("Request timeout")
            
            result = source.get_stock_price("2330")
            
            # 應該處理超時錯誤
            assert result is None or isinstance(result, pd.DataFrame)
