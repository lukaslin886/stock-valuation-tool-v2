"""
DCF 股票估值計算器
基於現金流量折現法，參考巴菲特價值投資理念
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional

# 支援相對導入和絕對導入
try:
    from .risk.slippage_model import SlippageModel
except ImportError:
    from risk.slippage_model import SlippageModel


class DCFCalculator:
    """DCF 股票估值計算器"""

    def __init__(self, enable_slippage: bool = True):
        """
        初始化計算器
        
        Args:
            enable_slippage: 是否啟用滑動風險計算
        """
        self.default_params = {
            'risk_free_rate': 0.04,    # 無風險利率 4%
            'risk_premium': 0.04,      # 風險補償 4%
            'inflation_rate': 0.03,    # 通貨膨脹率 3%
            'perpetual_growth': 0.02,  # 永續成長率 2%
        }
        
        # 滑動風險模型
        self.enable_slippage = enable_slippage
        if enable_slippage:
            self.slippage_model = SlippageModel()
        else:
            self.slippage_model = None

    def calculate_dcf_value(
        self,
        current_price: float,
        current_eps: float,
        growth_rates: List[float],
        discount_rate: Optional[float] = None,
        years: int = 10,
        stock_code: Optional[str] = None,
        stock_name: Optional[str] = None,
        data_source: Optional[str] = None,
        weighting_method: Optional[str] = None
    ) -> Dict:
        """
        計算 DCF 股票價值

        Args:
            current_price: 目前股價
            current_eps: 當前每股盈餘
            growth_rates: 成長率列表 [1-5年, 6-10年]
            discount_rate: 折現率 (如果為 None 則使用 CAPM 計算)
            years: 預測年數
            stock_code: 股票代碼（可選）
            stock_name: 股票名稱（可選）
            data_source: 資料來源（可選）
            weighting_method: 成長率計算方法（可選）

        Returns:
            包含計算結果的字典
        """

        # 計算折現率 (如果未提供)
        if discount_rate is None:
            discount_rate = self._calculate_capm_rate()

        # 預測未來現金流
        cash_flows = self._project_cash_flows(current_eps, growth_rates, years)

        # 計算現金流現值
        present_values = self._calculate_present_values(cash_flows, discount_rate)

        # 計算終值
        terminal_value = self._calculate_terminal_value(cash_flows, discount_rate)

        # 計算總價值
        total_value = sum(present_values) + terminal_value

        # 計算潛在獲利率
        upside_potential = (total_value - current_price) / current_price

        # 生成詳細結果
        result = {
            'current_price': current_price,
            'intrinsic_value': total_value,
            'upside_potential': upside_potential,
            'discount_rate': discount_rate,
            'cash_flows': cash_flows,
            'present_values': present_values,
            'terminal_value': terminal_value,
            'recommendation': self._get_investment_recommendation(upside_potential),
            'input_parameters': {
                'timestamp': datetime.now().isoformat(),
                'stock_code': stock_code,
                'stock_name': stock_name,
                'current_price': current_price,
                'current_eps': current_eps,
                'growth_rates': {
                    '1-5年': growth_rates[0] if len(growth_rates) > 0 else None,
                    '6-10年': growth_rates[1] if len(growth_rates) > 1 else None
                },
                'discount_rate': discount_rate,
                'years': years,
                'data_source': data_source or '未指定',
                'weighting_method': weighting_method or 'unknown'
            }
        }

        return result

    def _calculate_capm_rate(self) -> float:
        """使用 CAPM 模型計算折現率"""
        risk_free_rate = self.default_params['risk_free_rate']
        risk_premium = self.default_params['risk_premium']
        inflation = self.default_params['inflation_rate']

        capm_rate = risk_free_rate + risk_premium + inflation
        return capm_rate

    def _project_cash_flows(
        self,
        current_eps: float,
        growth_rates: List[float],
        years: int
    ) -> List[float]:
        """預測未來現金流"""

        cash_flows = []
        current_year_eps = current_eps

        # 確保成長率列表有足夠的元素
        while len(growth_rates) < 2:
            growth_rates.append(growth_rates[-1] if growth_rates else 0.08)

        # 1-5年使用第一個成長率
        for year in range(1, min(6, years + 1)):
            current_year_eps *= (1 + growth_rates[0])
            cash_flows.append(current_year_eps)

        # 6-10年使用第二個成長率
        for year in range(6, years + 1):
            current_year_eps *= (1 + growth_rates[1])
            cash_flows.append(current_year_eps)

        return cash_flows

    def _calculate_present_values(
        self,
        cash_flows: List[float],
        discount_rate: float
    ) -> List[float]:
        """計算現金流現值"""

        present_values = []
        for year, cash_flow in enumerate(cash_flows, 1):
            present_value = cash_flow / ((1 + discount_rate) ** year)
            present_values.append(present_value)

        return present_values

    def _calculate_terminal_value(
        self,
        cash_flows: List[float],
        discount_rate: float
    ) -> float:
        """計算終值"""

        if not cash_flows:
            return 0

        # 使用最後一年的現金流計算終值
        last_cash_flow = cash_flows[-1]
        perpetual_growth = self.default_params['perpetual_growth']

        # 終值公式: TV = CFn+1 / (r - g)
        terminal_value = last_cash_flow * (1 + perpetual_growth) / (discount_rate - perpetual_growth)

        # 折現到現值
        years = len(cash_flows)
        present_terminal_value = terminal_value / ((1 + discount_rate) ** years)

        return present_terminal_value

    def _get_investment_recommendation(self, upside_potential: float) -> str:
        """根據潛在獲利率提供投資建議"""

        if upside_potential > 0.5:  # 50%以上
            return "強烈推薦 - 具有顯著低估機會"
        elif upside_potential > 0.3:  # 30%以上
            return "推薦 - 具有投資價值"
        elif upside_potential > 0.1:  # 10%以上
            return "考慮 - 視市場情況決定"
        elif upside_potential > -0.1:  # -10%到10%
            return "觀望 - 價格接近內在價值"
        else:
            return "不推薦 - 可能被高估"

    def calculate_buy_recommendation(
        self,
        intrinsic_value: float,
        current_price: float,
        price_data: Optional[pd.DataFrame] = None,
        position_size: Optional[float] = None,
        safety_margin: float = 0.85
    ) -> Dict:
        """
        計算買入建議價格（考慮滑動風險與安全邊際）
        
        Args:
            intrinsic_value: DCF 計算的內在價值
            current_price: 目前股價
            price_data: 價格數據（用於滑價計算）
            position_size: 預計投資金額
            safety_margin: 安全邊際比例（預設 0.85，即 85% 內在價值）
            
        Returns:
            買入建議資訊字典
        """
        # 計算基礎建議買入價（考慮安全邊際）
        base_buy_price = intrinsic_value * safety_margin
        
        # 初始化結果
        result = {
            'intrinsic_value': intrinsic_value,
            'current_price': current_price,
            'safety_margin': safety_margin,
            'base_buy_price': base_buy_price,
            'recommended_buy_price': base_buy_price,
            'slippage_adjusted': False,
            'slippage_info': None,
            'is_undervalued': current_price < base_buy_price,
            'discount_pct': (intrinsic_value - current_price) / intrinsic_value if intrinsic_value > 0 else 0
        }
        
        # 如果啟用滑動風險且有價格數據，進行滑價調整
        if self.enable_slippage and self.slippage_model and price_data is not None:
            try:
                slippage_result = self.slippage_model.adjust_buy_price(
                    price_data=price_data,
                    target_price=base_buy_price,
                    position_size=position_size
                )
                
                if slippage_result['is_valid']:
                    result['recommended_buy_price'] = slippage_result['adjusted_price']
                    result['slippage_adjusted'] = True
                    result['slippage_info'] = {
                        'slippage_amount': slippage_result['slippage_amount'],
                        'slippage_pct': slippage_result['slippage_pct'],
                        'liquidity_tier': slippage_result['liquidity_tier'],
                        'message': slippage_result['message']
                    }
            except Exception as e:
                # 滑價計算失敗，使用基礎價格
                result['slippage_info'] = {
                    'error': str(e),
                    'message': '滑價計算失敗，使用基礎建議價格'
                }
        
        # 生成建議訊息
        if result['is_undervalued']:
            discount_pct = result['discount_pct'] * 100
            if discount_pct > 30:
                priority = '🔴 優先級 A'
            elif discount_pct > 15:
                priority = '🟡 優先級 B'
            else:
                priority = '🟢 優先級 C'
            
            result['recommendation'] = f'{priority} - 低估 {discount_pct:.1f}%，建議於 ${result["recommended_buy_price"]:.2f} 以下買入'
        else:
            overprice_pct = (current_price - base_buy_price) / base_buy_price * 100
            result['recommendation'] = f'⚠️ 不建議 - 目前價格高於建議買入價 {overprice_pct:.1f}%'
        
        return result
    
    def calculate_scenario_comparison(
        self,
        current_price: float,
        current_eps: float,
        base_growth_rates: List[float],
        discount_rate: Optional[float] = None,
        stock_code: Optional[str] = None,
        stock_name: Optional[str] = None,
        data_source: Optional[str] = None,
        weighting_method: Optional[str] = None
    ) -> Dict:
        """
        計算三種情境（保守、中性、樂觀）的 DCF 估值比較
        
        Args:
            current_price: 目前股價
            current_eps: 當前每股盈餘
            base_growth_rates: 基準成長率列表 [1-5年, 6-10年]
            discount_rate: 折現率
            stock_code: 股票代碼（可選）
            stock_name: 股票名稱（可選）
            data_source: 資料來源（可選）
            weighting_method: 成長率計算方法（可選）
        
        Returns:
            包含三種情境結果的字典
        """
        if discount_rate is None:
            discount_rate = self._calculate_capm_rate()
        
        scenarios = {
            '保守': {
                'growth_rates': [
                    max(-0.5, base_growth_rates[0] * 0.7),  # 降低30%，最低-50%
                    max(-0.5, base_growth_rates[1] * 0.7)
                ],
                'color': '#ef5350',
                'description': '成長率降低 30%'
            },
            '中性': {
                'growth_rates': base_growth_rates,
                'color': '#42a5f5',
                'description': '使用當前設定的成長率'
            },
            '樂觀': {
                'growth_rates': [
                    min(0.5, base_growth_rates[0] * 1.3),  # 增加30%，最高50%
                    min(0.5, base_growth_rates[1] * 1.3)
                ],
                'color': '#66bb6a',
                'description': '成長率增加 30%'
            }
        }
        
        results = {}
        for scenario_name, scenario_data in scenarios.items():
            result = self.calculate_dcf_value(
                current_price=current_price,
                current_eps=current_eps,
                growth_rates=scenario_data['growth_rates'],
                discount_rate=discount_rate,
                stock_code=stock_code,
                stock_name=stock_name,
                data_source=data_source,
                weighting_method=weighting_method
            )
            result['color'] = scenario_data['color']
            result['description'] = scenario_data['description']
            results[scenario_name] = result
        
        return results
    
    def sensitivity_analysis(
        self,
        current_price: float,
        current_eps: float,
        base_growth_rates: List[float],
        discount_rate: Optional[float] = None
    ) -> Dict:
        """敏感性分析"""

        results = {}

        # 測試不同的成長率組合
        growth_scenarios = [
            [base_growth_rates[0] * 0.8, base_growth_rates[1] * 0.8],  # 悲觀
            base_growth_rates,  # 基準
            [base_growth_rates[0] * 1.2, base_growth_rates[1] * 1.2],  # 樂觀
        ]

        # 測試不同的折現率
        discount_scenarios = [0.08, 0.11, 0.14]  # 8%, 11%, 14%

        for i, growth_rates in enumerate(growth_scenarios):
            scenario_name = ['悲觀', '基準', '樂觀'][i]
            results[scenario_name] = {}

            for disc_rate in discount_scenarios:
                dcf_result = self.calculate_dcf_value(
                    current_price, current_eps, growth_rates, disc_rate
                )
                results[scenario_name][f'折現率{disc_rate:.1%}'] = {
                    '內在價值': dcf_result['intrinsic_value'],
                    '潛在獲利率': dcf_result['upside_potential']
                }

        return results


# 測試函數
def test_dcf_calculator():
    """測試 DCF 計算器"""

    calculator = DCFCalculator()

    # 使用 Excel 中的測試數據
    test_data = {
        'current_price': 973,
        'current_eps': 32.34,
        'growth_rates': [0.23, 0.12],  # 1-5年 23%, 6-10年 12%
    }

    # 計算結果
    result = calculator.calculate_dcf_value(**test_data)

    print("=== DCF 計算結果 ===")
    print(f"目前股價: ${test_data['current_price']}")
    print(f"內在價值: ${result['intrinsic_value']:.2f}")
    print(f"潛在獲利率: {result['upside_potential']:.2%}")
    print(f"投資建議: {result['recommendation']}")

    # 敏感性分析
    sensitivity = calculator.sensitivity_analysis(**test_data)
    print("\n=== 敏感性分析 ===")
    for scenario, rates in sensitivity.items():
        print(f"\n{scenario}情境:")
        for rate, values in rates.items():
            print(f"  {rate}: 內在價值 ${values['內在價值']:.0f}, 潛在獲利率 {values['潛在獲利率']:.1%}")
    return result


if __name__ == "__main__":
    test_dcf_calculator()
