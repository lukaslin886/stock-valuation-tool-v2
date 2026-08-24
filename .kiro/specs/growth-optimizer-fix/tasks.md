# Implementation Plan

## Overview

This task list implements the bugfix for `app/views/growth_optimizer.py` using the exploratory bugfix workflow.
The bug causes an `AttributeError` when the Lambda 迴圈 attempts to access `DCFCalculator.recent_weight_ratio`,
an attribute that does not exist. The fix replaces incorrect API calls with the correct call sequence:
`data_manager.calculate_historical_growth_rate()` → `dcf_calculator.calculate_dcf_value()`.

Tasks follow the order: **Explore → Preserve → Implement → Validate**.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Lambda 迴圈呼叫不存在的 DCFCalculator 屬性
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: For deterministic bugs, scope the property to the concrete failing case: any (stock_code, lambda_value) pair triggers the AttributeError
  - Test that calling show_growth_optimizer triggers AttributeError: `'DCFCalculator' object has no attribute 'recent_weight_ratio'`
  - Test that the correct API (`data_manager.calculate_historical_growth_rate`, `data_manager.get_latest_eps`, `data_manager.get_latest_price`, `dcf_calculator.calculate_dcf_value`) is NOT called by the buggy code
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found: `AttributeError: 'DCFCalculator' object has no attribute 'recent_weight_ratio'` raised on first loop iteration
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3_

- [-] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - 非 Lambda 迴圈路徑（UI 驗證、邊界條件、警告訊息）行為維持不變
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: `lambda_min >= lambda_max` → shows error and returns on UNFIXED code
  - Observe: empty stock_code → shows warning and returns on UNFIXED code
  - Observe: all lambda results invalid → shows "無法計算出有效估值" warning on UNFIXED code
  - Write property-based tests: for all (lambda_min, lambda_max) where lambda_min >= lambda_max, the function shows error and returns without calling any API
  - Write property-based tests: for empty stock_code, function shows warning and returns without any calculation
  - Verify tests pass on UNFIXED code (these paths are unaffected by the bug)
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 3. Fix Lambda 迴圈 API 呼叫邏輯

  - [x] 3.1 Implement the fix in app/views/growth_optimizer.py
    - 在迴圈外新增：`current_eps = data_manager.get_latest_eps(stock_code)`
    - 在迴圈外新增：`current_price_val = data_manager.get_latest_price(stock_code)`
    - 新增驗證：若 `current_eps <= 0` 或 `current_price_val <= 0`，顯示錯誤並 return
    - 移除：`original_lambda = dcf_calculator.recent_weight_ratio`（屬性不存在）
    - 移除：`dcf_calculator.recent_weight_ratio = round(l, 2)`（屬性不存在）
    - 移除：`result = dcf_calculator.calculate(stock_code, data_manager)`（方法不存在）
    - 移除：`dcf_calculator.recent_weight_ratio = original_lambda`（屬性不存在）
    - 新增：`growth_info = data_manager.calculate_historical_growth_rate(stock_code, recent_weight_ratio=round(l, 2))`
    - 新增：`result = dcf_calculator.calculate_dcf_value(current_price_val, current_eps, [g1_5, g6_10], discount_rate=0.11, stock_code=stock_code, weighting_method=growth_info.get('weighting_method', 'time_weighted'))`
    - 修正結果欄位：`'Growth Rate 1-5Y (%)'` 和 `'Growth Rate 6-10Y (%)'`
    - 修正圖表取得股價：`data_manager.get_latest_price(stock_code)`（移除不存在的 `get_current_price`）
    - 修正 DataFrame 格式化欄位名稱配合新欄位
    - _Bug_Condition: isBugCondition((stock_code, lambda_value)) = True — 任何有效輸入均觸發 AttributeError_
    - _Expected_Behavior: data_manager.calculate_historical_growth_rate(stock_code, recent_weight_ratio=l) → dcf_calculator.calculate_dcf_value(...) → result['intrinsic_value']_
    - _Preservation: UI 元件、邊界條件驗證、圖表渲染、警告訊息邏輯保持不變_
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [-] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Lambda 迴圈正確呼叫 API 完成估值計算
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied: no AttributeError, correct API call sequence
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [~] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - 非 Lambda 迴圈路徑行為維持不變
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [~] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "探索與保留測試（需在修復前完成）"
    },
    {
      "wave": 2,
      "tasks": ["3.1"],
      "description": "實作修復（依賴 wave 1 的理解）",
      "dependsOn": ["1", "2"]
    },
    {
      "wave": 3,
      "tasks": ["3.2", "3.3"],
      "description": "驗證修復正確且無回歸",
      "dependsOn": ["3.1"]
    },
    {
      "wave": 4,
      "tasks": ["4"],
      "description": "Checkpoint — 確認所有測試通過",
      "dependsOn": ["3.2", "3.3"]
    }
  ]
}
```

**Key ordering constraints:**
- Tasks 1 and 2 MUST be written and run on UNFIXED code before any implementation begins
- Task 3.1 depends on insights from tasks 1 and 2
- Tasks 3.2 and 3.3 re-run the same tests from tasks 1 and 2 respectively (no new tests written)
- Task 4 can only be completed after 3.2 and 3.3 both pass

## Notes

- **File under fix**: `app/views/growth_optimizer.py` — only this file is modified
- **No other files changed**: `DCFCalculator`, `DataManagerV2`, and all other modules remain untouched
- **Root cause**: `recent_weight_ratio` is a parameter of `DataManagerV2.calculate_historical_growth_rate()`, not a property of `DCFCalculator`; the original code incorrectly treated it as a mutable object attribute
- **Correct API sequence**: `get_latest_eps` + `get_latest_price` (once, outside loop) → `calculate_historical_growth_rate(stock_code, recent_weight_ratio=l)` (per iteration) → `calculate_dcf_value(...)` (per iteration)
- **Property-based testing**: Task 2 uses Hypothesis to generate boundary inputs for stronger preservation guarantees across the full input domain
- **Test status legend**: `[x]` = complete, `[-]` = in progress / partially done, `[~]` = done as part of parent, `[ ]` = not started
