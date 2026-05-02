"""
新標的推薦頁面 (P2-42)

結合市場快照基本面篩選與 DCF 估值，
呈現優先級 A / B / C 的候選股票清單。
"""

from typing import Any

import pandas as pd
import streamlit as st

from opportunity_finder import OpportunityFinder


# ── 常數 ─────────────────────────────────────────────────────────────
_PRIORITY_COLORS = {
    "A": "#ef5350",   # 紅色（強烈推薦）
    "B": "#ffa726",   # 橘色（積極推薦）
    "C": "#66bb6a",   # 綠色（候選關注）
}

_PRIORITY_LABELS = {
    "A": "🔴 A 優先",
    "B": "🟡 B 積極",
    "C": "🟢 C 候選",
}

_PRIORITY_DESCRIPTIONS = {
    "A": "DCF 低估 ≥ 30% 且 ROE ≥ 15%",
    "B": "DCF 低估 ≥ 20% 且 ROE ≥ 10%",
    "C": "DCF 低估 ≥ 20%（其他）",
}


def show_new_opportunities(data_manager: Any, dcf_calculator: Any) -> None:
    """
    新標的推薦 Streamlit 頁面入口。

    Args:
        data_manager: DataManagerV2 實例。
        dcf_calculator: DCFCalculator 實例。
    """
    st.header("🔍 新標的推薦")
    st.markdown("結合 DCF 估值與基本面篩選，自動找出被市場低估的潛力個股。")

    # ── 側邊欄：篩選參數 ─────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 📋 推薦掃描設定")

        candidate_source = st.radio(
            "候選清單來源",
            ["台灣50大型股", "自訂清單"],
            index=0,
            help="台灣50大型股：系統內建的50檔主要大型股。\n自訂清單：手動輸入股票代碼。",
        )

        custom_codes_input = ""
        if candidate_source == "自訂清單":
            custom_codes_input = st.text_area(
                "自訂股票代碼（每行一個）",
                placeholder="2330\n2317\n2454",
                height=120,
                help="每行輸入一個台股代碼。",
            )

        st.markdown("---")
        dcf_threshold = st.slider(
            "DCF 低估門檻 (%)",
            min_value=5,
            max_value=50,
            value=20,
            step=5,
            help="只顯示 DCF 潛在獲利率高於此門檻的股票。",
        ) / 100.0

        min_roe = st.slider(
            "最低 ROE (%)",
            min_value=0,
            max_value=30,
            value=5,
            step=1,
            help="排除 ROE 低於此數值的股票（無快照資料時略過此篩選）。",
        ) / 100.0

        min_market_cap_b = st.number_input(
            "最低市值（億台幣）",
            min_value=0,
            max_value=10000,
            value=100,
            step=10,
            help="排除市值低於此數值的股票。",
        ) / 10.0  # 億 → 十億（內部單位）

        use_snapshot = st.checkbox(
            "使用市場快照加速篩選",
            value=True,
            help="啟用時優先從市場快照取得基本面資料，加快掃描速度並減少 API 呼叫。",
        )

    # ── 候選清單準備 ─────────────────────────────────────────────────
    if candidate_source == "自訂清單":
        candidate_stocks = _parse_custom_codes(custom_codes_input)
        if not candidate_stocks:
            st.info("請在左側側邊欄輸入至少一個股票代碼。")
            return
    else:
        candidate_stocks = None  # 使用 OpportunityFinder 預設清單

    # ── 掃描按鈕 ─────────────────────────────────────────────────────
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run_scan = st.button("🚀 開始掃描", type="primary", use_container_width=True)
    with col_info:
        n_candidates = len(candidate_stocks) if candidate_stocks else len(OpportunityFinder.TAIWAN_50_STOCKS)
        st.caption(
            f"候選股票：**{n_candidates}** 檔 ｜ "
            f"DCF門檻：**{dcf_threshold * 100:.0f}%** ｜ "
            f"ROE門檻：**{min_roe * 100:.0f}%** ｜ "
            f"市值門檻：**{min_market_cap_b * 10:.0f} 億**"
        )

    # ── 初始提示 ─────────────────────────────────────────────────────
    if not run_scan and "opportunity_results" not in st.session_state:
        _render_legend()
        return

    # ── 執行掃描 ─────────────────────────────────────────────────────
    if run_scan:
        market_scanner = st.session_state.get("market_scanner")
        finder = OpportunityFinder(
            data_manager=data_manager,
            dcf_calculator=dcf_calculator,
            market_scanner=market_scanner,
        )

        progress_bar = st.progress(0, text="準備中…")
        status_text = st.empty()

        def _progress(current: int, total: int, code: str) -> None:
            pct = int(current / total * 100)
            progress_bar.progress(pct, text=f"掃描中 ({current}/{total})…")
            status_text.caption(f"正在分析 {code}")

        with st.spinner("正在執行 DCF 掃描，請稍候…"):
            results = finder.scan_opportunities(
                candidate_stocks=candidate_stocks,
                dcf_threshold=dcf_threshold,
                min_roe=min_roe,
                min_market_cap_b=min_market_cap_b,
                use_market_snapshot=use_snapshot,
                progress_callback=_progress,
            )

        progress_bar.empty()
        status_text.empty()
        st.session_state["opportunity_results"] = results

    # ── 結果顯示 ─────────────────────────────────────────────────────
    results = st.session_state.get("opportunity_results", [])
    _render_results(results)


# ── 內部渲染函數 ─────────────────────────────────────────────────────

def _render_legend() -> None:
    """顯示優先級說明卡片。"""
    st.markdown("---")
    st.markdown("#### 📖 優先級說明")
    cols = st.columns(3)
    for i, (key, label) in enumerate(_PRIORITY_LABELS.items()):
        with cols[i]:
            color = _PRIORITY_COLORS[key]
            desc = _PRIORITY_DESCRIPTIONS[key]
            st.markdown(
                f'<div style="border-left:4px solid {color}; padding:8px 12px; '
                f'border-radius:4px; background:#fafafa;">'
                f'<b>{label}</b><br><small>{desc}</small></div>',
                unsafe_allow_html=True,
            )
    st.markdown("---")
    st.info("點擊「🚀 開始掃描」以啟動新標的推薦掃描。")


def _render_results(results: list) -> None:
    """顯示掃描結果。"""
    if not results:
        st.warning("本次掃描未找到符合條件的標的，請嘗試調整篩選門檻。")
        _render_legend()
        return

    # ── 摘要指標 ─────────────────────────────────────────────────────
    st.markdown(f"### ✅ 找到 **{len(results)}** 檔推薦標的")

    count_a = sum(1 for r in results if r["priority"] == "A")
    count_b = sum(1 for r in results if r["priority"] == "B")
    count_c = sum(1 for r in results if r["priority"] == "C")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("總推薦數", len(results))
    m2.metric("🔴 A 優先", count_a)
    m3.metric("🟡 B 積極", count_b)
    m4.metric("🟢 C 候選", count_c)

    st.markdown("---")

    # ── 優先級篩選 tab ─────────────────────────────────────────────
    tab_all, tab_a, tab_b, tab_c = st.tabs(
        [f"全部 ({len(results)})", f"A 優先 ({count_a})", f"B 積極 ({count_b})", f"C 候選 ({count_c})"]
    )

    for tab, priority_filter in [
        (tab_all, None),
        (tab_a, "A"),
        (tab_b, "B"),
        (tab_c, "C"),
    ]:
        with tab:
            filtered = [r for r in results if priority_filter is None or r["priority"] == priority_filter]
            if not filtered:
                st.info("此優先級暫無推薦標的。")
            else:
                _render_table(filtered)

    # ── 下載按鈕 ─────────────────────────────────────────────────────
    st.markdown("---")
    df_export = _to_export_df(results)
    csv_data = df_export.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        label="📥 下載推薦清單（CSV）",
        data=csv_data,
        file_name="new_opportunities.csv",
        mime="text/csv",
    )


def _render_table(rows: list) -> None:
    """以彩色標示渲染結果表格。"""
    records = []
    for r in rows:
        priority_label = _PRIORITY_LABELS.get(r["priority"], r["priority"])
        records.append(
            {
                "優先級": priority_label,
                "代碼": r["stock_code"],
                "股票名稱": r["stock_name"],
                "目前股價": f"{r['current_price']:,.1f}",
                "DCF 內在價值": f"{r['dcf_value']:,.1f}",
                "低估幅度": f"{r['upside_pct'] * 100:.1f}%",
                "ROE": f"{r['roe'] * 100:.1f}%" if r.get("roe") is not None else "—",
                "建議買入價": f"{r['buy_price']:,.1f}",
                "市值(億)": f"{r['market_cap_b'] * 10:.0f}" if r.get("market_cap_b") is not None else "—",
                "推薦原因": r.get("reason", ""),
            }
        )
    df = pd.DataFrame(records)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _to_export_df(results: list) -> pd.DataFrame:
    """將結果轉為可匯出的 DataFrame。"""
    records = []
    for r in results:
        records.append(
            {
                "優先級": r["priority"],
                "股票代碼": r["stock_code"],
                "股票名稱": r["stock_name"],
                "目前股價": r["current_price"],
                "DCF內在價值": r["dcf_value"],
                "低估幅度(%)": round(r["upside_pct"] * 100, 2),
                "ROE(%)": round(r["roe"] * 100, 2) if r.get("roe") is not None else None,
                "建議買入價": r["buy_price"],
                "市值(億台幣)": round(r["market_cap_b"] * 10, 1) if r.get("market_cap_b") is not None else None,
                "推薦原因": r.get("reason", ""),
            }
        )
    return pd.DataFrame(records)


def _parse_custom_codes(raw: str) -> list:
    """
    解析使用者輸入的自訂股票代碼文字。

    Args:
        raw: 多行文字，每行一個代碼。

    Returns:
        格式化的候選股票清單。
    """
    codes = []
    for line in raw.strip().splitlines():
        code = line.strip()
        if code:
            codes.append({"stock_id": code, "stock_name": code})
    return codes
