"""
股票估值工具 - Streamlit Web 應用主程式
整合 DCF 估值、回測、風險分析功能
"""

import streamlit as st
import os

from dcf_calculator import DCFCalculator
from data import DataManager
from backtest import BacktestEngine
from risk_analysis import RiskAnalyzer
from scheduler import get_or_create_scheduler

# 導入頁面模組（從 views 目錄）
from views import (
    show_dcf_valuation,
    show_backtest,
    show_risk_analysis,
    show_comprehensive_report,
    show_market_screener,
    show_user_guide,
    show_portfolio_analysis,
)
from views.new_opportunities import show_new_opportunities

# 頁面配置
st.set_page_config(page_title="台股 DCF 估值工具", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# 初始化 session state
if "data_manager" not in st.session_state:
    st.session_state.data_manager = DataManager()
if "dcf_calculator" not in st.session_state:
    st.session_state.dcf_calculator = DCFCalculator()
if "backtest_engine" not in st.session_state:
    st.session_state.backtest_engine = BacktestEngine(st.session_state.data_manager)
if "risk_analyzer" not in st.session_state:
    st.session_state.risk_analyzer = RiskAnalyzer(st.session_state.data_manager)

# 初始化排程器（可選）
if "scheduler" not in st.session_state:
    try:
        st.session_state.scheduler = get_or_create_scheduler(st.session_state.data_manager)
        st.session_state.scheduler_enabled = os.getenv("AUTO_UPDATE_SCHEDULER_ENABLED", "false").lower() == "true"
    except Exception as e:
        st.session_state.scheduler = None
        st.session_state.scheduler_enabled = False


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
            ["使用說明", "市場篩選器", "DCF 估值", "新標的推薦", "投資組合分析", "歷史回測", "風險分析", "綜合報告"],
            help="建議首次使用先閱讀「使用說明」，再進行估值與回測。",
        )

        st.markdown("---")

        # 檢查是否從篩選器帶入股票
        default_stock = "2330"
        if "selected_stock_from_screener" in st.session_state and st.session_state["selected_stock_from_screener"]:
            default_stock = st.session_state["selected_stock_from_screener"]
            # 清除狀態以免持續鎖定
            # del st.session_state['selected_stock_from_screener']
            # 註：不清除可保留選擇，但可能影響使用者手動修改，這裡選擇保留，讓 text_input 的 value 更新即可

        # 股票輸入（支援代碼或名稱）
        stock_input = st.text_input(
            "股票代碼或名稱",
            value=default_stock,
            help="可輸入台股代碼（例：2330）或完整名稱（例：台積電）。若輸入英文名稱，建議使用常見別名。",
            placeholder="範例：2330 或 台積電",
        )

        # 即時驗證與顯示
        stock_code = ""
        stock_name = ""
        if stock_input:
            stock_info = st.session_state.data_manager.normalize_stock_input(stock_input)

            if stock_info["is_valid"]:
                stock_code = stock_info["stock_code"]

                # 獲取完整的股票資訊以取得股票名稱
                try:
                    full_info = st.session_state.data_manager.get_stock_info(stock_code)
                    stock_name = full_info.get("stock_name", "") if full_info else ""
                except:
                    stock_name = ""

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
            step=10000,
            help="建議先以 100,000 元作為情境測試，再依個人資金調整。",
        )

        st.markdown("---")

        # 排程器控制面板
        if st.session_state.scheduler is not None:
            st.subheader("🔄 自動更新排程")
            
            scheduler_enabled = st.session_state.scheduler_enabled
            new_scheduler_state = st.checkbox(
                "啟用自動更新",
                value=scheduler_enabled,
                help="啟動背景排程，自動更新股價與財報資料。",
            )
            
            # 狀態變化處理
            if new_scheduler_state != scheduler_enabled:
                if new_scheduler_state:
                    # 啟動排程
                    success = st.session_state.scheduler.start_scheduler()
                    st.session_state.scheduler_enabled = success
                    if success:
                        st.success("✓ 自動更新排程已啟動")
                    else:
                        st.error("✗ 排程啟運失敗")
                else:
                    # 停止排程
                    success = st.session_state.scheduler.stop_scheduler()
                    st.session_state.scheduler_enabled = False
                    if success:
                        st.info("排程已停止")
            
            # 顯示排程狀態
            if st.session_state.scheduler_enabled:
                st.markdown("**狀態** 🟢 執行中")
                jobs = st.session_state.scheduler.get_all_jobs_status()
                if jobs:
                    with st.expander("查看排程任務"):
                        for job in jobs:
                            next_run = job.get("next_run_time", "未設定")
                            st.text(f"**{job['name']}**\n下次執行: {next_run}")
            else:
                st.markdown("**狀態** ⚫ 已停止")

        st.markdown("---")
        st.markdown("### 關於此工具")
        st.info("此工具使用 DCF（現金流量折現法）評估股票內在價值，" "整合 FinLab 數據，提供專業的投資分析。")

    # 根據選擇顯示不同頁面
    if page == "使用說明":
        show_user_guide()
    elif page == "市場篩選器":
        from views import show_market_screener

        show_market_screener(st.session_state.data_manager)
    elif page == "DCF 估值":
        show_dcf_valuation(stock_code, stock_name, investment_amount)
    elif page == "新標的推薦":
        show_new_opportunities(st.session_state.data_manager, st.session_state.dcf_calculator)
    elif page == "投資組合分析":
        show_portfolio_analysis(investment_amount)
    elif page == "歷史回測":
        show_backtest(stock_code, stock_name)
    elif page == "風險分析":
        show_risk_analysis(stock_code, stock_name, investment_amount)
    elif page == "綜合報告":
        show_comprehensive_report(stock_code, stock_name, investment_amount)


if __name__ == "__main__":
    main()
