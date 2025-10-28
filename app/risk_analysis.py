"""
風險分析模組
提供 VaR、Monte Carlo 模擬等風險評估工具
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from scipy import stats
from data_manager import DataManager


class RiskAnalyzer:
    """風險分析器"""

    def __init__(self, data_manager: DataManager):
        """
        初始化風險分析器

        Args:
            data_manager: 數據管理器實例
        """
        self.data_manager = data_manager

    def calculate_var(
        self,
        stock_code: str,
        confidence_level: float = 0.95,
        holding_period: int = 30,
        investment_amount: float = 100000
    ) -> Dict:
        """
        計算 Value at Risk (風險值)

        Args:
            stock_code: 股票代碼
            confidence_level: 信心水準（預設 95%）
            holding_period: 持有期間（天數）
            investment_amount: 投資金額

        Returns:
            VaR 計算結果
        """
        # 獲取歷史價格數據（過去一年）
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        price_data = self.data_manager.get_price_data(stock_code, start_date, end_date)
        
        if price_data is None or len(price_data) < 30:
            return {'error': '數據不足，無法計算 VaR'}

        # 計算日報酬率
        price_data = price_data.copy()
        price_data['returns'] = price_data['close_price'].pct_change()
        returns = price_data['returns'].dropna()

        # 計算持有期報酬率的標準差
        daily_std = returns.std()
        period_std = daily_std * np.sqrt(holding_period)

        # 計算 VaR（參數法）
        z_score = stats.norm.ppf(1 - confidence_level)
        var_percentage = z_score * period_std
        var_amount = investment_amount * abs(var_percentage)

        # 計算 VaR（歷史模擬法）
        historical_var_percentage = returns.quantile(1 - confidence_level) * np.sqrt(holding_period)
        historical_var_amount = investment_amount * abs(historical_var_percentage)

        # 計算 CVaR (Conditional VaR / Expected Shortfall)
        cvar_returns = returns[returns <= returns.quantile(1 - confidence_level)]
        cvar_percentage = cvar_returns.mean() * np.sqrt(holding_period)
        cvar_amount = investment_amount * abs(cvar_percentage)

        return {
            'stock_code': stock_code,
            'confidence_level': confidence_level,
            'holding_period_days': holding_period,
            'investment_amount': investment_amount,
            'parametric_var': {
                'percentage': var_percentage,
                'amount': var_amount
            },
            'historical_var': {
                'percentage': historical_var_percentage,
                'amount': historical_var_amount
            },
            'cvar': {
                'percentage': cvar_percentage,
                'amount': cvar_amount
            },
            'interpretation': f"在 {confidence_level:.0%} 信心水準下，"
                            f"持有 {holding_period} 天內，"
                            f"最大可能損失約為 ${var_amount:,.0f}"
        }

    def monte_carlo_simulation(
        self,
        stock_code: str,
        current_price: float,
        simulations: int = 10000,
        days: int = 252,
        investment_amount: float = 100000
    ) -> Dict:
        """
        Monte Carlo 模擬

        Args:
            stock_code: 股票代碼
            current_price: 當前價格
            simulations: 模擬次數
            days: 模擬天數（預設一年 252 個交易日）
            investment_amount: 投資金額

        Returns:
            模擬結果
        """
        # 獲取歷史數據計算參數
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        price_data = self.data_manager.get_price_data(stock_code, start_date, end_date)
        
        if price_data is None or len(price_data) < 30:
            return {'error': '數據不足，無法進行模擬'}

        # 計算歷史報酬率和波動率
        price_data = price_data.copy()
        price_data['returns'] = price_data['close_price'].pct_change()
        returns = price_data['returns'].dropna()
        
        mu = returns.mean()  # 日平均報酬率
        sigma = returns.std()  # 日波動率

        # 執行 Monte Carlo 模擬
        np.random.seed(42)  # 確保可重現性
        
        simulation_results = []
        
        for _ in range(simulations):
            # 生成隨機報酬率序列
            random_returns = np.random.normal(mu, sigma, days)
            
            # 計算價格路徑
            price_path = current_price * np.exp(np.cumsum(random_returns))
            
            # 記錄最終價格
            final_price = price_path[-1]
            final_return = (final_price - current_price) / current_price
            
            simulation_results.append({
                'final_price': final_price,
                'return': final_return,
                'price_path': price_path
            })

        # 分析結果
        final_prices = [r['final_price'] for r in simulation_results]
        returns_list = [r['return'] for r in simulation_results]
        
        # 計算統計量
        mean_final_price = np.mean(final_prices)
        median_final_price = np.median(final_prices)
        std_final_price = np.std(final_prices)
        
        # 計算信心區間
        percentile_5 = np.percentile(final_prices, 5)
        percentile_95 = np.percentile(final_prices, 95)
        
        # 計算可能的投資結果
        mean_return = np.mean(returns_list)
        loss_probability = sum(1 for r in returns_list if r < 0) / len(returns_list)
        
        # 計算投資金額對應的結果
        expected_value = investment_amount * (1 + mean_return)
        worst_case_5 = investment_amount * (1 + (percentile_5 - current_price) / current_price)
        best_case_95 = investment_amount * (1 + (percentile_95 - current_price) / current_price)

        return {
            'stock_code': stock_code,
            'current_price': current_price,
            'simulations': simulations,
            'days': days,
            'statistics': {
                'mean_price': mean_final_price,
                'median_price': median_final_price,
                'std_price': std_final_price,
                'percentile_5': percentile_5,
                'percentile_95': percentile_95
            },
            'returns': {
                'mean_return': mean_return,
                'loss_probability': loss_probability
            },
            'investment_results': {
                'initial_amount': investment_amount,
                'expected_value': expected_value,
                'worst_case_5_percent': worst_case_5,
                'best_case_95_percent': best_case_95,
                'expected_profit': expected_value - investment_amount,
                'max_potential_loss': investment_amount - worst_case_5
            },
            'simulation_paths': [r['price_path'] for r in simulation_results[:100]]  # 只保留前100條路徑用於繪圖
        }

    def calculate_volatility(
        self,
        stock_code: str,
        period_days: int = 252
    ) -> Dict:
        """
        計算波動率

        Args:
            stock_code: 股票代碼
            period_days: 計算期間（天數）

        Returns:
            波動率分析結果
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days + 30)  # 多取一些數據
        
        price_data = self.data_manager.get_price_data(stock_code, start_date, end_date)
        
        if price_data is None or len(price_data) < 30:
            return {'error': '數據不足'}

        # 計算報酬率
        price_data = price_data.copy()
        price_data['returns'] = price_data['close_price'].pct_change()
        returns = price_data['returns'].dropna()

        # 計算各種波動率指標
        daily_volatility = returns.std()
        annual_volatility = daily_volatility * np.sqrt(252)
        
        # 計算滾動波動率（30天）
        rolling_vol = returns.rolling(window=30).std() * np.sqrt(252)
        
        # 計算最大回撤
        cumulative_returns = (1 + returns).cumprod()
        running_max = cumulative_returns.cummax()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdown.min()

        return {
            'stock_code': stock_code,
            'period_days': period_days,
            'daily_volatility': daily_volatility,
            'annual_volatility': annual_volatility,
            'max_drawdown': max_drawdown,
            'current_rolling_volatility': rolling_vol.iloc[-1] if len(rolling_vol) > 0 else None,
            'volatility_history': rolling_vol.tolist()[-60:],  # 最近60天的滾動波動率
            'interpretation': {
                'risk_level': self._interpret_volatility(annual_volatility),
                'description': f"年化波動率為 {annual_volatility:.2%}，"
                             f"歷史最大回撤為 {max_drawdown:.2%}"
            }
        }

    def calculate_beta(
        self,
        stock_code: str,
        market_code: str = "0050",
        period_days: int = 252
    ) -> Dict:
        """
        計算 Beta 係數

        Args:
            stock_code: 股票代碼
            market_code: 市場代理指標（預設 0050）
            period_days: 計算期間

        Returns:
            Beta 分析結果
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days + 30)
        
        # 獲取股票和市場數據
        stock_data = self.data_manager.get_price_data(stock_code, start_date, end_date)
        market_data = self.data_manager.get_price_data(market_code, start_date, end_date)
        
        if stock_data is None or market_data is None:
            return {'error': '無法獲取數據'}

        # 計算報酬率
        stock_data = stock_data.copy()
        market_data = market_data.copy()
        
        stock_data['returns'] = stock_data['close_price'].pct_change()
        market_data['returns'] = market_data['close_price'].pct_change()
        
        # 合併數據
        merged = pd.merge(
            stock_data[['date', 'returns']],
            market_data[['date', 'returns']],
            on='date',
            suffixes=('_stock', '_market')
        ).dropna()
        
        if len(merged) < 30:
            return {'error': '數據不足'}

        # 計算 Beta
        covariance = merged['returns_stock'].cov(merged['returns_market'])
        market_variance = merged['returns_market'].var()
        beta = covariance / market_variance if market_variance != 0 else 1.0
        
        # 計算 Alpha（簡化版）
        stock_mean_return = merged['returns_stock'].mean() * 252
        market_mean_return = merged['returns_market'].mean() * 252
        alpha = stock_mean_return - beta * market_mean_return
        
        # 計算相關係數
        correlation = merged['returns_stock'].corr(merged['returns_market'])

        return {
            'stock_code': stock_code,
            'market_code': market_code,
            'beta': beta,
            'alpha': alpha,
            'correlation': correlation,
            'interpretation': {
                'beta_meaning': self._interpret_beta(beta),
                'risk_profile': f"Beta = {beta:.2f}，"
                              f"該股票波動性{'高於' if beta > 1 else '低於' if beta < 1 else '等於'}市場平均"
            }
        }

    def comprehensive_risk_report(
        self,
        stock_code: str,
        investment_amount: float = 100000
    ) -> Dict:
        """
        生成綜合風險報告

        Args:
            stock_code: 股票代碼
            investment_amount: 投資金額

        Returns:
            完整風險分析報告
        """
        # 獲取當前價格
        current_price = self.data_manager.get_latest_price(stock_code)
        
        if current_price == 0:
            return {'error': '無法獲取股票價格'}

        # 計算各項風險指標
        var_result = self.calculate_var(stock_code, investment_amount=investment_amount)
        volatility_result = self.calculate_volatility(stock_code)
        beta_result = self.calculate_beta(stock_code)
        mc_result = self.monte_carlo_simulation(
            stock_code, current_price, 
            simulations=5000, investment_amount=investment_amount
        )

        # 綜合風險評級
        risk_score = self._calculate_risk_score(var_result, volatility_result, beta_result)

        return {
            'stock_code': stock_code,
            'current_price': current_price,
            'investment_amount': investment_amount,
            'risk_score': risk_score,
            'value_at_risk': var_result,
            'volatility_analysis': volatility_result,
            'beta_analysis': beta_result,
            'monte_carlo_simulation': mc_result,
            'summary': self._generate_risk_summary(risk_score, var_result, volatility_result, beta_result)
        }

    # === 私有輔助方法 ===

    def _interpret_volatility(self, annual_volatility: float) -> str:
        """解讀波動率水準"""
        if annual_volatility < 0.15:
            return "低風險"
        elif annual_volatility < 0.25:
            return "中等風險"
        elif annual_volatility < 0.40:
            return "高風險"
        else:
            return "極高風險"

    def _interpret_beta(self, beta: float) -> str:
        """解讀 Beta 值"""
        if beta < 0.5:
            return "防禦型股票，波動性遠低於市場"
        elif beta < 0.8:
            return "低波動股票"
        elif beta < 1.2:
            return "與市場波動相近"
        elif beta < 1.5:
            return "高波動股票"
        else:
            return "超高波動股票，風險顯著"

    def _calculate_risk_score(
        self,
        var_result: Dict,
        volatility_result: Dict,
        beta_result: Dict
    ) -> Dict:
        """計算綜合風險評分"""
        score = 0
        max_score = 100
        
        # 波動率評分（40分）
        if 'annual_volatility' in volatility_result:
            vol = volatility_result['annual_volatility']
            vol_score = max(0, 40 - (vol * 100))  # 波動率越低分數越高
            score += vol_score
        
        # Beta 評分（30分）
        if 'beta' in beta_result:
            beta = abs(beta_result['beta'] - 1)  # 與1的偏離程度
            beta_score = max(0, 30 - (beta * 30))
            score += beta_score
        
        # VaR 評分（30分）
        if 'parametric_var' in var_result and 'investment_amount' in var_result:
            var_pct = abs(var_result['parametric_var']['percentage'])
            var_score = max(0, 30 - (var_pct * 100))
            score += var_score
        
        # 正規化到0-100
        normalized_score = (score / max_score) * 100
        
        # 風險等級
        if normalized_score >= 80:
            risk_level = "極低風險"
        elif normalized_score >= 60:
            risk_level = "低風險"
        elif normalized_score >= 40:
            risk_level = "中等風險"
        elif normalized_score >= 20:
            risk_level = "高風險"
        else:
            risk_level = "極高風險"
        
        return {
            'score': normalized_score,
            'level': risk_level
        }

    def _generate_risk_summary(
        self,
        risk_score: Dict,
        var_result: Dict,
        volatility_result: Dict,
        beta_result: Dict
    ) -> str:
        """生成風險摘要"""
        summary = f"風險評級: {risk_score['level']} (評分: {risk_score['score']:.1f}/100)\n\n"
        
        if 'parametric_var' in var_result:
            summary += f"VaR 分析: {var_result['interpretation']}\n\n"
        
        if 'interpretation' in volatility_result:
            summary += f"波動性: {volatility_result['interpretation']['description']}\n\n"
        
        if 'interpretation' in beta_result:
            summary += f"市場相關性: {beta_result['interpretation']['risk_profile']}\n"
        
        return summary


# 測試函數
def test_risk_analyzer():
    """測試風險分析器"""
    
    data_manager = DataManager()
    risk_analyzer = RiskAnalyzer(data_manager)
    
    stock_code = "2330"
    investment_amount = 100000
    
    print(f"=== 風險分析測試: {stock_code} ===\n")
    
    # 測試 VaR
    print("1. VaR 計算:")
    try:
        var_result = risk_analyzer.calculate_var(stock_code, investment_amount=investment_amount)
        if 'error' not in var_result:
            print(f"   參數法 VaR: ${var_result['parametric_var']['amount']:,.0f}")
            print(f"   {var_result['interpretation']}")
        else:
            print(f"   錯誤: {var_result['error']}")
    except Exception as e:
        print(f"   執行失敗: {str(e)}")
    
    # 測試波動率
    print("\n2. 波動率分析:")
    try:
        vol_result = risk_analyzer.calculate_volatility(stock_code)
        if 'error' not in vol_result:
            print(f"   年化波動率: {vol_result['annual_volatility']:.2%}")
            print(f"   風險等級: {vol_result['interpretation']['risk_level']}")
        else:
            print(f"   錯誤: {vol_result['error']}")
    except Exception as e:
        print(f"   執行失敗: {str(e)}")
    
    # 測試 Beta
    print("\n3. Beta 分析:")
    try:
        beta_result = risk_analyzer.calculate_beta(stock_code)
        if 'error' not in beta_result:
            print(f"   Beta: {beta_result['beta']:.2f}")
            print(f"   解讀: {beta_result['interpretation']['beta_meaning']}")
        else:
            print(f"   錯誤: {beta_result['error']}")
    except Exception as e:
        print(f"   執行失敗: {str(e)}")


if __name__ == "__main__":
    test_risk_analyzer()
