"""
股票分析器模組
負責持股分類、篩選與 DCF 估值分析
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import pandas as pd

# 確保可以導入 app 模組（從專案根目錄）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.data import DataManager
from app.dcf_calculator import DCFCalculator

# 導入滑動風險模型
try:
    from app.risk.slippage_model import SlippageModel
except ImportError:
    try:
        from ..app.risk.slippage_model import SlippageModel
    except ImportError:
        from risk.slippage_model import SlippageModel

# 導入策略配置
from . import config


class StockAnalyzer:
    """持股分析器"""
    
    # 從配置檔載入保護名單
    FINANCIAL_STOCKS = config.FINANCIAL_STOCKS
    CORE_STOCKS = config.CORE_STOCKS
    
    def __init__(self, enable_slippage: bool = True):
        """
        初始化分析器
        
        Args:
            enable_slippage: 是否啟用滑動風險模型，預設為 True
        """
        self.data_manager = DataManager()
        self.dcf_calculator = DCFCalculator()
        self.enable_slippage = enable_slippage
        
        # 初始化滑動風險模型
        if self.enable_slippage:
            self.slippage_model = SlippageModel()
        else:
            self.slippage_model = None
        
    def is_etf(self, stock_name: str) -> bool:
        """
        判斷是否為 ETF
        
        Args:
            stock_name: 股票名稱
            
        Returns:
            True 表示是 ETF
        """
        # ETF 通常包含這些關鍵字
        etf_keywords = ['元大', '富邦', '國泰', '中信', '永豐', 'ETF']
        
        # 或者股票代碼是 00 開頭、05 開頭
        if any(keyword in stock_name for keyword in etf_keywords):
            # 進一步檢查是否真的是 ETF（包含指數名稱等）
            etf_indicators = ['台灣50', '高股息', '美債', '日本', '日經', 
                            '公司治理', '中小', '永續', '科技', '電動車',
                            '綠能', '儲能', '小資']
            if any(indicator in stock_name for indicator in etf_indicators):
                return True
        
        return False
    
    def extract_stock_code(self, stock_name: str) -> Optional[str]:
        """
        從股票名稱中提取股票代碼（支援純中文名稱動態查詢）
        
        Args:
            stock_name: 股票名稱（可能包含代碼或純中文名稱）
            
        Returns:
            股票代碼，若無法提取則返回 None
        """
        # 1. 嘗試從名稱中提取4位數字代碼
        match = re.search(r'\b(\d{4})\b', stock_name)
        if match:
            return match.group(1)
        
        # 2. 如果名稱本身就是代碼
        if stock_name.isdigit() and len(stock_name) == 4:
            return stock_name
        
        # 3. 可能是純中文名稱，使用 DataManager 動態查詢
        try:
            normalized = self.data_manager.normalize_stock_input(stock_name)
            if normalized['is_valid'] and normalized['stock_code']:
                return normalized['stock_code']
        except Exception as e:
            # 查詢失敗，繼續
            pass
        
        return None
    
    def classify_stock(self, stock_name: str, stock_code: Optional[str] = None) -> str:
        """
        分類股票類型
        
        Args:
            stock_name: 股票名稱
            stock_code: 股票代碼（可選）
            
        Returns:
            'ETF', 'PROTECTED', 'NORMAL'
        """
        # 檢查是否為 ETF
        if self.is_etf(stock_name):
            return 'ETF'
        
        # 提取股票代碼
        if stock_code is None:
            stock_code = self.extract_stock_code(stock_name)
        
        if stock_code:
            # 檢查是否為保護名單
            if stock_code in self.FINANCIAL_STOCKS or stock_code in self.CORE_STOCKS:
                return 'PROTECTED'
        
        return 'NORMAL'
    
    def should_analyze(self, row: pd.Series) -> Tuple[bool, str]:
        """
        判斷是否應該進行 DCF 分析（階段1篩選）
        
        Args:
            row: 持股資料列
            
        Returns:
            (是否分析, 原因)
        """
        return_rate = row['報酬率']
        current_value = row.get('現值', 0)
        
        # 從配置檔讀取篩選條件
        profit_threshold = config.PROFIT_THRESHOLD
        loss_threshold = config.LOSS_THRESHOLD
        position_threshold = config.POSITION_THRESHOLD
        
        # 篩選條件
        if return_rate > profit_threshold:
            return True, f"獲利 {return_rate:.1f}%"
        elif return_rate < loss_threshold:
            return True, f"虧損 {return_rate:.1f}%"
        elif current_value > position_threshold:
            return True, f"重要部位 NT${current_value:,.0f}"
        
        # 明確列出不符合的條件
        reasons = []
        
        # 報酬率條件
        if loss_threshold <= return_rate <= profit_threshold:
            reasons.append(f"報酬率 {return_rate:.1f}%（需 >{profit_threshold}% 或 <{loss_threshold}%）")
        
        # 部位條件
        if current_value <= position_threshold:
            reasons.append(f"部位 NT${current_value:,.0f}（需 >NT${position_threshold:,.0f}）")
        
        reason_text = "、".join(reasons) if reasons else "未達篩選標準"
        return False, reason_text
    
    def analyze_single_stock(self, stock_code: str, stock_name: str, 
                           current_price: float, cost_price: float,
                           return_rate: float) -> Optional[Dict]:
        """
        分析單一股票
        
        Args:
            stock_code: 股票代碼
            stock_name: 股票名稱
            current_price: 目前市價
            cost_price: 成本價
            return_rate: 報酬率
            
        Returns:
            分析結果字典，若失敗則返回 None
        """
        try:
            # 獲取 EPS
            current_eps = self.data_manager.get_latest_eps(stock_code)
            
            if current_eps <= 0:
                return {
                    'success': False,
                    'error': '無法獲取有效 EPS'
                }
            
            # 計算建議成長率（從配置讀取時間加權設定）
            growth_rates_info = self.data_manager.calculate_historical_growth_rate(
                stock_code,
                use_time_weighting=config.ENABLE_TIME_WEIGHTING,
                recent_weight_ratio=config.RECENT_WEIGHT_RATIO
            )
            growth_rate_1 = max(-0.5, min(0.5, growth_rates_info['growth_rate_1_5']))
            growth_rate_2 = max(-0.5, min(0.5, growth_rates_info['growth_rate_6_10']))
            
            # 執行 DCF 計算
            dcf_result = self.dcf_calculator.calculate_dcf_value(
                current_price=current_price,
                current_eps=current_eps,
                growth_rates=[growth_rate_1, growth_rate_2],
                discount_rate=0.11
            )
            
            # 計算估值偏離程度
            intrinsic_value = dcf_result['intrinsic_value']
            valuation_gap = (current_price / intrinsic_value - 1) * 100 if intrinsic_value > 0 else 0
            
            return {
                'success': True,
                'stock_code': stock_code,
                'stock_name': stock_name,
                'current_price': current_price,
                'cost_price': cost_price,
                'return_rate': return_rate,
                'eps': current_eps,
                'intrinsic_value': intrinsic_value,
                'valuation_gap': valuation_gap,
                'dcf_recommendation': dcf_result['recommendation'],
                'upside_potential': dcf_result['upside_potential']
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def determine_action(self, analysis: Dict, stock_type: str) -> Tuple[str, str, str]:
        """
        判斷賣出建議
        
        Args:
            analysis: 分析結果
            stock_type: 股票類型 ('PROTECTED' 或 'NORMAL')
            
        Returns:
            (動作, 優先級, 理由)
            動作: 'SELL', 'HOLD'
            優先級: 'A', 'B', 'C'
        """
        valuation_gap = analysis['valuation_gap']
        return_rate = analysis['return_rate']
        dcf_rec = analysis['dcf_recommendation']
        
        # 從配置檔讀取賣出策略參數
        protected_overvalue = config.PROTECTED_OVERVALUE
        sell_a_overvalue = config.SELL_A_OVERVALUE
        sell_a_profit = config.SELL_A_PROFIT
        sell_b_overvalue = config.SELL_B_OVERVALUE
        sell_b_profit_min = config.SELL_B_PROFIT_MIN
        sell_b_profit_max = config.SELL_B_PROFIT_MAX
        sell_b_loss = config.SELL_B_LOSS
        
        # 保護名單特殊處理
        if stock_type == 'PROTECTED':
            if valuation_gap >= protected_overvalue:
                return 'SELL', 'B', f'保護名單但嚴重高估 {valuation_gap:.1f}%'
            else:
                return 'HOLD', 'C', '保護名單（長期持有）'
        
        # 一般股票判斷
        # 優先級A：強烈建議賣出
        if valuation_gap >= sell_a_overvalue and return_rate >= sell_a_profit and '不建議' in dcf_rec:
            return 'SELL', 'A', f'高估 {valuation_gap:.1f}% 且已獲利 {return_rate:.1f}%'
        
        # 優先級B：考慮賣出
        if valuation_gap >= sell_b_overvalue:
            return 'SELL', 'B', f'高估 {valuation_gap:.1f}%'
        
        if sell_b_profit_min <= return_rate < sell_b_profit_max and '可考慮' in dcf_rec:
            return 'SELL', 'B', f'已獲利 {return_rate:.1f}% 且估值合理'
        
        if return_rate < sell_b_loss and '不建議' in dcf_rec:
            return 'SELL', 'B', f'虧損 {return_rate:.1f}% 且DCF不建議（停損考慮）'
        
        # 續抱
        if '推薦' in dcf_rec or '強烈推薦' in dcf_rec:
            return 'HOLD', 'C', f'DCF {dcf_rec}'
        
        if abs(valuation_gap) <= 15:
            return 'HOLD', 'C', f'估值合理（偏離 {valuation_gap:.1f}%）'
        
        return 'HOLD', 'C', '一般持有'
    
    def analyze_buy_opportunities_from_holdings(
        self,
        analysis_results: Dict,
        holdings_df: pd.DataFrame,
        total_portfolio_value: float
    ) -> List[Dict]:
        """
        分析持股中的加碼機會
        
        Args:
            analysis_results: analyze_portfolio 的分析結果
            holdings_df: 持股資料 DataFrame
            total_portfolio_value: 投資組合總值
            
        Returns:
            加碼機會清單
        """
        print("\n[分析] 開始分析持股加碼機會...")
        
        buy_opportunities = []
        
        # 合併所有已分析的持股（持有建議 + 保護名單）
        analyzed_stocks = (
            analysis_results.get('hold_list', []) +
            analysis_results.get('protected_list', [])
        )
        
        # 從配置檔讀取加碼策略參數
        MIN_UNDERVALUED = config.BUY_MIN_UNDERVALUED
        MIN_UPSIDE_POTENTIAL = config.BUY_MIN_UPSIDE
        STRONG_UNDERVALUED = config.BUY_STRONG_UNDERVALUED
        STRONG_UPSIDE = config.BUY_STRONG_UPSIDE
        MAX_POSITION_NORMAL = config.BUY_MAX_POSITION_NORMAL
        MAX_POSITION_PROTECTED = config.BUY_MAX_POSITION_PROTECTED
        MAX_LOSS_THRESHOLD = config.BUY_MAX_LOSS
        BUY_A_UNDERVALUED = config.BUY_A_UNDERVALUED
        BUY_A_POSITION = config.BUY_A_POSITION
        BUY_B_UNDERVALUED = config.BUY_B_UNDERVALUED
        BUY_B_POSITION = config.BUY_B_POSITION
        IDEAL_PRICE_RATIO = config.BUY_IDEAL_PRICE_RATIO
        
        for stock in analyzed_stocks:
            stock_code = stock['stock_code']
            stock_name = stock['stock_name']
            
            # 1. 估值條件檢查
            valuation_gap = stock.get('valuation_gap', 0)
            upside_potential = stock.get('upside_potential', 0)
            dcf_rec = stock.get('dcf_recommendation', '')
            
            # 靈活篩選邏輯：
            # 1. 先檢查是否符合強條件（嚴重低估 OR 高潛在報酬）
            # 2. 如果符合強條件之一，即使另一條件不足也通過
            # 3. 如果都不符合強條件，才檢查是否同時滿足基本門檻
            
            is_strong_undervalued = valuation_gap < STRONG_UNDERVALUED
            is_strong_upside = upside_potential > STRONG_UPSIDE
            
            # 如果不符合任何強條件，檢查基本門檻
            if not (is_strong_undervalued or is_strong_upside):
                # 基本門檻：必須同時滿足低估和潛在報酬
                if valuation_gap > MIN_UNDERVALUED or upside_potential < MIN_UPSIDE_POTENTIAL:
                    continue
            
            # DCF 建議必須是「推薦」或「強烈推薦」
            if '推薦' not in dcf_rec and '強烈推薦' not in dcf_rec:
                continue
            
            # 2. 部位條件檢查
            current_value = stock.get('current_value', 0)
            position_weight = (current_value / total_portfolio_value * 100) if total_portfolio_value > 0 else 0
            
            # 判斷是否為保護名單
            is_protected = stock_code in (self.FINANCIAL_STOCKS + self.CORE_STOCKS)
            max_position = MAX_POSITION_PROTECTED if is_protected else MAX_POSITION_NORMAL
            
            # 部位已達上限，不建議加碼
            if position_weight >= max_position:
                continue
            
            # 3. 排除條件檢查
            return_rate = stock.get('return_rate', 0)
            
            # 排除：已在賣出清單
            if stock in analysis_results.get('sell_list', []):
                continue
            
            # 排除：虧損過大（避免攤平風險）
            if return_rate < MAX_LOSS_THRESHOLD:
                continue
            
            # 4. 負債比檢查（未來實作）
            # TODO: 加入負債比限制（例如 < 50%）
            # 需要 DataManager 支援 get_debt_ratio() 方法
            # debt_ratio = self.data_manager.get_debt_ratio(stock_code)
            # if debt_ratio > 50:
            #     continue
            
            # 5. 計算建議加碼資訊
            intrinsic_value = stock.get('intrinsic_value', 0)
            current_price = stock.get('current_price', 0)
            
            # 建議加碼價位：從配置檔讀取比例（安全邊際）
            base_buy_price = intrinsic_value * IDEAL_PRICE_RATIO
            
            # 整合滑價調整
            ideal_buy_price = base_buy_price  # 預設值
            slippage_info = None
            
            if self.enable_slippage and self.slippage_model:
                try:
                    # 獲取價格數據用於滑價計算（最近 10 根日 K 棒）
                    price_data = self.data_manager.get_stock_price(
                        stock_code, 
                        days=10
                    )
                    
                    if price_data is not None and len(price_data) >= 2:
                        # 計算滑價調整後的買入價
                        slippage_result = self.slippage_model.adjust_buy_price(
                            base_price=base_buy_price,
                            price_data=price_data,
                            position_size=100000  # 預設部位大小 10萬元
                        )
                        
                        if slippage_result['success']:
                            ideal_buy_price = slippage_result['adjusted_price']
                            slippage_info = {
                                'slippage_amount': slippage_result['slippage_amount'],
                                'slippage_rate': slippage_result['slippage_rate'],
                                'liquidity_tier': slippage_result['liquidity_tier'],
                                'message': slippage_result['message']
                            }
                except Exception as e:
                    # 滑價計算失敗時使用基礎價格
                    print(f"  ⚠️ {stock_code} 滑價計算失敗: {e}")
                    ideal_buy_price = base_buy_price
            
            # 可加碼空間
            available_space = max_position - position_weight
            
            # 6. 判斷優先級（使用配置檔參數）
            if valuation_gap < BUY_A_UNDERVALUED and '強烈推薦' in dcf_rec and position_weight < BUY_A_POSITION:
                priority = 'A'
                priority_text = '強烈推薦加碼'
            elif valuation_gap < BUY_B_UNDERVALUED and '推薦' in dcf_rec and position_weight < BUY_B_POSITION:
                priority = 'B'
                priority_text = '建議加碼'
            else:
                priority = 'C'
                priority_text = '可考慮加碼'
            
            # 7. 建立加碼建議資訊
            buy_opportunity = {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'current_price': current_price,
                'base_buy_price': base_buy_price,  # 基礎建議價（未含滑價）
                'ideal_buy_price': ideal_buy_price,  # 最終建議價（含滑價）
                'intrinsic_value': intrinsic_value,
                'valuation_gap': valuation_gap,
                'upside_potential': upside_potential,
                'cost_price': stock.get('cost_price', 0),
                'current_position_weight': position_weight,
                'available_space': available_space,
                'max_position': max_position,
                'is_protected': is_protected,
                'priority': priority,
                'recommendation': priority_text,
                'slippage_enabled': self.enable_slippage and slippage_info is not None,
                'slippage_info': slippage_info,  # 滑價詳細資訊
                'reason': self._generate_buy_reason(
                    valuation_gap, 
                    upside_potential, 
                    position_weight,
                    is_protected,
                    slippage_info
                )
            }
            
            buy_opportunities.append(buy_opportunity)
            print(f"  ✓ 發現加碼機會: {stock_code} {stock_name} ({priority_text})")
        
        # 排序：優先級 A > B > C，同優先級按低估幅度排序
        buy_opportunities.sort(key=lambda x: (x['priority'], x['valuation_gap']))
        
        print(f"\n[結果] 共發現 {len(buy_opportunities)} 個加碼機會")
        if buy_opportunities:
            priority_counts = {'A': 0, 'B': 0, 'C': 0}
            for opp in buy_opportunities:
                priority_counts[opp['priority']] += 1
            print(f"  優先級 A: {priority_counts['A']} 個")
            print(f"  優先級 B: {priority_counts['B']} 個")
            print(f"  優先級 C: {priority_counts['C']} 個")
        
        return buy_opportunities
    
    def _generate_buy_reason(
        self,
        valuation_gap: float,
        upside_potential: float,
        position_weight: float,
        is_protected: bool,
        slippage_info: Optional[Dict] = None
    ) -> str:
        """
        生成買入理由說明
        
        Args:
            valuation_gap: 估值偏離程度
            upside_potential: 潛在報酬率
            position_weight: 目前部位比例
            is_protected: 是否為保護名單
            slippage_info: 滑價資訊（可選）
            
        Returns:
            理由說明文字
        """
        reasons = []
        
        # 估值理由
        if valuation_gap < -30:
            reasons.append(f"嚴重低估 {abs(valuation_gap):.1f}%")
        elif valuation_gap < -20:
            reasons.append(f"明顯低估 {abs(valuation_gap):.1f}%")
        else:
            reasons.append(f"低估 {abs(valuation_gap):.1f}%")
        
        # 潛在報酬理由
        if upside_potential > 50:
            reasons.append(f"高潛在報酬 {upside_potential:.1f}%")
        elif upside_potential > 30:
            reasons.append(f"良好潛在報酬 {upside_potential:.1f}%")
        
        # 部位理由
        if position_weight < 5:
            reasons.append("部位較小，可積極加碼")
        elif position_weight < 10:
            reasons.append("部位適中，可考慮加碼")
        
        # 保護名單標註
        if is_protected:
            reasons.append("保護名單（長期投資）")
        
        # 滑價資訊（如果有）
        if slippage_info:
            liquidity = slippage_info.get('liquidity_tier', 'unknown')
            slippage_rate = slippage_info.get('slippage_rate', 0)
            if liquidity == 'very_low':
                reasons.append(f"低流動性（滑價 {slippage_rate:.2f}%）")
            elif slippage_rate > 0.5:
                reasons.append(f"滑價較高 {slippage_rate:.2f}%")
        
        return "、".join(reasons)
    
    def analyze_portfolio(self, holdings_df: pd.DataFrame) -> Optional[Dict]:
        """
        分析整個投資組合
        
        Args:
            holdings_df: 持股資料 DataFrame
            
        Returns:
            分析結果字典
        """
        print("[分析] 開始分析投資組合...")
        
        results = {
            'sell_list': [],      # 賣出建議清單
            'hold_list': [],      # 持有建議清單
            'protected_list': [], # 保護名單
            'skipped_list': [],   # 未分析清單
            'buy_opportunities': [],  # 加碼機會清單（新增）
            'statistics': {}
        }
        
        # 統計計數器
        total_count = len(holdings_df)
        etf_count = 0
        protected_count = 0
        analyzed_count = 0
        skipped_count = 0
        strong_sell_count = 0
        consider_sell_count = 0
        hold_count = 0
        
        # 逐筆分析
        for idx, row in holdings_df.iterrows():
            stock_name = row['股票名稱']
            
            # 提取股票代碼
            stock_code = self.extract_stock_code(stock_name)
            
            # 分類股票
            stock_type = self.classify_stock(stock_name, stock_code)
            
            # ETF 直接跳過
            if stock_type == 'ETF':
                etf_count += 1
                continue
            
            # 檢查是否需要分析
            should_do_analysis, reason = self.should_analyze(row)
            
            # 保護名單需要分析但特殊處理
            if stock_type == 'PROTECTED':
                should_do_analysis = True
                protected_count += 1
            
            # 準備基本資料
            stock_info = {
                'stock_code': stock_code or stock_name,
                'stock_name': stock_name,
                'shares': row['股數'],
                'cost_price': row['成交均價'],
                'current_price': row['市價'],
                'return_rate': row['報酬率'],
                'current_value': row.get('現值', 0),
                'profit_loss': row.get('總損益', 0)
            }
            
            if not should_do_analysis:
                # 未達篩選標準
                stock_info['skip_reason'] = reason
                results['skipped_list'].append(stock_info)
                skipped_count += 1
                continue
            
            # 執行 DCF 分析
            if not stock_code:
                stock_info['skip_reason'] = '無法識別股票代碼'
                results['skipped_list'].append(stock_info)
                skipped_count += 1
                continue
            
            print(f"  [{analyzed_count + 1}] 分析 {stock_code} {stock_name}...", end='')
            
            analysis = self.analyze_single_stock(
                stock_code=stock_code,
                stock_name=stock_name,
                current_price=stock_info['current_price'],
                cost_price=stock_info['cost_price'],
                return_rate=stock_info['return_rate']
            )
            
            if not analysis or not analysis.get('success'):
                error = analysis.get('error', '未知錯誤') if analysis else '分析失敗'
                print(f" 失敗 ({error})")
                stock_info['skip_reason'] = error
                results['skipped_list'].append(stock_info)
                skipped_count += 1
                continue
            
            print(f" 完成")
            analyzed_count += 1
            
            # 合併資料
            full_info = {**stock_info, **analysis}
            
            # 判斷動作
            action, priority, action_reason = self.determine_action(analysis, stock_type)
            full_info['action'] = action
            full_info['priority'] = priority
            full_info['action_reason'] = action_reason
            
            # 分類結果
            if stock_type == 'PROTECTED':
                results['protected_list'].append(full_info)
            elif action == 'SELL':
                results['sell_list'].append(full_info)
                if priority == 'A':
                    strong_sell_count += 1
                else:
                    consider_sell_count += 1
            else:
                results['hold_list'].append(full_info)
                hold_count += 1
        
        # 彙總統計
        results['statistics'] = {
            'total_holdings': total_count,
            'etf_count': etf_count,
            'protected_count': protected_count,
            'analyzed_count': analyzed_count,
            'skipped_count': skipped_count,
            'strong_sell_count': strong_sell_count,
            'consider_sell_count': consider_sell_count,
            'hold_count': hold_count
        }
        
        # 排序結果
        results['sell_list'].sort(key=lambda x: (x['priority'], -x['valuation_gap']))
        results['hold_list'].sort(key=lambda x: -x['current_value'])
        results['protected_list'].sort(key=lambda x: -x['current_value'])
        
        return results
