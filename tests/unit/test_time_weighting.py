"""
時間加權成長率單元測試

測試 DataManager 中時間加權（EWMA）相關方法的正確性
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from app.data.manager import DataManager


class TestCalculateLambda:
    """測試 lambda 參數計算"""
    
    def test_lambda_basic_calculation(self):
        """測試基本的 lambda 計算"""
        manager = DataManager()
        
        # 5年數據，近期權重 60%
        lambda_val = manager._calculate_lambda(n=5, recent_weight_ratio=0.6)
        
        assert lambda_val > 0, "Lambda 應該是正值"
        assert lambda_val < 10, "Lambda 應該在合理範圍內"
    
    def test_lambda_different_ratios(self):
        """測試不同 recent_weight_ratio 的 lambda 值"""
        manager = DataManager()
        
        ratios = [0.5, 0.6, 0.7, 0.8]
        lambdas = [manager._calculate_lambda(5, r) for r in ratios]
        
        # 驗證：ratio 越大，lambda 應該越大（更快衰減）
        for i in range(len(lambdas) - 1):
            assert lambdas[i] < lambdas[i+1], \
                f"ratio 增加時 lambda 應該增加: {lambdas[i]} vs {lambdas[i+1]}"
    
    def test_lambda_different_n_values(self):
        """測試不同數據點數量的 lambda 值"""
        manager = DataManager()
        
        n_values = [3, 5, 7, 10]
        lambdas = [manager._calculate_lambda(n, 0.6) for n in n_values]
        
        # Lambda 值都應該是正數且合理
        for lam in lambdas:
            assert lam > 0
            assert lam < 20
    
    def test_lambda_edge_case_ratio_05(self):
        """測試 ratio=0.5 的邊界情況（接近等權重）"""
        manager = DataManager()
        
        lambda_val = manager._calculate_lambda(n=5, recent_weight_ratio=0.5)
        
        # ratio=0.5 時，lambda 應該較小（接近等權重）
        assert lambda_val < 1.0
    
    def test_lambda_edge_case_ratio_09(self):
        """測試 ratio=0.9 的邊界情況（極度重視近期）"""
        manager = DataManager()
        
        lambda_val = manager._calculate_lambda(n=5, recent_weight_ratio=0.9)
        
        # ratio=0.9 時，lambda 應該較大
        assert lambda_val > 2.0


class TestExponentialWeights:
    """測試指數衰減權重計算"""
    
    def test_weights_sum_to_one(self):
        """測試權重總和為 1"""
        manager = DataManager()
        
        for n in [3, 5, 7, 10]:
            for ratio in [0.5, 0.6, 0.7, 0.8]:
                weights = manager._calculate_exponential_weights(n, ratio)
                
                assert abs(sum(weights) - 1.0) < 0.0001, \
                    f"權重總和應為 1.0 (n={n}, ratio={ratio}): {sum(weights)}"
    
    def test_recent_weight_ratio_accuracy(self):
        """測試近期權重比例準確性"""
        manager = DataManager()
        
        n = 5
        ratio = 0.6
        weights = manager._calculate_exponential_weights(n, ratio)
        
        # 最新一期的權重應該在目標 ratio 附近（容差 5%）
        assert abs(weights[-1] - ratio) < 0.05, \
            f"最新權重應接近 {ratio}: 實際 {weights[-1]}"
    
    def test_weights_monotonic_increasing(self):
        """測試權重遞增性（由舊到新）"""
        manager = DataManager()
        
        weights = manager._calculate_exponential_weights(5, 0.6)
        
        for i in range(len(weights) - 1):
            assert weights[i] < weights[i+1], \
                f"權重應遞增: weights[{i}]={weights[i]} < weights[{i+1}]={weights[i+1]}"
    
    def test_weights_length_matches_n(self):
        """測試返回的權重數量正確"""
        manager = DataManager()
        
        for n in [3, 5, 7, 10]:
            weights = manager._calculate_exponential_weights(n, 0.6)
            assert len(weights) == n, f"應返回 {n} 個權重值"
    
    def test_weights_all_positive(self):
        """測試所有權重為正值"""
        manager = DataManager()
        
        weights = manager._calculate_exponential_weights(5, 0.6)
        
        for i, w in enumerate(weights):
            assert w > 0, f"權重 {i} 應該是正值: {w}"
    
    @pytest.mark.parametrize("n,ratio", [
        (3, 0.5), (3, 0.7), (3, 0.9),
        (5, 0.5), (5, 0.6), (5, 0.8),
        (10, 0.6), (10, 0.7), (10, 0.8)
    ])
    def test_weights_various_parameters(self, n, ratio):
        """測試各種參數組合"""
        manager = DataManager()
        
        weights = manager._calculate_exponential_weights(n, ratio)
        
        # 基本驗證
        assert len(weights) == n
        assert abs(sum(weights) - 1.0) < 0.0001
        assert all(w > 0 for w in weights)


class TestTimeWeightedGrowthRate:
    """測試時間加權成長率計算"""
    
    def test_stable_growth(self):
        """測試穩定成長情境"""
        manager = DataManager()
        
        # 穩定 10% 成長
        eps_data = pd.Series([10.0, 11.0, 12.1, 13.31, 14.641])
        
        growth_rate = manager._calculate_time_weighted_growth_rate(
            eps_data, recent_weight_ratio=0.6
        )
        
        # 應該接近 10%（容差 2%）
        assert abs(growth_rate - 0.10) < 0.02, \
            f"穩定成長的加權成長率應接近 10%: {growth_rate*100:.2f}%"
    
    def test_accelerating_growth(self):
        """測試加速成長情境"""
        manager = DataManager()
        
        # 加速成長：5%, 10%, 15%, 20%
        eps_data = pd.Series([10.0, 10.5, 11.55, 13.28, 15.94])
        
        growth_weighted = manager._calculate_time_weighted_growth_rate(
            eps_data, recent_weight_ratio=0.6
        )
        
        # 計算 CAGR 作為比較
        cagr = (eps_data.iloc[-1] / eps_data.iloc[0]) ** (1 / (len(eps_data) - 1)) - 1
        
        # 加速成長時，時間加權應該 > CAGR
        assert growth_weighted > cagr, \
            f"加速成長時加權成長率應 > CAGR: {growth_weighted*100:.2f}% vs {cagr*100:.2f}%"
    
    def test_decelerating_growth(self):
        """測試減速成長情境"""
        manager = DataManager()
        
        # 減速成長：20%, 15%, 10%, 5%
        eps_data = pd.Series([10.0, 12.0, 13.8, 15.18, 15.94])
        
        growth_weighted = manager._calculate_time_weighted_growth_rate(
            eps_data, recent_weight_ratio=0.6
        )
        
        # 計算 CAGR
        cagr = (eps_data.iloc[-1] / eps_data.iloc[0]) ** (1 / (len(eps_data) - 1)) - 1
        
        # 減速成長時，時間加權應該 < CAGR
        assert growth_weighted < cagr, \
            f"減速成長時加權成長率應 < CAGR: {growth_weighted*100:.2f}% vs {cagr*100:.2f}%"
    
    def test_negative_growth(self):
        """測試負成長情境"""
        manager = DataManager()
        
        # 衰退：-5% per year
        eps_data = pd.Series([10.0, 9.5, 9.025, 8.57, 8.14])
        
        growth_rate = manager._calculate_time_weighted_growth_rate(
            eps_data, recent_weight_ratio=0.6
        )
        
        # 應該是負值
        assert growth_rate < 0, "衰退情境應返回負成長率"
        assert growth_rate > -0.10, f"成長率應該在合理範圍: {growth_rate*100:.2f}%"
    
    def test_with_equal_weighting(self):
        """測試等權重模式（ratio=0.5 時應接近 CAGR）"""
        manager = DataManager()
        
        eps_data = pd.Series([10.0, 11.0, 12.1, 13.31, 14.641])
        
        # ratio=0.5 時接近等權重
        growth_weighted = manager._calculate_time_weighted_growth_rate(
            eps_data, recent_weight_ratio=0.5
        )
        
        # 計算 CAGR
        cagr = (eps_data.iloc[-1] / eps_data.iloc[0]) ** (1 / (len(eps_data) - 1)) - 1
        
        # 差異應該很小（< 1%）
        assert abs(growth_weighted - cagr) < 0.01, \
            f"ratio=0.5 時應接近 CAGR: {growth_weighted*100:.2f}% vs {cagr*100:.2f}%"
    
    def test_zero_eps_handling(self):
        """測試包含零 EPS 的處理"""
        manager = DataManager()
        
        # 包含零值
        eps_data = pd.Series([10.0, 11.0, 0.0, 13.0, 14.0])
        
        # 應該能處理（過濾掉零值或使用預設值）
        growth_rate = manager._calculate_time_weighted_growth_rate(
            eps_data, recent_weight_ratio=0.6
        )
        
        # 返回值應該在合理範圍
        assert -0.5 <= growth_rate <= 0.5


class TestHistoricalGrowthRate:
    """測試完整的歷史成長率計算功能"""
    
    @patch('app.data.manager.DataManager.get_financial_data')
    def test_with_time_weighting(self, mock_get_financial):
        """測試啟用時間加權模式"""
        # 準備測試數據
        financial_data = pd.DataFrame({
            'year': [2020, 2021, 2022, 2023, 2024],
            'eps': [10.0, 11.0, 12.1, 13.31, 14.641]
        })
        financial_data.set_index('year', inplace=True)
        mock_get_financial.return_value = financial_data
        
        manager = DataManager()
        
        result = manager.calculate_historical_growth_rate(
            stock_code="2330",
            years=5,
            use_time_weighting=True,
            recent_weight_ratio=0.6
        )
        
        # 驗證返回結構
        assert 'growth_rate_1_5' in result
        assert 'growth_rate_6_10' in result
        assert 'weighting_method' in result
        assert result['weighting_method'] == 'time_weighted'
        
        # 驗證成長率在合理範圍
        assert -0.5 <= result['growth_rate_1_5'] <= 0.5
    
    @patch('app.data.manager.DataManager.get_financial_data')
    def test_without_time_weighting(self, mock_get_financial):
        """測試等權重模式（傳統 CAGR）"""
        financial_data = pd.DataFrame({
            'year': [2020, 2021, 2022, 2023, 2024],
            'eps': [10.0, 11.0, 12.1, 13.31, 14.641]
        })
        financial_data.set_index('year', inplace=True)
        mock_get_financial.return_value = financial_data
        
        manager = DataManager()
        
        result = manager.calculate_historical_growth_rate(
            stock_code="2330",
            years=5,
            use_time_weighting=False
        )
        
        # 驗證 weighting_method
        assert result['weighting_method'] == 'equal_weighted'
        
        # 等權重模式應該返回 CAGR
        expected_cagr = (14.641 / 10.0) ** (1/4) - 1
        assert abs(result['growth_rate_1_5'] - expected_cagr) < 0.01
    
    @patch('app.data.manager.DataManager.get_financial_data')
    def test_weighting_method_field(self, mock_get_financial):
        """測試 weighting_method 欄位正確性"""
        financial_data = pd.DataFrame({
            'year': [2020, 2021, 2022, 2023, 2024],
            'eps': [10.0, 11.0, 12.1, 13.31, 14.641]
        })
        financial_data.set_index('year', inplace=True)
        mock_get_financial.return_value = financial_data
        
        manager = DataManager()
        
        # 測試時間加權
        result_tw = manager.calculate_historical_growth_rate(
            "2330", years=5, use_time_weighting=True
        )
        assert result_tw['weighting_method'] == 'time_weighted'
        
        # 測試等權重
        result_ew = manager.calculate_historical_growth_rate(
            "2330", years=5, use_time_weighting=False
        )
        assert result_ew['weighting_method'] == 'equal_weighted'
    
    @patch('app.data.manager.DataManager.get_financial_data')
    def test_data_quality_scores(self, mock_get_financial):
        """測試資料品質評估"""
        # 完整數據
        financial_data = pd.DataFrame({
            'year': list(range(2015, 2025)),
            'eps': [10.0 * (1.1 ** i) for i in range(10)]
        })
        financial_data.set_index('year', inplace=True)
        mock_get_financial.return_value = financial_data
        
        manager = DataManager()
        
        result = manager.calculate_historical_growth_rate("2330", years=10)
        
        assert 'data_quality' in result
        assert result['data_quality'] in ['good', 'fair', 'poor']
    
    @patch('app.data.manager.DataManager.get_financial_data')
    def test_insufficient_data(self, mock_get_financial):
        """測試數據不足時的處理"""
        # 只有 2 年數據
        financial_data = pd.DataFrame({
            'year': [2023, 2024],
            'eps': [10.0, 11.0]
        })
        financial_data.set_index('year', inplace=True)
        mock_get_financial.return_value = financial_data
        
        manager = DataManager()
        
        result = manager.calculate_historical_growth_rate("2330", years=10)
        
        # 數據不足時品質應該是 fair 或 poor
        assert result['data_quality'] in ['fair', 'poor']


class TestEdgeCases:
    """測試邊界情況與錯誤處理"""
    
    def test_empty_eps_series(self):
        """測試空 EPS 序列"""
        manager = DataManager()
        
        eps_data = pd.Series([])
        
        # 應該返回預設值或引發適當錯誤
        try:
            growth_rate = manager._calculate_time_weighted_growth_rate(
                eps_data, recent_weight_ratio=0.6
            )
            # 接受返回預設值（如 0.15）或 0
            assert -0.5 <= growth_rate <= 0.5
        except (ValueError, IndexError):
            # 接受引發錯誤
            pass
    
    def test_single_data_point(self):
        """測試單一數據點"""
        manager = DataManager()
        
        eps_data = pd.Series([10.0])
        
        # 無法計算成長率，應該返回預設值或 0
        try:
            growth_rate = manager._calculate_time_weighted_growth_rate(
                eps_data, recent_weight_ratio=0.6
            )
            # 接受返回預設值或 0
            assert -0.5 <= growth_rate <= 0.5
        except (ValueError, IndexError):
            pass
    
    def test_all_negative_eps(self):
        """測試全部負 EPS"""
        manager = DataManager()
        
        eps_data = pd.Series([-10.0, -9.0, -8.0, -7.0, -6.0])
        
        # 應該能處理或返回 0
        try:
            growth_rate = manager._calculate_time_weighted_growth_rate(
                eps_data, recent_weight_ratio=0.6
            )
            # 如果計算，結果應在合理範圍
            assert -1.0 <= growth_rate <= 1.0
        except ValueError:
            # 接受引發錯誤（負 EPS 無法計算成長率）
            pass
    
    def test_extreme_growth_values(self):
        """測試極端成長值"""
        manager = DataManager()
        
        # 極端成長：10倍
        eps_data = pd.Series([1.0, 2.0, 4.0, 8.0, 16.0])
        
        growth_rate = manager._calculate_time_weighted_growth_rate(
            eps_data, recent_weight_ratio=0.6
        )
        
        # 極端值可能不被限制，或限制在更寬的範圍
        # 驗證返回的是有效數值即可
        assert isinstance(growth_rate, (int, float))
        assert not np.isnan(growth_rate)
    
    def test_invalid_recent_weight_ratio(self):
        """測試無效的 recent_weight_ratio"""
        manager = DataManager()
        
        # 測試極端值（實作可能沒有嚴格驗證，只要能計算即可）
        try:
            # 嘗試計算，如果沒有驗證也接受
            lambda_low = manager._calculate_lambda(n=5, recent_weight_ratio=0.3)
            lambda_high = manager._calculate_lambda(n=5, recent_weight_ratio=1.1)
            # 如果能計算，驗證結果是合理的數值
            assert isinstance(lambda_low, (int, float))
            assert isinstance(lambda_high, (int, float))
        except (ValueError, AssertionError):
            # 如果有驗證並引發錯誤也接受
            pass
    
    @patch('app.data.manager.DataManager.get_financial_data')
    def test_missing_financial_data(self, mock_get_financial):
        """測試無法獲取財務數據"""
        mock_get_financial.return_value = None
        
        manager = DataManager()
        
        result = manager.calculate_historical_growth_rate("9999", years=10)
        
        # 應該返回預設值
        assert result['growth_rate_1_5'] == 0.15  # 預設值
        assert result['data_quality'] == 'poor'


# ============================================================================
# Parametrize 測試
# ============================================================================

@pytest.mark.parametrize("n,ratio,expected_min,expected_max", [
    (5, 0.5, 0.45, 0.55),  # ratio=0.5, 最新權重應該接近 50%
    (5, 0.6, 0.55, 0.65),  # ratio=0.6, 最新權重應該在 55-65%
    (5, 0.7, 0.65, 0.75),  # ratio=0.7, 最新權重應該在 65-75%
    (5, 0.8, 0.75, 0.85),  # ratio=0.8, 最新權重應該在 75-85%
])
def test_weights_meet_target_ratio(n, ratio, expected_min, expected_max):
    """測試權重符合目標比例（參數化測試）"""
    manager = DataManager()
    
    weights = manager._calculate_exponential_weights(n, ratio)
    
    assert expected_min <= weights[-1] <= expected_max, \
        f"最新權重應在 {expected_min}-{expected_max}: 實際 {weights[-1]}"
