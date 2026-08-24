# TODO List - Stock Valuation Tool

## 🟢 當前進度: v2.4.0 (Data Fusion Hub)

### 1. 核心引擎優化 (Core Engine)
- [x] **FinLab 數據源優化**
    - [x] 實作 `company_basic_info` 名稱對照表補完計畫
    - [x] 實作 ROE/Yield 單位自適應校正 (0.05 -> 5.0)
    - [x] 修復市值與本益比模糊搜尋路徑 (price/etl category)
    - [x] 完成 252 天歷史回溯計算 52週高低點
- [x] **實作 Data Fusion Hub (v2.4.0)**
    - [x] 整合 Yahoo Finance 2026 即時股價補丁
    - [x] 建立 `_finalize_and_save_snapshot` 統一數據中樞
- [x] **篩選器邏輯修正**
    - [x] 修正「低基期」位階篩選器邏輯
    - [x] 修正零值 (0.0) 導致的空清單過濾問題
- [ ] **FinMind 引擎 (備援)**
    - [x] 評估是否需要實作 FinMind 專業版批次 API — **結論：現行批次快照用途不需升級 Pro**（見 `docs/FinMind_Backup_Evaluation_20260706.md`）
    - [ ] 優化 FinMind 頻率限制處理 — 評估完成，建議：402 明確處理 + `user_info` 用量預檢 + 退避重試 + 優先批次（見評估報告第四節，實作待排）

### 2. UI/UX 改善
- [x] 篩選器結果即時顯示公司名稱
- [x] 位階欄位格式化顯示 (0.0 ~ 1.0)
- [x] 增加「一鍵導出 Excel」進度條 — `app/excel_export.py`（分批寫入 + progress_callback），market_screener 改「準備→進度條→下載」兩段式；測試 `tests/unit/test_excel_export.py`（11 檢查通過，2026-07-06）
- [x] 搜尋結果分頁處理 (若股票數 > 500) — `app/pagination.py` 的 `slice_page` 純函式 + market_screener 主表分頁（每頁筆數/頁碼，匯出仍全量）；測試 `tests/unit/test_pagination.py`（10 檢查通過，2026-07-06）

### 3. 未來規劃 (Roadmap)
- [x] 加入技術指標篩選 (RSI/MACD) — `app/technical_indicators.py` + `app/technical_filter_ui.py`，已接入 market_screener Stage-3；單元測試 `tests/unit/test_technical_indicators.py`（2026-07-06）
- [ ] 加入法人籌碼篩選 (外資/投信買超)
- [ ] 支援美股 (Yahoo Finance API 整合)
- [ ] 撰寫監控腳本：當用戶回報 Bug 超過一定數量，自動觸發 SkillOpt 流程修改專案的 _AI_Rules
- [ ] 升級成自動交易機器人：將寫好的 DCF 估值模型，交給 AI 來自動判斷是否該買進
- [ ] 引入大語言模型 (LLM)：讓 AI 自動閱讀財報新聞，並結合 `stock_analyzer.py` 產出分析報告
