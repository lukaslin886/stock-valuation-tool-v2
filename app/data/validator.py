"""
DataValidator - 資料有效性檢查模組

提供資料品質檢查與異常偵測功能
"""

from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np
from datetime import datetime


class DataValidator:
    """
    資料驗證器
    
    功能：
    - EPS 合理性檢查
    - 股價合理性檢查
    - 財務數據異常偵測
    - 資料品質評分
    """
    
    # 合理範圍定義
    EPS_MIN = -100.0  # 最小 EPS（虧損）
    EPS_MAX = 500.0   # 最大 EPS
    PRICE_MIN = 1.0   # 最小股價
    PRICE_MAX = 10000.0  # 最大股價
    VOLUME_MIN = 0    # 最小成交量
    REVENUE_MIN = 0   # 最小營收
    
    # 異常偵測閾值
    EPS_CHANGE_THRESHOLD = 3.0  # EPS 年變化倍數閾值
    PRICE_CHANGE_THRESHOLD = 0.3  # 股價日變化率閾值（30%）
    
    def __init__(self):
        """初始化驗證器"""
        self.warnings: List[str] = []
        self.errors: List[str] = []
    
    def validate_eps(self, eps: float, stock_code: str = "") -> Dict[str, Any]:
        """
        驗證 EPS 值的合理性
        
        Args:
            eps: EPS 值
            stock_code: 股票代碼（用於訊息）
            
        Returns:
            驗證結果字典，包含:
            - is_valid: 是否有效
            - value: 修正後的值
            - warnings: 警告訊息列表
            - severity: 問題嚴重度 ('ok', 'warning', 'error')
        """
        warnings = []
        severity = 'ok'
        
        # 1. 檢查是否為數值
        if not isinstance(eps, (int, float)) or np.isnan(eps):
            return {
                'is_valid': False,
                'value': 0.0,
                'warnings': [f'{stock_code} EPS 非數值'],
                'severity': 'error'
            }
        
        # 2. 檢查範圍
        if eps < self.EPS_MIN:
            warnings.append(f'{stock_code} EPS 過低: {eps:.2f} < {self.EPS_MIN}')
            severity = 'warning'
            eps = self.EPS_MIN
        
        if eps > self.EPS_MAX:
            warnings.append(f'{stock_code} EPS 過高: {eps:.2f} > {self.EPS_MAX}')
            severity = 'warning'
            eps = self.EPS_MAX
        
        # 3. 檢查特殊情況
        if eps == 0:
            warnings.append(f'{stock_code} EPS 為零')
            severity = 'warning'
        
        if eps < 0:
            warnings.append(f'{stock_code} EPS 為負值（虧損）: {eps:.2f}')
            severity = 'warning'
        
        return {
            'is_valid': True,
            'value': eps,
            'warnings': warnings,
            'severity': severity
        }
    
    def validate_stock_price(self, price: float, stock_code: str = "") -> Dict[str, Any]:
        """
        驗證股價的合理性
        
        Args:
            price: 股價
            stock_code: 股票代碼（用於訊息）
            
        Returns:
            驗證結果字典
        """
        warnings = []
        severity = 'ok'
        
        # 1. 檢查是否為數值
        if not isinstance(price, (int, float)) or np.isnan(price):
            return {
                'is_valid': False,
                'value': 0.0,
                'warnings': [f'{stock_code} 股價非數值'],
                'severity': 'error'
            }
        
        # 2. 檢查範圍
        if price <= 0:
            return {
                'is_valid': False,
                'value': 0.0,
                'warnings': [f'{stock_code} 股價必須大於零: {price:.2f}'],
                'severity': 'error'
            }
        
        if price < self.PRICE_MIN:
            warnings.append(f'{stock_code} 股價過低: {price:.2f} < {self.PRICE_MIN}')
            severity = 'warning'
        
        if price > self.PRICE_MAX:
            warnings.append(f'{stock_code} 股價過高: {price:.2f} > {self.PRICE_MAX}')
            severity = 'warning'
        
        return {
            'is_valid': True,
            'value': price,
            'warnings': warnings,
            'severity': severity
        }
    
    def validate_financial_data(
        self,
        financial_df: pd.DataFrame,
        stock_code: str = ""
    ) -> Dict[str, Any]:
        """
        驗證財務數據的完整性與合理性
        
        Args:
            financial_df: 財務數據 DataFrame
            stock_code: 股票代碼
            
        Returns:
            驗證結果字典，包含:
            - is_valid: 資料是否有效
            - warnings: 警告訊息列表
            - quality_score: 資料品質評分 (0-100)
            - issues: 問題詳情
        """
        warnings = []
        issues = []
        quality_score = 100.0
        
        # 1. 檢查 DataFrame 基本有效性
        if financial_df is None or len(financial_df) == 0:
            return {
                'is_valid': False,
                'warnings': [f'{stock_code} 財務數據為空'],
                'quality_score': 0.0,
                'issues': ['資料為空']
            }
        
        # 2. 檢查必要欄位
        required_columns = ['date', 'eps', 'revenue']
        missing_columns = [col for col in required_columns if col not in financial_df.columns]
        
        if missing_columns:
            quality_score -= 30
            issues.append(f'缺少欄位: {", ".join(missing_columns)}')
            warnings.append(f'{stock_code} 缺少必要欄位: {missing_columns}')
        
        # 3. 檢查資料完整性（缺失值）
        if 'eps' in financial_df.columns:
            eps_null_ratio = financial_df['eps'].isnull().sum() / len(financial_df)
            if eps_null_ratio > 0.3:
                quality_score -= 20
                issues.append(f'EPS 缺失率過高: {eps_null_ratio:.1%}')
                warnings.append(f'{stock_code} EPS 缺失值過多')
        
        if 'revenue' in financial_df.columns:
            rev_null_ratio = financial_df['revenue'].isnull().sum() / len(financial_df)
            if rev_null_ratio > 0.3:
                quality_score -= 20
                issues.append(f'營收缺失率過高: {rev_null_ratio:.1%}')
                warnings.append(f'{stock_code} 營收缺失值過多')
        
        # 4. 檢查 EPS 數值合理性
        if 'eps' in financial_df.columns:
            valid_eps = financial_df['eps'].dropna()
            if len(valid_eps) > 0:
                # 檢查異常值
                eps_outliers = self._detect_outliers(valid_eps)
                if len(eps_outliers) > 0:
                    quality_score -= 10
                    issues.append(f'發現 {len(eps_outliers)} 個 EPS 異常值')
                    warnings.append(f'{stock_code} EPS 存在異常值')
                
                # 檢查劇烈變化
                if len(valid_eps) >= 2:
                    changes = valid_eps.pct_change().dropna()
                    extreme_changes = changes[abs(changes) > self.EPS_CHANGE_THRESHOLD]
                    if len(extreme_changes) > 0:
                        quality_score -= 10
                        issues.append(f'EPS 劇烈變化: {len(extreme_changes)} 次')
                        warnings.append(f'{stock_code} EPS 存在劇烈變化')
        
        # 5. 檢查營收合理性
        if 'revenue' in financial_df.columns:
            valid_revenue = financial_df['revenue'].dropna()
            if len(valid_revenue) > 0:
                # 負營收檢查
                negative_revenue = valid_revenue[valid_revenue < 0]
                if len(negative_revenue) > 0:
                    quality_score -= 15
                    issues.append(f'發現 {len(negative_revenue)} 筆負營收')
                    warnings.append(f'{stock_code} 存在負營收數據')
        
        # 6. 檢查資料時間範圍
        if 'date' in financial_df.columns:
            try:
                dates = pd.to_datetime(financial_df['date'])
                date_range = (dates.max() - dates.min()).days
                if date_range < 365:
                    quality_score -= 10
                    issues.append(f'資料時間範圍過短: {date_range} 天')
                    warnings.append(f'{stock_code} 歷史資料不足一年')
            except:
                quality_score -= 10
                issues.append('日期欄位格式錯誤')
        
        is_valid = quality_score >= 50.0
        
        return {
            'is_valid': is_valid,
            'warnings': warnings,
            'quality_score': max(0, quality_score),
            'issues': issues
        }
    
    def validate_price_data(
        self,
        price_df: pd.DataFrame,
        stock_code: str = ""
    ) -> Dict[str, Any]:
        """
        驗證價格數據的完整性與合理性
        
        Args:
            price_df: 價格數據 DataFrame
            stock_code: 股票代碼
            
        Returns:
            驗證結果字典
        """
        warnings = []
        issues = []
        quality_score = 100.0
        
        # 1. 檢查基本有效性
        if price_df is None or len(price_df) == 0:
            return {
                'is_valid': False,
                'warnings': [f'{stock_code} 價格數據為空'],
                'quality_score': 0.0,
                'issues': ['資料為空']
            }
        
        # 2. 檢查必要欄位
        required_columns = ['date', 'close_price']
        missing_columns = [col for col in required_columns if col not in price_df.columns]
        
        if missing_columns:
            quality_score -= 30
            issues.append(f'缺少欄位: {", ".join(missing_columns)}')
            warnings.append(f'{stock_code} 缺少必要欄位')
        
        # 3. 檢查收盤價合理性
        if 'close_price' in price_df.columns:
            valid_prices = price_df['close_price'].dropna()
            
            # 零或負值
            invalid_prices = valid_prices[valid_prices <= 0]
            if len(invalid_prices) > 0:
                quality_score -= 20
                issues.append(f'發現 {len(invalid_prices)} 個無效價格（≤0）')
                warnings.append(f'{stock_code} 存在無效價格')
            
            # 異常值偵測
            if len(valid_prices) > 0:
                outliers = self._detect_outliers(valid_prices)
                if len(outliers) > 0:
                    quality_score -= 10
                    issues.append(f'發現 {len(outliers)} 個價格異常值')
                    warnings.append(f'{stock_code} 價格存在異常值')
            
            # 劇烈變化檢查
            if len(valid_prices) >= 2:
                changes = valid_prices.pct_change().dropna()
                extreme_changes = changes[abs(changes) > self.PRICE_CHANGE_THRESHOLD]
                if len(extreme_changes) > 0:
                    quality_score -= 10
                    issues.append(f'價格劇烈變化: {len(extreme_changes)} 次')
                    warnings.append(f'{stock_code} 價格存在劇烈變化')
        
        # 4. 檢查成交量
        if 'volume' in price_df.columns:
            valid_volumes = price_df['volume'].dropna()
            zero_volume = valid_volumes[valid_volumes == 0]
            if len(zero_volume) > len(valid_volumes) * 0.1:
                quality_score -= 10
                issues.append(f'零成交量過多: {len(zero_volume)} 筆')
                warnings.append(f'{stock_code} 零成交量天數過多')
        
        is_valid = quality_score >= 50.0
        
        return {
            'is_valid': is_valid,
            'warnings': warnings,
            'quality_score': max(0, quality_score),
            'issues': issues
        }
    
    def _detect_outliers(
        self,
        series: pd.Series,
        method: str = 'iqr'
    ) -> pd.Series:
        """
        偵測異常值（離群值）
        
        Args:
            series: 數據序列
            method: 偵測方法 ('iqr' 或 'zscore')
            
        Returns:
            異常值序列
        """
        if method == 'iqr':
            # IQR 方法（四分位距）
            Q1 = series.quantile(0.25)
            Q3 = series.quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            outliers = series[(series < lower_bound) | (series > upper_bound)]
        else:
            # Z-score 方法
            z_scores = np.abs((series - series.mean()) / series.std())
            outliers = series[z_scores > 3]
        
        return outliers
    
    def get_warnings(self) -> List[str]:
        """獲取所有警告訊息"""
        return self.warnings.copy()
    
    def get_errors(self) -> List[str]:
        """獲取所有錯誤訊息"""
        return self.errors.copy()
    
    def clear_messages(self):
        """清除所有訊息"""
        self.warnings.clear()
        self.errors.clear()
    
    def summary_report(self, validations: List[Dict[str, Any]]) -> str:
        """
        生成驗證摘要報告
        
        Args:
            validations: 驗證結果列表
            
        Returns:
            格式化的摘要報告
        """
        total = len(validations)
        valid = sum(1 for v in validations if v.get('is_valid', False))
        warnings = sum(len(v.get('warnings', [])) for v in validations)
        
        avg_quality = 0.0
        if total > 0:
            quality_scores = [v.get('quality_score', 0) for v in validations]
            avg_quality = sum(quality_scores) / len(quality_scores)
        
        valid_pct = (valid / total * 100) if total > 0 else 0.0
        
        report = f"""
資料驗證摘要報告
{'='*50}
總驗證項目: {total}
有效項目: {valid} ({valid_pct:.1f}%)
警告數量: {warnings}
平均品質分數: {avg_quality:.1f}/100

狀態: {'[OK] 通過' if valid == total and total > 0 else '⚠ 發現問題' if total > 0 else '無資料'}
"""
        return report
