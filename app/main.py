"""股票估值工具 - Streamlit Web 應用主程式。

整合 DCF 估值、回測、風險分析功能。
啟動時初始化 DI Container 與結構化日誌系統。

Architecture:
    本模組為 Streamlit 應用的唯一入口，負責：
    1. 建立 DI Container 並存入 session_state（新架構）
    2. 保留既有直接實例化模式（過渡期向下相容）
    3. 初始化結構化日誌
    4. 側邊欄導覽與頁面路由

Requirements: 1.2, 1.3
"""

from __future__ import annotations

import os
from typing import Any, Type

import streamlit as st
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 結構化日誌（模組層級初始化）
from infra.logging import get_logger

logger = get_logger(__name__)

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
)
from views.new_opportunities import show_new_opportunities

# 頁面配置 (UI-EXCEPTION: Using emojis for browser icon)
st.set_page_config(page_title="台股 DCF 估值工具", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# DI Container 初始化（新架構 — 過渡期與既有模式並存）
# ---------------------------------------------------------------------------
if "container" not in st.session_state:
    from container import setup_container

    st.session_state.container = setup_container()
    logger.info("DI Container 初始化完成")

# ---------------------------------------------------------------------------
# 既有 session_state 初始化（向下相容，views/ 仍依賴這些實例）
# ---------------------------------------------------------------------------
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
        logger.warning("排程器初始化失敗", exc_info=e)
        st.session_state.scheduler = None
        st.session_state.scheduler_enabled = False


# ---------------------------------------------------------------------------
# 服務存取輔助函式
# ---------------------------------------------------------------------------


def get_service(service_type: Type[Any]) -> Any:
    """從 DI Container 解析服務實例。

    提供統一的服務存取介面，供 views 層逐步遷移至 DI 模式使用。
    過渡期間 views 仍可直接存取 st.session_state 中的舊實例。

    Args:
        service_type: 要解析的服務介面型別（Protocol 或具體類別）。

    Returns:
        對應的服務實例。

    Raises:
        KeyError: 當指定型別尚未在 Container 中註冊時。
    """
    return st.session_state.container.resolve(service_type)


def main() -> None:
    """主程式入口。

    負責頁面路由與側邊欄 UI 渲染。
    """

    # 標題 (UI-EXCEPTION: Using emojis for UX)
    st.title("📈 台股 DCF 估值工具")
    st.markdown("基於現金流量折現法的股票內在價值分析系統")

    # 側邊欄
    with st.sidebar:
        st.header("⚙️ 設定")

        # 功能選擇
        page = st.selectbox(
            "選擇功能",
            ["市場篩選器", "DCF 估值", "新標的推薦", "成長參數優化", "歷史回測", "風險分析", "綜合報告"],
            help="請選擇要使用的功能模組。",
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
                except Exception as exc:
                    logger.debug(
                        "取得股票名稱失敗",
                        extra={"stock_code": stock_code},
                        exc_info=exc,
                    )
                    stock_name = ""

                # 顯示完整名稱
                display_name = f"{stock_code} {stock_name}" if stock_name else stock_code
                st.success(f"[OK] {display_name}")
            else:
                st.error("[WARN] 無效的股票代碼或名稱")
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
                        st.success("[OK] 自動更新排程已啟動")
                    else:
                        st.error("[FAIL] 排程啟運失敗")
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
    if page == "市場篩選器":
        from views import show_market_screener

        show_market_screener(st.session_state.data_manager)
    elif page == "DCF 估值":
        show_dcf_valuation(stock_code, stock_name, investment_amount)
    elif page == "新標的推薦":
        show_new_opportunities(st.session_state.data_manager, st.session_state.dcf_calculator)
    elif page == "成長參數優化":
        from views import show_growth_optimizer
        show_growth_optimizer(stock_code, stock_name)
    elif page == "歷史回測":
        show_backtest(stock_code, stock_name)
    elif page == "風險分析":
        show_risk_analysis(stock_code, stock_name, investment_amount)
    elif page == "綜合報告":
        show_comprehensive_report(stock_code, stock_name, investment_amount)


if __name__ == "__main__":
    main()
