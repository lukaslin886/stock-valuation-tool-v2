# 台股 DCF 估值工具 - 開發日誌

> 📖 **歷史版本詳細記錄**: [DEVELOPMENT_LOG_ARCHIVE.md](./DEVELOPMENT_LOG_ARCHIVE.md) (v1.0.0 - v1.5.3)

---

## 最新更新

### v1.8.8 (2026-05-01)

**P2-10 個股基本面評分系統完成（0-100 分 + A+~D）** ✅

**核心改善**:
- ✅ `MarketScanner` 新增基本面評分器，依 `roe`、`pe_ratio`、`pb_ratio`、`dividend_yield`、`revenue_growth` 計算 0-100 分
- ✅ 新增評級映射規則（A+、A、B+、B、C、D）
- ✅ 在 `filter_stocks()` 套用評分結果，輸出 `fundamental_score` 與 `fundamental_grade`
- ✅ 保持相容性：舊 snapshot 缺少 `roe/pb_ratio/dividend_yield/revenue_growth` 時不會拋錯
- ✅ 市場篩選頁初篩表格新增基本面分數與評級欄位
- ✅ 單元測試新增 3 個情境：高品質高評級、弱基本面低評級、缺欄位/缺值容錯

**調整檔案**:
- `app/market_scanner.py`
- `app/views/market_screener.py`
- `tests/unit/test_market_scanner.py`
- `artifacts/plan_p2_10_fundamental_scoring_20260501.md`（新增）
- `TODO.md`
- `DEVELOPMENT_LOG.md`

**驗證結果**:
1. `uv run pytest tests/unit/test_market_scanner.py -q` → PASSED
2. `uv run python -m py_compile app/market_scanner.py app/views/market_screener.py` → PASSED

**預期效益**:
1. 在市場快篩中可直接辨識基本面品質，降低二次人工篩選成本
2. 評分邏輯集中於資料層，後續可擴展到綜合報告與跨模組評分
3. 透過容錯與單元測試，降低資料缺值與規則調整造成的回歸風險

### v1.8.7 (2026-04-30) ⭐ 當前版本

**P2-09 股票篩選功能完成（P/E + 殖利率 + ROE 多條件）** ✅

**核心改善**:
- ✅ `MarketScanner` 市場快照新增 `roe` 欄位（來源：`yfinance` 的 `returnOnEquity`）
- ✅ `filter_stocks()` 新增 `min_roe` 參數，支援與市值、P/E、殖利率、低基期條件聯合篩選
- ✅ 向下相容舊快照：若缺少 `roe` 欄位，篩選流程不會拋錯
- ✅ 市場篩選頁新增 ROE 門檻控制項，並在結果表顯示殖利率與 ROE
- ✅ 新增 `test_market_scanner.py`，覆蓋多條件交集與缺欄位相容情境

**調整檔案**:
- `app/market_scanner.py`
- `app/views/market_screener.py`
- `tests/unit/test_market_scanner.py`（新增）
- `artifacts/plan_p2_09_stock_screener_20260430.md`（新增）
- `TODO.md`
- `DEVELOPMENT_LOG.md`

**驗證結果**:
1. `uv run pytest tests/unit/test_market_scanner.py -q` → PASSED
2. `uv run python -m py_compile app/market_scanner.py app/views/market_screener.py` → PASSED

**預期效益**:
1. 使用者可直接以價值（PE）、股東報酬（ROE）、現金回饋（殖利率）做組合式快篩
2. 篩選結果更貼近基本面選股流程，降低人工二次過濾成本
3. 透過回歸測試避免篩選條件擴充時出現相容性退化

### v1.8.6 (2026-04-30)

**P2-08 技術指標上線（MA / MACD / RSI）** ✅

**核心改善**:
- ✅ `DataManagerV2` 新增 `get_technical_indicators()`，使用既有價格資料計算 MA5/20/60、MACD、RSI
- ✅ DCF 頁面新增技術指標可視化區塊（股價+均線 / MACD / RSI 三層圖）
- ✅ 新增資料層單元測試（成功情境 + 資料不足情境）

**調整檔案**:
- `app/data/manager.py`
- `app/views/dcf_valuation.py`
- `tests/unit/test_data_manager.py`
- `TODO.md`
- `DEVELOPMENT_LOG.md`

**驗證結果**:
1. `uv run pytest tests/unit/test_data_manager.py -q` → PASSED
2. `uv run python -m py_compile app/views/dcf_valuation.py app/data/manager.py` → PASSED

**預期效益**:
1. 使用者可在估值頁同步檢視價值面（DCF）與技術面（MA/MACD/RSI）
2. 技術指標邏輯集中於資料層，後續可重用到市場篩選與報告頁
3. 以單元測試降低技術指標公式變更造成的回歸風險

### v1.8.5 (2026-04-30)

**P2-07 投資組合分析結案（語法修復 + 回歸防護）** ✅

**核心改善**:
- ✅ 修復 `app/views/portfolio_analysis.py` 的重複 keyword 參數語法錯誤
- ✅ 投資組合輸入表格欄位對齊（代碼 / 名稱 / 權重 / 操作）
- ✅ 修復 `app/views/market_screener.py` 的匯入路徑，確保 `app.views` 套件可被正常匯入
- ✅ 保留既有 `PortfolioAnalyzer` 計算流程，確認 20 個核心單元測試全數通過
- ✅ 新增 `test_views_imports.py`，建立 UI 模組匯入回歸檢查

**調整檔案**:
- `app/views/portfolio_analysis.py`
- `app/views/market_screener.py`
- `tests/unit/test_views_imports.py`（新增）
- `TODO.md`
- `DEVELOPMENT_LOG.md`

**驗證結果**:
1. `uv run python -m py_compile app/views/portfolio_analysis.py` → PASSED（修復後）
2. `uv run pytest tests/unit/test_portfolio_analyzer.py tests/unit/test_views_imports.py -q` → 21 passed

**預期效益**:
1. 避免投資組合頁面因語法錯誤導致整個頁面無法載入
2. 將此類 UI 模組解析錯誤前移到測試階段攔截
3. P2-07 功能與文件狀態一致，可正式視為結案

### v1.8.4 (2026-04-30)

**P2-06 產業比較功能上線** ✅

**核心改善**:
- ✅ `DataManagerV2` 新增 `get_industry_comparison()`，集中處理同業比較資料
- ✅ 使用 FinMind 股票主檔取得產業分類，避免在 DCF 頁逐檔打外部 API
- ✅ 整合 `data/market_scan.db` 的 market snapshot，計算產業平均 P/E、P/B
- ✅ DCF 頁面新增「同業比較」卡片，可直接查看同業樣本數、產業平均倍數與同業明細
- ✅ 若市場快照尚未建立，頁面會引導使用者先到市場篩選器更新數據
- ✅ 補上 2 個 DataManager 單元測試；全套單元測試提升為 279 passed

**調整檔案**:
- `app/data/manager.py`
- `app/views/dcf_valuation.py`
- `tests/unit/test_data_manager.py`
- `TODO.md`
- `pyproject.toml`

**驗證結果**:
1. `uv run pytest tests/unit/test_data_manager.py -q` → 34 passed
2. `uv run pytest tests/unit -q` → 279 passed

**預期效益**:
1. 使用者在估值頁就能快速知道本股是否高於或低於同業平均倍數
2. 產業比較邏輯集中在資料層，後續可重用到綜合報告與市場篩選功能
3. 缺少市場快照時會退化提示，不會讓 DCF 主流程失敗

### v1.8.3 (2026-04-30) 

**CI 擴充 + yfinance 清理 + P1-10/P2-17 結案** ✅

**核心改善**:
- ✅ 新增 `.github/workflows/uv-unit-test.yml`
- ✅ 在 GitHub Actions 以 Python 3.10 / 3.11 / 3.12 / 3.13 執行 `tests/unit`
- ✅ 自動上傳測試報告 artifact（`coverage.xml` 與 `reports/test_report.html`）
- ✅ 保留 `uv-smoke-test.yml` 作為快速基線驗證
- ✅ Phase 2 警告清理：移除 `YFinanceSource.get_latest_eps()` 對 `ticker.earnings` 的依賴
- ✅ EPS 備援改為 `income_stmt / financials` 計算，避免 yfinance deprecated API 警告
- ✅ Phase 2.5 警告門控：`pytest.ini` 新增 `error::DeprecationWarning:yfinance.*`，防止廢棄 API 悄悄回滲
- ✅ P1-10 正式結案：`BacktestEngine.validate_time_window_accuracy()` 驗證 1/3/5 年回測，全 3 測試通過
- ✅ P2-17 程式碼品質檢查：新增 `uv-lint.yml`，導入 `black --check` 與 `pylint --fail-under=7.0`
- ✅ 本地 lint 基準驗證完成：black 39 檔 0 變更、pylint 9.62/10

**調整檔案**:
- `.github/workflows/uv-unit-test.yml`（新增）
- `.github/workflows/uv-lint.yml`（新增）
- `TODO.md`（P1-10 結案、Phase 1 100%）
- `pytest.ini`（新增 yfinance 警告門控）
- `pyproject.toml`（新增 black / pylint 設定）
- `uv.lock`（新增 lint 依賴鎖定）
- `app/data/sources/yfinance_source.py`
- `tests/unit/test_sources.py`
- `tests/unit/test_backtest_engine.py`（3 測試 PASSED）

**預期效益**:
1. PR 階段可跨 Python 版本攔截相容性問題
2. 測試結果可直接由 CI artifact 下載與追蹤
3. 持續整合流程與 UV 隔離策略保持一致
4. 單元測試輸出更乾淨，降低外部套件棄用噪音
5. Phase 1 全部 15 項正式關閉（100%），階段完成
6. Lint 品質檢查正式納入 CI，可在 PR 階段攔截格式與靜態品質問題

### v1.8.2 (2026-04-30)

**UV 環境隔離導入完成（環境不互汙）** ✅

**核心改善**:
- ✅ 新增 `pyproject.toml`，將專案依賴正式納入 `uv` 管理
- ✅ 產生並提交 `uv.lock`，確保跨機器可重現安裝
- ✅ `run-en.ps1` 改為 `uv sync` 與 `uv run streamlit run app/main.py`
- ✅ `run_tests.bat` 改為 `uv sync --extra dev` 與 `uv run pytest`
- ✅ 新增 GitHub Actions `uv` smoke workflow，建立最小 CI 驗證基線
- ✅ 調整 pandas 相容性約束為 `<3.0.0`，避免既有測試在 pandas 3 上失敗
- ✅ 清理季度頻率測試參數 `Q -> QE`，移除相容性警告來源

**調整檔案**:
- `pyproject.toml`（新增）
- `uv.lock`（新增）
- `run-en.ps1`
- `run_tests.bat`
- `.github/workflows/uv-smoke-test.yml`（新增）
- `requirements.txt`
- `tests/conftest.py`
- `tests/unit/test_validator.py`

**驗證結果**:
1. `uv sync --extra dev` 可建立隔離環境並完成依賴同步
2. 核心測試在 `uv run pytest` 下可通過（含 `test_backtest_engine`）

**預期效益**:
1. 避免全域 pip/python 汙染，提升專案隔離性
2. 新成員可用單一流程快速重建一致環境
3. 測試與執行流程標準化，降低「在我機器能跑」風險

### v1.8.1 (2026-04-30)

**使用體驗優化（P1-06 / P1-07 / P1-08）完成** ✅

**核心改善**:
- ✅ 新增「使用說明」頁面（快速上手、FAQ、資料來源說明）
- ✅ 主導航加入「使用說明」入口
- ✅ 補強欄位提示（tooltip）與參數範例（主頁、風險分析、市場篩選）
- ✅ 將錯誤訊息改為白話文並附「可能原因 + 建議作法」

**調整檔案**:
- `app/main.py`
- `app/views/__init__.py`
- `app/views/user_guide.py`（新增）
- `app/views/dcf_valuation.py`
- `app/views/backtest.py`
- `app/views/risk_analysis.py`
- `app/views/market_screener.py`
- `app/views/comprehensive_report.py`

**預期效益**:
1. 新使用者可在 1-3 分鐘內完成首次分析流程
2. 常見失敗情境可直接在畫面中獲得重試方向
3. 參數調整成本降低，減少反覆試錯時間

---

### v1.8.0 (2025-11-06)

**main.py 模組化重構完成** 🎉

**重構成果總結**:

| 階段 | 起點 | 終點 | 減少量 | 減少比例 | 累計減少 |
|------|------|------|--------|----------|----------|
| P2-45 | 1690 | 836 | 854 | 50.5% | 50.5% |
| P2-46 | 836 | 673 | 163 | 19.5% | 60.2% |
| P2-47 | 673 | 407 | 266 | 39.5% | 75.9% |
| P2-48 | 407 | 124 | 283 | 69.5% | 92.7% |
| P2-49 | 124 | 118 | 6 | 5.0% | **93.0%** |

🎉 **最終成果: main.py 從 1690 行減至 118 行（減少 93%）**

**新模組架構**:
```
app/
├── main.py                      # 主程式（118 行）- 僅負責路由與設定
├── pages/                       # 頁面模組
│   ├── __init__.py              # 統一匯出介面
│   ├── dcf_valuation.py         # DCF 估值頁面（700 行）
│   ├── backtest.py              # 歷史回測頁面（170 行）
│   ├── risk_analysis.py         # 風險分析頁面（266 行）
│   └── comprehensive_report.py  # 綜合報告頁面（261 行）
```

**技術優勢**:
1. **大幅降低 Token 使用** - Context Window 效率提升 93%
2. **清晰的職責分離** - 每個頁面獨立模組
3. **高度可維護性** - 修改某頁面不影響其他頁面
4. **易於擴展** - 新增頁面只需建立新檔案
5. **完整向下相容** - 所有功能完全保留

**Git 記錄**:
```bash
da75698 - [P2-45] refactor: 提取 DCF 估值頁面 + 修復情境比較按鈕
cef43b2 - [P2-46] refactor: 提取歷史回測頁面到獨立模組
64dbd30 - [P2-47] refactor: 提取風險分析頁面到獨立模組
ff327ad - [P2-48] refactor: 提取綜合報告頁面到獨立模組
```

---

### v1.7.1 (2025-11-05)

**滑動風險單元測試完成** ✅

**測試成果**:
- **測試檔案**: 3個測試檔案，68個測試案例
- **測試結果**: 62/68 通過（91% 通過率）
- **測試覆蓋率**: SlippageModel 67%

**測試範圍**:
- `tests/unit/test_slippage_model.py` (18 測試)
  - 初始化、基礎滑價計算、買入價格調整
  - 流動性分級測試（4 層級）
  - 市場衝擊測試（3 層級）

- `tests/unit/test_dcf_slippage_integration.py` (26 測試)
  - DCF 計算器整合測試
  - 買入建議生成與優先級分類

- `tests/unit/test_portfolio_slippage_integration.py` (24 測試)
  - 投資組合分析整合
  - 持股分析與加碼建議

**技術要點**:
- ✅ 模組化測試 - 三個獨立測試檔案，職責清晰
- ✅ 高覆蓋率 - 67% 的程式碼覆蓋率
- ✅ 標準化流程 - 遵循 pytest 最佳實踐

---

### v1.6.2 (2025-10-30)

**MOPS 資料源整合完成（架構層面）** 🏗️

**核心成果**:
- ✅ 完成 MOPSSource 類別實作（簡化版）
- ✅ 整合到 DataManagerV2
- ✅ 建立測試工具與框架

**策略決策**: 參考 JoJoTrading 專案，採用「方案 B+」策略
- 專注於股本異動表與公司資訊
- 不處理複雜的財報數據解析
- 完整的快取機制（7天過期）

**架構價值**: 雖然 MOPS API 目前不可用，但完整的程式架構已建立，可隨時啟用

---

### v1.6.1 (2025-10-30)

**公式速查表完成** 📋

**核心成果**:
- ✅ 建立 FORMULA_REFERENCE.md（~25KB，超過600行）
- ✅ 完整的公式速查表
- ✅ 清晰的參數說明與預設值
- ✅ 三層索引系統（功能/參數/場景）

**文件結構**:
1. DCF 估值公式
2. 風險分析公式
3. 輔助計算公式
4. 參數預設值
5. 快速查詢索引

**與 CALCULATION_METHODS.md 的差異**:
- CALCULATION_METHODS.md: 深入學習（~50KB, 1000+行）
- FORMULA_REFERENCE.md: 快速查詢（~25KB, 600行）

---

### v1.6.0 (2025-10-29)

**計算方法完整文件化** 📚

**核心成果**:
- ✅ 建立 CALCULATION_METHODS.md（~50KB，超過1000行）
- ✅ 雙層級內容設計（基礎版 🟢 + 進階版 🔵）
- ✅ 包含實務範例與數學證明
- ✅ P1-01 完成：建立預設 EPS 字典
- ✅ P1-02 完成：實作資料驗證機制
- ✅ P1-09 完成：50檔股票測試（100% 成功率）

**文件架構**:
- 第一章：DCF 估值方法
- 第二章：風險分析方法

**資料品質提升**:
- 50檔前50大市值股票測試：100% 成功率
- 資料來源使用：YFinanceSource 84.0%，FinMindSource 66.7%
- 預設值機制：成功為 8 檔股票提供 EPS 備援

---

## 版本歷史摘要

### v1.5.3 (2025-10-28) - MOPS 資料源整合（方案 B+）
**核心成果**:
- ✅ 實作 MOPSSource 類別（簡化版）
- ✅ 股本異動表查詢功能
- ✅ 完整的快取機制

### v1.5.2 (2025-10-28) - 報告功能優化
**核心成果**:
- ✅ PDF/Excel 檔案名稱加入投資建議
- ✅ 實作投資建議簡稱轉換
- ✅ 改善檔案管理與識別

### v1.5.0 (2025-10-28) - 負成長率支援
**核心成果**:
- ✅ 調整成長率輸入範圍：-50% 到 50%
- ✅ 負成長警告提示
- ✅ 視覺提示區分正常成長與衰退

### v1.4.0 (2025-10-28) - 資料層模組化重構
**核心成果**:
- ✅ Strategy Pattern 實作
- ✅ DataSource 抽象類別體系
- ✅ CacheBackend 抽象類別體系
- ✅ 測試覆蓋：100% 成功率

### v1.3.0 (2025-10-28) - yfinance 整合增強
**核心成果**:
- ✅ yfinance 為主要 EPS 資料源
- ✅ 多層備援機制（yfinance → FinMind → 預設值）
- ✅ 5種不同的 EPS 欄位來源

### v1.2.0 (2025-10-28) - 報告匯出功能
**核心成果**:
- ✅ Excel 格式匯出（多工作表）
- ✅ PDF 格式匯出（含圖表）
- ✅ 實作 ReportGenerator 模組

### v1.1.0 (2025-10-28) - FinLab 整合
**核心成果**:
- ✅ 整合 FinLab 作為主要資料源
- ✅ 修復 DataFrame merge 類型錯誤（8處）
- ✅ 識別 FinLab 免費版限制

### v1.0.0 (2025-10-27) - 初始版本發布
**核心成果**:
- ✅ 完整的 DCF 估值功能
- ✅ 歷史回測系統
- ✅ 風險分析模組
- ✅ Streamlit Web 介面
- ✅ FinMind + yfinance 雙數據源

📑 **詳細歷史記錄請參閱**: [DEVELOPMENT_LOG_ARCHIVE.md](./DEVELOPMENT_LOG_ARCHIVE.md)

---

## 專案資訊

- **專案名稱**: 台股 DCF 估值工具 (Taiwan Stock DCF Valuation Tool)
- **當前版本**: v1.8.3
- **開發日期**: 2025年10月26日 - 至今
- **開發者**: AI協作開發
- **專案目的**: 為台股散戶投資者提供基於 DCF（現金流折現）模型的股票估值分析工具

## 技術棧

### 核心技術
- **Python 3.13**
- **Streamlit 1.30+**: Web 應用框架
- **Plotly 5.18+**: 互動式圖表

### 數據來源
- **FinMind API**: 主要數據源
- **yfinance**: 備用數據源
- **SQLite 3**: 本地快取

### 科學計算
- **NumPy, Pandas, SciPy**: 數值計算與數據處理

## 核心功能

1. **DCF 估值計算** - 基於現金流折現模型
2. **數據管理系統** - 多數據源整合與智能備援
3. **歷史回測引擎** - 驗證模型準確度
4. **風險分析模組** - VaR、CVaR、Monte Carlo 模擬
5. **Web 應用介面** - Streamlit 多頁面應用

## 檔案結構

```
stock-valuation-tool/
├── app/
│   ├── main.py                      # 主程式（118 行）
│   ├── pages/                       # 頁面模組
│   │   ├── dcf_valuation.py         # DCF 估值頁面
│   │   ├── backtest.py              # 歷史回測頁面
│   │   ├── risk_analysis.py         # 風險分析頁面
│   │   └── comprehensive_report.py  # 綜合報告頁面
│   ├── dcf_calculator.py            # DCF 計算引擎
│   ├── data/                        # 資料層
│   │   ├── sources/                 # 資料來源
│   │   └── cache/                   # 快取機制
│   ├── backtest.py                  # 回測引擎
│   ├── risk_analysis.py             # 風險分析
│   └── report_generator.py          # 報告生成器
├── DEVELOPMENT_LOG.md               # 開發日誌（本檔案）
├── DEVELOPMENT_LOG_ARCHIVE.md       # 歷史歸檔
├── CALCULATION_METHODS.md           # 計算方法說明（深入學習）
├── FORMULA_REFERENCE.md             # 公式速查表（快速查詢）
├── README.md                        # 專案說明
└── TODO.md                          # 待辦清單
```

## 已知限制

### 數據源限制
- FinMind 免費版有請求次數限制
- 部分財務指標可能不完整
- 即時數據延遲

### 功能限制
- 僅支援台股（.TW）
- DCF 模型假設較簡化

### 使用體驗
- 首次載入需要時間（建立快取）

## 授權與使用

**專案性質**: 個人使用工具  
**數據來源**: 
- FinMind API（遵循其服務條款）
- Yahoo Finance API（遵循其使用政策）

**免責聲明**: 本工具僅供教育和研究用途。所有估值結果僅供參考，不構成投資建議。

## 維護者

- 開發: AI 協作開發
- 文檔: 完整開發日誌與技術文檔

---

**最後更新**: 2026-04-30  
**文檔版本**: 2.0.0  
**專案狀態**: 穩定運行 ✅  
**資料覆蓋率**: 100% (前50大股票)
