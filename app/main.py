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
from pages import show_dcf_valuation, show_backtest


def get_recommendation_short_name(recommendation: str) -> str:
    """
    將投資建議轉換為簡短名稱，用於檔案命名
    
    Args:
        recommendation: 完整的投資建議文字
        
    Returns:
        簡短的投資建議名稱
    """
    # 注意：必須先檢查「不推薦」和「不建議」，避免被「推薦」子字串誤判
    if "不推薦" in recommendation or "不建議" in recommendation:
        return "不建議"
    elif "強烈推薦" in recommendation:
        return "強烈推薦"
    elif "推薦" in recommendation:
        return "推薦買入"
    elif "考慮" in recommendation:
        return "可考慮"
    else:
        return "不建議"


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


def show_risk_analysis(stock_code: str, stock_name: str, investment_amount: float):
    """顯示風險分析頁面"""
    
    # 組合顯示名稱
    display_title = f"{stock_code} {stock_name}" if stock_name else stock_code
    st.header(f"⚠️ 風險分析 - {display_title}")
    
    # 分析選項
    analysis_type = st.radio(
        "選擇分析類型",
        ["VaR 分析", "Monte Carlo 模擬", "波動率分析", "Beta 分析"],
        horizontal=True
    )
    
    if analysis_type == "VaR 分析":
        show_var_analysis(stock_code, investment_amount)
    elif analysis_type == "Monte Carlo 模擬":
        show_monte_carlo(stock_code, investment_amount)
    elif analysis_type == "波動率分析":
        show_volatility_analysis(stock_code)
    elif analysis_type == "Beta 分析":
        show_beta_analysis(stock_code)


def show_var_analysis(stock_code: str, investment_amount: float):
    """VaR 分析"""
    
    confidence_level = st.slider("信心水準", 0.90, 0.99, 0.95, 0.01, format="%.0f%%")
    holding_period = st.slider("持有期間（天）", 1, 30, 1)
    
    if st.button("計算 VaR"):
        with st.spinner("計算中..."):
            try:
                result = st.session_state.risk_analyzer.calculate_var(
                    stock_code=stock_code,
                    confidence_level=confidence_level,
                    holding_period=holding_period,
                    investment_amount=investment_amount
                )
                
                if 'error' in result:
                    st.error(result['error'])
                    return
                
                st.success(result['interpretation'])
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "參數法 VaR",
                        f"${result['parametric_var']['amount']:,.0f}"
                    )
                
                with col2:
                    st.metric(
                        "歷史模擬法 VaR",
                        f"${result['historical_var']['amount']:,.0f}"
                    )
                
                with col3:
                    st.metric(
                        "CVaR",
                        f"${result['cvar']['amount']:,.0f}"
                    )
                
            except Exception as e:
                st.error(f"計算失敗: {str(e)}")


def show_monte_carlo(stock_code: str, investment_amount: float):
    """Monte Carlo 模擬"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        simulations = st.select_slider(
            "模擬次數",
            options=[1000, 5000, 10000, 20000],
            value=10000
        )
    
    with col2:
        days = st.slider("模擬天數", 30, 365, 252)
    
    if st.button("開始模擬"):
        with st.spinner("模擬中，請稍候..."):
            try:
                current_price = st.session_state.data_manager.get_latest_price(stock_code)
                
                result = st.session_state.risk_analyzer.monte_carlo_simulation(
                    stock_code=stock_code,
                    current_price=current_price,
                    simulations=simulations,
                    days=days,
                    investment_amount=investment_amount
                )
                
                if 'error' in result:
                    st.error(result['error'])
                    return
                
                # 顯示結果
                st.markdown("---")
                st.subheader("📊 模擬結果")
                
                # 統計摘要
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "預期最終價格",
                        f"${result['statistics']['mean_price']:.2f}"
                    )
                
                with col2:
                    st.metric(
                        "預期報酬率",
                        f"{result['returns']['mean_return']:.2%}"
                    )
                
                with col3:
                    st.metric(
                        "虧損機率",
                        f"{result['returns']['loss_probability']:.1%}"
                    )
                
                # 投資結果
                st.markdown("### 💰 投資結果預測")
                
                inv_result = result['investment_results']
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "預期價值",
                        f"${inv_result['expected_value']:,.0f}",
                        delta=f"${inv_result['expected_profit']:,.0f}"
                    )
                
                with col2:
                    st.metric(
                        "最佳情境 (95%)",
                        f"${inv_result['best_case_95_percent']:,.0f}"
                    )
                
                with col3:
                    st.metric(
                        "最壞情境 (5%)",
                        f"${inv_result['worst_case_5_percent']:,.0f}",
                        delta=f"-${inv_result['max_potential_loss']:,.0f}",
                        delta_color="inverse"
                    )
                
                # 價格分布圖
                st.markdown("### 📊 價格分布")
                
                fig = go.Figure()
                
                # 繪製部分模擬路徑
                for path in result['simulation_paths'][:20]:
                    fig.add_trace(go.Scatter(
                        y=path,
                        mode='lines',
                        line=dict(width=0.5),
                        opacity=0.3,
                        showlegend=False
                    ))
                
                fig.update_layout(
                    title="價格模擬路徑（顯示前20條）",
                    xaxis_title="天數",
                    yaxis_title="價格",
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"模擬失敗: {str(e)}")


def show_volatility_analysis(stock_code: str):
    """波動率分析"""
    
    period_days = st.slider("分析期間（天）", 30, 365, 252)
    
    if st.button("分析波動率"):
        with st.spinner("分析中..."):
            try:
                result = st.session_state.risk_analyzer.calculate_volatility(
                    stock_code=stock_code,
                    period_days=period_days
                )
                
                if 'error' in result:
                    st.error(result['error'])
                    return
                
                # 顯示指標
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("日波動率", f"{result['daily_volatility']:.2%}")
                
                with col2:
                    st.metric("年化波動率", f"{result['annual_volatility']:.2%}")
                
                with col3:
                    st.metric("最大回撤", f"{result['max_drawdown']:.2%}")
                
                # 風險等級
                risk_level = result['interpretation']['risk_level']
                if risk_level == "低風險":
                    st.success(f"風險等級: {risk_level}")
                elif risk_level == "中等風險":
                    st.info(f"風險等級: {risk_level}")
                else:
                    st.warning(f"風險等級: {risk_level}")
                
                st.write(result['interpretation']['description'])
                
            except Exception as e:
                st.error(f"分析失敗: {str(e)}")


def show_beta_analysis(stock_code: str):
    """Beta 分析"""
    
    market_code = st.text_input("市場基準代碼", value="0050")
    period_days = st.slider("分析期間（天）", 30, 365, 252, key="beta_period")
    
    if st.button("分析 Beta"):
        with st.spinner("分析中..."):
            try:
                result = st.session_state.risk_analyzer.calculate_beta(
                    stock_code=stock_code,
                    market_code=market_code,
                    period_days=period_days
                )
                
                if 'error' in result:
                    st.error(result['error'])
                    return
                
                # 顯示指標
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Beta 係數", f"{result['beta']:.2f}")
                
                with col2:
                    st.metric("Alpha", f"{result['alpha']:.2%}")
                
                with col3:
                    st.metric("相關係數", f"{result['correlation']:.2f}")
                
                # 解讀
                st.info(result['interpretation']['beta_meaning'])
                st.write(result['interpretation']['risk_profile'])
                
            except Exception as e:
                st.error(f"分析失敗: {str(e)}")


def show_comprehensive_report(stock_code: str, stock_name: str, investment_amount: float):
    """顯示綜合報告"""
    
    # 組合顯示名稱
    display_title = f"{stock_code} {stock_name}" if stock_name else stock_code
    st.header(f"📋 綜合分析報告 - {display_title}")
    
    # DCF 參數設定區
    with st.expander("⚙️ DCF 參數設定", expanded=False):
        st.markdown("### 成長率假設")
        st.caption("系統會根據歷史數據提供建議值，您也可以自行調整")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 獲取系統建議值作為預設
            try:
                suggested_rates = st.session_state.data_manager.calculate_historical_growth_rate(stock_code)
                default_gr1 = max(-50.0, min(50.0, suggested_rates['growth_rate_1_5'] * 100))
                suggestion_message = suggested_rates['message']
            except:
                default_gr1 = 23.0
                suggestion_message = "使用預設成長率"
            
            growth_rate_1 = st.number_input(
                "成長率 1-5年 (%)",
                min_value=-50.0,
                max_value=50.0,
                value=default_gr1,
                step=0.1,
                key="comp_gr1",
                help="系統根據歷史數據建議的成長率，可自行調整"
            ) / 100
        
        with col2:
            try:
                default_gr2 = max(-50.0, min(50.0, suggested_rates['growth_rate_6_10'] * 100))
            except:
                default_gr2 = 12.0
            
            growth_rate_2 = st.number_input(
                "成長率 6-10年 (%)",
                min_value=-50.0,
                max_value=30.0,
                value=default_gr2,
                step=0.1,
                key="comp_gr2",
                help="系統根據歷史數據建議的成長率，可自行調整"
            ) / 100
        
        # 顯示建議訊息
        if suggestion_message:
            if default_gr1 < 0 or default_gr2 < 0:
                st.warning(f"⚠️ {suggestion_message}")
            else:
                st.info(f"💡 {suggestion_message}")
    
    if st.button("🚀 生成完整報告", type="primary"):
        with st.spinner("生成報告中，請稍候..."):
            try:
                # 獲取基本資訊
                current_price = st.session_state.data_manager.get_latest_price(stock_code)
                current_eps = st.session_state.data_manager.get_latest_eps(stock_code)
                
                if current_price == 0 or current_eps == 0:
                    st.error("無法獲取股票數據")
                    return
                
                # DCF 估值 - 使用輸入的成長率
                st.markdown("## 💎 DCF 估值")
                dcf_result = st.session_state.dcf_calculator.calculate_dcf_value(
                    current_price=current_price,
                    current_eps=current_eps,
                    growth_rates=[growth_rate_1, growth_rate_2],
                    stock_code=stock_code,
                    stock_name=stock_name,
                    data_source='YFinance/FinMind',
                    weighting_method=st.session_state.get('weighting_method', 'equal_weighted')
                )
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("內在價值", f"${dcf_result['intrinsic_value']:.2f}")
                with col2:
                    st.metric("目前股價", f"${dcf_result['current_price']:.2f}")
                with col3:
                    st.metric("潛在獲利率", f"{dcf_result['upside_potential']:.1%}")
                
                st.info(f"投資建議: {dcf_result['recommendation']}")
                
                # 風險分析
                st.markdown("## ⚠️ 風險評估")
                
                risk_report = st.session_state.risk_analyzer.comprehensive_risk_report(
                    stock_code=stock_code,
                    investment_amount=investment_amount
                )
                
                if 'error' not in risk_report:
                    # 風險評分
                    risk_score = risk_report['risk_score']
                    st.metric("風險評分", f"{risk_score['score']:.1f}/100")
                    
                    if risk_score['score'] >= 60:
                        st.success(f"風險等級: {risk_score['level']}")
                    elif risk_score['score'] >= 40:
                        st.info(f"風險等級: {risk_score['level']}")
                    else:
                        st.warning(f"風險等級: {risk_score['level']}")
                    
                    # 風險指標
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if 'volatility_analysis' in risk_report:
                            vol = risk_report['volatility_analysis']
                            st.metric("年化波動率", f"{vol.get('annual_volatility', 0):.2%}")
                    
                    with col2:
                        if 'beta_analysis' in risk_report:
                            beta = risk_report['beta_analysis']
                            st.metric("Beta 係數", f"{beta.get('beta', 0):.2f}")
                    
                    # VaR
                    if 'value_at_risk' in risk_report and 'error' not in risk_report['value_at_risk']:
                        var = risk_report['value_at_risk']
                        st.warning(var.get('interpretation', ''))
                
                # 總結
                st.markdown("## 📝 投資總結")
                
                summary_text = f"""
                ### 估值分析
                - 目前股價: ${current_price:.2f}
                - DCF 內在價值: ${dcf_result['intrinsic_value']:.2f}
                - 潛在獲利率: {dcf_result['upside_potential']:.1%}
                - 投資建議: {dcf_result['recommendation']}
                
                ### 風險評估
                """
                
                if 'error' not in risk_report:
                    summary_text += f"""
                - 風險等級: {risk_score['level']}
                - 風險評分: {risk_score['score']:.1f}/100
                """
                
                st.markdown(summary_text)
                
                # 匯出報告區
                st.markdown("---")
                st.markdown("## 📥 匯出報告")
                
                # 初始化報告生成器（如果尚未初始化）
                if 'report_generator' not in st.session_state:
                    st.session_state.report_generator = ReportGenerator()
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # 生成 Excel 報告
                    try:
                        excel_buffer = st.session_state.report_generator.generate_excel_report(
                            stock_code=stock_code,
                            stock_name=stock_name,
                            dcf_result=dcf_result,
                            risk_report=risk_report,
                            current_price=current_price,
                            current_eps=current_eps,
                            investment_amount=investment_amount
                        )
                        
                        # 取得簡短投資建議用於檔名
                        recommendation_short = get_recommendation_short_name(dcf_result['recommendation'])
                        
                        st.download_button(
                            label="📊 下載 Excel 報告",
                            data=excel_buffer,
                            file_name=f"{stock_code}_{stock_name}_{recommendation_short}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error(f"Excel 生成失敗: {str(e)}")
                
                with col2:
                    # 生成 PDF 報告
                    try:
                        # 準備圖表圖片（可選）
                        chart_images = {}
                        
                        # 轉換現金流圖表為圖片
                        try:
                            cash_flow_df = pd.DataFrame({
                                '年度': [f"第{i+1}年" for i in range(len(dcf_result['cash_flows']))],
                                '預測現金流': dcf_result['cash_flows'],
                                '現值': dcf_result['present_values']
                            })
                            
                            fig = go.Figure()
                            fig.add_trace(go.Bar(
                                x=cash_flow_df['年度'],
                                y=cash_flow_df['預測現金流'],
                                name='預測現金流',
                                marker_color='lightblue'
                            ))
                            fig.add_trace(go.Bar(
                                x=cash_flow_df['年度'],
                                y=cash_flow_df['現值'],
                                name='現值',
                                marker_color='darkblue'
                            ))
                            
                            fig.update_layout(
                                title="未來現金流與現值",
                                xaxis_title="年度",
                                yaxis_title="金額",
                                barmode='group',
                                height=400
                            )
                            
                            chart_img = st.session_state.report_generator.save_plotly_chart_as_image(fig)
                            if chart_img:
                                chart_images['cash_flow_chart'] = chart_img
                        except Exception as chart_error:
                            st.warning(f"圖表轉換失敗: {str(chart_error)}")
                        
                        pdf_buffer = st.session_state.report_generator.generate_pdf_report(
                            stock_code=stock_code,
                            stock_name=stock_name,
                            dcf_result=dcf_result,
                            risk_report=risk_report,
                            current_price=current_price,
                            current_eps=current_eps,
                            investment_amount=investment_amount,
                            chart_images=chart_images
                        )
                        
                        # 取得簡短投資建議用於檔名
                        recommendation_short = get_recommendation_short_name(dcf_result['recommendation'])
                        
                        st.download_button(
                            label="📄 下載 PDF 報告",
                            data=pdf_buffer,
                            file_name=f"{stock_code}_{stock_name}_{recommendation_short}_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error(f"PDF 生成失敗: {str(e)}")
                
                # 免責聲明
                st.markdown("---")
                st.warning(
                    "⚠️ **免責聲明**: "
                    "本工具僅供參考，不構成投資建議。"
                    "投資有風險，請謹慎評估後再做決定。"
                )
                
            except Exception as e:
                st.error(f"生成報告失敗: {str(e)}")


if __name__ == "__main__":
    main()
