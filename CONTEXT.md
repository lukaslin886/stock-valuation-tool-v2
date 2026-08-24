# Antigravity Context - Stock Valuation Tool (v2.4.0)

## 📌 Project Overview
An advanced stock valuation and market screening tool for Taiwan Stock Market (TWSE/TPEx).
Combines DCF (Discounted Cash Flow) valuation with real-time market scanning and fundamental analysis.

## 🏗️ Architecture (v2.4.0 Refactor)
- **Frontend**: Streamlit-based interactive dashboard.
- **Data Layer**: Unified Data Fusion Pipeline.
- **Scanning Engine**: Hybrid Integration (FinLab fundamentals + Yahoo Finance 2026 realtime price).
- **Database**: SQLite (`app/data/market_scan.db`) for caching standard-schema snapshots.

## 🔑 Data Fusion Strategy (核心數據混合策略)
由於不同數據源的特性，系統採用以下混合策略確保數據最優化：

| 數據維度 | 來源 | 處理邏輯 |
|---|---|---|
| **目前股價 (2026)** | Yahoo Finance | 強制補丁，確保估值基於最新行情。 |
| **52週高低點 (2026)** | Yahoo Finance | 回溯 1 年價格動態計算，修復位階精準度。 |
| **ROE / 殖利率** | FinLab (或 FinMind) | 使用 `P5-UNIT-ADAPTIVE` 進行單位歸一化。 |
| **公司名稱** | FinLab | 使用 `P5-NAME-RECOVERY` 從 `company_basic_info` 映射。 |
| **本益比 / 市值** | FinLab | 使用 `P5-EXHAUSTIVE-SEARCH` 進行模糊搜尋。 |

## ⚙️ Configuration (.env)
```env
FINLAB_API_TOKEN=...                   # FinLab token
FINMIND_TOKEN=...                      # FinMind token
DATABASE_PATH=app/data/market_scan.db
```

## 📝 Version History
- **v2.4.0**: 重構為 Data Fusion Hub。徹底解決 FinLab 免費版數據過舊問題，實作 2026 即時價格/位階同步。
- **v2.3.7**: 名稱補完與單位自適應實作。
- **v2.3.2**: FinLab 穩定版，解決資料集對齊問題。
