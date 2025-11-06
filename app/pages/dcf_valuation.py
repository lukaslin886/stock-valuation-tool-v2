"""
DCF 估值頁面
提供完整的 DCF 估值分析功能
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd


def show_dcf_valuation(stock_code: str, stock_name: str, investment_amount: float):
    """
    顯示 DCF 估值頁面
    
    Args:
        stock_code: 股票代碼
        stock_name: 股票名稱
        investment_amount: 投資金額
    """
    
    # 組合顯示名稱
    display_title = f"{stock_code} {stock_name}" if stock_name else stock_code
    st.header(f"🎯 DCF 估值分析 - {display_title}")
    
    # 參數設定區
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("參數設定")
        
        # 取得建議成長率（如果有的話）
        suggested_gr1 = st.session_state.get('suggested_gr1', 23.0)
        suggested_gr2 = st.session_state.get('suggested_gr2', 12.0)
        growth_message = st.session_state.get('growth_message', '')
        
        # 確保值在合理範圍內（-50% 到 50%）
        suggested_gr1 = max(-50.0, min(50.0, suggested_gr1))
        suggested_gr2 = max(-50.0, min(50.0, suggested_gr2))
        
        # 顯示數據來源說明（負成長時顯示警告）
        if growth_message:
            if suggested_gr1 < 0 or suggested_gr2 < 0:
                st.warning(f"⚠️ {growth_message}")
            else:
                st.info(f"📊 {growth_message}")
        
        # 成長率（1-5年）- 滑桿 + 精確輸入
        st.markdown("**成長率（1-5年）**")
        slider_col1, input_col1 = st.columns([3, 1])
        with slider_col1:
            growth_rate_1_slider = st.slider(
                "快速調整",
                min_value=0,
                max_value=50,
                value=int(suggested_gr1),
                step=1,
                format="%d%%",
                key="gr1_slider",
                label_visibility="collapsed"
            )
        with input_col1:
            growth_rate_1_input = st.number_input(
                "精確值 (%)",
                min_value=-50.0,
                max_value=50.0,
                value=float(suggested_gr1),
                step=0.1,
                format="%.1f",
                key="gr1_input",
                help="可輸入負值表示衰退"
            )
        growth_rate_1 = growth_rate_1_input / 100
        
        # 成長率（6-10年）- 滑桿 + 精確輸入
        st.markdown("**成長率（6-10年）**")
        slider_col2, input_col2 = st.columns([3, 1])
        with slider_col2:
            growth_rate_2_slider = st.slider(
                "快速調整",
                min_value=0,
                max_value=30,
                value=int(suggested_gr2),
                step=1,
                format="%d%%",
                key="gr2_slider",
                label_visibility="collapsed"
            )
        with input_col2:
            growth_rate_2_input = st.number_input(
                "精確值 (%)",
                min_value=-50.0,
                max_value=30.0,
                value=float(suggested_gr2),
                step=0.1,
                format="%.1f",
                key="gr2_input",
                help="可輸入負值表示衰退"
            )
        growth_rate_2 = growth_rate_2_input / 100
        
        # 折現率 - 滑桿 + 精確輸入
        st.markdown("**折現率**")
        st.caption("可使用 CAPM 模型計算，或手動設定")
        slider_col3, input_col3 = st.columns([3, 1])
        with slider_col3:
            discount_rate_slider = st.slider(
                "快速調整",
                min_value=5,
                max_value=20,
                value=11,
                step=1,
                format="%d%%",
                key="dr_slider",
                label_visibility="collapsed"
            )
        with input_col3:
            discount_rate_input = st.number_input(
                "精確值 (%)",
                min_value=5.0,
                max_value=20.0,
                value=11.0,
                step=0.1,
                format="%.1f",
                key="dr_input"
            )
        discount_rate = discount_rate_input / 100
    
    with col2:
        st.subheader("股票資訊")
        
        # 獲取股票資訊 - 添加詳細進度訊息
        progress_text = st.empty()
        progress_bar = st.progress(0)
        
        try:
            # 步驟 1: 獲取股價
            progress_text.info("📊 正在獲取最新股價...")
            progress_bar.progress(25)
            current_price = st.session_state.data_manager.get_latest_price(stock_code)
            
            # 步驟 2: 獲取 EPS
            progress_text.info("💰 正在獲取 EPS 數據...")
            progress_bar.progress(50)
            current_eps = st.session_state.data_manager.get_latest_eps(stock_code)
            
            # 步驟 3: 計算成長率
            progress_text.info("📈 正在分析歷史成長率...")
            progress_bar.progress(75)
            
            # 清除進度指示器
            progress_bar.progress(100)
            progress_text.success("✅ 數據載入完成！")
            progress_bar.empty()
            progress_text.empty()
            
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
            
            # 計算建議成長率
            growth_rates = st.session_state.data_manager.calculate_historical_growth_rate(stock_code)
            
            # 計算原始值
            gr1_raw = growth_rates['growth_rate_1_5'] * 100
            gr2_raw = growth_rates['growth_rate_6_10'] * 100
            
            # 儲存到 session state 供參數設定使用（限制在合理範圍內）
            st.session_state['suggested_gr1'] = max(-50.0, min(50.0, gr1_raw))
            st.session_state['suggested_gr2'] = max(-50.0, min(50.0, gr2_raw))
            st.session_state['growth_data_quality'] = growth_rates['data_quality']
            
            # 修改訊息，如果是負成長則特別標註
            base_message = growth_rates['message']
            if gr1_raw < 0 or gr2_raw < 0:
                base_message = f"注意：此股票呈現負成長（衰退）趨勢。{base_message}"
            st.session_state['growth_message'] = base_message
            
            # 儲存加權方法資訊
            st.session_state['weighting_method'] = growth_rates.get('weighting_method', 'equal_weighted')
            
            # 顯示時間加權資訊
            weighting_method = growth_rates.get('weighting_method', 'equal_weighted')
            if weighting_method == 'time_weighted':
                st.info("⏰ **時間加權成長率**：使用指數加權（近期數據權重更高）")
            else:
                st.info("📊 **等權重成長率**：使用傳統 CAGR 計算方法")
            
            # 顯示 CAGR 計算基礎（如果有詳細資料）
            if 'eps_start' in growth_rates and growth_rates['eps_start']:
                with st.expander("📊 成長率計算基礎", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        year_label = f"起始 EPS"
                        if 'eps_start_year' in growth_rates:
                            year_label = f"起始 EPS ({growth_rates['eps_start_year']})"
                        st.metric(
                            year_label,
                            f"${growth_rates['eps_start']:.2f}"
                        )
                    
                    with col2:
                        year_label = f"最新 EPS"
                        if 'eps_latest_year' in growth_rates:
                            year_label = f"最新 EPS ({growth_rates['eps_latest_year']})"
                        st.metric(
                            year_label,
                            f"${growth_rates['eps_latest']:.2f}"
                        )
                    
                    with col3:
                        st.metric(
                            "計算年數",
                            f"{growth_rates['years_count']} 年"
                        )
                    
                    # CAGR 公式說明
                    cagr_pct = growth_rates['growth_rate_1_5'] * 100
                    st.caption(
                        f"📐 **CAGR 公式**: "
                        f"({growth_rates['eps_latest']:.2f} / {growth_rates['eps_start']:.2f}) "
                        f"^ (1/{growth_rates['years_count']}) - 1 = **{cagr_pct:.2f}%**"
                    )
                    
                    # 時間加權方法說明
                    if weighting_method == 'time_weighted':
                        st.markdown("---")
                        st.markdown("**⏰ 時間加權方法**")
                        
                        # 從 config 讀取參數
                        try:
                            from portfolio_analyzer.config import RECENT_WEIGHT_RATIO, ENABLE_TIME_WEIGHTING
                            
                            if ENABLE_TIME_WEIGHTING:
                                st.caption(
                                    f"✓ 使用指數衰減時間加權（EWMA）  \n"
                                    f"✓ 近期權重比例：{RECENT_WEIGHT_RATIO*100:.0f}%  \n"
                                    f"✓ 最近一年數據權重更高，更能反映近期趨勢"
                                )
                                
                                # 權重分配說明
                                # 計算實際權重分配
                                from app.data.manager import DataManagerV2
                                example_weights = DataManagerV2._calculate_exponential_weights(
                                    None, 5, RECENT_WEIGHT_RATIO
                                )
                                
                                # 顯示文字說明
                                st.caption(
                                    f"📊 **權重分配**（基於 5 年數據範例）：  \n"
                                    f"第1年（最舊）：{example_weights[0]*100:.1f}%  \n"
                                    f"第2年：{example_weights[1]*100:.1f}%  \n"
                                    f"第3年：{example_weights[2]*100:.1f}%  \n"
                                    f"第4年：{example_weights[3]*100:.1f}%  \n"
                                    f"第5年（最新）：{example_weights[4]*100:.1f}%"
                                )
                                
                                # 權重分配視覺化圖表
                                fig = go.Figure()
                                fig.add_trace(go.Bar(
                                    x=[f"第{i+1}年" for i in range(5)],
                                    y=[w*100 for w in example_weights],
                                    marker_color=['#e3f2fd', '#bbdefb', '#90caf9', '#64b5f6', '#42a5f5'],
                                    text=[f"{w*100:.1f}%" for w in example_weights],
                                    textposition='outside',
                                    hovertemplate='%{x}<br>權重: %{y:.1f}%<extra></extra>'
                                ))
                                
                                fig.update_layout(
                                    title={
                                        'text': '⏰ 指數衰減時間加權分配',
                                        'x': 0.5,
                                        'xanchor': 'center'
                                    },
                                    xaxis_title="年份",
                                    yaxis_title="權重 (%)",
                                    yaxis_range=[0, max([w*100 for w in example_weights]) * 1.2],
                                    height=350,
                                    showlegend=False,
                                    plot_bgcolor='rgba(0,0,0,0)',
                                    paper_bgcolor='rgba(0,0,0,0)'
                                )
                                
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # 說明文字
                                st.caption(
                                    "💡 **解讀**：圖表顯示各年數據在計算成長率時的權重。"
                                    "近期數據（第5年）獲得最高權重，更能反映當前趨勢。"
                                )
                        except ImportError:
                            st.caption("使用系統預設時間加權設定")
                
        except Exception as e:
            progress_bar.empty()
            progress_text.empty()
            st.error(f"❌ 數據獲取失敗: {str(e)}")
            st.info("💡 **建議**：請確認股票代碼是否正確，或稍後再試")
            return
    
    # 計算按鈕
    if st.button("🚀 開始計算", type="primary", use_container_width=True):
        # 創建進度指示器
        calc_progress_text = st.empty()
        calc_progress_bar = st.progress(0)
        
        try:
            # 步驟 1: 開始計算
            calc_progress_text.info("🧮 正在計算 DCF 內在價值...")
            calc_progress_bar.progress(30)
            
            # 執行 DCF 計算
            result = st.session_state.dcf_calculator.calculate_dcf_value(
                    current_price=current_price,
                    current_eps=current_eps,
                    growth_rates=[growth_rate_1, growth_rate_2],
                    discount_rate=discount_rate,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    data_source='YFinance/FinMind',
                    weighting_method=st.session_state.get('weighting_method', 'equal_weighted')
                )
            
            # 步驟 2: 計算完成
            calc_progress_bar.progress(100)
            calc_progress_text.success("✅ 計算完成！")
            calc_progress_bar.empty()
            calc_progress_text.empty()
            
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
                
            # DCF 估值說明
            st.info("""
💡 **關於 DCF 估值的重要提醒**

DCF（現金流量折現法）計算的內在價值會因為輸入參數不同而產生不同結果：

1. **成長率敏感性**：成長率每增加 5%，內在價值可能增加 20-30%
2. **折現率影響**：折現率越高，內在價值越低
3. **參數來源**：系統建議值基於歷史數據，但未來可能不同
4. **合理範圍**：建議同時查看「情境比較」了解可能的估值範圍

👉 **建議做法**：
- 使用多種參數組合計算
- 參考情境比較功能
- 結合其他估值方法（如本益比）
- 保持安全邊際
""")
            
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
            
            # 查看計算參數
            with st.expander("🔍 查看計算參數", expanded=False):
                params = result['input_parameters']
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**基本資訊**")
                    st.write(f"- 計算時間：{params['timestamp']}")
                    st.write(f"- 股票代碼：{params['stock_code']}")
                    st.write(f"- 股票名稱：{params['stock_name']}")
                    st.write(f"- 資料來源：{params['data_source']}")
                    st.write(f"- 成長率方法：{params['weighting_method']}")
                
                with col2:
                    st.write("**計算參數**")
                    st.write(f"- 目前股價：${params['current_price']:.2f}")
                    st.write(f"- 當前 EPS：${params['current_eps']:.2f}")
                    st.write(f"- 成長率1-5年：{params['growth_rates']['1-5年']*100:.1f}%")
                    st.write(f"- 成長率6-10年：{params['growth_rates']['6-10年']*100:.1f}%")
                    st.write(f"- 折現率：{params['discount_rate']*100:.1f}%")
            
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
            
            # 敏感性分析進度指示
            sens_progress = st.empty()
            sens_progress.info("📊 正在執行敏感性分析...")
            
            sensitivity = st.session_state.dcf_calculator.sensitivity_analysis(
                current_price=current_price,
                current_eps=current_eps,
                base_growth_rates=[growth_rate_1, growth_rate_2]
            )
            
            sens_progress.empty()
            
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
            
            # 情境比較分析
            st.markdown("### 📊 情境比較分析")
            st.caption("比較保守、中性、樂觀三種成長率假設下的估值差異")
            
            # 使用 checkbox 取代 button，確保狀態持久化
            st.checkbox(
                "🔮 顯示三種情境比較",
                key='show_scenarios',
                help="計算並比較保守（-30%）、中性（當前）、樂觀（+30%）三種成長率假設下的估值"
            )
            
            # 從 session_state 讀取實際狀態（確保獲取最新值）
            if st.session_state.get('show_scenarios', False):
                with st.spinner("計算情境比較中..."):
                    scenarios = st.session_state.dcf_calculator.calculate_scenario_comparison(
                        current_price=current_price,
                        current_eps=current_eps,
                        base_growth_rates=[growth_rate_1, growth_rate_2],
                        discount_rate=discount_rate,
                        stock_code=stock_code,
                        stock_name=stock_name,
                        data_source='YFinance/FinMind',
                        weighting_method=st.session_state.get('weighting_method', 'equal_weighted')
                    )
                    
                    # 顯示三種情境的結果
                    st.markdown("#### 三種情境估值結果")
                    scenario_cols = st.columns(3)
                    
                    for idx, (scenario_name, scenario_result) in enumerate(scenarios.items()):
                        with scenario_cols[idx]:
                            st.markdown(f"**{scenario_name}情境**")
                            
                            # 使用情境顏色的指標
                            delta_color = "normal" if scenario_result['upside_potential'] > 0 else "inverse"
                            
                            st.metric(
                                "內在價值",
                                f"${scenario_result['intrinsic_value']:.2f}",
                                delta=f"{scenario_result['upside_potential']:.1%}",
                                delta_color=delta_color
                            )
                            
                            # 成長率假設
                            gr = scenario_result['input_parameters']['growth_rates']
                            st.caption(f"📊 {scenario_result['description']}")
                            st.caption(f"成長率：{gr['1-5年']*100:.1f}% / {gr['6-10年']*100:.1f}%")
                    
                    # 情境比較圖表
                    st.markdown("#### 📊 視覺化比較")
                    
                    fig = go.Figure()
                    
                    scenario_names = []
                    scenario_values = []
                    scenario_colors = []
                    
                    for scenario_name, scenario_result in scenarios.items():
                        scenario_names.append(scenario_name)
                        scenario_values.append(scenario_result['intrinsic_value'])
                        scenario_colors.append(scenario_result['color'])
                    
                    fig.add_trace(go.Bar(
                        x=scenario_names,
                        y=scenario_values,
                        marker_color=scenario_colors,
                        text=[f"${v:.0f}" for v in scenario_values],
                        textposition='outside',
                        hovertemplate='%{x}<br>內在價值: $%{y:.2f}<extra></extra>'
                    ))
                    
                    # 添加目前股價參考線
                    fig.add_hline(
                        y=current_price,
                        line_dash="dash",
                        line_color="orange",
                        annotation_text=f"目前股價 ${current_price:.2f}",
                        annotation_position="right"
                    )
                    
                    fig.update_layout(
                        title="三種情境估值比較",
                        yaxis_title="內在價值 ($)",
                        showlegend=False,
                        height=400
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 說明
                    st.info("""
💡 **情境解讀**：
- **保守情境**：成長率降低 30%，適合悲觀預期或高風險股票
- **中性情境**：使用您設定的成長率，反映當前預期
- **樂觀情境**：成長率增加 30%，適合成長股或產業處於上升週期

**建議**：合理的內在價值範圍應落在三種情境之間。若目前股價低於保守情境估值，可能是絕佳買點。
""")
            
        except Exception as e:
            calc_progress_bar.empty()
            calc_progress_text.empty()
            st.error(f"❌ 計算失敗: {str(e)}")
            st.info("💡 **建議**：請檢查輸入參數，或聯繫技術支援")
