"""
Market Screener Page View
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import io
import os
from datetime import datetime
from market_scanner import MarketScanner
from technical_filter_ui import render_technical_filter
from excel_export import build_screener_excel
from pagination import slice_page


# [UI-EXCEPTION] Using emojis for UX in Web UI layer as per updated _AI_Rules
def show_market_screener(data_manager):
    st.header("🔍 市場篩選器 (Market Screener)")
    st.markdown("針對「低基期」與「優質股」進行全市場掃描與快篩。")

    # Initialize Scanner
    scanner = MarketScanner()

    # --- Sidebar Controls ---
    with st.sidebar:
        st.subheader("📡 數據源設定 (Data Source)")
        
        # 資料來源切換 (P6-Hybrid)
        data_source = st.radio(
            "選擇掃描引擎",
            ["Yahoo Finance (即時/免費)", "FinLab (批次/極速)", "FinMind (專業/穩定)"],
            index=0,
            help="Yahoo Finance: 免費但易被封鎖。\nFinLab: 適合全市場大掃描，速度最快。\nFinMind: 數據精確穩定，適合專業分析。"
        )
        
        token_input = ""
        if "FinLab" in data_source:
            env_token = os.getenv("FINLAB_API_TOKEN", "")
            if env_token:
                st.success("✅ 已自動載入 FinLab 系統金鑰")
                token_input = env_token
                if st.checkbox("修改 Token"):
                    token_input = st.text_input("FinLab API Token (Override)", type="password", value=env_token)
            else:
                token_input = st.text_input("FinLab API Token", type="password", help="請至 https://ai.finlab.tw/api_token 取得。")
                if not token_input:
                    st.warning("⚠️ 請輸入 FinLab Token。")
                    
        elif "FinMind" in data_source:
            env_token = os.getenv("FINMIND_TOKEN", "")
            if env_token:
                st.success("✅ 已自動載入 FinMind 系統金鑰")
                token_input = env_token
                if st.checkbox("修改 Token"):
                    token_input = st.text_input("FinMind API Token (Override)", type="password", value=env_token)
            else:
                token_input = st.text_input("FinMind API Token", type="password", help="請至 FinMind 官網取得 Token。")
                if not token_input:
                    st.warning("⚠️ 請輸入 FinMind Token。")

        st.markdown("---")
        st.subheader("篩選條件設定")

        # 1. Update Data Button
        st.info("💡 若數據過舊，請點擊下方按鈕更新。")
        if st.button("🔄 更新市場數據 (Update Market Data)"):
            status_placeholder = st.empty()
            status_placeholder.info("⏳ 正在初始化更新程序...")
            
            with st.spinner("正在執行掃描... 請稍候"):
                # 1. Get all stocks list
                status_placeholder.info("📡 正在從資料庫讀取股票清單...")
                all_stocks_df = data_manager.get_all_stocks()
                
                if all_stocks_df is not None:
                    status_placeholder.success(f"✅ 已獲取 {len(all_stocks_df)} 檔股票清單")
                    progress_bar = st.progress(0, text="準備更新引擎...")
                    
                    def update_progress(current, total, current_item=""):
                        percent = min(current / total, 1.0)
                        progress_text = f"正在處理：{current_item} ({current}/{total})"
                        progress_bar.progress(percent, text=progress_text)

                    # Execute Update with Error Catching
                    success = False
                    error_details = ""
                    try:
                        status_placeholder.info(f"🚀 正在啟動 {data_source} 引擎...")
                        if "FinLab" in data_source:
                            success = scanner.update_market_snapshot_finlab(token_input, progress_callback=update_progress)
                        elif "FinMind" in data_source:
                            success = scanner.update_market_snapshot_finmind(all_stocks_df, token_input, progress_callback=update_progress)
                        else:
                            success = scanner.update_market_snapshot(progress_callback=update_progress)
                    except Exception as e:
                        success = False
                        error_details = str(e)
                    
                    progress_bar.empty()
                    status_placeholder.empty()
                    
                    if success:
                        st.success(f"✅ {data_source} 更新完成！")
                        st.rerun()
                    else:
                        if "FinMind" in data_source:
                            st.error("❌ FinMind 更新失敗：帳號為免費版（register），批次查詢功能受限。")
                            st.info("💡 建議：\n1. 改用 **FinLab** 引擎（您的 FinLab Token 有效）\n2. 或至 [FinMind 贊助頁面](https://finmindtrade.com/analysis/#/Sponsor/sponsor) 升級帳號")
                        else:
                            st.error(f"❌ {data_source} 更新失敗。")
                        if error_details:
                            st.code(f"錯誤詳情: {error_details}")
                        st.warning("請檢查 API Token 是否正確，或嘗試切換不同數據源。")
                else:
                    status_placeholder.error("❌ 無法從 DataManager 獲取股票清單。")
                    st.error("錯誤：股票清單為空。請確認 DataManager 初始化是否正常。")
                    
        st.markdown("---")
        st.subheader("💡 建議篩選範本")
        if st.button("📊 價值型穩健股"):
            st.session_state['ms_min_cap'] = 100
            st.session_state['ms_max_pe'] = 15.0
            st.session_state['ms_min_yield'] = 5.0
            st.session_state['ms_min_roe'] = 10.0
            st.session_state['ms_low_base'] = True
            st.rerun()
            
        if st.button("🚀 成長型潛力股"):
            st.session_state['ms_min_cap'] = 20
            st.session_state['ms_max_pe'] = 30.0
            st.session_state['ms_min_yield'] = 1.0
            st.session_state['ms_min_roe'] = 15.0
            st.session_state['ms_low_base'] = False
            st.rerun()

        if st.button("💰 存股高息王"):
            st.session_state['ms_min_cap'] = 50
            st.session_state['ms_max_pe'] = 25.0
            st.session_state['ms_min_yield'] = 6.5
            st.session_state['ms_min_roe'] = 8.0
            st.session_state['ms_low_base'] = False
            st.rerun()

        if st.button("🏰 護城河優質股"):
            st.session_state['ms_min_cap'] = 200
            st.session_state['ms_max_pe'] = 40.0
            st.session_state['ms_min_yield'] = 0.0
            st.session_state['ms_min_roe'] = 25.0
            st.session_state['ms_low_base'] = False
            st.rerun()

        if st.button("📈 底部反轉機股"):
            st.session_state['ms_min_cap'] = 30
            st.session_state['ms_max_pe'] = 12.0
            st.session_state['ms_min_yield'] = 2.0
            st.session_state['ms_min_roe'] = 5.0
            st.session_state['ms_low_base'] = True
            st.rerun()

    # Get values from session state or defaults
    min_cap_def = st.session_state.get('ms_min_cap', 50)
    max_pe_def = st.session_state.get('ms_max_pe', 20.0)
    min_yield_def = st.session_state.get('ms_min_yield', 3.0)
    min_roe_def = st.session_state.get('ms_min_roe', 10.0)
    low_base_def = st.session_state.get('ms_low_base', True)

    # --- Main Area ---

    # Filter Controls (Top Row)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("1. 規模與價值 (Quality)")
        min_cap = st.slider("最低市值 (億台幣)", 0, 1000, min_cap_def, step=10, help="常見初篩可設 50-100 億，偏向中大型股。")
        max_pe = st.slider("最高本益比 (PE)", 5.0, 100.0, max_pe_def, step=0.5, help="保守估值可設 15-20；成長股可適度放寬。")

    with col2:
        st.subheader("2. 收益與成長 (Yield)")
        min_yield = st.slider("最低殖利率 (%)", 0.0, 10.0, min_yield_def, step=0.5, help="穩健型可從 3% 起，成長型可降低門檻。")
        min_roe = st.slider("最低股東權益報酬率 ROE (%)", 0.0, 40.0, min_roe_def, step=1.0, help="常見品質門檻可先設 10%-15%。")
        # Revenue Growth filter requires support in backend filter_stocks

    with col3:
        st.subheader("3. 時機 (Timing)")
        low_base_only = st.checkbox(
            "僅顯示「低基期」股票", value=low_base_def, help="篩選股價處於近 52 週低點區間（底部 30%）的股票"
        )

    # --- Run Filter ---
    filtered_df = scanner.filter_stocks(
        min_market_cap=min_cap,
        max_pe=max_pe,
        min_yield=min_yield,
        min_roe=min_roe,
        low_base_enabled=low_base_only,
    )

    # --- Display Results of Stage 1 ---
    # --- Display Results of Stage 1 ---
    st.markdown(f"### 🎯 初篩結果 (共 {len(filtered_df)} 檔股票)")

    if filtered_df.empty:
        st.warning("沒有符合條件的股票。請嘗試放寬篩選條件。")
        raw_df = scanner.get_market_snapshot()
        if raw_df.empty:
            st.error("資料庫為空！請務必先點擊側邊欄的「更新市場數據」按鈕。")
        return

    # --- 1. 摘要卡片 (Summary Cards) (P5-03) ---
    avg_yield = filtered_df["dividend_yield"].mean()
    avg_roe = filtered_df["roe"].mean()
    avg_score = filtered_df["fundamental_score"].mean()
    
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    m_col1.metric("🔍 標的總數", f"{len(filtered_df)} 檔")
    m_col2.metric("💡 平均評分", f"{avg_score:.1f}")
    m_col3.metric("💰 平均殖利率", f"{avg_yield:.2f}%")
    m_col4.metric("📈 平均 ROE", f"{avg_roe:.2f}%")

    # --- 2. 視覺化分析 (Visual Analysis) (P5-01) ---
    with st.expander("📊 視覺化分析：ROE vs PE 甜點區", expanded=True):
        # 準備繪圖數據 (過濾極端 PE 以利顯示)
        plot_df = filtered_df.copy()
        plot_df = plot_df[plot_df["pe_ratio"] < 60] # 排除極端值
        
        if not plot_df.empty:
            fig = px.scatter(
                plot_df,
                x="pe_ratio",
                y="roe",
                size="market_cap",
                color="fundamental_score",
                hover_name="stock_name",
                hover_data=["stock_code", "current_price", "dividend_yield", "fundamental_grade"],
                labels={
                    "pe_ratio": "本益比 (PE)",
                    "roe": "股東權益報酬率 (ROE)",
                    "fundamental_score": "綜合評分",
                    "market_cap": "市值"
                },
                title="🎯 ROE vs PE 散佈圖 (泡泡大小代表市值)",
                color_continuous_scale="RdYlGn", # 紅黃綠
                template="plotly_white"
            )
            
            # 增加輔助線 (例如 ROE 15%)
            fig.add_hline(y=15, line_dash="dash", line_color="gray", annotation_text="ROE 15% 門檻")
            fig.add_vline(x=15, line_dash="dash", line_color="gray", annotation_text="PE 15 門檻")
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("符合條件的標的 PE 皆大於 60，建議調整篩選範圍以檢視圖表。")

    # Sort by Fundamental Score descending by default to show top-ranked stocks
    preview_df = filtered_df.sort_values("fundamental_score", ascending=False)
    
    # 確保所有顯示欄位都存在，避免 KeyError
    required_display_cols = [
        "stock_code", "stock_name", "current_price", "market_cap", 
        "pe_ratio", "dividend_yield", "dividend_yield_5y", "payout_ratio", "roe", 
        "fundamental_score", "fundamental_grade", "price_position"
    ]
    for col in required_display_cols:
        if col not in preview_df.columns:
            if col == "fundamental_grade":
                preview_df[col] = "N/A"
            else:
                preview_df[col] = 0.0
    
    # 準備顯示用的 DataFrame
    display_df = preview_df[required_display_cols].copy()
    
    # 數值單位轉換與處理
    display_df["market_cap"] = display_df["market_cap"] / 100_000_000  # 轉為億元

    # --- 分頁處理（結果 > 500 筆時啟用；匯出仍為全量）---
    PAGE_TRIGGER = 500
    total_rows = len(display_df)
    page_df = display_df  # 供表格顯示（可能為當前頁切片）
    if total_rows > PAGE_TRIGGER:
        pg_c1, pg_c2, pg_c3 = st.columns([1, 1, 3])
        with pg_c1:
            page_size = st.selectbox("每頁筆數", [100, 200, 500], index=0, key="ms_page_size")
        n_pages_est = (total_rows + page_size - 1) // page_size
        with pg_c2:
            req_page = st.number_input(
                "頁碼", min_value=1, max_value=n_pages_est, value=1, step=1, key="ms_page"
            )
        start, end, n_pages, page = slice_page(total_rows, req_page, page_size)
        page_df = display_df.iloc[start:end]
        with pg_c3:
            st.caption(f"顯示第 {start + 1}–{end} 筆，共 {total_rows} 筆（第 {page}/{n_pages} 頁）。匯出為全部 {total_rows} 筆。")
    else:
        st.caption(f"共 {total_rows} 筆")

    # 定義評分顏色函數
    def get_score_color(val):
        if val >= 85:
            return 'background-color: #d4edda; color: #155724; font-weight: bold'  # 深綠 (極優)
        elif val >= 75:
            return 'background-color: #e2f3f5; color: #0c5460; font-weight: bold'  # 青綠 (優)
        elif val >= 60:
            return 'background-color: #fff3cd; color: #856404'  # 淺黃 (普通)
        else:
            return 'background-color: #f8d7da; color: #721c24'  # 淺紅 (差)

    # 欄位名稱對照表
    column_labels = {
        "stock_code": "代碼",
        "stock_name": "名稱",
        "current_price": "股價",
        "market_cap": "市值(億)",
        "pe_ratio": "PE",
        "dividend_yield": "殖利率",
        "dividend_yield_5y": "5Y平均殖利率",
        "payout_ratio": "發放率",
        "roe": "ROE",
        "fundamental_score": "評分",
        "fundamental_grade": "等級",
        "price_position": "位階"
    }
    
    # 套用樣式與格式（僅對當前頁 page_df；display_df 全量留給匯出）
    styled_df = page_df.rename(columns=column_labels).style.applymap(
        get_score_color, subset=['評分']
    ).format({
        "股價": "{:.2f}",
        "市值(億)": "{:,.1f}",
        "PE": "{:.2f}",
        "殖利率": "{:.2f}%",
        "5Y平均殖利率": "{:.2f}%",
        "發放率": "{:.2f}%",
        "ROE": "{:.2f}%",
        "評分": "{:.1f}",
        "位階": "{:.2f}"
    })

    # 使用 Streamlit Dataframe 顯示優化後的表格
    st.dataframe(
        styled_df,
        use_container_width=True,
        height=400,
        column_config={
            "代碼": st.column_config.TextColumn("代碼", width="small"),
            "名稱": st.column_config.TextColumn("名稱", width="medium"),
            "評分": st.column_config.NumberColumn("評分", format="%.1f"),
            "等級": st.column_config.TextColumn("等級", width="small"),
        }
    )

    # --- 3. 匯出功能 (P5-08)：一鍵導出 + 進度條 ---
    export_df = display_df.rename(columns=column_labels)
    export_sig = (len(export_df), tuple(export_df.columns))  # 判斷結果是否變動，變動即失效舊檔

    col_exp1, col_exp2 = st.columns([1, 5])
    with col_exp1:
        if st.button("📦 準備 Excel 匯出"):
            prog = st.progress(0.0, text="開始產生 Excel...")

            def _excel_progress(current, total):
                pct = min(current / total, 1.0) if total else 1.0
                prog.progress(pct, text=f"寫入中... {current}/{total} 列")

            try:
                excel_bytes = build_screener_excel(
                    export_df, sheet_name="篩選結果", progress_callback=_excel_progress
                )
                prog.progress(1.0, text="Excel 產生完成 ✅")
                st.session_state["screener_excel_bytes"] = excel_bytes
                st.session_state["screener_excel_sig"] = export_sig
            except Exception as e:
                prog.empty()
                st.error(f"❌ Excel 產生失敗：{e}")

        # 僅在已產生且結果未變動時提供下載
        if (
            st.session_state.get("screener_excel_bytes")
            and st.session_state.get("screener_excel_sig") == export_sig
        ):
            st.download_button(
                label="📥 下載 Excel",
                data=st.session_state["screener_excel_bytes"],
                file_name=f"台股篩選結果_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    with col_exp2:
        st.info("💡 提示：先點「準備 Excel 匯出」看進度條產生檔案，再點「下載 Excel」存檔。若調整篩選條件，需重新產生。")

    # --- Stage 3 (選配): 技術面篩選 RSI/MACD ---
    render_technical_filter(data_manager, filtered_df)

    # --- Stage 2: Deep Scan ---
    st.markdown("---")
    st.subheader("🚀 進階篩選 (Deep Scan)")
    st.info("針對上方初篩結果，讀取歷史財報以分析成長性與配息穩定度 (需時較久)。")

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        min_rev_cagr = st.slider(
            "最低營收成長率 (5年 CAGR)", -10.0, 30.0, 0.0, step=1.0, help="建議先從 0% 起測試，再逐步提高門檻。"
        )
        min_profit_cagr = st.slider(
            "最低獲利成長率 (5年 CAGR)", -10.0, 30.0, 5.0, step=1.0, help="獲利成長門檻過高可能導致候選過少。"
        )
    with col_d2:
        min_div_years = st.slider("連續配息最低年數", 0, 20, 5, help="偏好穩健股可設 5 年以上。")

    if st.button("開始深度分析"):
        if len(filtered_df) > 50:
            st.warning(f"目前初篩結果有 {len(filtered_df)} 檔，深度分析可能需要 1-2 分鐘，請耐心等候...")

        with st.spinner("正在下載歷史財報數據..."):
            stock_codes = filtered_df["stock_code"].tolist()

            # Progress UI
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_deep_progress(current, total):
                progress_bar.progress(current / total)
                status_text.text(f"已分析: {current} / {total}")

            deep_results = scanner.perform_deep_scan(stock_codes, progress_callback=update_deep_progress)

        if not deep_results.empty:
            # Merge with base data
            final_df = pd.merge(filtered_df, deep_results, on="stock_code", how="inner")

            # Apply Filters
            final_df = final_df[
                (final_df["revenue_cagr_5y"] >= min_rev_cagr / 100.0)
                & (final_df["profit_cagr_5y"] >= min_profit_cagr / 100.0)
                & (final_df["div_years"] >= min_div_years)
            ]

            st.success(f"深度分析完成！符合條件: {len(final_df)} 檔")

            # Final Display
            final_df["market_cap_b"] = final_df["market_cap"] / 1_000_000_000
            final_df["dividend_yield_pct"] = final_df["dividend_yield"] * 100
            final_df["rev_cagr_pct"] = final_df["revenue_cagr_5y"] * 100
            final_df["prof_cagr_pct"] = final_df["profit_cagr_5y"] * 100
            final_df["score"] = final_df["low_base_score"].fillna(0)

            # Formatting helpers
            def format_pos(x):
                if x < 0.2:
                    return "🟢 低檔"
                if x > 0.8:
                    return "🔴 高檔"
                return "⚪ 中間"

            final_df["pos_label"] = final_df["price_pos_5y"].apply(format_pos)

            # Sort by Score descending
            final_df = final_df.sort_values("score", ascending=False)

            display_cols = [
                "stock_code",
                "stock_name",
                "current_price",
                "market_cap_b",
                "pe_ratio",
                "score",
                "rev_cagr_pct",
                "prof_cagr_pct",
                "div_years",
                "pos_label",
            ]
            rename_map = {
                "stock_code": "代碼",
                "stock_name": "名稱",
                "current_price": "股價",
                "market_cap_b": "市值(億)",
                "pe_ratio": "PE",
                "score": "低基期分",
                "rev_cagr_pct": "營收成長(5Y)%",
                "prof_cagr_pct": "獲利成長(5Y)%",
                "div_years": "連配年",
                "pos_label": "5Y位階",
            }

            st.dataframe(
                final_df[display_cols]
                .rename(columns=rename_map)
                .style.format(
                    {
                        "股價": "{:.2f}",
                        "市值(億)": "{:.1f}",
                        "PE": "{:.1f}",
                        "低基期分": "{:.0f}",
                        "營收成長(5Y)%": "{:.1f}%",
                        "獲利成長(5Y)%": "{:.1f}%",
                    }
                )
                .background_gradient(subset=["低基期分"], cmap="RdYlGn", vmin=0, vmax=100)
            )

            st.session_state["last_scan_results"] = final_df  # Cache results in session?

            # Action Select
            st.divider()
            selected = st.selectbox("選擇股票進行估值", final_df["stock_code"] + " " + final_df["stock_name"])
            if st.button("前往 DCF 估值"):
                code = selected.split(" ")[0]
                st.session_state["selected_stock_from_screener"] = code
                st.switch_page("main.py")  # Try switch_page mechanism if supported, else relies on manual nav hint
                st.info(f"已選擇 {code}，請切換至 DCF 估值頁面。")  # Fallback
        else:
            st.warning("[WARN] 深度分析資料不足，尚無法產生可靠結果。")
            st.info("建議先放寬初篩條件，或先更新市場數據後再重試。")

    # --- Deep Dive Action (Original) ---
    # Hidden because we have it in deep scan step now, but kept for simple flow...
    # (Optional: remove the old button block)
