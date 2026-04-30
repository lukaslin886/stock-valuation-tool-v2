# P2-10 實作計畫：個股基本面評分系統（A+~D）

## 目標
- 建立可重現、可測試的「基本面綜合評分」機制，輸出 0-100 分。
- 依分數產生投資評級（A+ 到 D）。
- 在市場篩選器中可直接看到評分與評級，支援後續擴充（如 Phase 3 綜合評分整合）。

## 非目標
- 本次不新增外部資料源（沿用既有 snapshot 欄位）。
- 本次不改動投資組合頁與回測引擎邏輯。

## 資料基礎（沿用現有 market_snapshot）
- 可用欄位：`pe_ratio`, `pb_ratio`, `roe`, `dividend_yield`, `revenue_growth`。
- 評分僅依上述欄位，缺值視為中性或保守分數（避免崩潰與過度樂觀）。

## 評分模型（v1）
- 總分 100，採加權子分數：
  1. 獲利品質（35 分）：`roe`。
  2. 估值合理性（25 分）：`pe_ratio` + `pb_ratio`。
  3. 股東回饋（20 分）：`dividend_yield`。
  4. 成長性（20 分）：`revenue_growth`。
- 子分數採「區間映射 + 封頂」：
  - 以多段閾值映射至 0~100，再乘以權重。
  - 對異常值（負值、極端值）做截斷，避免單一欄位主導。

## 評級映射（v1）
- `A+`: score >= 85
- `A`: 80 <= score < 85
- `B+`: 75 <= score < 80
- `B`: 65 <= score < 75
- `C`: 50 <= score < 65
- `D`: score < 50

## 實作步驟（Step-by-step）
1. 在 `app/market_scanner.py` 新增純函式評分器
   - 新增 `_calculate_fundamental_score(row)`：回傳 `fundamental_score`（float）與 `fundamental_grade`（str）。
   - 將閾值與權重集中在常數區，避免散落 magic numbers。

2. 在 `app/market_scanner.py` 對 snapshot 套用評分
   - 在 `filter_stocks(...)` 讀取資料後，先確保必要欄位存在（缺欄位補 0）。
   - 對每列套用評分器，新增兩欄：`fundamental_score`, `fundamental_grade`。
   - 保持既有篩選行為不變（不破壞 P2-09）。

3. 在 `app/views/market_screener.py` 顯示評分與評級
   - 初篩表格新增 `fundamental_score`, `fundamental_grade` 欄位。
   - 針對分數做格式化（例如 1 位小數），評級維持文字顯示。

4. 單元測試補強（`tests/unit/test_market_scanner.py`）
   - 新增「高品質樣本」應得到高分高評級。
   - 新增「弱基本面樣本」應得到低分低評級。
   - 新增「缺欄位/缺值」不應拋錯，且分數在合理區間。
   - 保留既有 P2-09 測試，避免回歸。

5. 文件同步
   - `TODO.md`：勾選 `P2-10` 並更新進度比例。
   - `DEVELOPMENT_LOG.md`：新增 `v1.8.8` 條目（P2-10）。

## 驗證計畫
- 最小驗證：
  - `uv run pytest tests/unit/test_market_scanner.py -q`
  - `uv run python -m py_compile app/market_scanner.py app/views/market_screener.py`
- 回歸驗證（建議）：
  - `uv run pytest tests/unit -q`

## 驗收標準
- 市場篩選頁可見每檔股票的基本面分數與評級。
- 同一組輸入資料，分數與評級穩定可重現。
- 單元測試全部通過，且既有 P2-09 行為不回歸。

## 風險與緩解
- 風險 1：yfinance 欄位缺值造成分數偏低或失真。
  - 緩解：缺值採保守中性分，並保留後續參數調校空間。
- 風險 2：閾值設定過嚴導致評級集中在低分。
  - 緩解：先以 v1 閾值上線，透過測試樣本與實際分布再微調。
- 風險 3：前端欄位增加影響既有排序/格式。
  - 緩解：維持原欄位順序，新增欄位置於估值欄位後，並補格式化測試。
