"""
技術面篩選 UI 區塊 (RSI / MACD)

作為 market_screener 的 Stage-3 選配步驟：對 Stage-1 初篩結果，逐檔抓歷史收盤價、
計算 RSI/MACD 指標並套用篩選條件。與既有流程解耦，失敗只跳過該檔、不影響其他區塊。

對應 TODO.md「加入技術指標篩選 (RSI/MACD)」。

備註：本檔屬 Web UI 層，比照 market_screener.py 的 [UI-EXCEPTION] 慣例使用 emoji。
"""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from technical_indicators import compute_indicators, screen_rsi, screen_macd


def render_technical_filter(data_manager, filtered_df, max_symbols: int = 100):
    """
    繪製技術面篩選區塊。

    Args:
        data_manager: DataManager 實例（提供 get_stock_price）。
        filtered_df: Stage-1 初篩結果 DataFrame（需含 stock_code、stock_name）。
        max_symbols: 單次最多分析檔數，避免 API 過載。
    """
    st.markdown("---")
    st.subheader("📈 技術面篩選 (RSI / MACD)")
    st.info("針對上方初篩結果，抓取歷史收盤價計算技術指標。需連線行情資料源，耗時視檔數而定。")

    if filtered_df is None or filtered_df.empty:
        st.caption("（無初篩結果，略過技術面篩選。）")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        lookback = st.slider(
            "回溯天數 (日曆日)", 90, 400, 180, step=10,
            help="需涵蓋足夠交易日供 MACD(26) 與 RSI(14) 收斂；建議 ≥120。"
        )
        rsi_period = st.slider("RSI 週期", 5, 30, 14, step=1)
    with col2:
        rsi_mode = st.selectbox(
            "RSI 條件", ["不限", "超賣 (oversold)", "超買 (overbought)", "中性 (neutral)"],
            index=0,
        )
        rsi_low = st.slider("RSI 低門檻", 5, 50, 30, step=1)
        rsi_high = st.slider("RSI 高門檻", 50, 95, 70, step=1)
    with col3:
        macd_cond = st.selectbox(
            "MACD 條件",
            ["不限", "黃金交叉 (golden)", "死亡交叉 (dead)", "多頭 (hist>0)", "空頭 (hist<0)"],
            index=0,
        )

    if not st.button("🔎 執行技術面篩選"):
        return

    codes = filtered_df["stock_code"].astype(str).tolist()
    if len(codes) > max_symbols:
        st.warning(f"初篩結果 {len(codes)} 檔，超過上限，僅分析前 {max_symbols} 檔。")
        codes = codes[:max_symbols]

    name_map = dict(zip(filtered_df["stock_code"].astype(str), filtered_df["stock_name"]))
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback)

    rsi_mode_key = {
        "超賣 (oversold)": "oversold",
        "超買 (overbought)": "overbought",
        "中性 (neutral)": "neutral",
    }.get(rsi_mode)
    macd_want_key = {
        "黃金交叉 (golden)": "golden",
        "死亡交叉 (dead)": "dead",
        "多頭 (hist>0)": "bullish",
        "空頭 (hist<0)": "bearish",
    }.get(macd_cond)

    progress = st.progress(0.0, text="準備抓取行情...")
    rows = []
    skipped = 0
    total = len(codes)

    for i, code in enumerate(codes, start=1):
        progress.progress(i / total, text=f"分析 {code} ({i}/{total})")
        try:
            price_df = data_manager.get_stock_price(code, start_date, end_date)
            if price_df is None or len(price_df) < max(rsi_period + 1, 35):
                skipped += 1
                continue

            snap = compute_indicators(price_df, rsi_period=rsi_period)
            if snap["rsi"] is None:
                skipped += 1
                continue

            # 套用條件
            if rsi_mode_key and not screen_rsi(price_df, low=rsi_low, high=rsi_high, mode=rsi_mode_key):
                continue
            if macd_want_key and not screen_macd(price_df, want=macd_want_key):
                continue

            rows.append({
                "代碼": code,
                "名稱": name_map.get(code, ""),
                "RSI": snap["rsi"],
                "MACD(DIF)": snap["macd"],
                "訊號線": snap["signal"],
                "柱狀(Hist)": snap["hist"],
                "交叉": {"golden": "🟢 黃金", "dead": "🔴 死亡"}.get(snap["macd_cross"], "—"),
            })
        except Exception as e:  # 單檔失敗不影響整體
            skipped += 1
            print(f"[WARN] 技術面篩選略過 {code}: {e}")
            continue

    progress.empty()

    if not rows:
        st.warning("沒有符合技術面條件的股票（或行情資料不足）。可放寬條件或先更新市場數據。")
        if skipped:
            st.caption(f"（{skipped} 檔因資料不足或抓取失敗而略過。）")
        return

    result_df = pd.DataFrame(rows).sort_values("RSI").reset_index(drop=True)
    st.success(f"✅ 符合技術面條件：{len(result_df)} 檔（略過 {skipped} 檔）")

    styled = result_df.style.format({
        "RSI": "{:.1f}",
        "MACD(DIF)": "{:.4f}",
        "訊號線": "{:.4f}",
        "柱狀(Hist)": "{:.4f}",
    })
    st.dataframe(styled, use_container_width=True, height=400)

    st.session_state["technical_filter_results"] = result_df
    return result_df
