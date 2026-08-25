"""
Growth Optimizer View
提供參數最佳化功能，幫助使用者尋找最適合特定股票的權重參數 (lambda)。
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as plotly_go
from dcf_calculator import DCFCalculator
from data.manager import DataManagerV2


def show_growth_optimizer(stock_code: str, stock_name: str):
    st.header("📈 成長參數優化器 (Growth Optimizer)")
    st.markdown("透過模擬不同的近期權重參數 (Lambda, $\lambda$)，找出最穩健的估值基準。")

    if not stock_code:
        st.warning("請先在左側欄輸入股票代碼！")
        return

    st.subheader(f"分析標的: {stock_code} {stock_name}")

    # Slider for Lambda Range
    st.markdown("### 參數測試範圍設定")
    col1, col2 = st.columns(2)
    with col1:
        lambda_min = st.number_input("最小 Lambda", min_value=0.1, max_value=0.9, value=0.1, step=0.1)
    with col2:
        lambda_max = st.number_input("最大 Lambda", min_value=0.2, max_value=1.0, value=0.9, step=0.1)
    
    if lambda_min >= lambda_max:
        st.error("最小 Lambda 必須小於最大 Lambda")
        return

    if st.button("▶ 開始參數優化分析", type="primary"):
        with st.spinner("正在計算多重情境..."):
            try:
                # Get instances
                data_manager = st.session_state.data_manager
                dcf_calculator = st.session_state.dcf_calculator

                # --- Fix: 在迴圈外取得 EPS 與股價，避免重複 API 呼叫 ---
                current_eps = data_manager.get_latest_eps(stock_code)
                current_price_val = data_manager.get_latest_price(stock_code)

                if current_eps <= 0 or current_price_val <= 0:
                    st.error("無法取得有效的 EPS 或股價資料，請確認股票代碼是否正確。")
                    return

                # Prepare test points (以整數步進避免浮點累積誤差，確保不超出 lambda_max)
                test_lambdas = np.arange(
                    int(round(lambda_min * 10)),
                    int(round(lambda_max * 10)) + 1,
                    1,
                ) / 10.0
                results = []

                for l in test_lambdas:
                    # --- Fix: 以 recent_weight_ratio 參數呼叫 calculate_historical_growth_rate ---
                    growth_info = data_manager.calculate_historical_growth_rate(
                        stock_code, recent_weight_ratio=round(l, 2)
                    )
                    g1_5 = growth_info['growth_rate_1_5']
                    g6_10 = growth_info['growth_rate_6_10']

                    # --- Fix: 呼叫正確的 calculate_dcf_value 方法 ---
                    result = dcf_calculator.calculate_dcf_value(
                        current_price=current_price_val,
                        current_eps=current_eps,
                        growth_rates=[g1_5, g6_10],
                        discount_rate=0.11,
                        stock_code=stock_code,
                        weighting_method=growth_info.get('weighting_method', 'time_weighted')
                    )

                    if result and result.get('intrinsic_value', 0) > 0:
                        results.append({
                            'Lambda': round(l, 2),
                            'Intrinsic Value': result['intrinsic_value'],
                            'Growth Rate 1-5Y (%)': g1_5 * 100,
                            'Growth Rate 6-10Y (%)': g6_10 * 100,
                        })

                if not results:
                    st.warning("無法計算出有效估值，請確認該股票資料是否齊全。")
                    return

                results_df = pd.DataFrame(results)

                # Find optimal (median or most stable)
                median_val = results_df['Intrinsic Value'].median()
                optimal_row = results_df.iloc[(results_df['Intrinsic Value'] - median_val).abs().argsort()[:1]]
                optimal_lambda = optimal_row['Lambda'].values[0]
                optimal_value = optimal_row['Intrinsic Value'].values[0]

                st.success(f"✅ 分析完成！建議最佳 Lambda 為 **{optimal_lambda}** (得出穩健估值: {optimal_value:.2f})")

                # Plot
                fig = plotly_go.Figure()
                fig.add_trace(plotly_go.Scatter(
                    x=results_df['Lambda'],
                    y=results_df['Intrinsic Value'],
                    mode='lines+markers',
                    name='內在價值',
                    line=dict(color='#1f77b4', width=3),
                    marker=dict(size=8)
                ))

                # --- Fix: 改用 get_latest_price 取得目前股價 ---
                current_price = data_manager.get_latest_price(stock_code)
                if current_price:
                    fig.add_hline(y=current_price, line_dash="dash", line_color="red", annotation_text="目前股價")

                # Highlight optimal point
                fig.add_trace(plotly_go.Scatter(
                    x=[optimal_lambda],
                    y=[optimal_value],
                    mode='markers',
                    name='最佳參數建議',
                    marker=dict(color='green', size=15, symbol='star')
                ))

                fig.update_layout(
                    title="Lambda 權重對內在價值的影響敏感度分析",
                    xaxis_title="近期權重 (Lambda)",
                    yaxis_title="DCF 內在價值 (元)",
                    hovermode="x unified"
                )

                st.plotly_chart(fig, use_container_width=True)

                # Data Table
                with st.expander("查看詳細數據"):
                    st.dataframe(results_df.style.format({
                        'Lambda': '{:.1f}',
                        'Intrinsic Value': '{:.2f}',
                        'Growth Rate 1-5Y (%)': '{:.2f}%',
                        'Growth Rate 6-10Y (%)': '{:.2f}%',
                    }))

            except Exception as e:
                st.error(f"分析過程發生錯誤: {str(e)}")
