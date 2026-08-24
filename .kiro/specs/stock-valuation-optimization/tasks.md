# Implementation Plan: Stock Valuation Optimization

## Overview

將台股估值工具從原型級提升至生產級品質。實作順序：基礎設施（模型、錯誤、DI）→ 韌性元件 → 服務層 → 新功能 → 測試與品質自動化。所有程式碼以 Python 撰寫，使用 Pydantic v2、pytest、Hypothesis。

## Tasks

- [x] 1. 專案結構重組與基礎設施建立
  - [x] 1.1 建立目標目錄結構與 pyproject.toml
    - 建立 `app/core/models/`、`app/core/`、`app/services/filters/`、`app/infra/sources/`、`app/infra/resilience/`、`app/infra/cache/`、`app/views/`、`tests/unit/`、`tests/property/`、`tests/integration/`、`tests/fixtures/` 目錄
    - 建立 `pyproject.toml` 定義專案元資料、Python >=3.10、依賴清單（pydantic、hypothesis、pytest、pytest-cov、pytest-mock、ruff、mypy、pydocstyle）、開發依賴、ruff 規則集（E, F, I, N, W, UP, B, SIM）
    - 消除巢狀 `app/app/` 目錄，遷移模組至單一 `app/` 層級
    - _Requirements: 1.5, 20.4, 20.5_

  - [x] 1.2 定義自訂例外類別階層 (`app/core/errors.py`)
    - 實作 `StockToolError`（base）、`DataSourceError`、`ValidationError`、`TimeoutError`、`RateLimitError`、`CircuitOpenError`
    - 每個例外包含 `stock_code`、對應來源名稱等上下文欄位
    - 加入型別標註與 Google-style docstring
    - _Requirements: 2.1, 2.3_

  - [x] 1.3 定義 Protocol 介面 (`app/core/protocols.py`)
    - 實作 `DataSourceProtocol`、`CacheProtocol`、`CircuitBreakerProtocol`、`LLMBackendProtocol`、`BrokerAdapterProtocol`
    - 所有介面使用 `typing.Protocol`，包含完整型別標註與 docstring
    - _Requirements: 1.3, 13.5_

  - [x] 1.4 實作 Pydantic 核心資料模型 (`app/core/models/`)
    - `stock.py`：`StockInfo`、`PriceData`（含 `Market` enum、`field_validator`、`model_validator`）
    - `financial.py`：`FinancialData`、`DCFResult`（含 `normalize_percentage` validator、`Field()` 約束）
    - `scan.py`：`ScanResult`、`MarketSnapshot`（含百分比歸一化）
    - `trade.py`：`TradeSignal`、`SignalType` enum（含價格範圍驗證）
    - 所有模型提供 `.to_json()`、`.from_json()`、`.to_dataframe()`、`.from_dataframe()` 方法
    - _Requirements: 8.1, 8.3, 8.4, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

  - [x]* 1.5 撰寫 Pydantic 模型往返屬性測試 (`tests/property/test_pydantic_roundtrip.py`)
    - **Property 1: Pydantic 模型 JSON 往返特性**
    - 使用 Hypothesis 為 6 個核心模型產生任意有效實例，驗證 `Model.from_json(instance.to_json())` 產生等價物件
    - **Validates: Requirements 14.5, 14.6, 18.2**

  - [x]* 1.6 撰寫資料驗證拒絕屬性測試 (`tests/property/test_validation.py`)
    - **Property 12: 資料驗證拒絕不合理數值**
    - 驗證超出範圍的 PE ratio、ROE、股價 ≤ 0 被 Pydantic 拒絕
    - **Property 13: 單位歸一化冪等性**
    - 驗證 `normalize_percentage` 處理後再次處理產生相同結果
    - **Validates: Requirements 8.3, 8.4, 18.2**

  - [x] 1.7 實作 DI Container (`app/container.py`)
    - 實作 `Container` 類別：`register(interface, factory, lifetime)`、`resolve(interface)`、`override(interface, instance)`
    - 支援 `Lifetime.SINGLETON` 與 `Lifetime.TRANSIENT`
    - 建立 `setup_container()` 工廠函式完成所有服務註冊
    - _Requirements: 1.1, 1.2, 1.4_

  - [-]* 1.8 撰寫 DI Container 屬性測試 (`tests/property/test_di_container.py`)
    - **Property 14: DI Container 生命週期正確性**
    - 驗證 singleton 多次 resolve 回傳相同物件、transient 回傳不同物件
    - **Validates: Requirements 1.1, 1.4**

- [x] 2. Checkpoint - 確認基礎設施
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 結構化日誌與錯誤處理基礎設施

  - [x] 3.1 實作結構化日誌系統 (`app/infra/logging.py`)
    - 實作 `StructuredFormatter`（JSON 格式：timestamp、level、module、function、message、stock_code、source）
    - 配置 `RotatingFileHandler`（10MB/檔、保留 5 個歷史檔）
    - 支援環境切換（開發 DEBUG + console、生產 INFO + file only）
    - 提供 `get_logger(module_name)` 工廠函式
    - _Requirements: 2.2, 2.5_

  - [x] 3.2 實作統一錯誤處理器 (`app/infra/error_handler.py`)
    - 實作 `ErrorHandler` 類別：根據錯誤類型分流處理（DataSourceError → fallback、ValidationError → cached data、TimeoutError → circuit breaker 記錄、RateLimitError → backoff）
    - 記錄完整例外堆疊追蹤至日誌
    - 向使用者顯示友善錯誤訊息（取代裸露 except）
    - Market Scanner 個別股票錯誤不中斷整體流程，記錄後繼續
    - _Requirements: 2.1, 2.3, 2.4_

- [x] 4. 韌性元件（Circuit Breaker + Rate Limiter + Batch Downloader）

  - [x] 4.1 實作 Circuit Breaker (`app/infra/resilience/circuit_breaker.py`)
    - 狀態機：closed → open（60s 內 5 次失敗）→ half-open（5 分鐘後）→ closed（探測成功）
    - 滑動時間視窗（deque + timestamp）追蹤失敗次數
    - 每個外部資料來源獨立實例
    - 接受可注入 `time_func` 參數以利測試
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x]* 4.2 撰寫 Circuit Breaker 屬性測試 (`tests/property/test_circuit_breaker.py`)
    - **Property 9: 斷路器狀態轉換正確性**
    - 驗證 60s 內 N<5 失敗維持 closed；N≥5 轉 open；各來源失敗計數獨立
    - **Validates: Requirements 9.1, 9.2**

  - [x] 4.3 實作 Rate Limiter (`app/infra/resilience/rate_limiter.py`)
    - Token Bucket 演算法：max_tokens、refill_rate、acquire、wait_and_acquire
    - FinMind 專用邏輯：請求前呼叫 `user_info` 確認配額、配額 < 120% → 降速至 1 req/s
    - HTTP 402 處理：記錄事件 + 觸發 Circuit Breaker + 切換備援
    - 指數退避重試：1s → 2s → 4s（最大 60s，最多 3 次）
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [-]* 4.4 撰寫指數退避屬性測試 (`tests/property/test_retry_backoff.py`)
    - **Property 18: 指數退避重試間隔正確性**
    - 驗證第 N 次重試等待 min(2^(N-1), 60) 秒，最多 3 次
    - **Validates: Requirements 7.4**

  - [x] 4.5 實作 Batch Downloader (`app/infra/resilience/batch_downloader.py`)
    - 分批策略：每批 50 檔、批次間等待 1 秒
    - ThreadPoolExecutor（max_workers=5）並行下載
    - 逾時拆分：單批超過 30 秒 → 拆為兩個子批次重試
    - 連續 3 批失敗 → 中止並回傳部分資料
    - 進度回呼（已完成/總批次數）
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [-]* 4.6 撰寫 Batch Downloader 屬性測試 (`tests/property/test_batch_downloader.py`)
    - **Property 10: 批次分割正確性**
    - 驗證批次總數 = ceil(N/50)、每批 ≤ 50、聯集 = 原始清單
    - **Property 11: 並行度上限不變式**
    - 驗證活躍請求數永不超過 5
    - **Validates: Requirements 3.1, 6.1, 6.3, 6.4**

- [x] 5. Checkpoint - 確認韌性元件
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 快取層實作

  - [x] 6.1 實作 LRU Memory Cache (`app/infra/cache/memory_cache.py`)
    - 使用 `OrderedDict` 實作 LRU，容量上限 200 筆
    - Per-type TTL（股價 5min、財報 1hr、公司資訊 24hr、籌碼 4hr）
    - 取值回傳淺複製（`copy.copy()`）防止外部修改汙染
    - `invalidate_by_stock(stock_code)` 清除特定股票所有條目
    - `stats()` 回傳 hit_count、miss_count、eviction_count
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [-]* 6.2 撰寫 LRU Cache 屬性測試 (`tests/property/test_cache_properties.py`)
    - **Property 6: LRU 快取容量上限不變式**
    - 驗證任意 get/set/delete 操作序列後條目數 ≤ 200，外部修改不影響快取
    - **Property 7: 快取 TTL 過期正確性**
    - 驗證 TTL 內存取回傳有效資料、超過 TTL 回傳 None
    - **Property 8: 快取統計一致性**
    - 驗證 hit_count + miss_count = 總查詢次數
    - **Validates: Requirements 5.1, 5.3, 5.5, 10.5**

  - [x] 6.3 實作 SQLite Cache (`app/infra/cache/sqlite_cache.py`)
    - 複合索引：`stock_code`、`last_updated`、`pe_ratio`、`roe`、`dividend_yield`
    - 參數化查詢（非 Python 層面逐列過濾）
    - 寫入後執行 `ANALYZE` 更新查詢計畫統計
    - 30 天未更新記錄標記過期 + 查詢結果附警告
    - 向下相容（既有 SQLite 檔直接可用）
    - 啟用 WAL 模式、連線池
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 6.5_

- [x] 7. 資料來源與管線

  - [x] 7.1 實作資料來源基礎類別與 Yahoo Finance 來源 (`app/infra/sources/base.py`, `app/infra/sources/yfinance_source.py`)
    - `base.py`：實作 `DataSourceProtocol` 的共用邏輯（錯誤包裝、日誌）
    - `yfinance_source.py`：Yahoo Finance 資料來源，支援台股（`.TW`/`.TWO`）與美股
    - 整合 Circuit Breaker 保護
    - _Requirements: 3.1, 9.3, 11.2_

  - [x] 7.2 實作 FinMind 與 FinLab 資料來源 (`app/infra/sources/finmind_source.py`, `app/infra/sources/finlab_source.py`)
    - FinMind：整合 Rate Limiter + Circuit Breaker、HTTP 402 → 自動切換備援
    - FinLab：整合 Circuit Breaker 保護
    - 兩者皆實作 `DataSourceProtocol`
    - _Requirements: 7.1, 7.5, 9.1_

  - [x] 7.3 實作資料管線協調器 (`app/infra/data_pipeline.py`)
    - 統一資料存取入口：依優先順序嘗試來源（FinLab → Yahoo Finance → FinMind）
    - 並行擷取：ThreadPoolExecutor（max 5 workers）、個別逾時 15 秒
    - 部分失敗：回傳成功結果 + 記錄失敗股票代碼
    - 佇列排程：超過 5 支同時請求時排隊
    - 整合 Pydantic 驗證：API 回應經 schema 驗證 → range check → unit normalization
    - 驗證失敗但有快取 → 回傳快取 + 警告
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 7.4 實作美股代碼辨識邏輯 (`detect_market` in `app/core/models/stock.py`)
    - 純英文 1-5 字元 → Market.US
    - 純數字 4-6 位 → Market.TW 或 Market.TWO（≥6000 為上櫃）
    - 帶後綴格式支援（.TW、.TWO）
    - _Requirements: 11.1_

  - [-]* 7.5 撰寫美股代碼辨識屬性測試 (`tests/property/test_market_detection.py`)
    - **Property 15: 美股代碼辨識正確性**
    - 驗證 1-5 英文字母 → Market.US、4-6 位數字 → Market.TW/TWO
    - **Validates: Requirements 11.1, 11.2**

- [x] 8. Checkpoint - 確認資料層
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 服務層 — DCF Calculator 與 Market Scanner

  - [x] 9.1 重構 DCF Calculator (`app/services/dcf_calculator.py`)
    - 依賴注入：透過 Protocol 取得 DataManager，不直接實例化
    - 美股模式：使用美國市場預設參數（無風險利率 4.5%、風險溢酬 5%、通膨率 2.5%、永續成長率 2.5%）
    - 輸出 `DCFResult` Pydantic 模型
    - 型別標註 + Google-style docstring
    - _Requirements: 1.3, 11.3, 15.1, 15.2_

  - [x]* 9.2 撰寫 DCF Calculator 屬性測試 (`tests/property/test_dcf_invariants.py`)
    - **Property 2: DCF 內在價值有限正數不變式**
    - 任意正數 EPS（0.01~10000）與合理成長率（-50%~+50%），折現率 > 永續成長率 → 內在價值為有限正數
    - **Property 5: 常數 EPS 成長率零值不變式**
    - 常數 EPS 值 c > 0 重複 N 次（N≥2）→ 成長率為 0（±0.001）
    - **Validates: Requirements 18.1, 18.5**

  - [x] 9.3 重構 Market Scanner (`app/services/market_scanner.py`)
    - 依賴注入：透過 DI Container 取得 Batch Downloader、Data Pipeline
    - 整合增量更新模式：僅下載超過 4 小時未更新的股票
    - 個別股票錯誤記錄後繼續處理（不中斷）
    - 拆分篩選邏輯至 `app/services/filters/`
    - 輸出 `ScanResult` Pydantic 模型
    - _Requirements: 2.4, 3.5, 16.2_

  - [-]* 9.4 撰寫增量更新屬性測試 (`tests/property/test_incremental_update.py`)
    - **Property 17: 增量更新正確性**
    - 超過 4 小時的子集恰好被重新下載、4 小時內的被跳過
    - **Validates: Requirements 3.5**

  - [x] 9.5 實作篩選引擎 (`app/services/filters/fundamental.py`, `technical.py`, `chip.py`)
    - `fundamental.py`：本益比、ROE、殖利率、市值篩選
    - `technical.py`：價格位階、技術指標篩選
    - `chip.py`：外資/投信連續買超天數、三大法人合計買超量篩選
    - 篩選器為冪等操作（同條件套用兩次結果不變）
    - _Requirements: 10.2, 16.2, 18.3_

  - [x]* 9.6 撰寫篩選器屬性測試 (`tests/property/test_filter_properties.py`)
    - **Property 3: 篩選器冪等性**
    - 同一資料集套用相同條件兩次 = 一次
    - **Property 4: 篩選器資料縮減性**
    - 篩選後筆數 ≤ 篩選前筆數
    - **Validates: Requirements 18.3, 18.4**

- [x] 10. Checkpoint - 確認核心服務
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. 新功能模組

  - [x] 11.1 實作 Chip Analyzer (`app/services/chip_analyzer.py`)
    - 從 FinMind API 取得外資、投信、自營商每日買賣超張數
    - 計算衍生指標：連續買超天數、持股比例變化（5/20/60 日）
    - 建立 `chip_data` SQLite 資料表（含 schema 與索引）
    - 快取有效期 4 小時
    - 資料取得失敗時標示「籌碼資料不可用」而非隱藏
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 11.2 實作 LLM Analyzer (`app/services/llm_analyzer.py`)
    - 整合資料輸入：四季財報、DCF 結果、60 日價格走勢、法人籌碼變化
    - 結構化報告輸出：投資摘要（≤100 字）、財務體質評分（1-10）、風險因子列表、建議操作
    - 可抽換 LLM 後端（透過 `LLMBackendProtocol` DI 注入）
    - 降級策略：逾時 30 秒或 API 失敗 → rule-based 基礎分析
    - 標明資料來源與計算日期
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x] 11.3 實作 Trade Signal Engine (`app/services/trade_engine.py`)
    - `TradeSignal` 產生條件：DCF 低估 >30% AND 法人連續買超 >3 日 → 買入
    - 訊號佇列：持久化至 SQLite `trade_signals` 資料表（含 status: pending/consumed/expired）
    - Paper Trading 模式：記錄虛擬交易至 `paper_trades` 表、追蹤報酬率
    - `BrokerAdapterProtocol` 抽象介面（query_balance、place_order、cancel_order）
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [-]* 11.4 撰寫訊號佇列往返屬性測試 (`tests/property/test_signal_queue.py`)
    - **Property 16: 交易訊號佇列往返特性**
    - 驗證 TradeSignal 寫入 SQLite 後讀取回來欄位值相等
    - **Validates: Requirements 13.3**

  - [x] 11.5 實作美股支援整合
    - DCF Calculator 偵測市場別自動切換參數（台股 vs 美股預設值）
    - UI 標示台股/美股、TWD/USD 幣別
    - 美股資料取得失敗時顯示專屬錯誤訊息
    - _Requirements: 11.2, 11.3, 11.4, 11.5_

- [x] 12. Checkpoint - 確認新功能模組
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. DI Container 組裝與 Streamlit 入口整合

  - [x] 13.1 組裝 DI Container (`app/container.py` 完善)
    - 在 `setup_container()` 中註冊所有服務：DataPipeline、MemoryCache、SQLiteCache、CircuitBreaker×3、RateLimiter、BatchDownloader、DCFCalculator、MarketScanner、ChipAnalyzer、LLMAnalyzer、TradeEngine
    - 依據環境變數或設定檔切換 LLM 後端
    - _Requirements: 1.2_

  - [x] 13.2 整合 Streamlit 入口 (`app/main.py`)
    - 啟動時建立 DI Container、初始化日誌
    - 所有頁面透過 Container 取得服務實例
    - 取代現有直接實例化的模式
    - _Requirements: 1.2, 1.3_

- [ ] 14. 單元測試與涵蓋率

  - [-]* 14.1 撰寫 DCF Calculator 單元測試 (`tests/unit/test_dcf_calculator.py`)
    - ≥15 個測試案例：正常估值、邊界成長率、美股參數、零 EPS 處理、極端折現率
    - 使用 mock 替代 DataManager 依賴
    - _Requirements: 17.1, 17.3_

  - [-]* 14.2 撰寫 DataManager / Data Pipeline 單元測試 (`tests/unit/test_data_pipeline.py`)
    - ≥15 個測試案例：備援流程、快取命中/未命中、驗證失敗降級、並行擷取
    - 使用 mock 替代外部 API
    - _Requirements: 17.1, 17.3_

  - [-]* 14.3 撰寫 Market Scanner 單元測試 (`tests/unit/test_market_scanner.py`)
    - ≥15 個測試案例：篩選組合、評分邏輯、增量更新、個別股票錯誤處理
    - _Requirements: 17.1, 17.3_

  - [ ]* 14.4 撰寫 Pydantic 模型驗證單元測試 (`tests/unit/test_models.py`)
    - 有效輸入、邊界值、無效輸入三種情境
    - 覆蓋 6 個核心模型的所有 validator
    - _Requirements: 17.4_

- [ ] 15. 整合測試

  - [ ]* 15.1 撰寫 DataManager 備援流程整合測試 (`tests/integration/test_data_pipeline_integration.py`)
    - 主要來源失敗 → 自動切換備援 → 正確回傳資料
    - 使用預錄 fixture（`tests/fixtures/`）
    - 獨立測試資料庫 `test_market_scan.db`
    - _Requirements: 19.1, 19.3, 19.5_

  - [ ]* 15.2 撰寫 Market Scanner 完整掃描整合測試 (`tests/integration/test_scanner_integration.py`)
    - FinLab → Yahoo Finance patch → SQLite write → query 完整流程
    - 離線執行（預錄 API 回應 fixture）
    - _Requirements: 19.2, 19.5_

  - [ ]* 15.3 撰寫 Circuit Breaker 生命週期整合測試 (`tests/integration/test_circuit_breaker_integration.py`)
    - 模擬連續失敗觸發開啟、等待後恢復的完整生命週期
    - _Requirements: 19.4_

- [x] 16. Checkpoint - 確認測試涵蓋率
  - Ensure all tests pass, ask the user if questions arise.
  - 執行 `pytest --cov` 確認涵蓋率 ≥ 80%（排除 views/）

- [x] 17. 型別標註、文件字串與程式碼品質

  - [x] 17.1 為所有公開方法新增型別標註與 Google-style docstring
    - 完整型別標註（含 `Optional`、`Union`、`List`、`Dict` 泛型）
    - Google-style docstring（`Args`、`Returns`、`Raises`）
    - 私有方法超過 10 行者至少包含 `Args` 與 `Returns`
    - _Requirements: 15.1, 15.2, 15.3_

  - [x] 17.2 檔案行數限制檢查與模組拆分
    - 確保所有 Python 檔不超過 800 行（不含空白行與純註解行）
    - 超過者拆分為子模組，透過 `__init__.py` 重新匯出
    - 確認零循環匯入
    - _Requirements: 16.1, 16.2, 16.3, 16.5_

  - [x] 17.3 設定程式碼品質自動化工具
    - `pyproject.toml`：ruff 規則集（E, F, I, N, W, UP, B, SIM）、mypy strict、pydocstyle Google convention
    - `.pre-commit-config.yaml`：ruff check → ruff format → mypy → pytest 快速子集（30s 上限）
    - 行數檢查腳本 `scripts/check_line_count.py`（800 行警告、1000 行錯誤）
    - 從 `requirements.txt` 遷移至 `pyproject.toml` + `uv`
    - _Requirements: 15.4, 15.5, 16.4, 17.5, 20.1, 20.2, 20.3, 20.4, 20.5_

- [x] 18. Final checkpoint - 全面驗證
  - Ensure all tests pass, ask the user if questions arise.
  - 執行 `ruff check` 確認零違規
  - 執行 `mypy --strict` 確認零錯誤
  - 確認 `pytest --cov` 涵蓋率 ≥ 80%

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (18 properties mapped to 12 test files)
- Unit tests validate specific examples and edge cases
- All external API calls are mocked in tests; integration tests use offline fixtures
- Implementation language: Python（Pydantic v2, pytest, Hypothesis, ruff, mypy, uv）
- 檔案行數嚴格遵守 800 行預警 / 1000 行硬限制

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "1.7"] },
    { "id": 2, "tasks": ["1.5", "1.6", "1.8", "3.1"] },
    { "id": 3, "tasks": ["3.2", "4.1", "4.3"] },
    { "id": 4, "tasks": ["4.2", "4.4", "4.5", "6.1"] },
    { "id": 5, "tasks": ["4.6", "6.2", "6.3"] },
    { "id": 6, "tasks": ["7.1", "7.2", "7.4"] },
    { "id": 7, "tasks": ["7.3", "7.5"] },
    { "id": 8, "tasks": ["9.1", "9.3"] },
    { "id": 9, "tasks": ["9.2", "9.4", "9.5"] },
    { "id": 10, "tasks": ["9.6", "11.1", "11.2", "11.3"] },
    { "id": 11, "tasks": ["11.4", "11.5", "13.1"] },
    { "id": 12, "tasks": ["13.2"] },
    { "id": 13, "tasks": ["14.1", "14.2", "14.3", "14.4"] },
    { "id": 14, "tasks": ["15.1", "15.2", "15.3"] },
    { "id": 15, "tasks": ["17.1", "17.2"] },
    { "id": 16, "tasks": ["17.3"] }
  ]
}
```
