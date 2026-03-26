
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.data.manager import DataManagerV2
from app.data.sources.base import DataSource
from unittest.mock import MagicMock

def test_anomaly_integration():
    # 建立一個傳回異常數據的 Mock 資料源
    class AnomalySource(DataSource):
        def __init__(self):
            super().__init__("AnomalySource")
        def _init_source(self):
            self.is_available = True
        def get_stock_price(self, stock_code, start_date=None, end_date=None):
            dates = pd.date_range(start=start_date, end=end_date, periods=10)
            prices = [100.0] * 9 + [500.0]  # 最後一筆是離群值 (5倍)
            return pd.DataFrame({
                'date': dates,
                'close_price': prices,
                'volume': [1000] * 10
            })
        def get_financial_data(self, stock_code, years=5):
            return pd.DataFrame({
                'date': [datetime.now() - timedelta(days=30*i) for i in range(5)],
                'eps': [1.0, 1.1, 5.0, 1.2, 1.3],  # 5.0 是異常值
                'revenue': [100, 110, 120, 130, 140]
            })
        def get_latest_eps(self, stock_code): return 1.0
        def get_stock_info(self, stock_code): return {}
        def get_all_stocks(self): return pd.DataFrame()

    # 初始化管理器並插入 Mock 來源
    manager = DataManagerV2(db_path="data/test_anomaly.db")
    manager.sources = [AnomalySource()]
    
    print("\n--- 測試價格異常偵測 ---")
    price_data = manager.get_stock_price("2330", datetime.now()-timedelta(days=30), datetime.now())
    
    # 檢查是否產生了警告
    warnings = manager.data_warnings["2330"]
    print(f"偵測到的警告: {warnings}")
    
    has_price_anomaly = any("價格存在異常值" in w for w in warnings)
    print(f"價格異常偵測成功: {has_price_anomaly}")
    
    print("\n--- 測試財務異常偵測 ---")
    fin_data = manager.get_financial_data("2330", years=5)
    
    warnings = manager.data_warnings["2330"]
    has_fin_anomaly = any("EPS 存在異常值" in w or "EPS 存在劇烈變化" in w for w in warnings)
    print(f"財務異常偵測成功: {has_fin_anomaly}")
    
    # 檢查品質分數是否受損
    scores = manager.quality_scores["2330"]
    print(f"品質分數記錄: {scores}")
    
    assert has_price_anomaly
    assert has_fin_anomaly
    print("\n✅ P1-03 整合驗證成功！")

if __name__ == "__main__":
    test_anomaly_integration()
