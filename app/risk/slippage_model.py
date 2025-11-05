"""
滑動風險模型 (Slippage Risk Model)

基於 2 根日線 K 棒的滑價計算模型
混合模型包含：
1. 波動性滑價 (Volatility Slippage)
2. 流動性滑價 (Liquidity Slippage)  
3. 市場衝擊滑價 (Market Impact Slippage)

應用場景：
- DCF 買入建議價格修正
- 投資組合回測滑價估算
"""

from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


class SlippageModel:
    """
    滑動風險模型
    
    使用 2 根日線 K 棒計算滑價：
    - K1: 前一交易日（參考日）
    - K2: 當前交易日（交易日）
    
    混合模型：
    Total Slippage = α × Volatility + β × Liquidity + γ × Market Impact
    
    參數：
        α (volatility_weight): 波動性權重，預設 0.4
        β (liquidity_weight): 流動性權重，預設 0.3
        γ (impact_weight): 市場衝擊權重，預設 0.3
    """
    
    # ========== 流動性分級標準 ==========
    # 基於日均成交量（千股）
    LIQUIDITY_TIER = {
        'high': 100000,      # 高流動性：>= 10萬張
        'medium': 10000,     # 中流動性：>= 1萬張
        'low': 1000,         # 低流動性：>= 1000張
        # < 1000張：極低流動性
    }
    
    # ========== 滑價係數 ==========
    SLIPPAGE_COEFFICIENTS = {
        'volatility': {
            'buy': 1.0,      # 買入時波動性滑價係數
            'sell': 0.8,     # 賣出時波動性滑價係數（較小）
        },
        'liquidity': {
            'high': 0.001,   # 高流動性：0.1% 滑價
            'medium': 0.003, # 中流動性：0.3% 滑價
            'low': 0.005,    # 低流動性：0.5% 滑價
            'very_low': 0.01 # 極低流動性：1.0% 滑價
        },
        'impact': {
            'small': 0.0005,  # 小單：0.05% 市場衝擊
            'medium': 0.002,  # 中單：0.2% 市場衝擊
            'large': 0.005    # 大單：0.5% 市場衝擊
        }
    }
    
    def __init__(
        self,
        volatility_weight: float = 0.4,
        liquidity_weight: float = 0.3,
        impact_weight: float = 0.3,
        max_slippage: float = 0.05  # 最大滑價限制 5%
    ):
        """
        初始化滑動風險模型
        
        Args:
            volatility_weight: 波動性權重 (α)
            liquidity_weight: 流動性權重 (β)
            impact_weight: 市場衝擊權重 (γ)
            max_slippage: 最大滑價限制（比例）
        """
        # 確保權重總和為 1
        total_weight = volatility_weight + liquidity_weight + impact_weight
        if not np.isclose(total_weight, 1.0):
            # 標準化權重
            self.volatility_weight = volatility_weight / total_weight
            self.liquidity_weight = liquidity_weight / total_weight
            self.impact_weight = impact_weight / total_weight
        else:
            self.volatility_weight = volatility_weight
            self.liquidity_weight = liquidity_weight
            self.impact_weight = impact_weight
        
        self.max_slippage = max_slippage
    
    def calculate_slippage(
        self,
        price_data: pd.DataFrame,
        trade_type: str = 'buy',
        position_size: Optional[float] = None,
        reference_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        計算總滑價
        
        Args:
            price_data: 價格數據 DataFrame，必須包含：
                - date: 日期
                - close_price: 收盤價
                - high_price: 最高價
                - low_price: 最低價
                - volume: 成交量（股）
            trade_type: 交易類型 ('buy' 或 'sell')
            position_size: 交易部位大小（元），用於計算市場衝擊
            reference_date: 參考日期，預設使用最後一個交易日
            
        Returns:
            滑價資訊字典，包含：
            - total_slippage_pct: 總滑價百分比
            - total_slippage_amount: 總滑價金額
            - volatility_slippage: 波動性滑價
            - liquidity_slippage: 流動性滑價
            - impact_slippage: 市場衝擊滑價
            - liquidity_tier: 流動性分級
            - reference_price: 參考價格
            - adjusted_price: 調整後價格
            - is_valid: 是否有效計算
            - message: 說明訊息
        """
        # 驗證數據
        if price_data is None or len(price_data) < 2:
            return self._create_invalid_result(
                "價格數據不足（需要至少 2 根 K 棒）"
            )
        
        # 確保數據按日期排序
        price_data = price_data.sort_values('date')
        
        # 選擇參考日期（K1）和交易日期（K2）
        if reference_date:
            # 找到最接近參考日期的數據
            price_data['date_dt'] = pd.to_datetime(price_data['date'])
            ref_idx = (price_data['date_dt'] - reference_date).abs().argmin()
            if ref_idx >= len(price_data) - 1:
                ref_idx = len(price_data) - 2
        else:
            # 使用最後兩根 K 棒
            ref_idx = len(price_data) - 2
        
        k1 = price_data.iloc[ref_idx]      # 參考日（前一交易日）
        k2 = price_data.iloc[ref_idx + 1]  # 交易日（當前交易日）
        
        # 參考價格（使用 K2 的收盤價）
        reference_price = float(k2['close_price'])
        
        # 計算各項滑價
        volatility_slippage = self._calculate_volatility_slippage(
            k1, k2, trade_type
        )
        
        liquidity_slippage, liquidity_tier = self._calculate_liquidity_slippage(
            price_data, trade_type
        )
        
        impact_slippage = self._calculate_market_impact(
            k2, position_size, trade_type
        )
        
        # 加權總滑價
        total_slippage_pct = (
            self.volatility_weight * volatility_slippage +
            self.liquidity_weight * liquidity_slippage +
            self.impact_weight * impact_slippage
        )
        
        # 限制最大滑價
        total_slippage_pct = min(total_slippage_pct, self.max_slippage)
        
        # 計算滑價金額和調整後價格
        if trade_type == 'buy':
            # 買入：滑價增加成本
            total_slippage_amount = reference_price * total_slippage_pct
            adjusted_price = reference_price * (1 + total_slippage_pct)
        else:  # sell
            # 賣出：滑價減少收入
            total_slippage_amount = reference_price * total_slippage_pct
            adjusted_price = reference_price * (1 - total_slippage_pct)
        
        return {
            'total_slippage_pct': total_slippage_pct,
            'total_slippage_amount': total_slippage_amount,
            'volatility_slippage': volatility_slippage,
            'liquidity_slippage': liquidity_slippage,
            'impact_slippage': impact_slippage,
            'liquidity_tier': liquidity_tier,
            'reference_price': reference_price,
            'adjusted_price': adjusted_price,
            'is_valid': True,
            'message': f'{trade_type.upper()} 滑價計算完成 (流動性: {liquidity_tier})'
        }
    
    def _calculate_volatility_slippage(
        self,
        k1: pd.Series,
        k2: pd.Series,
        trade_type: str
    ) -> float:
        """
        計算波動性滑價
        
        基於 2 根 K 棒的價格波動範圍：
        Volatility = (High - Low) / Close
        
        Args:
            k1: 參考日 K 棒
            k2: 交易日 K 棒
            trade_type: 交易類型
            
        Returns:
            波動性滑價百分比
        """
        try:
            # K1 和 K2 的波動率
            vol_k1 = (k1['high_price'] - k1['low_price']) / k1['close_price']
            vol_k2 = (k2['high_price'] - k2['low_price']) / k2['close_price']
            
            # 平均波動率
            avg_volatility = (vol_k1 + vol_k2) / 2
            
            # 應用交易類型係數
            coefficient = self.SLIPPAGE_COEFFICIENTS['volatility'][trade_type]
            
            # 波動性滑價 = 平均波動率 × 係數 × 半數（取中間值）
            volatility_slippage = avg_volatility * coefficient * 0.5
            
            return float(volatility_slippage)
            
        except Exception as e:
            print(f"波動性滑價計算錯誤: {e}")
            return 0.002  # 預設 0.2% 滑價
    
    def _calculate_liquidity_slippage(
        self,
        price_data: pd.DataFrame,
        trade_type: str
    ) -> Tuple[float, str]:
        """
        計算流動性滑價
        
        基於平均成交量分級：
        - 高流動性 (>= 10萬張)：0.1% 滑價
        - 中流動性 (>= 1萬張)：0.3% 滑價
        - 低流動性 (>= 1000張)：0.5% 滑價
        - 極低流動性 (< 1000張)：1.0% 滑價
        
        Args:
            price_data: 價格數據 DataFrame
            trade_type: 交易類型
            
        Returns:
            (流動性滑價百分比, 流動性分級)
        """
        try:
            # 計算平均日成交量（股）
            avg_volume = price_data['volume'].tail(10).mean()
            
            # 轉換為張數（1張 = 1000股）
            avg_volume_k_shares = avg_volume / 1000
            
            # 判斷流動性分級
            if avg_volume_k_shares >= self.LIQUIDITY_TIER['high']:
                tier = 'high'
                slippage = self.SLIPPAGE_COEFFICIENTS['liquidity']['high']
            elif avg_volume_k_shares >= self.LIQUIDITY_TIER['medium']:
                tier = 'medium'
                slippage = self.SLIPPAGE_COEFFICIENTS['liquidity']['medium']
            elif avg_volume_k_shares >= self.LIQUIDITY_TIER['low']:
                tier = 'low'
                slippage = self.SLIPPAGE_COEFFICIENTS['liquidity']['low']
            else:
                tier = 'very_low'
                slippage = self.SLIPPAGE_COEFFICIENTS['liquidity']['very_low']
            
            return slippage, tier
            
        except Exception as e:
            print(f"流動性滑價計算錯誤: {e}")
            return 0.003, 'medium'  # 預設中流動性
    
    def _calculate_market_impact(
        self,
        k2: pd.Series,
        position_size: Optional[float],
        trade_type: str
    ) -> float:
        """
        計算市場衝擊滑價
        
        基於交易部位大小相對於日成交金額的比例：
        - 小單 (< 1% 日成交額)：0.05% 市場衝擊
        - 中單 (1-5% 日成交額)：0.2% 市場衝擊
        - 大單 (> 5% 日成交額)：0.5% 市場衝擊
        
        Args:
            k2: 交易日 K 棒
            position_size: 交易部位大小（元）
            trade_type: 交易類型
            
        Returns:
            市場衝擊滑價百分比
        """
        if position_size is None or position_size <= 0:
            # 無部位大小資訊，使用小單假設
            return self.SLIPPAGE_COEFFICIENTS['impact']['small']
        
        try:
            # 計算日成交金額
            daily_turnover = k2['volume'] * k2['close_price']
            
            # 計算部位相對大小
            if daily_turnover > 0:
                relative_size = position_size / daily_turnover
            else:
                # 無成交量資訊，使用中單假設
                return self.SLIPPAGE_COEFFICIENTS['impact']['medium']
            
            # 判斷訂單大小並返回對應衝擊
            if relative_size < 0.01:  # < 1%
                return self.SLIPPAGE_COEFFICIENTS['impact']['small']
            elif relative_size < 0.05:  # 1-5%
                return self.SLIPPAGE_COEFFICIENTS['impact']['medium']
            else:  # > 5%
                return self.SLIPPAGE_COEFFICIENTS['impact']['large']
            
        except Exception as e:
            print(f"市場衝擊計算錯誤: {e}")
            return self.SLIPPAGE_COEFFICIENTS['impact']['medium']
    
    def _create_invalid_result(self, message: str) -> Dict[str, Any]:
        """
        創建無效結果
        
        Args:
            message: 錯誤訊息
            
        Returns:
            無效結果字典
        """
        return {
            'total_slippage_pct': 0.0,
            'total_slippage_amount': 0.0,
            'volatility_slippage': 0.0,
            'liquidity_slippage': 0.0,
            'impact_slippage': 0.0,
            'liquidity_tier': 'unknown',
            'reference_price': 0.0,
            'adjusted_price': 0.0,
            'is_valid': False,
            'message': message
        }
    
    def adjust_buy_price(
        self,
        price_data: pd.DataFrame,
        target_price: float,
        position_size: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        調整買入建議價格（考慮滑價）
        
        用於 DCF Calculator 的買入建議
        
        Args:
            price_data: 價格數據
            target_price: 目標買入價格（DCF 建議價）
            position_size: 預計交易金額
            
        Returns:
            調整後的價格資訊
        """
        slippage_info = self.calculate_slippage(
            price_data=price_data,
            trade_type='buy',
            position_size=position_size
        )
        
        if not slippage_info['is_valid']:
            return {
                'original_price': target_price,
                'adjusted_price': target_price,
                'slippage_amount': 0.0,
                'slippage_pct': 0.0,
                'is_valid': False,
                'message': slippage_info['message']
            }
        
        # 根據參考價格調整目標價格
        price_ratio = target_price / slippage_info['reference_price']
        adjusted_target = slippage_info['adjusted_price'] * price_ratio
        
        slippage_amount = adjusted_target - target_price
        slippage_pct = slippage_amount / target_price if target_price > 0 else 0
        
        return {
            'original_price': target_price,
            'adjusted_price': adjusted_target,
            'slippage_amount': slippage_amount,
            'slippage_pct': slippage_pct,
            'liquidity_tier': slippage_info['liquidity_tier'],
            'is_valid': True,
            'message': f'買入價格已調整 (滑價: {slippage_pct*100:.2f}%)'
        }
    
    def adjust_backtesting_trades(
        self,
        trades: pd.DataFrame,
        price_data: pd.DataFrame
    ) -> pd.DataFrame:
        """
        調整回測交易記錄（考慮滑價）
        
        用於 Portfolio Analyzer 的回測功能
        
        Args:
            trades: 交易記錄 DataFrame，包含：
                - date: 交易日期
                - type: 交易類型 ('buy' 或 'sell')
                - price: 原始交易價格
                - quantity: 交易數量
            price_data: 價格數據
            
        Returns:
            調整後的交易記錄（新增 adjusted_price 欄位）
        """
        adjusted_trades = trades.copy()
        adjusted_trades['adjusted_price'] = adjusted_trades['price']
        adjusted_trades['slippage_pct'] = 0.0
        adjusted_trades['slippage_amount'] = 0.0
        
        for idx, trade in trades.iterrows():
            # 獲取交易日期前後的價格數據
            trade_date = pd.to_datetime(trade['date'])
            relevant_data = price_data[
                price_data['date'] <= trade_date
            ].tail(10)  # 取最近 10 根 K 棒
            
            if len(relevant_data) < 2:
                continue
            
            # 計算滑價
            position_size = trade['price'] * trade['quantity'] if 'quantity' in trade else None
            
            slippage_info = self.calculate_slippage(
                price_data=relevant_data,
                trade_type=trade['type'],
                position_size=position_size,
                reference_date=trade_date
            )
            
            if slippage_info['is_valid']:
                adjusted_trades.loc[idx, 'adjusted_price'] = slippage_info['adjusted_price']
                adjusted_trades.loc[idx, 'slippage_pct'] = slippage_info['total_slippage_pct']
                adjusted_trades.loc[idx, 'slippage_amount'] = slippage_info['total_slippage_amount']
        
        return adjusted_trades
