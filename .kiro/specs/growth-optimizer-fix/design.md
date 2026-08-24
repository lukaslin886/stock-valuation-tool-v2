# Growth Optimizer Fix — Bugfix Design

## Overview

`app/views/growth_optimizer.py` 中的「成長參數優化」頁面，在使用者點擊「▶ 開始參數優化分析」時，
試圖存取 `DCFCalculator` 上不存在的屬性 `recent_weight_ratio` 及方法 `calculate()`，
導致 `AttributeError` 並讓功能完全失效。

修復策略：**最小範圍修改**，只改動 `app/views/growth_optimizer.py` 中的 Lambda 迴圈邏輯，
以正確的 API 呼叫序列取代錯誤的呼叫，同時修正 `get_current_price` → `get_latest_price`，
不修改任何其他檔案或類別。

---

## Glossary

- **Bug_Condition (C)**: 觸發 Bug 的條件 — 使用者點擊「開始參數優化分析」後，程式試圖存取
  `DCFCalculator.recent_weight_ratio`，該屬性根本不存在，導致 `AttributeError`。
- **Property (P)**: 修復後的期望行為 — 每個 lambda 值均透過正確 API 取得成長率並成功計算 DCF 估值，不拋出異常。
- **Preservation**: 必須維持不變的既有行為 — UI 元件（滑桿、按鈕）、圖表渲染、邊界條件警告訊息等。
- **`isBugCondition(X)`**: 判斷輸入是否觸發 Bug 的偽碼函式。
- **`DCFCalculator.calculate_dcf_value`**: 位於 `app/dcf_calculator.py`，正確的 DCF 計算方法，
  接受 `current_price, current_eps, growth_rates, discount_rate, stock_code, weighting_method` 等參數。
- **`DataManagerV2.calculate_historical_growth_rate`**: 位於 `app/data/manager.py`，
  接受 `stock_code, recent_weight_ratio` 參數，回傳 `{'growth_rate_1_5': float, 'growth_rate_6_10': float, 'weighting_method': str, ...}`。
- **`DataManagerV2.get_latest_eps`**: 回傳指定股票的最新 EPS（float）。
- **`DataManagerV2.get_latest_price`**: 回傳指定股票的最新股價（float），取代原本錯誤呼叫的 `get_current_price`。
- **`recent_weight_ratio` (λ)**: 計算歷史成長率時近期資料的權重比例，範圍 [0.1, 1.0]，
  是 `calculate_historical_growth_rate` 的函式參數，**不是** `DCFCalculator` 的屬性。

---

## Bug Details

### Bug Condition

Bug 在使用者觸發優化分析後的 Lambda 迴圈中發生。原始程式碼假設 `DCFCalculator` 持有
`recent_weight_ratio` 屬性並提供 `calculate(stock_code, data_manager)` 方法，
但這兩者均不存在於 `DCFCalculator` 的實作中。

由於 `recent_weight_ratio` 是 `DataManagerV2.calculate_historical_growth_rate()` 的
**函式參數**，正確的做法是在每次迴圈中以不同的 lambda 值呼叫該函式，而非試圖修改計算器的屬性狀態。

此外，`data_manager.get_current_price(stock_code)` 方法同樣不存在，
應改為 `data_manager.get_latest_price(stock_code)`。

**Formal Specification:**

```
FUNCTION isBugCondition(X)
  INPUT: X = (stock_code, lambda_value)
  OUTPUT: boolean

  // 任何有效的 (stock_code, lambda_value) 輸入都會觸發此 bug
  // 因為 DCFCalculator.recent_weight_ratio 屬性根本不存在
  RETURN True
END FUNCTION
```

### Examples

- **範例 1**：使用者對股票 `2330`，lambda 範圍 0.1–0.9 點擊分析
  - 實際：第一次迴圈即拋出 `AttributeError: 'DCFCalculator' object has no attribute 'recent_weight_ratio'`
  - 期望：依序對 0.1, 0.2, ..., 0.9 計算並顯示敏感度圖表

- **範例 2**：使用者對任意股票執行優化分析
  - 實際：UI 顯示「分析過程發生錯誤: 'DCFCalculator' object has no attribute 'recent_weight_ratio'」
  - 期望：顯示 Lambda vs 內在價值折線圖，並標示最佳 lambda 建議

- **範例 3**：即使該股票 EPS 或股價資料不足
  - 實際：在 `AttributeError` 前就崩潰，從未驗證資料有效性
  - 期望：呼叫 `get_latest_eps` / `get_latest_price` 後，若數值 ≤ 0 則顯示明確錯誤提示

- **邊界情境**：lambda 範圍僅有單一測試點（min = max - 0.1）
  - 期望：仍正確計算並顯示單點圖表，不崩潰

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- 滑桿設定（Lambda 最小值、最大值）及「最小 Lambda 必須小於最大 Lambda」驗證邏輯維持不變
- 頁面未輸入股票代碼時的警告訊息維持不變
- 所有 lambda 測試點均無有效估值時的警告訊息維持不變
- Lambda vs 內在價值折線圖的渲染邏輯維持不變（包含紅色虛線股價標示、星形最佳點標示）
- 「查看詳細數據」折疊式 DataFrame 表格維持不變
- `DCFCalculator`、`DataManagerV2` 及所有其他檔案的程式碼維持不變

**Scope:**

所有不涉及 Lambda 迴圈內部計算邏輯的程式路徑，均不受此次修復影響。具體包含：

- UI 元件渲染（`st.header`、`st.number_input`、`st.button` 等）
- 邊界條件檢查（lambda_min ≥ lambda_max、無 stock_code）
- 圖表建立與格式化邏輯
- 無有效估值時的警告路徑

---

## Hypothesized Root Cause

根據 Bug 描述及程式碼分析，最可能的原因如下：

1. **API 誤解：錯誤地將函式參數視為物件屬性**
   - 開發者誤以為可透過設定 `dcf_calculator.recent_weight_ratio` 屬性來影響後續計算
   - 實際上 `recent_weight_ratio` 是 `DataManagerV2.calculate_historical_growth_rate()` 的函式參數，必須在呼叫時傳入

2. **方法名稱錯誤：使用不存在的 `calculate()` 方法**
   - 原始程式呼叫 `dcf_calculator.calculate(stock_code, data_manager)`
   - `DCFCalculator` 的實際計算方法是 `calculate_dcf_value(current_price, current_eps, growth_rates, ...)`，
     需要先從 `DataManagerV2` 取得 EPS、股價、成長率後再呼叫

3. **API 名稱錯誤：`get_current_price` 不存在**
   - 原始程式呼叫 `data_manager.get_current_price(stock_code)`
   - 正確方法名稱為 `data_manager.get_latest_price(stock_code)`

4. **資料流設計錯誤：未先取得 EPS 與股價**
   - 正確的呼叫序列應為：先取得 EPS 和股價（在迴圈外，避免重複 API 呼叫），
     再在迴圈內以不同 lambda 取得成長率，最後呼叫 DCF 計算

---

## Correctness Properties

Property 1: Bug Condition — Lambda 迴圈正確呼叫 API 完成估值計算

_For any_ 有效的 `(stock_code, lambda_value)` 輸入（即 `isBugCondition` 回傳 True 的情況），
修復後的 `show_growth_optimizer` 函式 SHALL 依照下列順序成功執行而不拋出 `AttributeError`：
呼叫 `data_manager.get_latest_eps(stock_code)` 與 `data_manager.get_latest_price(stock_code)` 取得有效數值，
再對每個 lambda 值呼叫 `data_manager.calculate_historical_growth_rate(stock_code, recent_weight_ratio=lambda_value)`，
最後以 `dcf_calculator.calculate_dcf_value(current_price, current_eps, [g1_5, g6_10], ...)` 計算出含 `intrinsic_value` 的結果字典。

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation — 非迴圈邏輯的既有行為維持不變

_For any_ 不涉及 Lambda 迴圈內部計算邏輯的程式路徑（UI 元件、邊界條件驗證、圖表渲染、警告訊息），
修復後的程式碼 SHALL 產生與原始程式碼完全相同的行為，保留所有邊界條件提示、圖表格式，以及無有效估值時的警告流程。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

---

## Fix Implementation

### Changes Required

**File**: `app/views/growth_optimizer.py`

**Function**: `show_growth_optimizer` — `if st.button(...)` 區塊內的 `with st.spinner(...)` 段落

**Specific Changes**:

1. **在迴圈外取得 EPS 與股價（避免重複 API 呼叫）**
   - 新增：`current_eps = data_manager.get_latest_eps(stock_code)`
   - 新增：`current_price = data_manager.get_latest_price(stock_code)`
   - 新增驗證：若 `current_eps <= 0` 或 `current_price <= 0`，顯示錯誤訊息並 `return`

2. **修正 Lambda 迴圈內的 API 呼叫**
   - 移除：`original_lambda = dcf_calculator.recent_weight_ratio`（屬性不存在）
   - 移除：`dcf_calculator.recent_weight_ratio = round(l, 2)`（屬性不存在）
   - 移除：`result = dcf_calculator.calculate(stock_code, data_manager)`（方法不存在）
   - 移除：`dcf_calculator.recent_weight_ratio = original_lambda`（屬性不存在）
   - 新增：呼叫 `data_manager.calculate_historical_growth_rate(stock_code, recent_weight_ratio=round(l, 2))`
   - 新增：呼叫 `dcf_calculator.calculate_dcf_value(current_price, current_eps, [g1_5, g6_10], discount_rate=0.11, stock_code=stock_code, weighting_method=growth_info.get('weighting_method', 'time_weighted'))`

3. **修正結果字典欄位**
   - 原：`'Growth Rate': result.get('growth_rate', 0) * 100`（欄位不存在）
   - 新：`'Growth Rate 1-5Y (%)': g1_5 * 100` 和 `'Growth Rate 6-10Y (%)': g6_10 * 100`

4. **修正股價取得方法名稱**
   - 原：`data_manager.get_current_price(stock_code)`（方法不存在）
   - 新：`data_manager.get_latest_price(stock_code)`

5. **修正 DataFrame 格式化欄位名稱**
   - 配合新欄位名稱更新 `.style.format()` 的 key：`'Growth Rate 1-5Y (%)'` 和 `'Growth Rate 6-10Y (%)'`

**完整修復後的 Lambda 迴圈（偽碼）：**

```python
# 迴圈外：取得 EPS 與股價
current_eps = data_manager.get_latest_eps(stock_code)
current_price = data_manager.get_latest_price(stock_code)

if current_eps <= 0 or current_price <= 0:
    st.error("無法取得有效的 EPS 或股價資料，請確認股票代碼是否正確。")
    return

for l in test_lambdas:
    growth_info = data_manager.calculate_historical_growth_rate(
        stock_code, recent_weight_ratio=round(l, 2)
    )
    g1_5 = growth_info['growth_rate_1_5']
    g6_10 = growth_info['growth_rate_6_10']

    result = dcf_calculator.calculate_dcf_value(
        current_price=current_price,
        current_eps=current_eps,
        growth_rates=[g1_5, g6_10],
        discount_rate=0.11,
        stock_code=stock_code,
        weighting_method=growth_info.get('weighting_method', 'time_weighted')
    )

    if result and result.get('intrinsic_value', 0) > 0:
        results.append({
            'Lambda': round(l, 2),
            'Intrinsic Value': result['intrinsic_value'],
            'Growth Rate 1-5Y (%)': g1_5 * 100,
            'Growth Rate 6-10Y (%)': g6_10 * 100,
        })
```

---

## Testing Strategy

### Validation Approach

測試策略分兩階段進行：
1. **探索階段**：在未修復的程式碼上執行測試，確認 Bug 可重現並釐清根本原因
2. **驗證階段**：修復後執行 Fix Checking 與 Preservation Checking，確保修復有效且無回歸

### Exploratory Bug Condition Checking

**Goal**: 在修復前，以測試確認 Bug 可重現，並驗證根本原因分析正確。
若測試結果與預期不符，需重新分析根本原因。

**Test Plan**: Mock `DCFCalculator` 和 `DataManagerV2`，直接呼叫 `show_growth_optimizer`
（或提取其 Lambda 迴圈邏輯），在原始程式碼上斷言 `AttributeError` 被拋出。

**Test Cases**:

1. **屬性不存在測試**：對任意股票代碼觸發分析，斷言拋出 `AttributeError: 'DCFCalculator' object has no attribute 'recent_weight_ratio'`（未修復前必然失敗）
2. **方法不存在測試**：即使暫時 monkey-patch `recent_weight_ratio`，仍應在呼叫 `calculate()` 時拋出 `AttributeError`（未修復前必然失敗）
3. **get_current_price 不存在測試**：驗證 `DataManagerV2` 無 `get_current_price` 方法（未修復前必然失敗）
4. **API 呼叫序列測試**：驗證修復前的程式碼從未呼叫 `calculate_historical_growth_rate` 或 `calculate_dcf_value`

**Expected Counterexamples**:

- `AttributeError: 'DCFCalculator' object has no attribute 'recent_weight_ratio'` 在第一次迴圈迭代時被拋出
- 可能原因：API 設計誤解、屬性名稱錯誤、呼叫序列錯誤

### Fix Checking

**Goal**: 驗證修復後，所有 lambda 值均能成功計算並取得 `intrinsic_value`，不拋出異常。

**Pseudocode:**

```
FOR ALL (stock_code, lambda_value) WHERE isBugCondition((stock_code, lambda_value)) DO
  growth_info ← data_manager.calculate_historical_growth_rate(stock_code, recent_weight_ratio=lambda_value)
  eps         ← data_manager.get_latest_eps(stock_code)
  price       ← data_manager.get_latest_price(stock_code)
  result      ← dcf_calculator.calculate_dcf_value(price, eps, [growth_info['growth_rate_1_5'], growth_info['growth_rate_6_10']], discount_rate=0.11, ...)
  ASSERT no AttributeError raised
  ASSERT result is dict
  ASSERT 'intrinsic_value' in result
  ASSERT result['intrinsic_value'] > 0
END FOR
```

### Preservation Checking

**Goal**: 驗證修復後，所有非 Lambda 迴圈邏輯的程式路徑行為與原始程式碼相同。

**Pseudocode:**

```
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT show_growth_optimizer_original(X) = show_growth_optimizer_fixed(X)
END FOR
```

**Testing Approach**: 建議使用 property-based testing（如 Hypothesis）進行 Preservation Checking，原因：

- 可自動產生大量測試案例覆蓋不同 UI 狀態（空股票代碼、lambda 邊界、無效資料等）
- 能捕捉人工測試容易遺漏的邊界案例
- 對「非錯誤路徑行為不變」提供較強的保證

**Test Plan**: 先在未修復程式碼上觀察各 UI 路徑的正確行為，再撰寫 property-based tests 驗證修復後這些行為持續成立。

**Test Cases**:

1. **邊界條件保留測試**：驗證 `lambda_min >= lambda_max` 時仍顯示錯誤訊息並 return
2. **無股票代碼保留測試**：驗證未輸入 stock_code 時仍顯示警告訊息並 return
3. **無有效估值保留測試**：驗證所有 lambda 均無有效估值時仍顯示「無法計算出有效估值」警告
4. **圖表渲染保留測試**：驗證圖表建立邏輯（Scatter trace、hline、layout）與修復前相同
5. **DataFrame 格式化保留測試**：驗證「查看詳細數據」的 DataFrame 格式化邏輯正確反映新欄位名稱

### Unit Tests

- 測試修復後 `current_eps <= 0` 分支：應顯示錯誤訊息並 return，不繼續迴圈
- 測試修復後 `current_price <= 0` 分支：應顯示錯誤訊息並 return，不繼續迴圈
- 測試 `calculate_historical_growth_rate` 回傳無效成長率時的處理（`intrinsic_value <= 0` 過濾）
- 測試 lambda 範圍僅一個測試點時仍能正常運作

### Property-Based Tests

- 以 Hypothesis 產生隨機 `(stock_code, lambda_min, lambda_max)` 組合，驗證修復後不拋出 `AttributeError`
- 以 Hypothesis 產生隨機的 `growth_rate_1_5` 與 `growth_rate_6_10` 組合，驗證 `calculate_dcf_value` 呼叫參數正確
- 驗證所有 lambda ∈ [0.1, 1.0] 的值，`recent_weight_ratio` 均以正確精度（`round(l, 2)`）傳入

### Integration Tests

- 測試完整的 `show_growth_optimizer` 流程：Mock `DataManagerV2` 和 `DCFCalculator`，驗證從按鈕點擊到圖表渲染的完整路徑
- 測試 `get_latest_price` 回傳有效價格時，圖表中確實添加了紅色虛線
- 測試 lambda 範圍 0.1–0.9（9 個測試點）時，`results_df` 包含正確的欄位名稱與數值格式
