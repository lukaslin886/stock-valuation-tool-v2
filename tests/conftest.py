"""
pytest 共用 fixtures 設定檔

提供測試用的共用資料、Mock 物件、和工具函式
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
from unittest.mock import Mock, MagicMock
import sys
import os

# 添加專案根目錄到路徑
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# ============================================================================
# 測試資料 Fixtures
# ============================================================================

@pytest.fixture
def sample_stock_code():
    """提供測試用股票代碼"""
    return "2330"


@pytest.fixture
def sample_stock_codes():
    """提供測試用股票代碼列表"""
    return ["2330", "2317", "2454", "2308", "2881"]


@pytest.fixture
def valid_eps_values():
    """提供有效的 EPS 測試值"""
    return {
        'positive': 15.5,
        'zero': 0.0,
        'negative': -5.2,
        'high': 50.0,
        'low': 0.1
    }


@pytest.fixture
def invalid_eps_values():
    """提供無效的 EPS 測試值"""
    return {
        'too_high': 600.0,
        'too_low': -150.0,
        'nan': np.nan,
        'none': None,
        'string': "not_a_number"
    }


@pytest.fixture
def valid_price_values():
    """提供有效的股價測試值"""
    return {
        'normal': 500.0,
        'low': 10.0,
        'high': 1000.0,
        'decimal': 123.45
    }


@pytest.fixture
def invalid_price_values():
    """提供無效的股價測試值"""
    return {
        'zero': 0.0,
        'negative': -50.0,
        'too_high': 15000.0,
        'nan': np.nan,
        'none': None
    }


@pytest.fixture
def sample_financial_data():
    """提供測試用財務數據 DataFrame"""
    dates = pd.date_range(start='2020-01-01', periods=12, freq='Q')
    
    df = pd.DataFrame({
        'date': dates,
        'eps': [3.5, 4.2, 4.8, 5.1, 5.5, 6.0, 6.3, 6.8, 7.2, 7.5, 8.0, 8.5],
        'revenue': [100, 105, 110, 115, 120, 125, 130, 135, 140, 145, 150, 155],
        'net_income': [35, 42, 48, 51, 55, 60, 63, 68, 72, 75, 80, 85],
        'total_assets': [1000, 1050, 1100, 1150, 1200, 1250, 1300, 1350, 1400, 1450, 1500, 1550]
    })
    
    return df


@pytest.fixture
def incomplete_financial_data():
    """提供不完整的財務數據（含缺失值）"""
    dates = pd.date_range(start='2020-01-01', periods=12, freq='Q')
    
    df = pd.DataFrame({
        'date': dates,
        'eps': [3.5, np.nan, 4.8, np.nan, 5.5, 6.0, np.nan, 6.8, 7.2, np.nan, 8.0, 8.5],
        'revenue': [100, 105, np.nan, 115, np.nan, 125, 130, np.nan, 140, 145, np.nan, 155]
    })
    
    return df


@pytest.fixture
def sample_price_data():
    """提供測試用價格數據 DataFrame"""
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    
    # 模擬股價走勢（基準價 500，帶隨機波動）
    base_price = 500
    prices = [base_price + np.random.uniform(-20, 20) for _ in range(30)]
    volumes = [np.random.randint(10000, 100000) for _ in range(30)]
    
    df = pd.DataFrame({
        'date': dates,
        'close_price': prices,
        'open_price': [p + np.random.uniform(-5, 5) for p in prices],
        'high_price': [p + np.random.uniform(0, 10) for p in prices],
        'low_price': [p - np.random.uniform(0, 10) for p in prices],
        'volume': volumes
    })
    
    return df


@pytest.fixture
def anomaly_price_data():
    """提供含異常值的價格數據"""
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    
    prices = [500 + np.random.uniform(-20, 20) for _ in range(30)]
    # 插入異常值
    prices[10] = 1000  # 突然翻倍
    prices[20] = 0     # 無效值
    
    df = pd.DataFrame({
        'date': dates,
        'close_price': prices,
        'volume': [np.random.randint(10000, 100000) for _ in range(30)]
    })
    
    return df


@pytest.fixture
def sample_stock_info():
    """提供測試用股票資訊"""
    return {
        'stock_code': '2330',
        'stock_name': '台積電',
        'industry': '半導體業',
        'market_cap': 10000000,
        'listing_date': '1994-09-05'
    }


# ============================================================================
# Mock 物件 Fixtures
# ============================================================================

@pytest.fixture
def mock_data_source():
    """提供 Mock 資料來源"""
    mock = Mock()
    
    # 設定預設回傳值
    mock.get_stock_price.return_value = 500.0
    mock.get_latest_eps.return_value = 15.5
    mock.get_financial_data.return_value = pd.DataFrame({
        'date': pd.date_range('2020-01-01', periods=4, freq='Q'),
        'eps': [3.5, 4.0, 4.5, 5.0],
        'revenue': [100, 105, 110, 115]
    })
    mock.get_stock_info.return_value = {
        'stock_code': '2330',
        'stock_name': '台積電'
    }
    
    return mock


@pytest.fixture
def mock_cache():
    """提供 Mock 快取系統"""
    mock = Mock()
    
    # 模擬快取行為
    cache_data = {}
    
    def get_side_effect(key):
        return cache_data.get(key)
    
    def set_side_effect(key, value, ttl=None):
        cache_data[key] = value
    
    mock.get.side_effect = get_side_effect
    mock.set.side_effect = set_side_effect
    mock.clear.side_effect = cache_data.clear
    
    return mock


@pytest.fixture
def mock_api_client():
    """提供 Mock API 客戶端"""
    mock = Mock()
    
    # 設定 API 回應
    mock.get.return_value = {'status': 'success', 'data': []}
    mock.post.return_value = {'status': 'success'}
    mock.is_connected.return_value = True
    
    return mock


# ============================================================================
# 應用程式物件 Fixtures
# ============================================================================

@pytest.fixture
def dcf_calculator():
    """提供 DCFCalculator 實例"""
    from app.dcf_calculator import DCFCalculator
    return DCFCalculator()


# ============================================================================
# 環境設定 Fixtures
# ============================================================================

@pytest.fixture
def test_data_dir(tmp_path):
    """建立臨時測試資料目錄"""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir()
    
    # 建立子目錄
    (data_dir / "cache").mkdir()
    (data_dir / "reports").mkdir()
    
    return data_dir


@pytest.fixture
def test_env_vars(monkeypatch):
    """設定測試用環境變數"""
    monkeypatch.setenv("FINMIND_TOKEN", "test_token_123")
    monkeypatch.setenv("FINLAB_API_TOKEN", "test_finlab_token")
    monkeypatch.setenv("TEST_MODE", "true")


@pytest.fixture
def clean_cache_db(tmp_path):
    """提供乾淨的測試用快取資料庫"""
    db_path = tmp_path / "test_cache.db"
    yield db_path
    
    # 清理
    if db_path.exists():
        db_path.unlink()


# ============================================================================
# 工具函式 Fixtures
# ============================================================================

@pytest.fixture
def assert_dataframe_equal():
    """提供 DataFrame 比較函式"""
    def _assert_equal(df1, df2, **kwargs):
        """比較兩個 DataFrame 是否相等"""
        pd.testing.assert_frame_equal(df1, df2, **kwargs)
    
    return _assert_equal


@pytest.fixture
def create_test_csv(tmp_path):
    """提供建立測試 CSV 檔案的函式"""
    def _create_csv(filename, data):
        """建立測試用 CSV 檔案"""
        filepath = tmp_path / filename
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
        return filepath
    
    return _create_csv


@pytest.fixture
def timer():
    """提供計時器工具"""
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = datetime.now()
        
        def stop(self):
            self.end_time = datetime.now()
        
        def elapsed(self):
            if self.start_time and self.end_time:
                return (self.end_time - self.start_time).total_seconds()
            return None
    
    return Timer()


# ============================================================================
# 測試配置
# ============================================================================

def pytest_configure(config):
    """pytest 配置"""
    # 註冊自定義 markers
    config.addinivalue_line(
        "markers", "unit: 單元測試"
    )
    config.addinivalue_line(
        "markers", "integration: 整合測試"
    )
    config.addinivalue_line(
        "markers", "performance: 效能測試"
    )
    config.addinivalue_line(
        "markers", "slow: 執行時間較長的測試"
    )
    config.addinivalue_line(
        "markers", "api: 需要 API 存取的測試"
    )
    config.addinivalue_line(
        "markers", "cache: 與快取互動的測試"
    )


def pytest_collection_modifyitems(config, items):
    """修改測試項目收集"""
    # 為未標記的測試自動添加 unit marker
    for item in items:
        if not any(mark.name in ['unit', 'integration', 'performance'] for mark in item.iter_markers()):
            item.add_marker(pytest.mark.unit)
