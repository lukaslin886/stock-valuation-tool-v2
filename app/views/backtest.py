"""
歷史回測頁面模組
提供股票投資策略的歷史回測功能
"""

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd


def show_backtest(stock_code: str, stock_name: str):
    """顯示回測頁面"""
    
    # 組合顯示名稱
    display_title = f"{stock_code} {stock_name}" if stock_name else stock_code
    st.header(f"⏮️ 歷史回測 - {display_title}")
    
    # 回測參數
    col1, col2 = st.columns(2)
    
    with col1:
        backtest_years = st.slider("回測年數", 1, 5, 2)
        
        # 成長率（1-5年）- 滑桿 + 精確輸入
        st.markdown("**成長率（1-5年）**")
        bt_slider_col1, bt_input_col1 = st.columns([3, 1])
        with bt_slider_col1:
            growth_rate_1_slider = st.slider(
                "快速調整",
                min_value=0,
                max_value=50,
                value=23,
                step=1,
                format="%d%%",
                key="bt_gr1_slider",
                label_visibility="collapsed"
            )
        with bt_input_col1:
            growth_rate_1_input = st.number_input(
                "精確值 (%)",
                min_value=-50.0,
                max_value=50.0,
                value=23.0,
                step=0.1,
                format="%.1f",
                key="bt_gr1_input",
                help="可輸入負值表示衰退"
            )
        growth_rate_1 = growth_rate_1_input / 100
    
    with col2:
        rebalance_months = st.slider("重新計算週期（月）", 1, 12, 3)
        
        # 成長率（6-10年）- 滑桿 + 精確輸入
        st.markdown("**成長率（6-10年）**")
        bt_slider_col2, bt_input_col2 = st.columns([3, 1])
        with bt_slider_col2:
            growth_rate_2_slider = st.slider(
                "快速調整",
                min_value=0,
                max_value=30,
                value=12,
                step=1,
                format="%d%%",
                key="bt_gr2_slider",
                label_visibility="collapsed"
            )
        with bt_input_col2:
            growth_rate_2_input = st.number_input(
                "精確值 (%)",
                min_value=-50.0,
                max_value=30.0,
                value=12.0,
                step=0.1,
                format="%.1f",
                key="bt_gr2_input",
                help="可輸入負值表示衰退"
            )
        growth_rate_2 = growth_rate_2_input / 100
    
    if st.button("🔄 執行回測", type="primary"):
        # 顯示更詳細的進度訊息
        progress_placeholder = st.empty()
        
        with st.spinner("正在準備回測數據，請稍候..."):
            try:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=365*backtest_years)
                
                # 顯示回測資訊
                st.info(f"""
                📊 **回測設定**
                - 股票代碼：{stock_code}
                - 回測期間：{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')} ({backtest_years} 年)
                - 成長率假設：1-5年 {growth_rate_1:.1%}，6-10年 {growth_rate_2:.1%}
                - 重新計算週期：每 {rebalance_months} 個月
                """)
                
                progress_placeholder.info("⏳ 正在獲取歷史數據並執行回測...")
                
                results = st.session_state.backtest_engine.run_backtest(
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    growth_rates=[growth_rate_1, growth_rate_2],
                    rebalance_months=rebalance_months
                )
                
                progress_placeholder.empty()
                
                if 'error' in results:
                    st.error(f"❌ **回測失敗**\n\n{results['error']}")
                    
                    # 提供建議
                    st.warning("""
                    💡 **改善建議**：
                    - 嘗試縮短回測年數（例如改為 1 年）
                    - 增加重新計算週期（例如改為 6 個月）
                    - 確認股票代碼是否正確
                    - 檢查網路連線是否正常
                    """)
                    return
                
                # 顯示成功訊息
                if 'failed_points' in results and results['failed_points'] > 0:
                    st.warning(f"⚠️ 部分回測點失敗（{results['failed_points']} 個），但已成功完成部分回測")
                
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
