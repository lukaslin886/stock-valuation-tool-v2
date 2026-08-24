# Bugfix Requirements Document

## Introduction

「成長參數優化」頁面（`app/views/growth_optimizer.py`）在使用者點擊「▶ 開始參數優化分析」按鈕時，會拋出 `'DCFCalculator' object has no attribute 'recent_weight_ratio'` 的錯誤。根本原因是 `growth_optimizer.py` 呼叫了兩個 `DCFCalculator` 上不存在的成員：

1. `dcf_calculator.recent_weight_ratio` — 該屬性從未定義在 `DCFCalculator.__init__` 中；`recent_weight_ratio` 實際上是 `DataManagerV2.calculate_historical_growth_rate()` 的一個函式參數。
2. `dcf_calculator.calculate(stock_code, data_manager)` — `DCFCalculator` 沒有 `calculate()` 方法；正確的方法是 `calculate_dcf_value(current_price, current_eps, growth_rates, ...)`。

此 Bug 導致優化分析功能完全無法使用，影響所有嘗試執行參數優化的使用者。

---

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN 使用者在「成長參數優化」頁面點擊「▶ 開始參數優化分析」按鈕時 THEN the system 拋出 `AttributeError: 'DCFCalculator' object has no attribute 'recent_weight_ratio'`，並在 UI 顯示「分析過程發生錯誤: 'DCFCalculator' object has no attribute 'recent_weight_ratio'」

1.2 WHEN 程式嘗試讀取 `dcf_calculator.recent_weight_ratio` 並將其暫存後再呼叫 `dcf_calculator.calculate(stock_code, data_manager)` 時 THEN the system 因存取不存在的屬性而提前崩潰，`calculate()` 方法從未被呼叫

1.3 WHEN Lambda 迴圈試圖以 `dcf_calculator.recent_weight_ratio = round(l, 2)` 修改計算器狀態來驅動不同 lambda 值的估值時 THEN the system 未能透過正確的 API（`data_manager.calculate_historical_growth_rate(stock_code, recent_weight_ratio=l)`）傳遞 lambda 值，導致迴圈邏輯完全錯誤

### Expected Behavior (Correct)

2.1 WHEN 使用者點擊「▶ 開始參數優化分析」按鈕時 THEN the system SHALL 依序對每個測試 lambda 值呼叫 `data_manager.calculate_historical_growth_rate(stock_code, recent_weight_ratio=l)`，取得對應的 `growth_rate_1_5` 與 `growth_rate_6_10`，再呼叫 `dcf_calculator.calculate_dcf_value(current_price, current_eps, [growth_rate_1_5, growth_rate_6_10], ...)` 計算 DCF 內在價值，不發生任何 AttributeError

2.2 WHEN 需要取得目前股價與 EPS 時 THEN the system SHALL 分別呼叫 `data_manager.get_latest_price(stock_code)` 與 `data_manager.get_latest_eps(stock_code)` 取得所需數值，並在數值無效時顯示明確的錯誤提示而非崩潰

2.3 WHEN 每個 lambda 值的估值計算成功時 THEN the system SHALL 在結果表格與圖表中正確顯示 Lambda、Intrinsic Value、Growth Rate 1-5Y（%）、Growth Rate 6-10Y（%）等欄位，並標示最佳 lambda 建議

### Unchanged Behavior (Regression Prevention)

3.1 WHEN lambda 迴圈正常執行並取得有效估值時 THEN the system SHALL CONTINUE TO 顯示 Lambda 對內在價值的敏感度折線圖，並以星形標記標示最佳（最接近中位數）lambda 點

3.2 WHEN `data_manager.get_current_price(stock_code)` 回傳有效價格時 THEN the system SHALL CONTINUE TO 在圖表上以紅色虛線標示目前股價

3.3 WHEN 所有 lambda 測試點均未產生有效估值（`intrinsic_value <= 0`）時 THEN the system SHALL CONTINUE TO 顯示「無法計算出有效估值，請確認該股票資料是否齊全。」警告訊息

3.4 WHEN 使用者設定的最小 lambda 大於或等於最大 lambda 時 THEN the system SHALL CONTINUE TO 顯示「最小 Lambda 必須小於最大 Lambda」錯誤並阻止分析執行

3.5 WHEN 頁面載入但未輸入股票代碼時 THEN the system SHALL CONTINUE TO 顯示「請先在左側欄輸入股票代碼！」警告訊息

3.6 WHEN 使用者展開「查看詳細數據」時 THEN the system SHALL CONTINUE TO 顯示格式化的 DataFrame 表格

---

## Bug Condition (Pseudocode)

**Bug Condition Function**:
```pascal
FUNCTION isBugCondition(X)
  INPUT: X = (stock_code, lambda_value)
  OUTPUT: boolean

  // Bug 在使用者觸發優化分析且試圖存取 DCFCalculator.recent_weight_ratio 時發生
  RETURN True  // 任何有效輸入都會觸發此 bug（屬性根本不存在）
END FUNCTION
```

**Fix Checking Property**:
```pascal
// Property: Fix Checking — 確保任何 lambda 值均可成功計算估值
FOR ALL (stock_code, lambda_value) WHERE isBugCondition((stock_code, lambda_value)) DO
  growth_info ← data_manager.calculate_historical_growth_rate(stock_code, recent_weight_ratio=lambda_value)
  eps         ← data_manager.get_latest_eps(stock_code)
  price       ← data_manager.get_latest_price(stock_code)
  result      ← dcf_calculator.calculate_dcf_value(price, eps, [growth_info['growth_rate_1_5'], growth_info['growth_rate_6_10']], ...)
  ASSERT no AttributeError raised
  ASSERT result is dict containing 'intrinsic_value'
END FOR
```

**Preservation Checking Property**:
```pascal
// Property: Preservation Checking — 非錯誤路徑（UI 元件、圖表、警告訊息）行為不變
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)  // UI 邏輯、圖表渲染、邊界條件提示維持原有行為
END FOR
```
