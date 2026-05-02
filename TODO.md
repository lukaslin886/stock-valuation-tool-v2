# 台股 DCF 估值工具 - 開發待辦清單

> 📅 **最後更新**：2026-05-01  
> 📦 **當前版本**：v1.9.0  
> 👨‍💻 **維護者**：AI 協作開發

---

## 📋 使用說明

### 狀態標記
- `[ ]` 未完成項目
- `[x]` 已完成項目

### 優先級標示
- 🔴 **高優先級** - 需要立即處理（1-2週內）
- 🟡 **中優先級** - 重要但不緊急（1-3個月內）
- 🟢 **低優先級** - 長期規劃項目（3-6個月內）

### 維護規範
1. **完成項目後**立即更新狀態（標記為 `[x]`）
2. **每週檢視**進度並調整優先級
3. **新增需求時**同步更新此檔案
4. **Git commit 時**標註相關 TODO 項目編號

---

## 📊 進度概覽

- **Phase 1（短期）**：15/15 完成 (100%) 🎉
- **Phase 2（中期）**：27/39 完成 (69%)
- **Phase 3（長期）**：2/33 完成 (6%)
- **Phase 4（維運）**：0/13 完成 (0%)

**總進度**：44/100 完成 (44%)

---

## 🔴 Phase 1: 短期改善（1-2週內）

### 1.1 資料品質提升

- [x] **P1-01** 增加更多重要股票的預設 EPS 值（前50大市值股票）✅
  - 目標：提供至少50檔重要股票的預設 EPS
  - 相關檔案：`app/data/manager.py`
  - 完成日期：2025-10-28
  
- [x] **P1-02** 實作資料有效性檢查機制 ✅
  - 檢查 EPS、股價、財務數據的合理範圍
  - 標記異常數據並記錄
  - 完成日期：2025-10-28
  
- [x] **P1-03** 建立異常值偵測與處理機制 ✅
  - 使用統計方法 (IQR/Z-Score) 偵測離群值
  - 整合進 `DataManagerV2` 自動偵測並顯示警告
  - 完成日期：2026-02-23
  
- [x] **P1-04** 添加資料品質評分系統 ✅
  - 為每筆資料來源評分 (0-100)
  - 綜合考量完整性、數量、缺失率與合理性
  - 完成日期：2026-02-23

### 1.2 使用體驗優化

- [x] **P1-05** 添加載入進度指示器（Streamlit spinner 改善）✅
  - 顯示詳細的載入步驟
  - 使用 st.progress() 和 st.empty() 實作進度條與訊息
  - 完成日期：2025-10-30
  - 相關檔案：`app/main.py`
  
- [x] **P1-06** 改善錯誤訊息的使用者友善度 ✅
  - ✅ 將主要分析頁面的錯誤訊息改為「可能原因 + 建議作法」
  - ✅ 補充可操作的重試指引（參數、期間、代碼格式）
  - 完成日期：2026-04-30
  - 相關檔案：`app/views/dcf_valuation.py`, `app/views/backtest.py`, `app/views/risk_analysis.py`, `app/views/comprehensive_report.py`
  
- [x] **P1-07** 增加操作提示與說明文字 ✅
  - ✅ 為主介面與市場篩選、風險分析關鍵欄位補上 tooltip
  - ✅ 補充常用參數範例與使用情境說明
  - 完成日期：2026-04-30
  - 相關檔案：`app/main.py`, `app/views/dcf_valuation.py`, `app/views/market_screener.py`, `app/views/risk_analysis.py`
  
- [x] **P1-08** 建立使用者操作指南頁面 ✅
  - ✅ 新增「使用說明」頁面（快速上手 + FAQ + 資料來源）
  - ✅ 導航列加入「使用說明」並可直接切換
  - 完成日期：2026-04-30
  - 相關檔案：`app/views/user_guide.py`, `app/views/__init__.py`, `app/main.py`

### 1.3 測試與驗證

- [x] **P1-09** 測試更多股票代碼（至少50檔）✅
  - 測試不同產業股票
  - 記錄測試結果
  - 完成日期：2025-10-28
  - 測試結果：100% 成功率（A+ 優秀）
  
- [x] **P1-10** 驗證不同時間區間的回測準確度 ✅
  - ✅ 測試 1年、3年、5年回測時間視窗（`years_windows=[1, 3, 5]`）
  - ✅ 驗證 `BacktestEngine.validate_time_window_accuracy()` 正確比較準確率並回傳最佳視窗
  - ✅ 測試覆蓋：全部成功（3/3）、部分失敗（2/3）、全部失敗（0/3）三種情境
  - ✅ 模擬結果：1年 61%、3年 68%（最佳）、5年 64%；平均 64.3%
  - 完成日期：2026-04-30
  - 相關檔案：`app/backtest.py`, `tests/unit/test_backtest_engine.py`
  
- [x] **P1-11** 確認 FinMind API Token 權限範圍 ✅
  - ✅ 測試 API 權限與端點可用性
  - ✅ 確認免費版可用功能範圍
  - ✅ 建立權限測試腳本
  - 完成日期：2025-10-30
  - 相關檔案：`test_finmind_permissions.py`
  
- [x] **P1-12** 建立 pytest 測試框架 ✅
  - [x] 1. pytest 套件安裝與配置 ✅
  - [x] 2. 測試目錄結構建立 (`tests/unit/`, `tests/integration/`) ✅
  - [x] 3. pytest.ini 設定檔（覆蓋率、HTML報告、Markers） ✅
  - [x] 4. conftest.py 測試固定裝置（20+ fixtures） ✅
  - [x] 5. test_validator.py（60+ 測試案例，97% 覆蓋率） ✅
  - [x] 6. test_data_manager.py（32 測試案例，83% 覆蓋率） ✅
  - [x] 7. run_tests.bat 執行腳本 ✅
  - [x] 8. test_dcf_calculator.py（46 測試案例，83% 覆蓋率） ✅
  - [x] 9. test_sources.py（41 測試案例，YFinance 72%/FinMind 79% 覆蓋率） ✅
  - [x] 10. 整合測試（26 測試案例）✅
  - [x] 11. 修正所有失敗測試 ✅
  - [x] 12. 驗證核心模組覆蓋率 ≥80% ✅
  - [x] 13. 清理臨時檔案並收尾 ✅
  - **完成日期**：2026-02-23
  - **最終結果**：274 測試全部通過，0 失敗。核心模組覆蓋率：manager 83%、dcf_calculator 83%、slippage_model 86%、validator 97%
  - **相關檔案**：`requirements.txt`, `pytest.ini`, `tests/conftest.py`, `tests/unit/test_*.py`, `run_tests.bat`

### 1.4 報告功能優化

- [x] **P1-13** PDF/Excel 檔案名稱加入投資建議 ✅
  - 檔案格式：`{股票代碼}_{股票名稱}_{投資建議簡稱}_{日期}`
  - 投資建議簡稱對應：
    - 強烈推薦買入 → 強烈推薦
    - 推薦買入 → 推薦買入
    - 可考慮 → 可考慮
    - 不建議 → 不建議
  - 完成日期：2025-10-28
  - 相關檔案：`app/main.py`（`get_recommendation_short_name` 函式）

### 1.5 文件與教育

- [x] **P1-14** 建立計算方法完整說明文件 🔴 ✅
  - 整理 DCF、VaR、Beta 等所有計算公式
  - 分為基礎版（一般投資人）和進階版（專業用戶）
  - 包含實務範例與數學推導
  - 相關檔案：`CALCULATION_METHODS.md`
  - 完成日期：2025-10-29
  
- [x] **P1-15** 建立公式速查表 🔴 ✅
  - 快速參考所有計算公式
  - 包含參數說明與預設值
  - 獨立文件 FORMULA_REFERENCE.md
  - 整合到 README.md
  - 完成日期：2025-10-30
  - 相關檔案：`FORMULA_REFERENCE.md`, `README.md`

---

## 🟡 Phase 2: 中期改善（1-3個月內）

### 2.1 資料層統一管理器

- [x] **P2-01** 設計 DataManagerV2 架構 ✅
  - 整合所有資料來源，實作 Strategy Pattern
  - 完成日期：2025-10-28
  
- [x] **P2-02** 實作智能備援策略（多來源自動切換） ✅
  - 自動選擇最佳資料來源，失敗時自動切換
  - 完成日期：2025-10-28
  
- [x] **P2-03** 建立資料品質評分與選擇機制 ✅
  - 整合 `DataValidator` 進行深度品質評估
  - 完成日期：2026-02-23
  
- [x] **P2-04** 實作資料來源效能監控 ✅
  - 記錄成功/失敗統計 (source_stats)
  - 完成日期：2026-02-23
  
- [x] **P2-05** 添加資料來源使用統計儀表板 ✅
  - 實作 `get_source_statistics()` 與 `get_quality_scores()`
  - 完成日期：2026-02-23

### 2.2 功能擴充

- [x] **P2-06** 增加產業比較功能 ✅
  - ✅ 在 DCF 估值頁新增同業比較卡片與同業明細表
  - ✅ 以 FinMind 股票主檔取得產業分類，結合 market snapshot 計算產業平均 P/E、P/B
  - ✅ 若缺少市場快照資料，提供「先到市場篩選器更新數據」的退化提示
  - 完成日期：2026-04-30
  - 相關檔案：`app/data/manager.py`, `app/views/dcf_valuation.py`, `tests/unit/test_data_manager.py`
  
- [x] **P2-07** 支援投資組合分析（多檔股票） ✅
  - ✅ 支援 2-10 檔股票的動態輸入、權重配置與總和驗證
  - ✅ 顯示投資組合核心指標（P/E、風險、報酬、Sharpe）與持股明細
  - ✅ 整合 `PortfolioAnalyzer` 並修復投資組合頁面語法問題
  - ✅ 新增 view 匯入健全性測試，避免 UI 模組語法錯誤回滲
  - 完成日期：2026-04-30
  - 相關檔案：`app/views/portfolio_analysis.py`, `app/portfolio/analyzer.py`, `tests/unit/test_portfolio_analyzer.py`, `tests/unit/test_views_imports.py`
  
- [x] **P2-08** 添加技術分析指標（MA, MACD, RSI） ✅
  - ✅ 在 DataManagerV2 新增 `get_technical_indicators()`，計算 MA5/20/60、MACD(12,26,9)、RSI(14)
  - ✅ 在 DCF 估值頁新增技術指標圖（價格+均線、MACD、RSI）
  - ✅ 新增 2 個單元測試，覆蓋成功/資料不足兩種情境
  - 完成日期：2026-04-30
  - 相關檔案：`app/data/manager.py`, `app/views/dcf_valuation.py`, `tests/unit/test_data_manager.py`
  
- [x] **P2-09** 實作股票篩選功能（依條件搜尋） ✅
  - ✅ 依 P/E、殖利率、ROE 條件篩選
  - ✅ 支援多條件組合篩選
  - 完成日期：2026-04-30
  - 相關檔案：`app/market_scanner.py`, `app/views/market_screener.py`, `tests/unit/test_market_scanner.py`
  
- [x] **P2-10** 新增個股基本面評分系統 ✅
  - ✅ 綜合財務指標評分
  - ✅ 產生投資評級（A+ 到 D）
  - 完成日期：2026-05-01
  - 相關檔案：`app/market_scanner.py`, `app/views/market_screener.py`, `tests/unit/test_market_scanner.py`

### 2.3 資料管理

- [ ] **P2-11** 建立資料自動更新排程（使用 APScheduler）
  - 每日自動更新股價
  - 每季自動更新財報
  
- [ ] **P2-12** 實作快取過期機制（TTL 設定）
  - 股價快取：1小時
  - 財報快取：7天
  
- [ ] **P2-13** 優化資料庫索引結構
  - 加速查詢效能
  - 減少磁碟空間使用
  
- [ ] **P2-14** 考慮新增其他資料來源（如 TEJ）
  - 評估 TEJ 資料庫成本與效益
  - 研究整合方式

### 2.4 品質提升

- [x] **P2-15** 建立完整的單元測試（pytest） ✅
  - 目標：測試覆蓋率 > 80% (實際已達 83-97%)
  - 完成日期：2026-02-23 (與 P1-12 同步)
  
- [x] **P2-16** 實作持續整合（GitHub Actions） ✅
  - 自動執行測試
  - 自動產生測試報告
  - ✅ 已完成最小可用版本：新增 `uv` smoke workflow（核心單元測試）
  - ✅ 已完成完整單元測試矩陣：Python 3.10 / 3.11 / 3.12 / 3.13
  - ✅ 已完成測試報告上傳：`coverage.xml`、`reports/test_report.html`
  - 完成日期：2026-04-30
  
- [x] **P2-17** 建立程式碼品質檢查（pylint, black） ✅
  - ✅ 新增 `uv-lint.yml`，在 GitHub Actions 執行 `black --check` 與 `pylint`
  - ✅ `pyproject.toml` 新增 black / pylint 設定與 dev 依賴
  - ✅ black 檢查結果：39 個檔案符合格式（0 變更）
  - ✅ pylint 基準分數：9.62/10（門檻設定：7.0）
  - 完成日期：2026-04-30
  - 相關檔案：`pyproject.toml`, `.github/workflows/uv-lint.yml`, `uv.lock`
  - 檢查程式碼品質分數
  
- [ ] **P2-18** 撰寫 API 文件（使用 Sphinx）
  - 自動生成 API 文件
  - 發布到 GitHub Pages

### 2.5 風險模型與時間加權（新增）🔴

- [ ] **P2-26** 設計滑動風險模型架構 🔴 **最高優先**
  - 基於日線 K 棒（2根）的滑價計算
  - 支援買入/賣出建議修正
  - 支援投資組合回測
  - 混合模型：波動性 + 流動性 + 市場衝擊
  
- [x] **P2-27** 實作 SlippageModel 類別 🔴 ✅
  - ✅ 建立 `app/risk/slippage_model.py`
  - ✅ 實作 `calculate_slippage()` 方法
  - ✅ 實作波動性滑價計算
  - ✅ 實作流動性滑價計算
  - ✅ 實作市場衝擊滑價計算
  - ✅ 實作 `adjust_buy_price()` 方法（DCF 應用）
  - ✅ 實作 `adjust_backtesting_trades()` 方法（Portfolio 應用）
  - ✅ 測試驗證：5 項測試全部通過
  - 完成日期：2025-11-05
  - 相關檔案：`app/risk/slippage_model.py`, `test_slippage_model.py`
  
- [x] **P2-28** 整合滑動風險到 DCF Calculator 🔴 ✅
  - ✅ 添加 SlippageModel 導入
  - ✅ 初始化 SlippageModel（enable_slippage 參數）
  - ✅ 實作 `calculate_buy_recommendation()` 方法
  - ✅ 滑價調整的買入價格計算
  - ✅ 安全邊際與優先級分類
  - ✅ 測試驗證：4 項測試全部通過
  - 完成日期：2025-11-05
  - 相關檔案：`app/dcf_calculator.py`, `test_dcf_slippage_integration.py`
  
- [x] **P2-29** 整合滑動風險到 Portfolio Analyzer 🔴 ✅
  - ✅ 添加 SlippageModel 導入（支援多種路徑）
  - ✅ 初始化選項（enable_slippage 參數）
  - ✅ 整合到 `analyze_buy_opportunities_from_holdings()` 方法
  - ✅ 修改加碼建議價位計算（base_buy_price + slippage）
  - ✅ 更新買入理由生成（包含滑價資訊）
  - ✅ 測試驗證：4 項測試全部通過（初始化、分析、加碼建議、停用模式）
  - 完成日期：2025-11-05
  - 相關檔案：`portfolio_analyzer/analyzer.py`, `test_portfolio_slippage_integration.py`
  
- [x] **P2-30** 建立滑動風險單元測試 ✅
  - ✅ 將測試腳本改寫為 pytest 格式
  - ✅ 整合三個測試檔案到 tests/unit/ 目錄
  - ✅ 測試結果：68 個測試，62 個通過（91%）
  - ✅ 測試覆蓋範圍：SlippageModel 67%、DCF整合、Portfolio整合
  - 完成日期：2025-11-05
  - 相關檔案：`tests/unit/test_slippage_model.py`, `tests/unit/test_dcf_slippage_integration.py`, `tests/unit/test_portfolio_slippage_integration.py`
  
- [x] **P2-31** 滑動風險配置參數與文件 ✅
  - ✅ 更新 `portfolio_analyzer/config.py`（新增80行配置區塊）
  - ✅ 更新 `STRATEGY.md`（新增第7章，約1500行）
  - ⏸️ 更新 `CALCULATION_METHODS.md`（技術文件，可選，列為獨立任務）
  - 完成日期：2025-11-05
  - 相關檔案：`portfolio_analyzer/config.py`, `portfolio_analyzer/STRATEGY.md`
  - Git commits: b0e42d6, 4e7ef6e
  
- [x] **P2-32** 實作指數衰減時間加權函式 🔴 ✅
  - ✅ 修改 `calculate_historical_growth_rate()` 支援時間加權
  - ✅ 實作 `_calculate_lambda()` 計算衰減參數
  - ✅ 實作 `_calculate_exponential_weights()` 計算指數權重
  - ✅ 實作 `_calculate_time_weighted_growth_rate()` 時間加權成長率
  - ✅ 新增配置參數到 `config.py`（ENABLE_TIME_WEIGHTING, RECENT_WEIGHT_RATIO）
  - ✅ 建立完整測試檔案並通過所有測試
  - 完成日期：2025-11-05
  - 相關檔案：`app/data/manager.py`, `portfolio_analyzer/config.py`, `test_time_weighting.py`
  - 測試結果：4 項測試全部通過 ✓
  
- [x] **P2-33** 時間加權參數優化與計算 ✅
  - ✅ 實作 `_calculate_exponential_weights()` 計算指數權重
  - ✅ 實作 `_calculate_lambda()` 衰減參數計算
  - ✅ 支援向後相容（可切換回等權重）
  - ✅ 配置參數已加入 `portfolio_analyzer/config.py`
  - 完成日期：2025-11-05（與 P2-32 同時完成）
  - 備註：此任務實際已包含在 P2-32 實作中
  
- [x] **P2-34** 時間加權配置與 UI 顯示 ✅
  - ✅ 更新 `portfolio_analyzer/config.py`（已完成）
  - ✅ 在 Streamlit DCF 估值頁面顯示加權方法資訊
  - ✅ 顯示 RECENT_WEIGHT_RATIO 設定值
  - ✅ 顯示權重分配範例說明
  - ✅ 時間加權與等權重方法自動識別顯示
  - 完成日期：2025-11-05
  - 相關檔案：`app/main.py`
  
- [x] **P2-35** 建立時間加權單元測試 ✅
  - ✅ 建立標準 pytest 單元測試檔案（700+ 行，5個測試類別）
  - ✅ 40 個測試案例，全部通過 ✓
  - ✅ 測試覆蓋：Lambda計算、權重分配、成長率計算、完整功能、邊界情況
  - ✅ 使用 Mock 隔離資料來源依賴
  - ✅ 整合測試改名為 test_time_weighting_integration.py
  - 完成日期：2025-11-05
  - 相關檔案：`tests/unit/test_time_weighting.py`, `test_time_weighting_integration.py`
  
- [x] **P2-36** 時間加權視覺化與文件 ✅
  - ✅ UI 權重分配圖表 (Plotly Bar Chart)
  - ✅ 更新 `CALCULATION_METHODS.md`
  - ✅ 更新 `README.md`
  - ✅ 更新 `TIME_WEIGHTING.md`
  - 完成日期：2026-02-23
  
- [ ] **P2-37** 時間加權效果驗證與調優
  - A/B 測試：等權重 vs 時間加權
  - 分析成長率預測準確度
  - 調整預設參數

### 2.6 程式碼重構與優化

- [x] **P2-45** 修復情境比較按鈕並重構 main.py 模組化 ✅
  - ✅ 修復情境比較按鈕：從 st.button() 改為 st.checkbox()
  - ✅ 建立 app/pages/ 模組結構
  - ✅ 提取 show_dcf_valuation() 到獨立模組（約 700 行）
  - ✅ main.py 從 1690 行縮減到 836 行（減少 50.5%）
  - ✅ 刪除重複函式定義
  - ✅ 測試驗證所有功能正常
  - 完成日期：2025-11-05
  - 相關檔案：`app/main.py`, `app/pages/dcf_valuation.py`, `app/pages/__init__.py`
  - Git commit: da75698
  
- [x] **P2-46** 提取歷史回測頁面到獨立模組 ✅
  - ✅ 提取 show_backtest() 到 pages/backtest.py（170 行）
  - ✅ 更新 pages/__init__.py 匯出
  - ✅ 更新 main.py 導入並刪除重複函式
  - ✅ main.py 從 836 行減至 673 行（減少 19.5%）
  - 完成日期：2025-11-06
  - 相關檔案：`app/pages/backtest.py`
  - Git commit: cef43b2
  
- [x] **P2-47** 提取風險分析頁面到獨立模組 ✅
  - ✅ 提取 show_risk_analysis() 到 pages/risk_analysis.py（266 行，5 個函式）
  - ✅ 更新 pages/__init__.py 匯出
  - ✅ 更新 main.py 導入並刪除重複函式
  - ✅ main.py 從 673 行減至 407 行（減少 39.5%）
  - 完成日期：2025-11-06
  - 相關檔案：`app/pages/risk_analysis.py`
  - Git commit: 64dbd30
  
- [x] **P2-48** 提取綜合報告頁面到獨立模組 ✅
  - ✅ 提取 show_comprehensive_report() 到 pages/comprehensive_report.py（261 行）
  - ✅ 提取 get_recommendation_short_name() 輔助函式
  - ✅ 更新 pages/__init__.py 匯出
  - ✅ 更新 main.py 導入並刪除重複函式
  - ✅ main.py 從 407 行減至 124 行（減少 69.5%）
  - 完成日期：2025-11-06
  - 相關檔案：`app/pages/comprehensive_report.py`
  - Git commit: ff327ad
  
- [x] **P2-49** 完成 main.py 模組化重構收尾 ✅
  - ✅ 確認所有四個頁面模組提取完成
  - ✅ 清理 main.py 不必要的導入（移除 plotly, pandas, numpy, datetime, ReportGenerator）
  - ✅ main.py 最終優化至 118 行（累計減少 93%！）
  - ✅ 更新 TODO.md 標記完成項目
  - ✅ 更新 DEVELOPMENT_LOG.md 記錄重構歷程
  - ✅ 最終 Git commit 標記 P2-49 完成
  - 完成日期：2025-11-06
  - **重構成果總結**：
    - 起點：main.py 1690 行（未模組化）
    - P2-45：1690 → 836 行（-50.5%）
    - P2-46：836 → 673 行（-19.5%）
    - P2-47：673 → 407 行（-39.5%）
    - P2-48：407 → 124 行（-69.5%）
    - P2-49：124 → 118 行（-5.0%）
    - **最終：118 行（累計減少 93.0%）** 🎉
  - Git commit: 57b1b2b

### 2.7 新標的推薦功能（買入建議 Phase 2）

- [x] **P2-38** 設計新標的推薦系統架構
  - 定義候選股票來源（台灣50、富邦臺灣中小00733、自訂清單）
  - 設計篩選流程與邏輯
  - 規劃與 Phase 1 持股加碼分析的整合方式
  
- [x] **P2-39** 實作候選股票掃描器
  - 支援台灣50成分股自動掃描
  - 支援自訂股票清單輸入
  - 整合資料來源獲取候選股票基本資料
  
- [x] **P2-40** 實作 DCF 基礎篩選邏輯
  - DCF 低估程度 > 20%
  - 安全邊際計算
  - 排除數據品質不佳的股票
  
- [x] **P2-41** 實作進階篩選條件
  - 負債比限制（< 50%）
  - 市值門檻篩選
  - ROE、毛利率等財務指標篩選
  - 流動性篩選（成交量）
  
- [x] **P2-42** 建立新標的推薦報表
  - Excel 工作表：「新標的推薦」
  - 欄位：股票代碼、名稱、目前價格、DCF價值、低估%、負債比、ROE、建議買入價、推薦原因
  - 依優先級排序（A/B/C）
  
- [x] **P2-43** 整合到 portfolio_analyzer 主流程
  - 在 `analyzer.py` 中新增 `analyze_new_opportunities()` 方法
  - 在 `report_generator.py` 中新增工作表生成
  - 在 `run_analysis.py` 中整合執行流程
  
- [x] **P2-44** 建立完整測試與驗證
  - 單元測試：篩選邏輯正確性
  - 整合測試：與 Phase 1 功能共存
  - 效能測試：掃描50檔股票的執行時間
  - 驗證推薦結果的合理性

## 🟢 Phase 3: 長期規劃（3-6個月內）

### 3.1 市場掃描器進階功能 (Market Screener Phase 2)

- [x] **P3-01** 實作「深度掃描」模式 (Deep Scan) ✅
  - ✅ 針對初篩結果(約50-100檔)進行歷史數據獲取
  - ✅ 計算 5年/10年 營收與獲利 CAGR
  - ✅ 檢查連續配息年份
  - ✅ 實作 OCF/NI 現金流品質檢查與毛利穩定度分析
  - 完成日期：2026-05-02
  
- [x] **P3-02** 整合智慧選股策略快選 ✅
  - ✅ 綜合評分系統：整合品質分數與位階分數
  - ✅ 實作「穩定現金牛」、「高成長價值」、「超級低基期」預設按鈕
  - ✅ UI 視覺化強化（背景漸層顏色）
  - 完成日期：2026-05-02

- [ ] **P3-03** 效能優化與快取策略
  - 深度掃描結果快取 (避免重複請求)
  - 批次處理 API 請求

### 3.2 資料與評估指標優化

- [ ] **P3-04** 增加產業比較功能
### 3.2 資料與評估指標優化 (規劃中)

- [ ] **P3-04** 個股財報深度挖掘與分析

### 3.3 其他長期規劃

- [ ] **P3-05** 支援國際股市資料 (yfinance 已支援部分)
- [ ] **P3-06** 實作行動裝置版本介面

---

## 🔧 Phase 4: 維運與監控（持續進行）

### 4.1 基礎維運

- [ ] **P4-01** 錯誤日誌記錄
  - 記錄 API 錯誤與異常
  - 便於問題追蹤

- [ ] **P4-02** 文件維護
  - 持續更新開發日誌
  - 維護 README 與計算方法文件

### 4.2 資料源維護

- [ ] **P4-03** 定期檢查 API 可用性
  - FinMind / yfinance 來源狀態確認
  
- [ ] **P4-04** 資料驗證
  - 定期驗證數據準確性

---

## 📝 版本更新記錄

### v1.9.0 (2026-05-01) - 新標的推薦系統上線
- ✅ 完成 **P2-38 ~ P2-44**：新標的推薦系統（OpportunityFinder）
- ✅ 新增 `app/opportunity_finder.py`：OpportunityFinder 類別，台灣50候選股 DCF 掃描
- ✅ 新增 `app/views/new_opportunities.py`：Streamlit 新標的推薦頁面（A/B/C 優先級彩色表格）
- ✅ `app/main.py` 新增「新標的推薦」頁面路由
- ✅ 新增 `tests/unit/test_opportunity_finder.py`：30+ 單元測試（篩選、優先級、邊界情況）

### v1.8.4 (2026-04-30) - 產業比較功能上線
- ✅ 完成 **P2-06**：DCF 頁面新增同業比較卡片與同業估值明細
- ✅ 新增 `DataManagerV2.get_industry_comparison()`，整合 FinMind 產業分類與 market snapshot
- ✅ 產業平均 P/E、P/B 可直接顯示，並附帶本股與同業差值
- ✅ 測試驗證：`uv run pytest tests/unit -q` 通過 279 tests

### v1.8.3 (2026-04-30) - CI 完整單元測試矩陣
- ✅ 完成 **P2-16**：新增 `uv` full unit workflow（Python 3.10-3.13）
- ✅ CI 產出並上傳 `coverage.xml` 與 `pytest` HTML 報告 artifact
- ✅ 保留 smoke workflow 作為快速基線檢查
- ✅ Phase 2 完成：移除 `ticker.earnings` 路徑，改為 `income_stmt / financials` EPS 備援計算
- ✅ `uv run pytest tests/unit -q` 驗證 277 passed，警告摘要已清空

### v1.8.2 (2026-04-30) - UV 環境隔離落地
- ✅ 新增 `pyproject.toml` 與 `uv.lock`，建立專案級隔離環境
- ✅ `run-en.ps1` 改為 `uv sync` + `uv run streamlit run app/main.py`
- ✅ `run_tests.bat` 改為 `uv sync --extra dev` + `uv run pytest`
- ✅ 新增 GitHub Actions `uv` smoke workflow（核心測試）
- ✅ 修正 pandas 版本相容性（`<3.0.0`）並清理測試中的 `Q` 週期警告來源

### v1.8.1 (2026-04-30) - 使用體驗與引導強化
- ✅ 完成 **P1-06**：錯誤訊息白話化與可行修正建議
- ✅ 完成 **P1-07**：關鍵輸入欄位 tooltip 與範例提示
- ✅ 完成 **P1-08**：新增「使用說明」頁面與 FAQ
- ✅ 側邊欄新增「使用說明」導覽入口，降低新使用者上手門檻

### v1.7.0 (2025-11-06) - 市場掃描器與路徑修復
- ✅ 新增 Market Screener 模組 (可針對市值、PE、殖利率初步篩選)
- ✅ 修復 run-en.ps1 在外部目錄執行時的路徑錯誤
- 🗑️ 移除不必要的 MOPS、XBRL、CRE 研究與商業化規劃，聚焦核心價值

### v1.6.1 (2025-10-30) - test_sources.py 測試完成
- ✅ **P1-12 Item 9** 完成資料來源模組單元測試（test_sources.py）
- ✅ 測試覆蓋範圍：
  - YFinanceSource: 20 個測試案例，覆蓋率 65%
  - FinMindSource: 18 個測試案例，覆蓋率 79%
  - 資料來源整合: 3 個測試案例（一致性、錯誤恢復、超時處理）
  - 總計: 41 個測試案例，全部通過 ✅
- ✅ 測試內容完整：
  - 初始化與設定測試
  - 資料獲取功能測試（股價、財報、EPS、股票資訊）
  - 錯誤處理測試（API 失敗、超時、無效輸入）
  - Mock 測試覆蓋外部 API（yfinance、FinMind）
  - 資料一致性驗證
- ✅ 專案整體測試進度：
  - 單元測試: 196 個測試案例（test_validator 60、test_data_manager 28、test_dcf_calculator 45、test_sources 41、整合測試 22）
  - 測試通過率: 97% (191/196)
  - 四個核心模組覆蓋率均達標（>65%）
- 📊 進度更新：P1-12 完成度從 62% 提升至 69%（9/13），Phase 1 從 40% 提升至 47%（7/15）
- 相關檔案：`tests/unit/test_sources.py`、`tests/conftest.py`、`TODO.md`

### v1.6.0 (2025-10-29) - 計算方法文件化完成
- ✅ **P1-14** 建立計算方法完整說明文件（CALCULATION_METHODS.md）
- ✅ 完整整理所有計算公式與原理：
  - 第一章：DCF 估值方法（DCF、折現率、現金流預測、終值計算、敏感性分析）
  - 第二章：風險分析方法（VaR、CVaR、Monte Carlo、波動率、Beta）
- ✅ 雙層級內容設計：
  - 基礎版 🟢：適合一般投資人理解核心概念
  - 進階版 🔵：提供完整數學推導與專業知識
- ✅ 包含實務範例：使用台積電實際數據示範計算過程
- ✅ 完整數學證明：Gordon Growth Model 無窮等比級數推導
- ✅ 新增 P1-15 項目：規劃建立公式速查表（預計 2025-11-05 完成）
- ✅ 更新文件：README.md、DEVELOPMENT_LOG.md
- 📊 進度更新：Phase 1 完成度從 33% 提升至 40%（6/15）
- 相關檔案：`CALCULATION_METHODS.md`、`TODO.md`、`README.md`、`DEVELOPMENT_LOG.md`
- 下一步：整合到 DataManagerV2 並測試

### v1.5.2 (2025-10-28) - 報告功能優化
- ✅ **P1-13** 完成 PDF/Excel 檔案名稱加入投資建議功能
- ✅ 實作 `get_recommendation_short_name()` 函式
- ✅ 投資建議簡稱對應完成（強烈推薦、推薦買入、可考慮、不建議）
- ✅ 檔案命名格式：`{股票代碼}_{股票名稱}_{投資建議簡稱}_{日期}`
- ✅ 建立測試檔案驗證功能正常運作

### v1.5.1 (2025-10-28) - TODO 更新至 3.1.1
- ✅ 更新 Phase 3.1.1：從 TWSE OpenAPI 改為 MOPS 資料源整合
- ✅ 研究發現 TWSE OpenAPI 端點不可用
- ✅ 參考 JoJoTrading 專案，採用公開資訊觀測站 (MOPS) 方案
- ✅ 詳細規劃 MOPSSource 類別實作步驟
- ✅ 定義完整的測試策略

### v1.5.0 (2025-10-28)
- ✅ 修復負成長率支援問題
- ✅ 建立 TODO.md 檔案
- ✅ 定義完整的開發路線圖

### v1.4.0 (2025-10-28)
- ✅ 完成資料層模組化重構
- ✅ 實作 Strategy Pattern
- ✅ 建立獨立的資料來源與快取模組

### v1.3.0 (2025-10-28)
- ✅ 增強 yfinance 整合
- ✅ 實作多層備援機制
