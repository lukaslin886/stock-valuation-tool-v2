"""
歷史回測系統
驗證 DCF 估值模型的歷史表現
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from dcf_calculator import DCFCalculator
from data import DataManager
from risk.slippage_model import SlippageModel


class BacktestEngine:
    """回測引擎"""

    def __init__(self, data_manager: DataManager):
        """
        初始化回測引擎

        Args:
            data_manager: 數據管理器實例
        """
        self.data_manager = data_manager
        self.dcf_calculator = DCFCalculator()

    def run_backtest(
        self,
        stock_code: str,
        start_date: datetime,
        end_date: datetime,
        growth_rates: List[float],
        rebalance_months: int = 3
    ) -> Dict:
        """
        執行回測

        Args:
            stock_code: 股票代碼
            start_date: 回測開始日期
            end_date: 回測結束日期
            growth_rates: 成長率假設 [1-5年, 6-10年]
            rebalance_months: 重新計算週期（月）

        Returns:
            回測結果字典
        """
        print(f"\n========== 開始回測 {stock_code} ==========")
        print(f"期間: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
        print(f"成長率假設: 1-5年={growth_rates[0]:.1%}, 6-10年={growth_rates[1]:.1%}")
        print(f"重新計算週期: {rebalance_months} 個月")

        # 獲取歷史價格數據
        print("\n[1/3] 正在獲取歷史價格數據...")
        price_data = self.data_manager.get_price_data(
            stock_code, 
            start_date, 
            end_date
        )
        
        if price_data is None or len(price_data) == 0:
            error_msg = f'無法獲取 {stock_code} 的價格數據，請檢查股票代碼或網路連線'
            print(f"❌ {error_msg}")
            return {'error': error_msg}
        
        print(f"✅ 成功獲取 {len(price_data)} 筆價格數據")
        print(f"   期間: {price_data['date'].min()} 至 {price_data['date'].max()}")

        # 獲取財務數據
        print("\n[2/3] 正在獲取財務數據...")
        financial_data = self.data_manager.get_financial_data(
            stock_code, 
            years=10
        )
        
        if financial_data is None or len(financial_data) == 0:
            error_msg = f'無法獲取 {stock_code} 的財務數據，請稍後再試'
            print(f"❌ {error_msg}")
            return {'error': error_msg}
        
        # 檢查 EPS 數據品質
        valid_eps = financial_data[financial_data['eps'] > 0]
        print(f"✅ 成功獲取 {len(financial_data)} 筆財務數據")
        print(f"   有效 EPS 數據: {len(valid_eps)} 筆")
        
        if len(valid_eps) < 2:
            error_msg = f'EPS 數據不足（僅 {len(valid_eps)} 筆），無法進行回測。建議選擇其他股票或縮短回測期間。'
            print(f"[WARN] {error_msg}")
            return {'error': error_msg}

        # 生成回測點
        backtest_points = self._generate_backtest_points(
            start_date, end_date, rebalance_months
        )
        
        print(f"\n[3/3] 開始執行回測（共 {len(backtest_points)} 個時間點）...")

        # 執行回測
        results = []
        failed_points = []
        
        for idx, test_date in enumerate(backtest_points, 1):
            result = self._backtest_single_point(
                stock_code,
                test_date,
                price_data,
                financial_data,
                growth_rates
            )
            
            if result:
                results.append(result)
                print(f"  [OK] 點 {idx}/{len(backtest_points)}: {test_date.strftime('%Y-%m-%d')} - 成功")
            else:
                failed_points.append(test_date)
                print(f"  [FAIL] 點 {idx}/{len(backtest_points)}: {test_date.strftime('%Y-%m-%d')} - 失敗（數據不足）")

        print(f"\n回測完成:")
        print(f"  成功: {len(results)} 個點")
        print(f"  失敗: {len(failed_points)} 個點")
        
        if len(results) == 0:
            error_msg = '所有回測點都失敗了。可能原因：\n' \
                       '1. 回測期間太早，缺乏歷史數據\n' \
                       '2. EPS 數據品質不佳\n' \
                       '建議：縮短回測期間（例如改為 1 年）或選擇數據更完整的股票'
            print(f"❌ {error_msg}")
            return {'error': error_msg}

        # 分析結果
        print("\n正在分析回測結果...")
        analysis = self._analyze_backtest_results(results)
        
        if 'error' in analysis:
            print(f"[WARN] {analysis['error']}")
        else:
            print(f"✅ 分析完成")
            print(f"   有效預測: {analysis.get('valid_predictions', 0)} 筆")
            print(f"   預測準確度: {analysis.get('accuracy', 0):.1%}")

        return {
            'stock_code': stock_code,
            'start_date': start_date,
            'end_date': end_date,
            'results': results,
            'analysis': analysis,
            'failed_points': len(failed_points)
        }

    def _generate_backtest_points(
        self,
        start_date: datetime,
        end_date: datetime,
        rebalance_months: int
    ) -> List[datetime]:
        """生成回測時間點"""
        points = []
        current_date = start_date
        
        while current_date <= end_date:
            points.append(current_date)
            current_date += timedelta(days=rebalance_months * 30)
        
        return points

    def _backtest_single_point(
        self,
        stock_code: str,
        test_date: datetime,
        price_data: pd.DataFrame,
        financial_data: pd.DataFrame,
        growth_rates: List[float]
    ) -> Optional[Dict]:
        """在單一時間點執行回測"""
        
        # 確保 date 欄位為 datetime 型態
        price_data = price_data.copy()
        financial_data = financial_data.copy()
        price_data['date'] = pd.to_datetime(price_data['date'])
        financial_data['date'] = pd.to_datetime(financial_data['date'])
        
        # 獲取該時間點的價格
        price_df = price_data[price_data['date'] <= test_date]
        if len(price_df) == 0:
            return None
        
        current_price = price_df.iloc[-1]['close_price']
        
        # 獲取該時間點的 EPS
        eps_df = financial_data[financial_data['date'] <= test_date]
        if len(eps_df) == 0:
            return None
        
        current_eps = eps_df.iloc[-1]['eps']
        
        if pd.isna(current_eps) or current_eps <= 0:
            return None

        # 計算 DCF 價值
        try:
            dcf_result = self.dcf_calculator.calculate_dcf_value(
                current_price=current_price,
                current_eps=current_eps,
                growth_rates=growth_rates
            )
        except Exception as e:
            print(f"計算 DCF 失敗 ({test_date}): {str(e)}")
            return None

        # 計算未來實際報酬（如果有數據）
        future_date = test_date + timedelta(days=365)  # 1年後
        future_price_df = price_data[price_data['date'] >= future_date]
        
        actual_return = None
        slippage_cost = 0.0
        if len(future_price_df) > 0:
            future_price = future_price_df.iloc[0]['close_price']
            
            # 套用滑價模型
            try:
                # 擷取當時的 K 棒資料以計算滑價
                recent_data = price_data[price_data['date'] <= test_date].tail(20)
                if len(recent_data) >= 2:
                    slippage = SlippageModel.calculate_slippage(recent_data)
                    # 買進與賣出均有滑價成本
                    slippage_cost = (slippage['buy_slippage_pct'] + slippage['sell_slippage_pct']) / 100.0
            except Exception as e:
                print(f"[WARN] 滑價計算失敗，忽略滑價: {e}")
                
            actual_return = ((future_price - current_price) / current_price) - slippage_cost

        return {
            'date': test_date,
            'current_price': current_price,
            'current_eps': current_eps,
            'intrinsic_value': dcf_result['intrinsic_value'],
            'predicted_upside': dcf_result['upside_potential'],
            'actual_return': actual_return,
            'slippage_cost_applied': slippage_cost,
            'recommendation': dcf_result['recommendation']
        }

    def _analyze_backtest_results(self, results: List[Dict]) -> Dict:
        """分析回測結果"""
        
        if not results:
            return {'error': '沒有有效的回測結果'}

        # 轉換為 DataFrame
        df = pd.DataFrame(results)

        # 過濾出有實際報酬數據的記錄
        df_with_actual = df[df['actual_return'].notna()].copy()

        if len(df_with_actual) == 0:
            return {'error': '沒有足夠的數據計算實際報酬'}

        # 計算預測準確度
        df_with_actual['prediction_correct'] = (
            (df_with_actual['predicted_upside'] > 0) & 
            (df_with_actual['actual_return'] > 0)
        ) | (
            (df_with_actual['predicted_upside'] <= 0) & 
            (df_with_actual['actual_return'] <= 0)
        )

        accuracy = df_with_actual['prediction_correct'].mean()

        # 計算平均誤差
        df_with_actual['error'] = abs(
            df_with_actual['predicted_upside'] - df_with_actual['actual_return']
        )
        mean_error = df_with_actual['error'].mean()

        # 計算相關係數
        correlation = df_with_actual['predicted_upside'].corr(
            df_with_actual['actual_return']
        )

        # 按推薦等級分組分析
        recommendation_performance = {}
        for rec in df_with_actual['recommendation'].unique():
            rec_df = df_with_actual[df_with_actual['recommendation'] == rec]
            recommendation_performance[rec] = {
                'count': len(rec_df),
                'avg_predicted_upside': rec_df['predicted_upside'].mean(),
                'avg_actual_return': rec_df['actual_return'].mean(),
                'accuracy': rec_df['prediction_correct'].mean()
            }

        return {
            'total_backtest_points': len(results),
            'valid_predictions': len(df_with_actual),
            'accuracy': accuracy,
            'mean_absolute_error': mean_error,
            'correlation': correlation,
            'recommendation_performance': recommendation_performance,
            'avg_predicted_upside': df_with_actual['predicted_upside'].mean(),
            'avg_actual_return': df_with_actual['actual_return'].mean()
        }

    def compare_with_market(
        self,
        stock_code: str,
        benchmark_code: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict:
        """
        與市場基準比較

        Args:
            stock_code: 股票代碼
            benchmark_code: 基準指數代碼（如：0050）
            start_date: 開始日期
            end_date: 結束日期

        Returns:
            比較結果
        """
        # 獲取股票價格數據
        stock_prices = self.data_manager.get_price_data(stock_code, start_date, end_date)
        
        # 獲取基準價格數據
        benchmark_prices = self.data_manager.get_price_data(benchmark_code, start_date, end_date)

        if stock_prices is None or benchmark_prices is None:
            return {'error': '無法獲取價格數據'}

        # 計算報酬率
        stock_return = self._calculate_total_return(stock_prices)
        benchmark_return = self._calculate_total_return(benchmark_prices)

        # 計算超額報酬
        excess_return = stock_return - benchmark_return

        # 計算夏普比率（簡化版）
        stock_sharpe = self._calculate_sharpe_ratio(stock_prices)
        benchmark_sharpe = self._calculate_sharpe_ratio(benchmark_prices)

        return {
            'stock_code': stock_code,
            'benchmark_code': benchmark_code,
            'period': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            'stock_return': stock_return,
            'benchmark_return': benchmark_return,
            'excess_return': excess_return,
            'stock_sharpe_ratio': stock_sharpe,
            'benchmark_sharpe_ratio': benchmark_sharpe,
            'outperformed': stock_return > benchmark_return
        }

    def _calculate_total_return(self, price_data: pd.DataFrame) -> float:
        """計算總報酬率"""
        if len(price_data) < 2:
            return 0.0
        
        start_price = price_data.iloc[0]['close_price']
        end_price = price_data.iloc[-1]['close_price']
        
        return (end_price - start_price) / start_price

    def _calculate_sharpe_ratio(self, price_data: pd.DataFrame) -> float:
        """計算夏普比率（簡化版）"""
        if len(price_data) < 2:
            return 0.0
        
        # 計算日報酬率
        price_data = price_data.copy()
        price_data['returns'] = price_data['close_price'].pct_change()
        
        # 移除 NaN
        returns = price_data['returns'].dropna()
        
        if len(returns) == 0:
            return 0.0
        
        # 計算年化報酬率和波動率
        avg_return = returns.mean() * 252  # 年化
        std_return = returns.std() * np.sqrt(252)  # 年化
        
        # 假設無風險利率為 2%
        risk_free_rate = 0.02
        
        if std_return == 0:
            return 0.0
        
        sharpe_ratio = (avg_return - risk_free_rate) / std_return
        
        return sharpe_ratio


# 測試函數
def test_backtest():
    """測試回測系統"""
    
    # 初始化
    data_manager = DataManager()
    backtest_engine = BacktestEngine(data_manager)
    
    # 測試參數
    stock_code = "2330"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*2)  # 回測2年
    growth_rates = [0.23, 0.12]
    
    print(f"=== 回測測試: {stock_code} ===")
    
    # 執行回測
    try:
        results = backtest_engine.run_backtest(
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            growth_rates=growth_rates,
            rebalance_months=3
        )
        
        if 'error' in results:
            print(f"回測失敗: {results['error']}")
        else:
            analysis = results['analysis']
            print(f"\n回測結果:")
            print(f"  總回測點數: {analysis.get('total_backtest_points', 0)}")
            print(f"  有效預測數: {analysis.get('valid_predictions', 0)}")
            print(f"  預測準確度: {analysis.get('accuracy', 0):.2%}")
            print(f"  平均絕對誤差: {analysis.get('mean_absolute_error', 0):.2%}")
            print(f"  相關係數: {analysis.get('correlation', 0):.2f}")
            
    except Exception as e:
        print(f"回測執行失敗: {str(e)}")
    
    # 測試與市場比較
    print(f"\n=== 市場比較測試 ===")
    try:
        comparison = backtest_engine.compare_with_market(
            stock_code="2330",
            benchmark_code="0050",
            start_date=start_date,
            end_date=end_date
        )
        
        if 'error' in comparison:
            print(f"市場比較失敗: {comparison['error']}")
        else:
            print(f"股票報酬: {comparison['stock_return']:.2%}")
            print(f"基準報酬: {comparison['benchmark_return']:.2%}")
            print(f"超額報酬: {comparison['excess_return']:.2%}")
            print(f"是否跑贏大盤: {'是' if comparison['outperformed'] else '否'}")
            
    except Exception as e:
        print(f"市場比較執行失敗: {str(e)}")


if __name__ == "__main__":
    test_backtest()
