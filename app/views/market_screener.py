"""
Market Screener Page View
"""

import streamlit as st
import pandas as pd
from app.market_scanner import MarketScanner


def show_market_screener(data_manager):
    st.header("🔍 市場篩選器 (Market Screener)")
    st.markdown("針對「低基期」與「優質股」進行全市場掃描與快篩。")

    # Initialize Scanner
    scanner = MarketScanner()

    # --- Sidebar Controls ---
    with st.sidebar:
        st.subheader("篩選條件設定")

        # 1. Update Data Button
        st.info("💡 若數據過舊，請點擊下方按鈕更新（需時約 2-5 分鐘）。")
        if st.button("🔄 更新市場數據 (Update Market Data)"):
            with st.spinner("正在掃描全市場股票 (約 2000 檔)... 請稍候"):
                # Get all stocks list from DataManager
                all_stocks_df = data_manager.get_all_stocks()

                if all_stocks_df is not None:
                    # Convert to list of dicts
                    stock_list = all_stocks_df.to_dict("records")

                    # Progress Bar
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    def update_progress(current, total):
                        progress = current / total
                        progress_bar.progress(progress)
                        status_text.text(f"已處理: {current} / {total}")

                    # Run Update
                    scanner.update_market_snapshot(stock_list, progress_callback=update_progress)
                    st.success("市場數據更新完成！")
                else:
                    st.error("無法取得股票清單，請檢查網路或 DataManager 設定。")

    # --- Main Area ---

    # Filter Controls (Top Row)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("1. 規模與價值 (Quality)")
        min_cap = st.slider("最低市值 (億台幣)", 0, 1000, 50, step=10, help="常見初篩可設 50-100 億，偏向中大型股。")
        max_pe = st.slider("最高本益比 (PE)", 5.0, 100.0, 20.0, step=0.5, help="保守估值可設 15-20；成長股可適度放寬。")

    with col2:
        st.subheader("2. 收益與成長 (Yield)")
        min_yield = st.slider("最低殖利率 (%)", 0.0, 10.0, 3.0, step=0.5, help="穩健型可從 3% 起，成長型可降低門檻。")
        min_roe = st.slider("最低股東權益報酬率 ROE (%)", 0.0, 40.0, 10.0, step=1.0, help="常見品質門檻可先設 10%-15%。")
        # Revenue Growth filter requires support in backend filter_stocks

    with col3:
        st.subheader("3. 時機 (Timing)")
        low_base_only = st.checkbox(
            "僅顯示「低基期」股票", value=True, help="篩選股價處於近 52 週低點區間（底部 30%）的股票"
        )

    # --- Run Filter ---
    filtered_df = scanner.filter_stocks(
        min_market_cap=min_cap,
        max_pe=max_pe,
        min_yield=min_yield / 100.0,  # Convert to decimal
        min_roe=min_roe / 100.0,
        low_base_enabled=low_base_only,
    )

    # --- Display Results of Stage 1 ---
    st.subheader(f"初篩結果: 共 {len(filtered_df)} 檔股票")

    if filtered_df.empty:
        st.warning("沒有符合條件的股票。請嘗試放寬篩選條件。")
        raw_df = scanner.get_market_snapshot()
        if raw_df.empty:
            st.error("資料庫為空！請務必先點擊側邊欄的「更新市場數據」按鈕。")
        return

    # Sort by Market Cap descending by default for preview
    preview_df = filtered_df.sort_values("market_cap", ascending=False)
    if "price_position" not in preview_df.columns:
        preview_df["price_position"] = pd.NA

    # Simple table for Stage 1
    st.dataframe(
        preview_df[
            [
                "stock_code",
                "stock_name",
                "current_price",
                "market_cap",
                "pe_ratio",
                "dividend_yield",
                "roe",
                "fundamental_score",
                "fundamental_grade",
                "price_position",
            ]
        ].style.format(
            {
                "current_price": "{:.2f}",
                "market_cap": "{:,.0f}",
                "pe_ratio": "{:.2f}",
                "dividend_yield": "{:.2%}",
                "roe": "{:.2%}",
                "fundamental_score": "{:.1f}",
                "price_position": "{:.2f}",
            }
        ),
        height=200,
    )

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
            st.warning("⚠️ 深度分析資料不足，尚無法產生可靠結果。")
            st.info("建議先放寬初篩條件，或先更新市場數據後再重試。")

    # --- Deep Dive Action (Original) ---
    # Hidden because we have it in deep scan step now, but kept for simple flow...
    # (Optional: remove the old button block)
