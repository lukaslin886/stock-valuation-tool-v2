# FinMind 備援引擎評估（2026-07-06）

> 對應 TODO.md：「評估是否需要實作 FinMind 專業版批次 API」「優化 FinMind 頻率限制處理」。
> 結論先講：**不需要為現行快照用途升級 Pro；真正該補的是頻率限制的防呆與 402 處理。**

---

## 一、結論與建議（TL;DR）

1. **是否需要 Pro 批次 API？→ 目前用途：不需要。**
   現行全市場快照是「**依日期批次**」抓取（`taiwan_stock_daily(start_date=...)` 一次回整個市場、`taiwan_stock_per_pbr(start_date=...)` 一次回全市場 PE/PB/殖利率），**單次更新只花約 2 個 request**，遠低於註冊會員 600 次/小時的上限。為此升級付費方案沒有效益。
2. **Pro 只有在這些情況才值得**：需要目前免費/註冊層拿不到或會失敗的資料集（`taiwan_stock_financial_statement`、`taiwan_stock_dividend`、`taiwan_stock_month_revenue`——見既有權限報告皆為 ❌）、或改成**逐檔迴圈**深度分析（request 數 ×N 檔會逼近上限）、或需要即時/intraday。
3. **真正該做的是頻率限制處理優化**（低成本、高價值）：預檢用量、明確處理 HTTP **402**、退避重試、優先批次而非逐檔。詳見第四節。

---

## 二、現況（Codebase）

- **定位**：FinMind 是「備援」，非主力。資料融合策略以 Yahoo（即時股價/52 週高低）+ FinLab（ROE/殖利率/PE/名稱）為主（見 `CONTEXT.md`）。
- **批次快照**：`app/market_scanner.py:155` `update_market_snapshot_finmind()` 用 `taiwan_stock_daily(start_date=近5日)` 取全市場收盤 + `taiwan_stock_per_pbr(start_date=latest_date)` 取 PE/PB/殖利率，合併後存快照。**已是批次、request 數極省。**
- **逐檔來源**：`app/data/sources/finmind_source.py` 的 `get_stock_price()` 用 `taiwan_stock_daily(stock_id=...)`（單檔）；供 `DataManager._get_with_fallback`（`app/data/manager.py:890`）在 Yahoo 之後備援。
- **缺口**：
  - `finmind_source.py` 與 scanner 的 FinMind 區塊**沒有任何頻率限制/重試/退避處理**（無 `sleep`/`retry`/`402` 判斷）。
  - `update_market_snapshot_finmind` 以 `except Exception: return False` 吞掉所有錯誤 → 402（超限）、金鑰失效、資料集無權限全部混為「失敗」，UI 只能猜（現行 UI 已硬編一段「免費版 register 批次受限」的臆測訊息）。
  - 既有 `finmind_api_permissions_report.md`（2025-10-30）顯示：`taiwan_stock_info/price/per_pbr/margin` ✅；`financial_statement/dividend/month_revenue/holding_shares_per` ❌（部分為 API 參數簽名問題，部分疑為權限）。

---

## 三、FinMind 方案與限制（2026-07 查證）

- **請求上限**：未註冊 **300 次/小時**；註冊並驗證 email、帶 token → **600 次/小時**；另有 **Sponsor Pro** 付費方案提供更高上限與更多資料集（官方 Donate/Sponsor 頁，實際數字依當前方案為準）。
- **超限行為**：HTTP **402**，body `{"msg":"Requests reach the upper limit. https://finmindtrade.com/","status":402}`。
- **用量查詢**：`GET https://api.web.finmindtrade.com/v2/user_info`（帶 Bearer token）回 `user_count`（已用）與 `api_request_limit`（上限）；FinMind Python 亦有 `api.api_usage_limit`。→ **可在跑批次前預檢，避免中途 402。**

> 註：Sponsor Pro 的精確 request/小時與資料集清單官方文件未完整公開，升級前請至官方 Donate 頁或聯絡確認；不要以本文數字當合約值。

---

## 四、頻率限制處理優化（建議實作，依優先序）

1. **【高】明確處理 402 與錯誤分類**：把 `except Exception: return False` 拆開——攔截 402 → 回傳「已達每小時上限，請稍後或升級」；金鑰/權限錯誤 → 回傳對應訊息。讓 UI 顯示真因，而非硬編臆測。
2. **【高】批次前預檢用量**：跑大量抓取前先打 `user_info`，若 `user_count` 接近 `api_request_limit` 就提前警告/中止，附「剩餘 X 次、Y 分鐘後重置」。
3. **【中】退避重試**：對 402/timeout 做指數退避 + jitter（如 1s→2s→4s，上限 3 次）；純網路錯誤重試，402 不硬重試（改等待或中止）。
4. **【中】優先批次、避免逐檔迴圈**：深度分析若需 FinMind，盡量用「依日期一次抓全市場」而非 for-loop 逐檔；逐檔會把 request 數 ×N，才是真正逼近上限的來源。
5. **【中】善用既有 SQLite 快取**：同一交易日的快照/價量落地快取（專案已有 cache 層），避免重複抓取消耗額度。
6. **【低】集中頻率控制**：在 `FinMindSource` 包一層輕量 rate-limiter（記錄本小時用量），跨呼叫共用。

> 這些都不需付費升級即可完成，且能把現行「一失敗就整批 return False」的體驗大幅改善。

---

## 五、決策矩陣

| 情境 | 是否需要 FinMind Pro | 該做什麼 |
|:---|:---|:---|
| 現行每日全市場快照（批次 by date） | ❌ 不需要 | 第四節 1~5 的防呆即可 |
| 改逐檔深度財報/股利/月營收 | ⚠️ 可能需要 | 先確認資料集在 register 層是否可用；不行才評估 Pro |
| 需要 `financial_statement`/`dividend`/`month_revenue` | ⚠️ 視權限 | 先修 API 參數簽名問題，再判斷是否權限限制 |
| 即時/intraday | ✅ 需要 | 免費層不適用 |

**建議**：維持 FinMind 為備援、不升級 Pro；優先投入第四節第 1、2 項（402 處理 + 用量預檢），投資報酬最高。若日後要做逐檔財報分析，再單獨評估 Pro。

---

## Sources

- 專案：`app/market_scanner.py:155`、`app/data/sources/finmind_source.py`、`app/data/manager.py:890`、`CONTEXT.md`、`finmind_api_permissions_report.md`
- [FinMind API 使用次數（含 402 超限、user_info 用量查詢）](https://finmind.github.io/api_usage_count/)
- [FinMind Quick start](https://finmind.github.io/quickstart/)
- [FinMind 官方網站 / Sponsor 方案](https://finmindtrade.com/)
