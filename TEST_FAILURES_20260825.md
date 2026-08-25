# 整合收尾：23 個測試失敗分類（2026-08-25）

> 位置：`projects/Finance/stock-valuation-tool/`
> 背景：Task 13 全量測試 `pytest`（910 tests）→ 887 passed / 23 failed（97.5%）
> 失敗為「測試 ↔ 實作 API 不同步」的整合遺留，需逐一判定誰是權威後修復。

## ✅ 修復狀態（2026-08-25 全數修復）

**910 passed / 0 failed**（2026-08-25 08:55 獨立驗證，`pytest tests/ --no-cov` 全量實跑）

| 群 | 檔案 | 個數 | 判定 | 修改 |
|----|------|:---:|------|------|
| 群 1 | growth_optimizer_bugfix + fix_simple | 10 | 改測試（spec=[] 自相矛盾）+ 改實作（浮點 off-by-one + 註解殘留） | `tests/unit/test_growth_optimizer_bugfix.py`、`app/views/growth_optimizer.py` |
| 群 2 | market_scanner | 3 | 改實作（缺欄位容錯 + 弱股扣分，cron 選股路徑不變，已 smoke test） | `app/market_scanner.py` |
| 群 3 | update_scheduler | 4 | 改實作（加回注入參數，向後相容） | `app/scheduler.py` |
| 群 4 | validator | 2 | 改實作（`[OK]`→`✓`，測試是 spec） | `app/data/validator.py` |
| 群 5 | data_manager（本文件原未分類） | 4 | 改測試（實作 read-through 從未有 is_cache_valid） | `tests/unit/test_data_manager.py` |

## 原始失敗分類（供歷史查閱）

### 群 1：test_growth_optimizer_bugfix.py（10 個）+ test_growth_optimizer_fix_simple.py（1 個）

| 測試 | 錯誤 | 判定方向 |
|------|------|---------|
| test_preservation_empty_stock_code_shows_warning | 未顯示警告 | 測試期望 vs 實作行為 |
| test_preservation_lambda_min_ge_max_shows_error | 未顯示錯誤 | 同上 |
| test_preservation_no_valid_results_shows_warning | 未顯示警告 | 同上 |
| test_fix_no_attribute_error_raised | AttributeError | 實作缺方法 |
| test_fix_calls_get_latest_eps_once | Mock 缺屬性 | API 改名？ |
| test_fix_calls_get_latest_price_for_eps_price | Mock 缺屬性 | 同上 |
| test_fix_calls_calculate_historical_growth_rate_per_lambda | Mock 缺屬性 | 同上 |
| test_fix_calls_calculate_dcf_value_per_lambda | Mock 缺 `calculate_dcf_value` | 實作缺方法 |
| test_fix_calculate_dcf_value_receives_correct_growth_rates | Mock 缺屬性 | 同上 |
| test_fixed_code_no_obvious_attribute_errors | 程式碼仍呼叫 `get_current_price()` | 實作改為 `get_latest_price`？ |

> 疑點：實作側（growth optimizer）可能把 `get_current_price` 改為 `get_latest_price` 或新增 `calculate_dcf_value`，測試 Mock 未同步。需比對實作檔案實際方法名。

### 群 2：test_market_scanner.py（3 個）

| 測試 | 錯誤 | 判定方向 |
|------|------|---------|
| test_filter_stocks_compatible_without_roe_column | KeyError: 'roe' | 實作 `filter_stocks` 需容忍缺 roe 欄位 |
| test_fundamental_score_weak_stock_gets_low_grade | assert 70 < 50 | 弱股評分邏輯（70 分太高，閾值問題） |
| test_fundamental_score_handles_missing_columns_and_values | KeyError: 'dividend_yield' | 同上，缺欄位容錯 |

> 疑點：`MarketScanner._calculate_fundamental_score` 假設欄位必存在；測試期望缺欄位時優雅降級。**cron 關聯**：`market_scanner.py` 是低基期選股器的核心（`filter_stocks`），修復時勿改壞 cron 依賴的 `high_52w/low_52w` 邏輯。

### 群 3：test_update_scheduler.py（4 個）

| 測試 | 錯誤 |
|------|------|
| test_register_default_jobs | `DataUpdateScheduler.__init__() got an unexpected keyword argument` |
| test_run_daily_price_update | 同上 |
| test_run_quarterly_financial_update | 同上 |
| test_default_stock_list_provider | 同上 |

> 疑點：測試傳了 `scheduler.py` 的 `__init__` 不接受的參數（測試用舊 API 簽名）。已修正 import（`app.update_scheduler` → `app.scheduler`），但參數簽名仍不同步。比對 `app/scheduler.py` 的 `SchedulerConfig` 與測試期望。

### 群 4：test_validator.py（2 個）

| 測試 | 錯誤 |
|------|------|
| test_summary_report_all_valid | `'✓ 通過' not in 輸出` |
| test_complete_validation_workflow | 同上 |

> 疑點：validator 輸出格式改了（emoji/文字）？測試期望 `✓ 通過` 但實際輸出不同。比對 `app/data/validator.py` 的報告格式。

## 建議處理順序

1. 群 3（update_scheduler，4 個）最容易 — 純 API 簽名對齊
2. 群 1（growth_optimizer，11 個）— 先確認實作方法名，再同步測試 Mock
3. 群 4（validator，2 個）— 確認輸出格式權威
4. 群 2（market_scanner，3 個）— **最敏感（cron 依賴）**，修 `_calculate_fundamental_score` 容錯時跑 `stock_update.py` 驗證 cron 不受影響

## 已完成的收尾（本次 session）

- [x] fix_prices.py 提交（5311559：六日加量/補最舊/ZeroDivisionError）
- [x] DataManagerV2 快取評估修復（abd4e12：get_stock_price/get_financial_data 快取命中也評估品質）
- [x] test_update_scheduler import 修正（abd4e12）
- [x] pytest config 合併 pyproject + 刪 pytest.ini（da972f9）
- [ ] 23 個測試失敗修復（本文件）
