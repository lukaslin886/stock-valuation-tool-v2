"""
綜合報告頁面模組
提供完整的 DCF 估值與風險分析綜合報告，並支援匯出 Excel 和 PDF
"""

import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import pandas as pd


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
                from report_generator import ReportGenerator
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
