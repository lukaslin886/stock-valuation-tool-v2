"""
DataValidator 單元測試

測試 DataValidator 類別的所有驗證功能
"""

import pytest
import pandas as pd
import numpy as np
from app.data.validator import DataValidator


class TestDataValidatorInit:
    """測試 DataValidator 初始化"""
    
    def test_init_creates_instance(self):
        """測試建立 DataValidator 實例"""
        validator = DataValidator()
        assert validator is not None
        assert isinstance(validator, DataValidator)
    
    def test_init_empty_warnings_and_errors(self):
        """測試初始化後警告和錯誤列表為空"""
        validator = DataValidator()
        assert len(validator.get_warnings()) == 0
        assert len(validator.get_errors()) == 0


class TestValidateEPS:
    """測試 EPS 驗證功能"""
    
    def test_validate_positive_eps(self, valid_eps_values):
        """測試驗證正常的正值 EPS"""
        validator = DataValidator()
        result = validator.validate_eps(valid_eps_values['positive'], "2330")
        
        assert result['is_valid'] is True
        assert result['value'] == valid_eps_values['positive']
        assert result['severity'] == 'ok'
        assert len(result['warnings']) == 0
    
    def test_validate_zero_eps(self, valid_eps_values):
        """測試驗證 EPS 為零的情況"""
        validator = DataValidator()
        result = validator.validate_eps(valid_eps_values['zero'], "2330")
        
        assert result['is_valid'] is True
        assert result['value'] == 0.0
        assert result['severity'] == 'warning'
        assert len(result['warnings']) > 0
        assert 'EPS 為零' in result['warnings'][0]
    
    def test_validate_negative_eps(self, valid_eps_values):
        """測試驗證負值 EPS（虧損）"""
        validator = DataValidator()
        result = validator.validate_eps(valid_eps_values['negative'], "2330")
        
        assert result['is_valid'] is True
        assert result['value'] == valid_eps_values['negative']
        assert result['severity'] == 'warning'
        assert any('負值' in w or '虧損' in w for w in result['warnings'])
    
    def test_validate_high_eps(self, valid_eps_values):
        """測試驗證高 EPS 值"""
        validator = DataValidator()
        result = validator.validate_eps(valid_eps_values['high'], "2330")
        
        assert result['is_valid'] is True
        assert result['value'] == valid_eps_values['high']
    
    def test_validate_too_high_eps(self, invalid_eps_values):
        """測試驗證過高的 EPS（超出合理範圍）"""
        validator = DataValidator()
        result = validator.validate_eps(invalid_eps_values['too_high'], "2330")
        
        assert result['is_valid'] is True
        assert result['value'] == DataValidator.EPS_MAX  # 應被限制在最大值
        assert result['severity'] == 'warning'
        assert any('過高' in w for w in result['warnings'])
    
    def test_validate_too_low_eps(self, invalid_eps_values):
        """測試驗證過低的 EPS（低於最小值）"""
        validator = DataValidator()
        result = validator.validate_eps(invalid_eps_values['too_low'], "2330")
        
        assert result['is_valid'] is True
        assert result['value'] == DataValidator.EPS_MIN  # 應被限制在最小值
        assert result['severity'] == 'warning'
    
    def test_validate_nan_eps(self, invalid_eps_values):
        """測試驗證 NaN EPS"""
        validator = DataValidator()
        result = validator.validate_eps(invalid_eps_values['nan'], "2330")
        
        assert result['is_valid'] is False
        assert result['value'] == 0.0
        assert result['severity'] == 'error'
        assert any('非數值' in w for w in result['warnings'])
    
    def test_validate_none_eps(self, invalid_eps_values):
        """測試驗證 None EPS"""
        validator = DataValidator()
        result = validator.validate_eps(invalid_eps_values['none'], "2330")
        
        assert result['is_valid'] is False
        assert result['severity'] == 'error'
    
    def test_validate_string_eps(self, invalid_eps_values):
        """測試驗證字串類型的 EPS"""
        validator = DataValidator()
        result = validator.validate_eps(invalid_eps_values['string'], "2330")
        
        assert result['is_valid'] is False
        assert result['severity'] == 'error'


class TestValidateStockPrice:
    """測試股價驗證功能"""
    
    def test_validate_normal_price(self, valid_price_values):
        """測試驗證正常股價"""
        validator = DataValidator()
        result = validator.validate_stock_price(valid_price_values['normal'], "2330")
        
        assert result['is_valid'] is True
        assert result['value'] == valid_price_values['normal']
        assert result['severity'] == 'ok'
        assert len(result['warnings']) == 0
    
    def test_validate_low_price(self, valid_price_values):
        """測試驗證低股價"""
        validator = DataValidator()
        result = validator.validate_stock_price(valid_price_values['low'], "2330")
        
        assert result['is_valid'] is True
        assert result['value'] == valid_price_values['low']
    
    def test_validate_high_price(self, valid_price_values):
        """測試驗證高股價"""
        validator = DataValidator()
        result = validator.validate_stock_price(valid_price_values['high'], "2330")
        
        assert result['is_valid'] is True
        assert result['value'] == valid_price_values['high']
    
    def test_validate_decimal_price(self, valid_price_values):
        """測試驗證小數股價"""
        validator = DataValidator()
        result = validator.validate_stock_price(valid_price_values['decimal'], "2330")
        
        assert result['is_valid'] is True
        assert result['value'] == valid_price_values['decimal']
    
    def test_validate_zero_price(self, invalid_price_values):
        """測試驗證零股價（無效）"""
        validator = DataValidator()
        result = validator.validate_stock_price(invalid_price_values['zero'], "2330")
        
        assert result['is_valid'] is False
        assert result['severity'] == 'error'
        assert any('必須大於零' in w for w in result['warnings'])
    
    def test_validate_negative_price(self, invalid_price_values):
        """測試驗證負股價（無效）"""
        validator = DataValidator()
        result = validator.validate_stock_price(invalid_price_values['negative'], "2330")
        
        assert result['is_valid'] is False
        assert result['severity'] == 'error'
    
    def test_validate_too_high_price(self, invalid_price_values):
        """測試驗證過高股價"""
        validator = DataValidator()
        result = validator.validate_stock_price(invalid_price_values['too_high'], "2330")
        
        assert result['is_valid'] is True
        assert result['severity'] == 'warning'
        assert any('過高' in w for w in result['warnings'])
    
    def test_validate_nan_price(self, invalid_price_values):
        """測試驗證 NaN 股價"""
        validator = DataValidator()
        result = validator.validate_stock_price(invalid_price_values['nan'], "2330")
        
        assert result['is_valid'] is False
        assert result['severity'] == 'error'
    
    def test_validate_none_price(self, invalid_price_values):
        """測試驗證 None 股價"""
        validator = DataValidator()
        result = validator.validate_stock_price(invalid_price_values['none'], "2330")
        
        assert result['is_valid'] is False
        assert result['severity'] == 'error'


class TestValidateFinancialData:
    """測試財務數據驗證功能"""
    
    def test_validate_complete_financial_data(self, sample_financial_data):
        """測試驗證完整的財務數據"""
        validator = DataValidator()
        result = validator.validate_financial_data(sample_financial_data, "2330")
        
        assert result['is_valid'] is True
        assert result['quality_score'] >= 80.0
        assert len(result['warnings']) == 0
        assert len(result['issues']) == 0
    
    def test_validate_empty_financial_data(self):
        """測試驗證空的財務數據"""
        validator = DataValidator()
        
        # 測試 None
        result = validator.validate_financial_data(None, "2330")
        assert result['is_valid'] is False
        assert result['quality_score'] == 0.0
        
        # 測試空 DataFrame
        empty_df = pd.DataFrame()
        result = validator.validate_financial_data(empty_df, "2330")
        assert result['is_valid'] is False
        assert result['quality_score'] == 0.0
    
    def test_validate_incomplete_financial_data(self, incomplete_financial_data):
        """測試驗證不完整的財務數據（含缺失值）"""
        validator = DataValidator()
        result = validator.validate_financial_data(incomplete_financial_data, "2330")
        
        # 應該被標記為有問題，品質分數降低
        assert result['quality_score'] < 100.0
        assert len(result['warnings']) > 0
        assert len(result['issues']) > 0
    
    def test_validate_missing_required_columns(self):
        """測試驗證缺少必要欄位的財務數據"""
        validator = DataValidator()
        
        # 只有日期欄位，缺少 eps 和 revenue
        df = pd.DataFrame({
            'date': pd.date_range('2020-01-01', periods=4, freq='Q')
        })
        
        result = validator.validate_financial_data(df, "2330")
        
        assert result['quality_score'] < 100.0
        assert any('缺少欄位' in issue for issue in result['issues'])
    
    def test_validate_financial_data_with_outliers(self):
        """測試驗證含異常值的財務數據"""
        validator = DataValidator()
        
        # 建立含異常值的數據
        dates = pd.date_range('2020-01-01', periods=12, freq='Q')
        eps_values = [5.0] * 10 + [100.0, 5.0]  # 第11季度有異常值
        
        df = pd.DataFrame({
            'date': dates,
            'eps': eps_values,
            'revenue': [100] * 12
        })
        
        result = validator.validate_financial_data(df, "2330")
        
        # 應該偵測到異常值
        assert result['quality_score'] < 100.0
        assert any('異常值' in issue for issue in result['issues'])
    
    def test_validate_financial_data_with_negative_revenue(self):
        """測試驗證含負營收的財務數據"""
        validator = DataValidator()
        
        df = pd.DataFrame({
            'date': pd.date_range('2020-01-01', periods=4, freq='Q'),
            'eps': [5.0, 6.0, 7.0, 8.0],
            'revenue': [100, 105, -50, 115]  # 第3季度負營收
        })
        
        result = validator.validate_financial_data(df, "2330")
        
        assert result['quality_score'] < 100.0
        assert any('負營收' in issue for issue in result['issues'])
    
    def test_validate_financial_data_short_timerange(self):
        """測試驗證時間範圍過短的財務數據"""
        validator = DataValidator()
        
        # 只有3個月的數據
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=3, freq='M'),
            'eps': [5.0, 6.0, 7.0],
            'revenue': [100, 105, 110]
        })
        
        result = validator.validate_financial_data(df, "2330")
        
        assert result['quality_score'] < 100.0
        assert any('時間範圍' in issue for issue in result['issues'])


class TestValidatePriceData:
    """測試價格數據驗證功能"""
    
    def test_validate_complete_price_data(self, sample_price_data):
        """測試驗證完整的價格數據"""
        validator = DataValidator()
        result = validator.validate_price_data(sample_price_data, "2330")
        
        assert result['is_valid'] is True
        assert result['quality_score'] >= 70.0  # 隨機數據可能有些波動
    
    def test_validate_empty_price_data(self):
        """測試驗證空的價格數據"""
        validator = DataValidator()
        
        result = validator.validate_price_data(None, "2330")
        assert result['is_valid'] is False
        assert result['quality_score'] == 0.0
    
    def test_validate_anomaly_price_data(self, anomaly_price_data):
        """測試驗證含異常值的價格數據"""
        validator = DataValidator()
        result = validator.validate_price_data(anomaly_price_data, "2330")
        
        # 應該偵測到問題
        assert result['quality_score'] < 100.0
        assert len(result['warnings']) > 0
        assert len(result['issues']) > 0
    
    def test_validate_price_data_missing_columns(self):
        """測試驗證缺少必要欄位的價格數據"""
        validator = DataValidator()
        
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=10, freq='D')
            # 缺少 close_price
        })
        
        result = validator.validate_price_data(df, "2330")
        
        assert result['quality_score'] < 100.0
        assert any('缺少欄位' in issue for issue in result['issues'])
    
    def test_validate_price_data_with_zero_volume(self):
        """測試驗證含大量零成交量的價格數據"""
        validator = DataValidator()
        
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=20, freq='D'),
            'close_price': [500.0] * 20,
            'volume': [0] * 15 + [10000] * 5  # 75% 零成交量
        })
        
        result = validator.validate_price_data(df, "2330")
        
        assert result['quality_score'] < 100.0
        assert any('零成交量' in issue for issue in result['issues'])


class TestDetectOutliers:
    """測試異常值偵測功能"""
    
    def test_detect_outliers_iqr_method(self):
        """測試使用 IQR 方法偵測異常值"""
        validator = DataValidator()
        
        # 建立含異常值的序列
        data = pd.Series([10, 12, 11, 13, 12, 10, 100, 11, 12, 13])  # 100 是異常值
        
        outliers = validator._detect_outliers(data, method='iqr')
        
        assert len(outliers) > 0
        assert 100 in outliers.values
    
    def test_detect_outliers_zscore_method(self):
        """測試使用 Z-score 方法偵測異常值"""
        validator = DataValidator()
        
        # 建立含異常值的序列 (長度須夠長以超越 Z-score 3 閾值限制)
        data = pd.Series([10, 12, 11, 13, 12, 10, 11, 12, 13] * 10 + [500])
        
        outliers = validator._detect_outliers(data, method='zscore')
        
        assert len(outliers) > 0
        assert 500 in outliers.values
    
    def test_detect_no_outliers(self):
        """測試沒有異常值的情況"""
        validator = DataValidator()
        
        # 正常分佈的數據
        data = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19])
        
        outliers = validator._detect_outliers(data, method='iqr')
        
        assert len(outliers) == 0


class TestValidatorMessages:
    """測試訊息管理功能"""
    
    def test_get_warnings(self):
        """測試獲取警告訊息"""
        validator = DataValidator()
        validator.warnings = ["警告1", "警告2"]
        
        warnings = validator.get_warnings()
        
        assert len(warnings) == 2
        assert "警告1" in warnings
        assert "警告2" in warnings
    
    def test_get_errors(self):
        """測試獲取錯誤訊息"""
        validator = DataValidator()
        validator.errors = ["錯誤1", "錯誤2"]
        
        errors = validator.get_errors()
        
        assert len(errors) == 2
        assert "錯誤1" in errors
    
    def test_clear_messages(self):
        """測試清除訊息"""
        validator = DataValidator()
        validator.warnings = ["警告1"]
        validator.errors = ["錯誤1"]
        
        validator.clear_messages()
        
        assert len(validator.get_warnings()) == 0
        assert len(validator.get_errors()) == 0


class TestSummaryReport:
    """測試摘要報告功能"""
    
    def test_summary_report_all_valid(self):
        """測試全部驗證通過的摘要報告"""
        validator = DataValidator()
        
        validations = [
            {'is_valid': True, 'quality_score': 95, 'warnings': []},
            {'is_valid': True, 'quality_score': 90, 'warnings': []},
            {'is_valid': True, 'quality_score': 85, 'warnings': []}
        ]
        
        report = validator.summary_report(validations)
        
        assert '總驗證項目: 3' in report
        assert '有效項目: 3' in report
        assert '✓ 通過' in report
    
    def test_summary_report_with_issues(self):
        """測試有問題的摘要報告"""
        validator = DataValidator()
        
        validations = [
            {'is_valid': True, 'quality_score': 95, 'warnings': []},
            {'is_valid': False, 'quality_score': 40, 'warnings': ['警告1']},
            {'is_valid': True, 'quality_score': 85, 'warnings': ['警告2']}
        ]
        
        report = validator.summary_report(validations)
        
        assert '總驗證項目: 3' in report
        assert '有效項目: 2' in report
        assert '警告數量: 2' in report
        assert '⚠ 發現問題' in report
    
    def test_summary_report_empty(self):
        """測試空驗證列表的摘要報告"""
        validator = DataValidator()
        
        validations = []
        
        report = validator.summary_report(validations)
        
        assert '總驗證項目: 0' in report


class TestValidatorConstants:
    """測試驗證器常數設定"""
    
    def test_eps_range_constants(self):
        """測試 EPS 範圍常數"""
        assert DataValidator.EPS_MIN == -100.0
        assert DataValidator.EPS_MAX == 500.0
    
    def test_price_range_constants(self):
        """測試股價範圍常數"""
        assert DataValidator.PRICE_MIN == 1.0
        assert DataValidator.PRICE_MAX == 10000.0
    
    def test_threshold_constants(self):
        """測試閾值常數"""
        assert DataValidator.EPS_CHANGE_THRESHOLD == 3.0
        assert DataValidator.PRICE_CHANGE_THRESHOLD == 0.3


# ============================================================================
# 整合測試
# ============================================================================

@pytest.mark.integration
class TestValidatorIntegration:
    """驗證器整合測試"""
    
    def test_validate_multiple_stocks(self, sample_stock_codes, sample_financial_data):
        """測試批次驗證多支股票"""
        validator = DataValidator()
        
        results = []
        for stock_code in sample_stock_codes:
            result = validator.validate_financial_data(sample_financial_data, stock_code)
            results.append(result)
        
        assert len(results) == len(sample_stock_codes)
        assert all(r['is_valid'] for r in results)
    
    def test_complete_validation_workflow(self, sample_financial_data, sample_price_data):
        """測試完整的驗證工作流程"""
        validator = DataValidator()
        
        # 1. 驗證 EPS
        eps_result = validator.validate_eps(15.5, "2330")
        assert eps_result['is_valid']
        
        # 2. 驗證股價
        price_result = validator.validate_stock_price(500.0, "2330")
        assert price_result['is_valid']
        
        # 3. 驗證財務數據
        financial_result = validator.validate_financial_data(sample_financial_data, "2330")
        assert financial_result['is_valid']
        
        # 4. 驗證價格數據
        price_data_result = validator.validate_price_data(sample_price_data, "2330")
        assert price_data_result['is_valid']
        
        # 5. 生成摘要報告
        validations = [eps_result, price_result, financial_result, price_data_result]
        report = validator.summary_report(validations)
        
        assert '✓ 通過' in report
