# Phase 0 未提交變更盤點（Task 1.1 / 1.3）

> 對應 `projects/Finance/.kiro/specs/finance-platform-integration/` 需求 0（Git Baseline 與變更隔離）。
> 盤點日期：2026-08-19　工具：`git diff` / `git diff -w` / `git diff --ignore-space-at-eol`

## 摘要

`git status --short` 回報 137 筆變更（74 個 `M`、其餘為刪除與新增）。逐檔比對後發現：**74 個 M 檔案中，42 個是純換行符雜訊（CRLF/LF），零語意差異；只有 30 個真的有內容變更。** 另有 ~40 項未追蹤（`??`）新增，絕大多數就是先前已讀過的 Kiro spec v3.0 架構（`app/container.py`、`app/core/`、`app/infra/`、`app/services/`、`tests/property/`、`.kiro/` 本身等）。

判定方法：`git diff --stat`（全量）vs `git diff --ignore-space-at-eol --stat`（去除行尾雜訊後）兩者的檔案清單做差集，並對代表性檔案用 `file` 指令與 `git show HEAD:<path> | file -` 交叉驗證 CRLF 假設。

---

## 分類 A：純換行符雜訊（42 檔，零語意差異，安全）

確認方式：`git diff --ignore-space-at-eol` 對這些檔案輸出為空。根因是工作目錄檔案已被存成 CRLF，而上次 commit（`48f3c8b`）當時是 LF；repo 沒有 `.gitattributes`、也沒設定 `core.autocrlf`，導致换行符隨編輯器/系統飄移。

```
.clinerules, .env.example, CALCULATION_METHODS.md, DEVELOPMENT_LOG_ARCHIVE.md,
FORMULA_REFERENCE.md, TIME_WEIGHTING.md,
app/data/__init__.py, app/data/cache/__init__.py, app/data/cache/base.py,
app/data/sources/__init__.py, app/data/sources/base.py,
app/opportunity_finder.py, app/portfolio_report.py,
app/risk/__init__.py, app/risk/slippage_model.py, app/risk_analysis.py,
app/views/new_opportunities.py,
clear_cache.py, docs/DCF_VALUATION.md, docs/RISK_ANALYSIS.md,
finmind_api_permissions_report.md, finmind_demo.py,
portfolio_analyzer/{README.md,STRATEGY.md,__init__.py,analyzer.py,config.py,
  report_generator.py,run_analysis.bat,run_analysis.py},
run-en.ps1, run_tests.bat,
tests/conftest.py, tests/test_anomaly_system.py,
tests/unit/{test_dcf_slippage_integration.py,test_market_scanner.py,
  test_opportunity_finder.py,test_portfolio_slippage_integration.py,
  test_slippage_model.py,test_sources.py,test_time_weighting.py,test_validator.py}
```

**建議**：不是「保留內容」的問題，是「換行符標準化」的問題。建議 Task 1.2 執行前先建立 `.gitattributes`（`* text=auto eol=lf`），再對這 42 檔統一標準化，這樣未來不會每次編輯都出現滿版假 diff。

---

## 分類 B：有真實內容變更的既有檔案（30 檔）

逐檔以 `git diff --ignore-space-at-eol` 核實內容後分類：

| 檔案 | 變動規模 | 內容判斷 | 建議 |
|:---|---:|:---|:---|
| `app/main.py` | 109 行 | **已內建過渡態**：初始化 `st.session_state.container = setup_container()`，並新增 `get_service()` 橋接函式供 views 逐步遷移；但 views 仍全部走舊的 `st.session_state.dcf_calculator` 等直接實例。`get_service()` 目前**零呼叫**（已用 grep 確認）。 | 保留，屬既定功能（部分完成的過渡設計）。**修正 finance-platform-integration 需求 1 的前提**：main.py 並非「完全未接線」，而是「橋接器已建但未被使用」，比原設想更接近完工一步。 |
| `app/views/market_screener.py` | 380 行 | 大改動，需求 1 判定表要重點比對的檔案之一 | 保留，Task 3.2/3.4 判定時列為重點比對對象 |
| `app/market_scanner.py` | 605 行（在 `-w` 下） | 舊扁平版市場掃描器的實質修改 | 保留，Task 3.4 判定時與 `app/services/market_scanner.py` 比對 |
| `tests/unit/test_dcf_calculator.py` | 1034 行 | 測試大量擴充，與新增的 `tests/unit/test_*.py`（見分類 C）屬同批工作 | 保留 |
| `TODO.md` | 661 行 | 近乎重寫，記錄 v2.4.0 進度與新 roadmap | 保留 |
| `DEVELOPMENT_LOG.md` | 296 行 | 開發日誌更新 | 保留 |
| `README.md` | 52 行 | 說明文件更新 | 保留 |
| `app/data/manager.py` | 179 行 | 資料管理器邏輯調整 | 保留，Task 3 判定範圍 |
| `app/data/sources/mops_source.py` | 36 行 | MOPS 來源邏輯調整（注意：此檔本身仍存在，代表 MOPS 路徑尚未廢棄） | 保留，Task 3.3 判定時的重要輸入 |
| `app/backtest.py` / `app/dcf_calculator.py` / `app/stock_analyzer.py` / `app/report_generator.py` | 12–25 行 | 小幅調整（多為型別標註/docstring 補齊，符合 Clean AI 品質規範） | 保留 |
| `app/views/{__init__,backtest,comprehensive_report,dcf_valuation,risk_analysis}.py` | 2–16 行 | 小幅調整 | 保留 |
| `app/data/{cache/sqlite_cache,sources/finmind_source,sources/yfinance_source,validator}.py` | 2–4 行 | 極小幅調整 | 保留 |
| `pytest.ini` | 2 行 | 設定微調 | 保留 |
| `requirements.txt` | 5 行 | 加註「DEPRECATED，改用 pyproject.toml + uv」+ 補 2 個既有遺漏依賴（APScheduler、Sphinx） | 保留（此檔本身已自我標記棄用，Phase 2 統一 ENV 時應正式移除，改以 `pyproject.toml` 為準） |
| `.gitignore` | 5 行實質新增 | 加了 `.test_logs/`、`.test_logs_create/`、`docs/_build/` | 保留，但 **Task 1.2 執行前需再補幾條**（見分類 D、E） |
| `artifacts/plan_p2_10_fundamental_scoring_20260501.md` | 刪除 76 行 | 舊版功能規劃文件，內容已完成並體現在 `market_scanner.py` 的評分邏輯 | 接受刪除（歸檔性質，非資料遺失） |
| `coverage.xml` | 刪除 3513 行 | 測試覆蓋率報告，本不該進版控 | 見分類 D |
| `reports/test_report.html` | 39 行變更 | pytest-html 產生的測試報告 | 見分類 D |
| `MY_STOCK/*.csv` ×3（刪除） | 各 219–222 行 | 使用者個人證券未實現餘絀匯出檔（11/04、11/05、11/12 三個舊日期） | 見分類 E |

---

## 分類 C：未追蹤新增（`??`，~140 項）

比對先前已讀過的 `.kiro/specs/stock-valuation-optimization/tasks.md`（57 任務）與 `tasks.meta.json`（含真實 `pbtResults` 與 `executionHistory` 時間戳），這批新增檔案就是該 spec 的完整交付物，非隨意產出：

- **架構核心**：`app/__init__.py`、`app/container.py`、`app/core/`、`app/infra/`、`app/services/`
- **新頁面**：`app/views/growth_optimizer.py`（對應先前讀過的 growth-optimizer-fix bugfix spec）
- **測試**：`tests/__init__.py`、`tests/fixtures/`、`tests/integration/`、`tests/property/`、`tests/unit/__init__.py`、共 17 個新 `test_*.py`（container、circuit_breaker、rate_limiter、memory_cache、sqlite_cache、data_pipeline、error_handler、logging、models、detect_market、us_stock_support、llm_analyzer、trade_engine、market_scanner_service、technical_indicators、pagination、excel_export、update_scheduler、growth_optimizer 系列）
- **專案設定**：`pyproject.toml`、`uv.lock`、`.pre-commit-config.yaml`、`.github/`
- **規格本身**：`.kiro/`（含我們已讀過並在上一輪引用為範本的三份 spec 文件）
- **文件**：`CONTEXT.md`、`docs/FinMind_Backup_Evaluation_20260706.md`、`docs/Makefile`、`docs/environment-issues.md`、`docs/make.bat`、`docs/source/`（Sphinx）
- **腳本與小工具**：`scripts/`（含行數檢查腳本等）、`check_2330.py`、`fix_and_update.py`、`fix_prices.py`、`list_finlab_tables.py`、`scan_dcf.py`、`test_finlab_{catalog,diagnostic,paths}.py`、`run-mobile-tunnel.ps1`

**建議**：整批視為 Task 1.2 的合法提交內容，這是已測試、有執行紀錄佐證的既定工作，不是實驗性殘留。

---

## 分類 D：不該進版控的建置產物 / 高風險未追蹤檔（需先處理再提交）

| 項目 | 狀態 | 風險 | 建議動作 |
|:---|:---|:---|:---|
| `coverage.xml` | 已追蹤，工作目錄刪除 | 低（本就不該追蹤） | `git rm --cached coverage.xml`，加入 `.gitignore` |
| `reports/test_report.html` | 已追蹤，工作目錄修改 | 低 | `git rm --cached reports/test_report.html`，`reports/` 加入 `.gitignore` |
| `cloudflared.exe` | **未追蹤，且未被 .gitignore 排除** | **高**：65,846,200 bytes（約 63MB）二進位檔，若被 `git add .` 一併加入會讓 repo 永久膨脹（git 歷史無法輕易瘦身） | **Task 1.2 執行前必須**先在 `.gitignore` 加入 `cloudflared.exe`（或 `*.exe`），確認 `git status` 不再顯示它，才可執行任何 `git add` |

---

## 分類 E：個人資料（不建議逐檔進版控）

`MY_STOCK/` 目錄下是使用者個人證券交易匯出檔（檔名含日期戳，如 `20251104113055.csv`），本次還多了一個新的未追蹤檔 `20260812142620.csv`。這類檔案每次匯出檔名都不同，逐檔追蹤只會讓 git 歷史一直堆積過期個人資料。

**建議**：`.gitignore` 加入 `MY_STOCK/`，並對已追蹤的 3 個舊 CSV 執行 `git rm --cached`（保留工作目錄檔案本身，只是不再進版控）。此建議涉及刪除版控歷史中的個人資料路徑，依 `agent-sandbox-guardrails` 屬於需要使用者確認的操作，已在下方彙整的執行計畫中列出，尚未執行。

---

## Task 1.3：JoJoTrading-main 的 git 邊界

```
$ cd JoJoTrading-main && git rev-parse --show-toplevel
/sessions/.../CLINE_PROJECT          ← 不是 JoJoTrading-main 自己
$ ls JoJoTrading-main/.git
No such file or directory            ← 沒有獨立 .git
```

**判定**：JoJoTrading-main **沒有獨立的 git 倉庫**，它是被最上層 `CLINE_PROJECT` monorepo 追蹤的一般子目錄（此前在裡面跑 `git status` 會冒出一堆 `.agents/skills/...` 等無關變更，即為此故）。stock-valuation-tool 則確認有自己獨立的 `.git`（`git rev-parse --show-toplevel` 回報自身路徑）。

**對後續搬遷（tasks.md Task 10.1）的影響**：
- JoJoTrading-main → `apps/jojo/` 的搬遷，其 git 歷史本來就在 monorepo 裡，用一般 `git mv`（在 monorepo 層級執行）即可保留歷史，不需要額外的 repo 合併或 `git filter-repo` 操作。
- stock-valuation-tool 是獨立 repo，若整個 Finance 平台未來也要收斂進單一 monorepo 路徑下（例如 `apps/valuation/`），則需要決定是否保留其獨立 git 歷史（用 `git subtree`/`git filter-repo` 合併）或直接視為新起點——**此決策不在本次盤點範圍內，留待 Task 10.3 執行前另行確認**。

---

## 待使用者確認後才執行的動作（不在 Task 1.1 範圍內，屬 Task 1.2）

以下操作依 `agent-sandbox-guardrails` 技能的 Plan Approval Gate（跨 3 檔以上、影響版控基線），需先取得批准：

1. 建立 `.gitattributes`（`* text=auto eol=lf`），標準化分類 A 的 42 個檔案換行符。
2. 更新 `.gitignore`：加入 `cloudflared.exe`、`coverage.xml`（若尚未涵蓋 `*.xml` 需明確列出）、`reports/*.html`、`MY_STOCK/`。
3. `git rm --cached` 移除 `coverage.xml`、`reports/test_report.html`、`MY_STOCK/*.csv`（3 舊檔）的版控追蹤（保留工作目錄檔案）。
4. 分批 commit：(a) 換行符標準化、(b) `.gitignore`/建置產物清理、(c) 分類 B 的既定功能變更、(d) 分類 C 的 Kiro spec v3.0 新架構整批提交。
5. 建立 baseline tag（`pre-finance-integration-baseline`）。

本文件本身即為 Task 1.1 的產出，尚未執行任何寫入版控的操作。
