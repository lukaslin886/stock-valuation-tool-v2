# Requirements Document

## 簡介

本文件定義台股估值工具（Stock Valuation Tool v2.4.0）的全面性最佳化需求，涵蓋五大領域：架構重構、效能最佳化、資料管線韌性、新功能開發、以及測試與品質改善。目標是將現有 Streamlit 應用從原型級提升至生產級品質，同時維持向下相容性。

## 詞彙表

- **System（系統）**: 台股估值工具整體應用程式
- **Data_Pipeline（資料管線）**: 負責從外部 API 取得、驗證、轉換並快取股票資料的子系統
- **Market_Scanner（市場掃描器）**: 批次掃描市場全景並產出快照的模組（`market_scanner.py`）
- **DataManager（資料管理器）**: 統一資料存取層，提供智能備援與快取（`data/manager.py`）
- **DCF_Calculator（DCF 計算器）**: 現金流量折現估值引擎（`dcf_calculator.py`）
- **DI_Container（依賴注入容器）**: 集中管理物件生命週期與依賴關係的元件
- **Circuit_Breaker（斷路器）**: 偵測外部服務連續失敗並暫時中斷請求的保護機制
- **Pydantic_Model（Pydantic 模型）**: 使用 Pydantic 定義的資料結構，提供型別驗證與序列化
- **Rate_Limiter（速率限制器）**: 控制對外部 API 請求頻率的元件
- **LLM_Analyzer（LLM 分析器）**: 使用大型語言模型產出股票分析報告的模組
- **Chip_Analyzer（籌碼分析器）**: 分析法人買賣超與持股變化的模組
- **Error_Handler（錯誤處理器）**: 統一捕獲、分類與回報錯誤的全域元件
- **Logger（日誌記錄器）**: 結構化日誌記錄框架，取代 `print()` 語句
- **Batch_Downloader（批次下載器）**: 分批下載大量股票資料的元件，具備逾時保護
- **Cache_Layer（快取層）**: 包含記憶體快取與 SQLite 持久化快取的分層快取系統

---

## 需求

### 需求 1：依賴注入與模組解耦

**User Story:** 身為開發者，我希望系統採用依賴注入模式，以便各模組可獨立測試與替換。

#### 驗收準則

1. THE DI_Container SHALL 提供集中式物件註冊與解析介面，支援 singleton 與 transient 兩種生命週期
2. WHEN 應用程式啟動時，THE DI_Container SHALL 依據設定檔完成所有服務的註冊，且所有模組透過介面取得依賴而非直接實例化
3. THE System SHALL 定義抽象介面（Protocol 或 ABC）供 DataManager、Market_Scanner、DCF_Calculator 實作，使各模組僅依賴抽象而非具體類別
4. WHEN 單元測試執行時，THE DI_Container SHALL 支援以 mock 物件替換任何已註冊的服務
5. THE System SHALL 消除巢狀 `app/app/` 目錄結構，將所有模組置於單一 `app/` 層級之下

---

### 需求 2：統一錯誤處理與日誌記錄

**User Story:** 身為維運人員，我希望系統有統一的錯誤處理與結構化日誌，以便快速定位問題。

#### 驗收準則

1. THE Error_Handler SHALL 取代所有裸露的 `except:` 與 `except Exception:` 區塊，並依錯誤類型分類為 `DataSourceError`、`ValidationError`、`TimeoutError`、`RateLimitError`
2. THE Logger SHALL 使用 Python `logging` 模組搭配結構化格式（包含時間戳記、模組名、嚴重等級、股票代碼欄位），取代所有 `print()` 語句
3. WHEN 錯誤發生時，THE Error_Handler SHALL 記錄完整的例外堆疊追蹤至日誌檔，並向使用者顯示友善的錯誤訊息
4. IF Market_Scanner 處理個別股票時發生錯誤，THEN THE Error_Handler SHALL 記錄該股票代碼與錯誤細節，並繼續處理下一支股票而非靜默忽略
5. THE Logger SHALL 支援依環境切換日誌等級（開發環境 DEBUG、生產環境 INFO），且日誌輸出支援檔案輪替（每檔上限 10MB、保留 5 個歷史檔）

---

### 需求 3：Yahoo Finance 批次下載最佳化

**User Story:** 身為使用者，我希望市場掃描不會因大量股票同時下載而逾時失敗。

#### 驗收準則

1. THE Batch_Downloader SHALL 將股票清單分批處理，每批次上限 50 檔，批次間等待 1 秒
2. WHEN 單一批次下載逾時（超過 30 秒），THE Batch_Downloader SHALL 將該批次拆為兩個子批次並分別重試
3. THE Batch_Downloader SHALL 透過回呼函式回報目前進度（已完成批次數/總批次數）
4. IF 連續 3 個批次全部失敗，THEN THE Batch_Downloader SHALL 中止下載並回傳已成功取得的部分資料
5. THE Market_Scanner SHALL 支援增量更新模式，僅下載自上次更新後超過 4 小時的股票資料

---

### 需求 4：SQLite 索引與查詢最佳化

**User Story:** 身為使用者，我希望篩選器查詢回應時間在大量資料下仍保持快速。

#### 驗收準則

1. THE Cache_Layer SHALL 為 `market_snapshot` 資料表建立複合索引，涵蓋 `stock_code`、`last_updated`、`pe_ratio`、`roe`、`dividend_yield` 欄位
2. WHEN 篩選條件包含多個欄位時，THE Cache_Layer SHALL 使用參數化查詢而非在 Python 層面逐列過濾
3. THE Cache_Layer SHALL 於資料寫入後執行 `ANALYZE` 指令以更新查詢計畫統計資訊
4. WHEN 快取資料超過 30 天未更新，THE Cache_Layer SHALL 標記該記錄為過期並在查詢結果中標示警告
5. THE Cache_Layer SHALL 維持向下相容性，既有 SQLite 資料庫檔案可直接被新版系統讀取而無需遷移

---

### 需求 5：記憶體快取層強化

**User Story:** 身為使用者，我希望重複存取相同股票資料時無需等待 API 呼叫。

#### 驗收準則

1. THE Cache_Layer SHALL 實作 LRU（Least Recently Used）快取策略，容量上限 200 筆，且支援依資料類型設定不同的存活時間（股價 5 分鐘、財報 1 小時、公司資訊 24 小時）
2. WHEN 記憶體快取命中時，THE DataManager SHALL 直接回傳快取資料而不存取 SQLite 或外部 API
3. THE Cache_Layer SHALL 提供快取命中率統計介面，回傳命中次數、未命中次數、驅逐次數
4. WHEN 使用者手動觸發資料更新時，THE Cache_Layer SHALL 清除該股票代碼相關的所有快取條目
5. THE Cache_Layer SHALL 為快取物件實作淺複製，避免外部修改影響快取內容

---

### 需求 6：非同步並行資料擷取

**User Story:** 身為使用者，我希望多支股票的資料擷取能並行執行以縮短等待時間。

#### 驗收準則

1. THE Data_Pipeline SHALL 支援以 `asyncio` 或 `concurrent.futures.ThreadPoolExecutor` 並行擷取多支股票資料，並行度上限為 5 個同時請求
2. WHEN 同時請求超過 5 支股票時，THE Data_Pipeline SHALL 以佇列方式排程，確保不超過並行度上限
3. THE Data_Pipeline SHALL 在並行擷取時為每個請求設定獨立的逾時（預設 15 秒），個別逾時不影響其他請求
4. IF 並行請求中有部分失敗，THEN THE Data_Pipeline SHALL 回傳成功的結果並記錄失敗的股票代碼
5. THE Data_Pipeline SHALL 確保並行存取 SQLite 時使用連線池（connection pool）並啟用 WAL 模式以避免寫入鎖定

---

### 需求 7：FinMind 速率限制處理

**User Story:** 身為開發者，我希望系統能優雅處理 FinMind API 的速率限制，避免因超額請求導致服務中斷。

#### 驗收準則

1. WHEN FinMind API 回傳 HTTP 402 狀態碼時，THE Rate_Limiter SHALL 記錄事件並自動切換至備援資料來源（Yahoo Finance）
2. THE Rate_Limiter SHALL 在每次批次請求前呼叫 FinMind `user_info` 端點，確認剩餘配額是否足夠本次請求
3. WHEN 剩餘配額低於預計請求量的 120% 時，THE Rate_Limiter SHALL 降低請求頻率至每秒 1 次並記錄警告
4. THE Rate_Limiter SHALL 實作指數退避重試策略，初始等待 1 秒，最大等待 60 秒，最多重試 3 次
5. IF FinMind 連續 5 次請求失敗，THEN THE Circuit_Breaker SHALL 開啟並在 5 分鐘內不再嘗試 FinMind 來源

---

### 需求 8：資料驗證層

**User Story:** 身為開發者，我希望所有外部 API 回應在進入內部邏輯前都經過結構化驗證。

#### 驗收準則

1. THE Data_Pipeline SHALL 為每種 API 回應定義對應的 Pydantic_Model，包含 `StockPrice`、`FinancialReport`、`CompanyInfo`、`MarketSnapshot` 四種核心模型
2. WHEN API 回應缺少必要欄位時，THE Data_Pipeline SHALL 拒絕該筆資料並記錄詳細的驗證失敗原因
3. THE Data_Pipeline SHALL 對數值欄位執行合理性檢查：本益比介於 -100 至 10000、ROE 介於 -100% 至 200%、股價大於 0
4. THE Data_Pipeline SHALL 統一 ROE 與殖利率的單位表示法：內部一律使用百分比形式（例如 15.0 代表 15%），並在 Pydantic_Model 的 validator 中自動轉換小數形式（0.15）為百分比形式
5. WHEN 資料驗證失敗但存在快取資料時，THE Data_Pipeline SHALL 回傳快取資料並附加警告訊息標示資料可能過時

---

### 需求 9：斷路器模式

**User Story:** 身為使用者，我希望當外部服務異常時，系統能快速回應而非長時間等待。

#### 驗收準則

1. THE Circuit_Breaker SHALL 針對每個外部資料來源（Yahoo Finance、FinMind、FinLab）獨立追蹤失敗次數
2. WHEN 單一資料來源在 60 秒內失敗達 5 次，THE Circuit_Breaker SHALL 進入開啟狀態並立即回傳錯誤而不發送請求
3. WHILE Circuit_Breaker 處於開啟狀態，THE DataManager SHALL 自動略過該來源並使用下一優先順序的備援來源
4. WHEN Circuit_Breaker 開啟超過 5 分鐘後，THE Circuit_Breaker SHALL 進入半開狀態，允許一次試探性請求
5. IF 半開狀態的試探性請求成功，THEN THE Circuit_Breaker SHALL 重置失敗計數器並恢復為關閉狀態

---

### 需求 10：法人籌碼分析篩選

**User Story:** 身為投資人，我希望能依據法人買賣超篩選潛力標的。

#### 驗收準則

1. THE Chip_Analyzer SHALL 從 FinMind API 取得外資、投信、自營商的每日買賣超張數資料
2. WHEN 使用者啟用籌碼篩選時，THE Market_Scanner SHALL 支援以下條件組合：外資連續買超天數、投信連續買超天數、三大法人合計買超張數
3. THE Chip_Analyzer SHALL 計算法人持股比例變化（近 5 日、近 20 日、近 60 日），並以百分比變化量呈現
4. IF 籌碼資料取得失敗，THEN THE Chip_Analyzer SHALL 在篩選結果中標示「籌碼資料不可用」而非隱藏該欄位
5. THE Chip_Analyzer SHALL 將籌碼資料快取至 SQLite，快取有效期為 4 小時

---

### 需求 11：美股支援

**User Story:** 身為投資人，我希望使用相同的估值工具分析美股標的。

#### 驗收準則

1. THE System SHALL 擴充股票代碼辨識邏輯，支援美股 ticker 格式（純英文字母，例如 AAPL、MSFT）
2. WHEN 偵測到美股代碼時，THE DataManager SHALL 使用 Yahoo Finance API 取得美股股價與財報資料，無需加上 `.TW` 或 `.TWO` 後綴
3. THE DCF_Calculator SHALL 於美股模式下使用美國市場預設參數：無風險利率 4.5%、風險溢酬 5%、通膨率 2.5%
4. THE System SHALL 在 UI 上明確標示目前分析標的為台股或美股，並以對應貨幣單位（TWD/USD）顯示結果
5. IF 美股資料取得失敗，THEN THE System SHALL 顯示「美股資料暫時無法取得，請確認網路連線」錯誤訊息

---

### 需求 12：LLM 智慧分析報告

**User Story:** 身為投資人，我希望 AI 能自動閱讀財報新聞並產出結構化分析報告。

#### 驗收準則

1. THE LLM_Analyzer SHALL 接收股票代碼後整合以下資料作為分析輸入：最近四季財報數據、DCF 估值結果、近 60 日價格走勢、法人籌碼變化
2. WHEN 使用者觸發分析報告產生時，THE LLM_Analyzer SHALL 產出結構化報告包含：投資摘要（100 字內）、財務體質評分（1-10）、風險因子列表、建議操作
3. THE LLM_Analyzer SHALL 支援可抽換的 LLM 後端（OpenAI、Anthropic、本地模型），透過 DI_Container 注入
4. IF LLM API 呼叫失敗或逾時（超過 30 秒），THEN THE LLM_Analyzer SHALL 回傳基於規則的基礎分析報告（使用既有 DCF 結果與基本面分數）
5. THE LLM_Analyzer SHALL 在報告中標明所有數據來源與計算日期，確保可追溯性

---

### 需求 13：自動交易機器人基礎架構

**User Story:** 身為進階使用者，我希望系統提供自動化交易判斷的基礎架構，供未來整合券商 API。

#### 驗收準則

1. THE System SHALL 定義交易訊號介面（`TradeSignal` Protocol），包含：股票代碼、訊號類型（買入/賣出/觀望）、信心度（0-100）、觸發條件描述、建議價格區間
2. WHEN DCF 估值結果顯示低估超過 30% 且法人連續買超超過 3 日時，THE System SHALL 產生買入訊號
3. THE System SHALL 實作訊號佇列（Signal Queue），將產生的交易訊號持久化至 SQLite，供外部系統輪詢消費
4. THE System SHALL 提供模擬模式（paper trading），記錄虛擬交易並追蹤報酬率而不實際下單
5. THE System SHALL 定義券商 API 抽象介面（`BrokerAdapter` Protocol），包含查詢餘額、下單、取消委託三個方法，供未來實作

---

### 需求 14：Pydantic 資料模型遷移

**User Story:** 身為開發者，我希望所有內部資料結構使用 Pydantic 模型，以獲得自動驗證與序列化能力。

#### 驗收準則

1. THE System SHALL 為核心資料結構定義 Pydantic 模型：`StockInfo`、`PriceData`、`FinancialData`、`DCFResult`、`ScanResult`、`TradeSignal`
2. THE Pydantic_Model SHALL 於所有數值欄位定義 `Field()` 約束，包含 `ge`（大於等於）、`le`（小於等於）、`description` 屬性
3. WHEN 舊版 dict 資料傳入新版函式時，THE Pydantic_Model SHALL 透過 `model_validate()` 自動轉換並驗證，維持向下相容
4. THE Pydantic_Model SHALL 為所有模型提供 `.to_dataframe()` 與 `.from_dataframe()` 工廠方法，支援與 pandas DataFrame 的雙向轉換
5. THE Pydantic_Model SHALL 提供 `.to_json()` 輸出方法與 `.from_json()` 工廠方法
6. FOR ALL 有效的 Pydantic_Model 實例，序列化為 JSON 再反序列化 SHALL 產生等價的物件（往返特性）

---

### 需求 15：型別標註與文件字串

**User Story:** 身為開發者，我希望所有函式都有完整的型別標註與文件字串，以利 IDE 補全與團隊協作。

#### 驗收準則

1. THE System SHALL 為所有公開方法與函式新增完整的型別標註（參數型別與回傳型別），含 `Optional`、`Union`、`List`、`Dict` 等泛型標註
2. THE System SHALL 為所有公開方法新增 Google-style docstring，包含 `Args`、`Returns`、`Raises` 三個區段
3. WHEN 內部私有方法（以 `_` 開頭）超過 10 行時，THE System SHALL 為該方法新增至少包含 `Args` 與 `Returns` 的 docstring
4. THE System SHALL 通過 `mypy --strict` 型別檢查（允許外部套件忽略），零錯誤
5. THE System SHALL 通過 `pydocstyle` 文件字串風格檢查（Google convention），所有公開方法零違規

---

### 需求 16：檔案行數限制與模組拆分

**User Story:** 身為開發者，我希望每個檔案保持在可維護的行數範圍內。

#### 驗收準則

1. THE System SHALL 確保所有 Python 原始碼檔案不超過 800 行（不含空白行與純註解行），若超過則拆分為多個模組
2. WHEN `market_scanner.py` 超過 800 行時，THE System SHALL 將篩選邏輯拆至 `filters/` 子目錄，將評分邏輯拆至 `scoring.py`
3. THE System SHALL 在拆分後保持公開 API 不變，透過 `__init__.py` 重新匯出以維持向下相容
4. THE System SHALL 於 CI 流程中加入行數檢查腳本，超過 800 行產生警告、超過 1000 行產生錯誤
5. WHEN 模組拆分後，THE System SHALL 確保循環匯入（circular import）為零

---

### 需求 17：單元測試與涵蓋率

**User Story:** 身為開發者，我希望核心商業邏輯有充分的測試涵蓋率。

#### 驗收準則

1. THE System SHALL 為 DCF_Calculator、DataManager、Market_Scanner 三個核心模組各撰寫至少 15 個單元測試案例
2. THE System SHALL 達到整體程式碼涵蓋率 80% 以上（以 `pytest-cov` 量測，排除 UI 層與第三方套件）
3. WHEN 測試涉及外部 API 呼叫時，THE System SHALL 使用 mock 物件替代實際網路請求
4. THE System SHALL 為所有 Pydantic 模型撰寫驗證測試，涵蓋有效輸入、邊界值、與無效輸入三種情境
5. THE System SHALL 於每次 git commit 前透過 pre-commit hook 執行快速測試套件（執行時間上限 30 秒）

---

### 需求 18：屬性基測試（Property-Based Testing）

**User Story:** 身為開發者，我希望使用屬性基測試發現邊界案例的 bug。

#### 驗收準則

1. THE System SHALL 使用 Hypothesis 框架為 DCF_Calculator 撰寫屬性基測試，驗證：任意正數 EPS 與合理成長率（-50% 至 +50%）下，內在價值計算結果為有限正數
2. THE System SHALL 為 Pydantic 模型的 JSON 序列化/反序列化撰寫往返屬性測試：對任意有效模型實例，`Model.from_json(instance.to_json())` SHALL 產生等價實例
3. THE System SHALL 為篩選器邏輯撰寫幂等性屬性測試：對同一資料集連續套用相同篩選條件兩次，結果 SHALL 與套用一次相同
4. THE System SHALL 為排序功能撰寫變形屬性測試：篩選後資料筆數 SHALL 小於等於篩選前資料筆數
5. THE System SHALL 為成長率計算撰寫屬性測試：當所有期間 EPS 相同時，計算出的成長率 SHALL 為 0（容許浮點誤差 ±0.001）

---

### 需求 19：整合測試

**User Story:** 身為開發者，我希望驗證完整資料管線從 API 到快取到輸出的端對端正確性。

#### 驗收準則

1. THE System SHALL 撰寫整合測試驗證 DataManager 的完整備援流程：主要來源失敗時自動切換至備援來源並正確回傳資料
2. THE System SHALL 撰寫整合測試驗證 Market_Scanner 的完整掃描流程：從 FinLab 取得基礎資料、經 Yahoo Finance 補丁、寫入 SQLite、再查詢回傳
3. WHEN 整合測試執行時，THE System SHALL 使用獨立的測試資料庫檔案（`test_market_scan.db`），不影響正式資料
4. THE System SHALL 為 Circuit_Breaker 撰寫整合測試：模擬連續失敗觸發斷路器開啟，等待後恢復的完整生命週期
5. THE System SHALL 確保所有整合測試可在離線環境執行（使用預錄的 API 回應 fixture）

---

### 需求 20：程式碼品質自動化檢查

**User Story:** 身為開發者，我希望有自動化工具確保程式碼風格與品質一致。

#### 驗收準則

1. THE System SHALL 設定 `ruff` 作為 linter 與 formatter，並定義 `pyproject.toml` 中的規則集（啟用 E、F、I、N、W、UP、B、SIM 規則群）
2. THE System SHALL 設定 pre-commit hooks 執行：ruff check、ruff format、mypy、pytest（快速子集）
3. WHEN `ruff check` 回報違規時，THE System SHALL 以非零退出碼阻止 git commit
4. THE System SHALL 於 `pyproject.toml` 定義統一的專案元資料，包含 Python 版本需求（>=3.10）、依賴清單、與開發依賴清單
5. THE System SHALL 從 `requirements.txt` 遷移至 `pyproject.toml` 管理依賴，並使用 `uv` 作為套件管理工具

