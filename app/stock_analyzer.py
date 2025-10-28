"""
股票分析器模組
負責持股分類、篩選與 DCF 估值分析
"""

import re
from typing import Dict, List, Tuple, Optional
import pandas as pd
from app.data import DataManager
from app.dcf_calculator import DCFCalculator


class StockAnalyzer:
    """持股分析器"""
    
    # 保護名單：金融股代碼
    FINANCIAL_STOCKS = [
        '2801', '2809', '2834', '2867',  # 彰銀、台中銀、臺企銀、三商壽
        '2881', '2882', '2883', '2884',  # 富邦金、國泰金、開發金、玉山金
        '2885', '2886', '2887', '2889',  # 元大金、兆豐金、台新金、國票金
        '2891', '2892'                    # 中信金、第一金
    ]
    
    # 核心龍頭股代碼
    CORE_STOCKS = ['2330', '2317']  # 台積電、鴻海
    
    def __init__(self):
        """初始化分析器"""
        self.data_manager = DataManager()
        self.dcf_calculator = DCFCalculator()
        
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
        
        # 篩選條件
        if return_rate > 30:
            return True, f"獲利 {return_rate:.1f}%"
        elif return_rate < -20:
            return True, f"虧損 {return_rate:.1f}%"
        elif current_value > 50000:
            return True, f"重要部位 NT${current_value:,.0f}"
        
        return False, "未達篩選標準"
    
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
            
            # 計算建議成長率
            growth_rates_info = self.data_manager.calculate_historical_growth_rate(stock_code)
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
        
        # 保護名單特殊處理
        if stock_type == 'PROTECTED':
            if valuation_gap >= 50:
                return 'SELL', 'B', f'保護名單但嚴重高估 {valuation_gap:.1f}%'
            else:
                return 'HOLD', 'C', '保護名單（長期持有）'
        
        # 一般股票判斷
        # 優先級A：強烈建議賣出
        if valuation_gap >= 30 and return_rate >= 50 and '不建議' in dcf_rec:
            return 'SELL', 'A', f'高估 {valuation_gap:.1f}% 且已獲利 {return_rate:.1f}%'
        
        # 優先級B：考慮賣出
        if valuation_gap >= 15:
            return 'SELL', 'B', f'高估 {valuation_gap:.1f}%'
        
        if 30 <= return_rate < 50 and '可考慮' in dcf_rec:
            return 'SELL', 'B', f'已獲利 {return_rate:.1f}% 且估值合理'
        
        if return_rate < -30 and '不建議' in dcf_rec:
            return 'SELL', 'B', f'虧損 {return_rate:.1f}% 且DCF不建議（停損考慮）'
        
        # 續抱
        if '推薦' in dcf_rec or '強烈推薦' in dcf_rec:
            return 'HOLD', 'C', f'DCF {dcf_rec}'
        
        if abs(valuation_gap) <= 15:
            return 'HOLD', 'C', f'估值合理（偏離 {valuation_gap:.1f}%）'
        
        return 'HOLD', 'C', '一般持有'
    
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
