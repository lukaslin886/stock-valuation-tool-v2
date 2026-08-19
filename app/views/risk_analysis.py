"""
風險分析頁面模組
提供 VaR、Monte Carlo、波動率、Beta 等風險分析功能
"""

import streamlit as st
import plotly.graph_objects as go


def show_risk_analysis(stock_code: str, stock_name: str, investment_amount: float):
    """顯示風險分析頁面"""
    
    # 組合顯示名稱
    display_title = f"{stock_code} {stock_name}" if stock_name else stock_code
    st.header(f"[WARN] 風險分析 - {display_title}")
    
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
