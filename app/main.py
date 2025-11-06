"""
股票估值工具 - Streamlit Web 應用主程式
整合 DCF 估值、回測、風險分析功能
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from dcf_calculator import DCFCalculator
from data import DataManager
from backtest import BacktestEngine
from risk_analysis import RiskAnalyzer
from report_generator import ReportGenerator

# 導入頁面模組
from pages import show_dcf_valuation, show_backtest, show_risk_analysis, show_comprehensive_report


# 頁面配置
st.set_page_config(
    page_title="台股 DCF 估值工具",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化 session state
if 'data_manager' not in st.session_state:
    st.session_state.data_manager = DataManager()
if 'dcf_calculator' not in st.session_state:
    st.session_state.dcf_calculator = DCFCalculator()
if 'backtest_engine' not in st.session_state:
    st.session_state.backtest_engine = BacktestEngine(st.session_state.data_manager)
if 'risk_analyzer' not in st.session_state:
    st.session_state.risk_analyzer = RiskAnalyzer(st.session_state.data_manager)


def main():
    """主程式入口"""
    
    # 標題
    st.title("📈 台股 DCF 估值工具")
    st.markdown("基於現金流量折現法的股票內在價值分析系統")
    
    # 側邊欄
    with st.sidebar:
        st.header("⚙️ 設定")
        
        # 功能選擇
        page = st.selectbox(
            "選擇功能",
            ["DCF 估值", "歷史回測", "風險分析", "綜合報告"]
        )
        
        st.markdown("---")
        
        # 股票輸入（支援代碼或名稱）
        stock_input = st.text_input(
            "股票代碼或名稱",
            value="2330",
            help="請輸入台股代碼（例如：2330）或完整名稱（例如：台積電、TSMC）"
        )
        
        # 即時驗證與顯示
        stock_code = ""
        stock_name = ""
        if stock_input:
            stock_info = st.session_state.data_manager.normalize_stock_input(stock_input)
            
            if stock_info['is_valid']:
                stock_code = stock_info['stock_code']
                
                # 獲取完整的股票資訊以取得股票名稱
                try:
                    full_info = st.session_state.data_manager.get_stock_info(stock_code)
                    stock_name = full_info.get('stock_name', '') if full_info else ''
                except:
                    stock_name = ''
                
                # 顯示完整名稱
                display_name = f"{stock_code} {stock_name}" if stock_name else stock_code
                st.success(f"✓ {display_name}")
            else:
                st.error("⚠️ 無效的股票代碼或名稱")
                st.info("請輸入有效的台股代碼（如：2330）或完整股票名稱（如：台積電）")
                stock_code = ""
                stock_name = ""
        
        # 投資金額
        investment_amount = st.number_input(
            "投資金額（元）",
            min_value=10000,
            max_value=10000000,
            value=100000,
            step=10000
        )
        
        st.markdown("---")
        st.markdown("### 關於此工具")
        st.info(
            "此工具使用 DCF（現金流量折現法）評估股票內在價值，"
            "整合 FinLab 數據，提供專業的投資分析。"
        )
    
    # 根據選擇顯示不同頁面
    if page == "DCF 估值":
        show_dcf_valuation(stock_code, stock_name, investment_amount)
    elif page == "歷史回測":
        show_backtest(stock_code, stock_name)
    elif page == "風險分析":
        show_risk_analysis(stock_code, stock_name, investment_amount)
    elif page == "綜合報告":
        show_comprehensive_report(stock_code, stock_name, investment_amount)


if __name__ == "__main__":
    main()
