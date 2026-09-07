# cron 規則引擎現況核實基準文件（需求 0）

## 1. 核對資訊

| 項目 | 內容 |
|---|---|
| 核對日期 | 2026-09-07 |
| 執行者 | Claude（IDE agent，工單 3） |
| 核對對象 1 | `C:/Users/林皇辰/AppData/Local/hermes/scripts/stock_advisor.py`（517 行，完整逐行讀取） |
| 核對對象 2 | `C:/Users/林皇辰/AppData/Local/hermes/scripts/run_daily_advice.py`（85 行，完整讀取） |
| 核對對象 3 | `C:/Users/林皇辰/AppData/Local/hermes/scripts/low_base_screener.py`（309 行，完整讀取） |
| 核對對象 4 | `C:/Users/林皇辰/AppData/Local/hermes/scripts/stock_update.py`（84 行，完整讀取） |
| 對照文件 | `.kiro/specs/cron-rule-engine-canonical-core/requirements.md` 第 11-16 行「前置事實」 |

---

## ⚠️ 與 spec 前置事實的出入（非門檻數值錯誤，是文件遺漏的判斷條件）

核對後確認：spec 前置事實段落列出的**六條規則門檻數值全部正確**，沒有任何一個數字錯誤。但實際程式碼存在三處文件完全沒提到的邏輯細節，可能影響需求 1 的 Canonical_Core 判定基礎，已同步更新 spec 前置事實段落（見下方「已更新 spec」小節）：

1. **過熱規則（MA20 乖離 >15%）的判斷順序在分類之前，對所有分類（含存股）都適用**——不是只套用在波段類。（`stock_advisor.py:349-350`）
2. **存股分類的股票在規則引擎中永遠不會產生 🟢 買入訊號**——`decide_signal()` 對 `cls == "存股"` 的三個分支（跌破 MA60 連續3根／跌破未滿3根／其他）都必定 `return`，不會執行到後面的買入判斷。也就是說「買入規則只有一套」不只是文件摘要的簡化，而是程式碼結構上的必然結果：買入邏輯實質上只對「波段」分類生效。（`stock_advisor.py:351-374`）
3. **market_scan.db 有獨立於 K 棒陳舊守門之外的第二種資料新鮮度檢查**：`FUND_STALE_DAYS=5`，用於基本面資料（PE/殖利率）過期警示，只在 Telegram 訊息加一行警示文字，不影響買賣訊號分類。文件摘要的「資料守門」只提到 K 棒 >5 天，沒提到這條。（`stock_advisor.py:200, 419-426, 463-465`）

---

## 2. 逐條核對表

| # | Spec 前置事實摘要 | 判定 | 實際邏輯 | 行號 |
|---|---|---|---|---|
| 1 | 存股分類：殖利率≥4% 且 PE>0 | ✅ 相符 | `DIVIDEND_YIELD_THRESHOLD=4.0`；`classify_stock()`：`fund` 非空 且 `yield_ >= 4.0` 且 `pe > 0` → 回傳「存股」，否則「波段」 | `195`, `335-342` |
| 2 | 存股賣出：跌破 MA60 連續 3 根 | ✅ 相符 | `below60_n = int((close < ma60_s).tail(3).sum())`；`cls=="存股"` 且 `price < ma60` 且 `below60_n >= 3` → 🔴 賣出；未滿3根 → 🟡 觀察 | `296`, `353-356` |
| 3 | 波段賣出：連續 2 根 <MA20 且 MA5<MA10 且放量 | ✅ 相符 | `below20_n = int((close < ma20_s).tail(2).sum())`；`below20_n>=2` 且 `ma5<ma10` 且 `vol_ratio>1.0` → 🔴 波段出場 | `295`, `359-361` |
| 4 | 買入：MA5>MA10>MA20 且 MA20 向上且乖離 -3%~5% 且 52週位置 ≤60% 且 PE≥0 | ✅ 相符（附註：MA20向上=與5個交易日前的MA20比較；乖離=MA5乖離bias5，非MA20乖離） | `bull = ma5>ma10>ma20 and ma20>ma20_prev`（`ma20_prev`=`rolling(20).mean().iloc[-6]`，即5日前）；`BIAS_BUY_MIN,MAX=-3.0,5.0`；`POSITION_BUY_MAX=0.60`；`pe>=0`（`pe` 缺資料時預設 `0.0`，剛好滿足 `>=0`，不會因缺資料被排除） | `196-197`, `285`, `362-369` |
| 5 | 過熱：MA20 乖離 >15% | ⚠️ 有出入（門檻正確，但判斷順序遺漏） | `MA20_OVERHEAT=15.0`；`decide_signal()` 一開頭就檢查 `bias20 > 15` → 🟡，**在存股/波段分類判斷之前**，對所有分類（含存股）都優先適用，文件摘要未提及此優先順序 | `198`, `349-350` |
| 6 | 資料守門：最後 K 棒 >5 天視為陳舊 | ⚠️ 有出入（K棒守門本身相符，但遺漏另一條獨立的資料守門） | `STALE_DAYS=5`；`age=(today_utc - last_date).days`；`age>5` → 該檔不出訊號，列入「資料陳舊」清單。**另外還有** `FUND_STALE_DAYS=5`：`market_scan.db` 的 `last_updated` 超過5天 → `fund_stale=True`，Telegram 訊息加警示行（不排除訊號，只加警語），文件摘要完全沒提到這條 | `199-200`, `437-442`, `419-426`, `463-465` |
| 7 | （文件遺漏）存股分類股票不會產生買入訊號 | 📌 文件遺漏 | `decide_signal()` 對 `cls=="存股"` 的三個 return 分支涵蓋所有情況，不會執行到後面波段/買入判斷區塊 | `351-374` |
| 8 | （文件遺漏）大盤趨勢（^TWII）加註 | 📌 文件遺漏 | `fetch_market_trend()` 算加權指數 MA5/10/20 多空狀態；買入清單若大盤偏弱（`not above_ma20`）則在個股理由後加「⚠️大盤偏弱，建議縮減部位/分批」 | `50-79`, `455-458`, `486-488` |
| 9 | （文件遺漏）JoJo／利潤品質標記 | 📌 文件遺漏（不影響訊號分類，僅顯示標記） | `_jojo_tag()`／`_quality_tag()` 讀 `market_scan.db`／FinMind 附加 PE/ROE/外資連買/營益率/CFO 標記於個股顯示列，DB 無資料則不顯示，不影響 🟢/🟡/🔴 判定 | `92-161`, `475-478` |

---

## 3. `stock_advisor.py` 讀取 `market_scan.db` 的欄位清單

**直接 SQL 查詢**（`load_fundamentals()`，`stock_advisor.py:317-318`）：

```sql
SELECT stock_code, pe_ratio, pb_ratio, dividend_yield, roe, last_updated FROM market_snapshot
```

六個欄位：`stock_code`、`pe_ratio`、`pb_ratio`（讀取但規則引擎判斷未使用）、`dividend_yield`、`roe`（讀取但規則引擎判斷未使用，僅用於顯示）、`last_updated`。

**間接透過 `SQLiteCache`**（`_jojo_tag()`，`stock_advisor.py:92-161`，僅供標記顯示、不影響訊號）：
- `cache.get_snapshot(code)` → `pe_ratio`、`roe`
- `cache.get_chip_data(code, days=30)` → `foreign_buy`、`foreign_sell`（算外資連買天數）

---

## 4. Telegram 訊息確切格式（摘錄樣板，`stock_advisor.py:460-513`）

```
📊 持股建議 2026/09/07 ｜ 大盤(🔥多頭排列（積極進攻）)
🟢買入 3 ｜ 🟡持有 40 ｜ 🔴賣出 2（分析 45/50 檔）

⚠️ 基本面資料過期（2026-09-01），PE/殖利率僅供參考          ← 僅 fund_stale=True 時出現

**建議買入：**
  台積電 (2330.TW) 現價 1050.0｜乖離 +2.3%｜位置 45%｜PE 25｜PE25/ROE20%｜外資連買3天｜營益率56%/CFO正
    MA5>MA10>MA20 多頭排列，乖離 +2.3%，52週位置 45%，PE 25，可分批布局
  …另有 N 檔買入訊號未顯示                                    ← buys 數量 > BUY_SELL_DISPLAY(5) 時出現

**建議賣出：**
  XX (XXXX.TW) 現價 XX.X｜乖離 -X.X%｜位置 XX%｜殖 X.X%（存股）
    存股跌破季線 MA60（XX.X）連續3根，停利/停損檢視

ℹ️ 未對應代號 N 檔：XX、XX；抓取失敗 N 檔：XX；資料陳舊 N 檔：XX(N天)   ← 僅有資料時出現
⚠️ 建議僅供參考，AI 分析非投資建議
```

`fmt(r)` 個股列格式固定為：
`  {name} ({code}) 現價 {price:.1f}｜乖離 {bias5:+.1f}%｜位置 {pos*100:.0f}%{extra}{jojo標記}{品質標記}\n    {reason}`

其中 `extra` 為存股顯示「殖 X.X%（存股）」，波段且 PE>0 顯示「PE X」，否則空字串。買入/賣出各只顯示前 `BUY_SELL_DISPLAY=5` 檔，超過則追加「…另有 N 檔…未顯示」。

---

## 5. 均線還原判定

**結論：有還原（`auto_adjust=True`）。**

證據（`stock_advisor.py`）：
- 第 4 行 docstring：「yfinance 抓 1y 日線（auto_adjust=True 還原價）→ MA5/10/20/60、乖離率、52週位置、量能比」
- 第 54 行 `fetch_market_trend()`：`h = t.history(period="3mo", auto_adjust=True)`
- 第 270 行 `fetch_metrics()` docstring：「auto_adjust=True：還原價，避免除息跳空造成假訊號（F5 P0）」
- 第 276 行 `fetch_metrics()` 實際呼叫：`h = t.history(period="1y", auto_adjust=True)`

所有 MA5/10/20/60、乖離率、52週高低、量能比的計算輸入皆為還原後收盤價/成交量，除息當天不會產生假的跌破均線訊號。

**附註（非 spec 核對範圍，但相關）**：`low_base_screener.py:121` 的 `fetch_52w()` 呼叫 `t.history(period="1y")` **未明確傳入 `auto_adjust` 參數**，是否還原取決於當時安裝的 yfinance 版本預設值（未核實版本）。但 `low_base_screener.py` 只算 52 週高低與現價位置，不算 MA，不涉及「跌破均線」判斷，此差異不影響 spec 前置事實核對的結論。

---

## 6. 工單 7 兩條推論核實結果

**① 買入規則是否真的只有一套（動能型），而賣出規則分存股/波段兩套？**

**成立，且比推論本身描述得更絕對。** `decide_signal()`（`351-374`）中，`cls=="存股"` 分支的三個 `return`（跌破MA60連續3根／未滿3根／其他）涵蓋了存股類的所有情況，函式邏輯上不可能落到後面的買入判斷區塊。因此不只是「賣出規則分存股/波段兩套、買入規則一套」，而是「買入規則這一套實際上只對波段分類的股票生效，存股分類的股票在此規則引擎下結構性地不會出現 🟢 訊號」。

**② 存股分類條件「殖利率≥4%」在殖利率資料缺失時的實際行為？**

**歸類為波段，不會被排除。** `classify_stock()`（`335-342`）：若 `fund` 為空字典（該股票代號不在 `market_scan.db` 的 `market_snapshot` 表）→ `if fund:` 為假 → 直接回傳「波段」。若 `fund` 存在但 `dividend_yield` 欄位為 `NULL`，`load_fundamentals()`（`320-326`）已用 `float(dy) if dy else 0.0` 把它正規化為 `0.0`，`0.0 < 4.0` → 同樣落到「波段」。兩種缺失情況都不會讓該股票被跳過分析，只是分類為波段而非存股。

---

## 7. 已更新 spec

已依需求 0 驗收準則第 2 條，於 `requirements.md` 前置事實段落補充上述三點文件遺漏（過熱規則優先順序、存股不會有買入訊號、FUND_STALE_DAYS 獨立守門），見該文件第 11-16 行附近的新增段落。核心六條規則的門檻數值本身沒有錯誤，故不修改既有敘述，僅新增補充說明。
