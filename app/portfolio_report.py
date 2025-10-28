"""
投資組合報告生成模組
負責將分析結果生成 Excel 報告
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, List
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows


class PortfolioReportGenerator:
    """投資組合報告生成器"""
    
    def __init__(self):
        """初始化報告生成器"""
        # 定義顏色
        self.colors = {
            'header': 'FFD966',      # 淡黃色
            'strong_sell': 'FF9999', # 淡紅色
            'consider_sell': 'FFCC99', # 淡橘色
            'hold': '99CCFF',        # 淡藍色
            'protected': 'CCFFCC'    # 淡綠色
        }
        
    def create_sell_sheet(self, wb: Workbook, sell_list: List[Dict]) -> None:
        """
        建立賣出建議工作表
        
        Args:
            wb: Excel Workbook 物件
            sell_list: 賣出建議清單
        """
        ws = wb.create_sheet("賣出建議", 0)
        
        # 標題列
        headers = [
            '優先級', '股票代碼', '股票名稱', '股數', '成本價', '現價',
            '報酬率%', '現值', '損益', 'DCF內在價值', '估值偏離%',
            'DCF建議', '賣出理由'
        ]
        
        ws.append(headers)
        
        # 格式化標題列
        header_fill = PatternFill(start_color=self.colors['header'], 
                                 end_color=self.colors['header'], 
                                 fill_type='solid')
        header_font = Font(bold=True)
        
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # 填充資料
        for item in sell_list:
            priority_label = '🔴 高' if item['priority'] == 'A' else '🟡 中'
            
            row_data = [
                priority_label,
                item['stock_code'],
                item['stock_name'],
                int(item['shares']),
                round(item['cost_price'], 2),
                round(item['current_price'], 2),
                round(item['return_rate'], 2),
                round(item['current_value'], 0),
                round(item['profit_loss'], 0),
                round(item['intrinsic_value'], 2),
                round(item['valuation_gap'], 2),
                item['dcf_recommendation'],
                item['action_reason']
            ]
            
            ws.append(row_data)
            
            # 根據優先級著色
            row_num = ws.max_row
            fill_color = self.colors['strong_sell'] if item['priority'] == 'A' else self.colors['consider_sell']
            row_fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type='solid')
            
            for cell in ws[row_num]:
                cell.fill = row_fill
                cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # 調整欄寬
        column_widths = [10, 12, 20, 10, 12, 12, 12, 15, 15, 15, 12, 20, 30]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[chr(64 + i)].width = width
    
    def create_hold_sheet(self, wb: Workbook, hold_list: List[Dict]) -> None:
        """
        建立續抱建議工作表
        
        Args:
            wb: Excel Workbook 物件
            hold_list: 續抱建議清單
        """
        ws = wb.create_sheet("續抱建議", 1)
        
        # 標題列
        headers = [
            '股票代碼', '股票名稱', '股數', '成本價', '現價',
            '報酬率%', '現值', 'DCF內在價值', '估值偏離%',
            'DCF建議', '續抱理由'
        ]
        
        ws.append(headers)
        
        # 格式化標題列
        header_fill = PatternFill(start_color=self.colors['header'], 
                                 end_color=self.colors['header'], 
                                 fill_type='solid')
        header_font = Font(bold=True)
        
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # 填充資料
        for item in hold_list:
            row_data = [
                item['stock_code'],
                item['stock_name'],
                int(item['shares']),
                round(item['cost_price'], 2),
                round(item['current_price'], 2),
                round(item['return_rate'], 2),
                round(item['current_value'], 0),
                round(item['intrinsic_value'], 2),
                round(item['valuation_gap'], 2),
                item['dcf_recommendation'],
                item['action_reason']
            ]
            
            ws.append(row_data)
            
            # 著色
            row_num = ws.max_row
            row_fill = PatternFill(start_color=self.colors['hold'], 
                                  end_color=self.colors['hold'], 
                                  fill_type='solid')
            
            for cell in ws[row_num]:
                cell.fill = row_fill
                cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # 調整欄寬
        column_widths = [12, 20, 10, 12, 12, 12, 15, 15, 12, 20, 30]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[chr(64 + i)].width = width
    
    def create_protected_sheet(self, wb: Workbook, protected_list: List[Dict]) -> None:
        """
        建立保護名單工作表
        
        Args:
            wb: Excel Workbook 物件
            protected_list: 保護名單清單
        """
        ws = wb.create_sheet("保護名單", 2)
        
        # 標題列
        headers = [
            '類別', '股票代碼', '股票名稱', '股數', '成本價', '現價',
            '報酬率%', '現值', 'DCF內在價值', '估值偏離%',
            'DCF建議', '備註'
        ]
        
        ws.append(headers)
        
        # 格式化標題列
        header_fill = PatternFill(start_color=self.colors['header'], 
                                 end_color=self.colors['header'], 
                                 fill_type='solid')
        header_font = Font(bold=True)
        
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # 填充資料
        for item in protected_list:
            # 判斷類別
            stock_code = item['stock_code']
            if stock_code in ['2330', '2317']:
                category = '核心龍頭'
            else:
                category = '金融股'
            
            row_data = [
                category,
                item['stock_code'],
                item['stock_name'],
                int(item['shares']),
                round(item['cost_price'], 2),
                round(item['current_price'], 2),
                round(item['return_rate'], 2),
                round(item['current_value'], 0),
                round(item['intrinsic_value'], 2),
                round(item['valuation_gap'], 2),
                item['dcf_recommendation'],
                item['action_reason']
            ]
            
            ws.append(row_data)
            
            # 著色
            row_num = ws.max_row
            row_fill = PatternFill(start_color=self.colors['protected'], 
                                  end_color=self.colors['protected'], 
                                  fill_type='solid')
            
            for cell in ws[row_num]:
                cell.fill = row_fill
                cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # 調整欄寬
        column_widths = [12, 12, 20, 10, 12, 12, 12, 15, 15, 12, 20, 30]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[chr(64 + i)].width = width
    
    def create_detail_sheet(self, wb: Workbook, analysis_results: Dict) -> None:
        """
        建立完整分析明細工作表
        
        Args:
            wb: Excel Workbook 物件
            analysis_results: 分析結果
        """
        ws = wb.create_sheet("分析明細", 3)
        
        # 合併所有分析過的股票
        all_analyzed = (
            analysis_results['sell_list'] + 
            analysis_results['hold_list'] + 
            analysis_results['protected_list']
        )
        
        if not all_analyzed:
            ws.append(['無分析資料'])
            return
        
        # 標題列
        headers = [
            '股票代碼', '股票名稱', '股數', '成本價', '現價', '報酬率%',
            '現值', '損益', 'EPS', 'DCF內在價值', '估值偏離%',
            '潛在報酬%', 'DCF建議', '動作', '優先級', '理由'
        ]
        
        ws.append(headers)
        
        # 格式化標題列
        header_fill = PatternFill(start_color=self.colors['header'], 
                                 end_color=self.colors['header'], 
                                 fill_type='solid')
        header_font = Font(bold=True)
        
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # 填充資料
        for item in all_analyzed:
            row_data = [
                item['stock_code'],
                item['stock_name'],
                int(item['shares']),
                round(item['cost_price'], 2),
                round(item['current_price'], 2),
                round(item['return_rate'], 2),
                round(item['current_value'], 0),
                round(item['profit_loss'], 0),
                round(item['eps'], 2),
                round(item['intrinsic_value'], 2),
                round(item['valuation_gap'], 2),
                round(item['upside_potential'] * 100, 2),
                item['dcf_recommendation'],
                item['action'],
                item['priority'],
                item['action_reason']
            ]
            
            ws.append(row_data)
            
            # 根據動作著色
            row_num = ws.max_row
            for cell in ws[row_num]:
                cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # 調整欄寬
        column_widths = [12, 20, 10, 12, 12, 12, 15, 15, 10, 15, 12, 12, 20, 10, 10, 30]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[chr(64 + i)].width = width
    
    def create_skipped_sheet(self, wb: Workbook, skipped_list: List[Dict]) -> None:
        """
        建立未分析清單工作表
        
        Args:
            wb: Excel Workbook 物件
            skipped_list: 未分析清單
        """
        ws = wb.create_sheet("未分析清單", 4)
        
        if not skipped_list:
            ws.append(['所有符合條件的股票均已分析'])
            return
        
        # 標題列
        headers = [
            '股票代碼', '股票名稱', '股數', '成本價', '現價',
            '報酬率%', '現值', '未分析原因'
        ]
        
        ws.append(headers)
        
        # 格式化標題列
        header_fill = PatternFill(start_color=self.colors['header'], 
                                 end_color=self.colors['header'], 
                                 fill_type='solid')
        header_font = Font(bold=True)
        
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # 填充資料
        for item in skipped_list:
            row_data = [
                item['stock_code'],
                item['stock_name'],
                int(item['shares']),
                round(item['cost_price'], 2),
                round(item['current_price'], 2),
                round(item['return_rate'], 2),
                round(item['current_value'], 0),
                item['skip_reason']
            ]
            
            ws.append(row_data)
            
            # 格式化
            row_num = ws.max_row
            for cell in ws[row_num]:
                cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # 調整欄寬
        column_widths = [12, 20, 10, 12, 12, 12, 15, 30]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[chr(64 + i)].width = width
    
    def generate_report(self, analysis_results: Dict, holdings_df: pd.DataFrame) -> str:
        """
        生成完整的 Excel 報告
        
        Args:
            analysis_results: 分析結果字典
            holdings_df: 原始持股資料 DataFrame
            
        Returns:
            報告檔案路徑
        """
        # 建立 Workbook
        wb = Workbook()
        
        # 移除預設工作表
        if 'Sheet' in wb.sheetnames:
            wb.remove(wb['Sheet'])
        
        # 建立各個工作表
        self.create_sell_sheet(wb, analysis_results['sell_list'])
        self.create_hold_sheet(wb, analysis_results['hold_list'])
        self.create_protected_sheet(wb, analysis_results['protected_list'])
        self.create_detail_sheet(wb, analysis_results)
        self.create_skipped_sheet(wb, analysis_results['skipped_list'])
        
        # 生成檔案名稱
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'portfolio_analysis_{timestamp}.xlsx'
        filepath = Path('reports') / filename
        
        # 儲存檔案
        wb.save(filepath)
        
        return str(filepath)
