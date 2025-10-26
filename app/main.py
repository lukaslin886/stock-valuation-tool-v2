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
from data_manager import DataManager
from backtest import BacktestEngine
from risk_analysis import RiskAnalyzer


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
        
        # 股票代碼輸入
        stock_code = st.text_input(
            "股票代碼",
            value="2330",
            help="請輸入台股代碼，例如：2330（台積電）"
        )
        
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
        show_dcf_valuation(stock_code, investment_amount)
    elif page == "歷史回測":
        show_backtest(stock_code)
    elif page == "風險分析":
        show_risk_analysis(stock_code, investment_amount)
    elif page == "綜合報告":
        show_comprehensive_report(stock_code, investment_amount)


def show_dcf_valuation(stock_code: str, investment_amount: float):
    """顯示 DCF 估值頁面"""
    
    st.header(f"🎯 DCF 估值分析 - {stock_code}")
    
    # 參數設定區
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("參數設定")
        
        growth_rate_1 = st.slider(
            "成長率（1-5年）",
            min_value=0.0,
            max_value=0.50,
            value=0.23,
            step=0.01,
            format="%.0f%%"
        )
        
        growth_rate_2 = st.slider(
            "成長率（6-10年）",
            min_value=0.0,
            max_value=0.30,
            value=0.12,
            step=0.01,
            format="%.0f%%"
        )
        
        discount_rate = st.slider(
            "折現率",
            min_value=0.05,
            max_value=0.20,
            value=0.11,
            step=0.01,
            format="%.0f%%",
            help="可使用 CAPM 模型計算，或手動設定"
        )
    
    with col2:
        st.subheader("股票資訊")
        
        # 獲取股票資訊
        with st.spinner("正在獲取數據..."):
            try:
                current_price = st.session_state.data_manager.get_latest_price(stock_code)
                current_eps = st.session_state.data_manager.get_latest_eps(stock_code)
                
                if current_price > 0:
                    st.metric("目前股價", f"${current_price:.2f}")
                else:
                    st.warning("⚠️ 無法獲取股價，請檢查股票代碼")
                    return
                
                if current_eps > 0:
                    st.metric("最新 EPS", f"${current_eps:.2f}")
                    st.metric("本益比", f"{current_price/current_eps:.2f}")
                else:
                    st.warning("⚠️ 無法獲取 EPS 數據")
                    return
                    
            except Exception as e:
                st.error(f"數據獲取失敗: {str(e)}")
                return
    
    # 計算按鈕
    if st.button("🚀 開始計算", type="primary", use_container_width=True):
        with st.spinner("計算中..."):
            try:
                # 執行 DCF 計算
                result = st.session_state.dcf_calculator.calculate_dcf_value(
                    current_price=current_price,
                    current_eps=current_eps,
                    growth_rates=[growth_rate_1, growth_rate_2],
                    discount_rate=discount_rate
                )
                
                # 顯示結果
                st.markdown("---")
                st.subheader("📊 計算結果")
                
                # 關鍵指標
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "內在價值",
                        f"${result['intrinsic_value']:.2f}",
                        delta=f"{result['upside_potential']:.1%}",
                        delta_color="normal"
                    )
                
                with col2:
                    st.metric("目前股價", f"${result['current_price']:.2f}")
                
                with col3:
                    st.metric("折現率", f"{result['discount_rate']:.1%}")
                
                # 投資建議
                st.markdown("### 💡 投資建議")
                
                recommendation = result['recommendation']
                if "強烈推薦" in recommendation:
                    st.success(f"✅ {recommendation}")
                elif "推薦" in recommendation:
                    st.info(f"ℹ️ {recommendation}")
                elif "考慮" in recommendation:
                    st.warning(f"⚠️ {recommendation}")
                else:
                    st.error(f"❌ {recommendation}")
                
                # 現金流量表
                st.markdown("### 📈 未來現金流預測")
                
                cash_flow_df = pd.DataFrame({
                    '年度': [f"第{i+1}年" for i in range(len(result['cash_flows']))],
                    '預測現金流': result['cash_flows'],
                    '現值': result['present_values']
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
                
                st.plotly_chart(fig, use_container_width=True)
                
                # 詳細數據表
                with st.expander("📋 查看詳細數據"):
                    st.dataframe(cash_flow_df, use_container_width=True)
                
                # 敏感性分析
                st.markdown("### 🎛️ 敏感性分析")
                
                with st.spinner("執行敏感性分析..."):
                    sensitivity = st.session_state.dcf_calculator.sensitivity_analysis(
                        current_price=current_price,
                        current_eps=current_eps,
                        base_growth_rates=[growth_rate_1, growth_rate_2]
                    )
                    
                    # 製作敏感性分析表格
                    sensitivity_data = []
                    for scenario, rates in sensitivity.items():
                        for rate_name, values in rates.items():
                            sensitivity_data.append({
                                '情境': scenario,
                                '折現率': rate_name,
                                '內在價值': f"${values['內在價值']:.0f}",
                                '潛在獲利率': f"{values['潛在獲利率']:.1%}"
                            })
                    
                    sensitivity_df = pd.DataFrame(sensitivity_data)
                    st.dataframe(sensitivity_df, use_container_width=True)
                
            except Exception as e:
                st.error(f"計算失敗: {str(e)}")


def show_backtest(stock_code: str):
    """顯示回測頁面"""
    
    st.header(f"⏮️ 歷史回測 - {stock_code}")
    
    # 回測參數
    col1, col2 = st.columns(2)
    
    with col1:
        backtest_years = st.slider("回測年數", 1, 5, 2)
        growth_rate_1 = st.slider("成長率（1-5年）", 0.0, 0.50, 0.23, 0.01, format="%.0f%%", key="bt_gr1")
    
    with col2:
        rebalance_months = st.slider("重新計算週期（月）", 1, 12, 3)
        growth_rate_2 = st.slider("成長率（6-10年）", 0.0, 0.30, 0.12, 0.01, format="%.0f%%", key="bt_gr2")
    
    if st.button("🔄 執行回測", type="primary"):
        with st.spinner("回測中，這可能需要一些時間..."):
            try:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=365*backtest_years)
                
                results = st.session_state.backtest_engine.run_backtest(
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    growth_rates=[growth_rate_1, growth_rate_2],
                    rebalance_months=rebalance_months
                )
                
                if 'error' in results:
                    st.error(f"回測失敗: {results['error']}")
                    return
                
                # 顯示摘要
                st.markdown("---")
                st.subheader("📊 回測結果摘要")
                
                analysis = results['analysis']
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("總回測點數", analysis.get('total_backtest_points', 0))
                
                with col2:
                    st.metric("有效預測數", analysis.get('valid_predictions', 0))
                
                with col3:
                    accuracy = analysis.get('accuracy', 0)
                    st.metric("預測準確度", f"{accuracy:.1%}")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.metric("平均絕對誤差", f"{analysis.get('mean_absolute_error', 0):.2%}")
                
                with col2:
                    st.metric("相關係數", f"{analysis.get('correlation', 0):.2f}")
                
                # 推薦等級表現
                if 'recommendation_performance' in analysis:
                    st.markdown("### 📈 各推薦等級表現")
                    
                    perf_data = []
                    for rec, perf in analysis['recommendation_performance'].items():
                        perf_data.append({
                            '推薦等級': rec,
                            '次數': perf['count'],
                            '平均預測獲利率': f"{perf['avg_predicted_upside']:.2%}",
                            '平均實際報酬率': f"{perf['avg_actual_return']:.2%}",
                            '準確度': f"{perf['accuracy']:.1%}"
                        })
                    
                    st.dataframe(pd.DataFrame(perf_data), use_container_width=True)
                
            except Exception as e:
                st.error(f"回測執行失敗: {str(e)}")


def show_risk_analysis(stock_code: str, investment_amount: float):
    """顯示風險分析頁面"""
    
    st.header(f"⚠️ 風險分析 - {stock_code}")
    
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


def show_comprehensive_report(stock_code: str, investment_amount: float):
    """顯示綜合報告"""
    
    st.header(f"📋 綜合分析報告 - {stock_code}")
    
    if st.button("🚀 生成完整報告", type="primary"):
        with st.spinner("生成報告中，請稍候..."):
            try:
                # 獲取基本資訊
                current_price = st.session_state.data_manager.get_latest_price(stock_code)
                current_eps = st.session_state.data_manager.get_latest_eps(stock_code)
                
                if current_price == 0 or current_eps == 0:
                    st.error("無法獲取股票數據")
                    return
                
                # DCF 估值
                st.markdown("## 💎 DCF 估值")
                dcf_result = st.session_state.dcf_calculator.calculate_dcf_value(
                    current_price=current_price,
                    current_eps=current_eps,
                    growth_rates=[0.23, 0.12]
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
