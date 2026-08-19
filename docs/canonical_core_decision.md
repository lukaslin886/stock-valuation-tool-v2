# Canonical Core 判定紀錄

日期：2026-08-19

## 目前證據

`tests/golden_master/capture_baseline.py` 使用 20 個代表性台股代碼與固定本地輸入，
比較 `app/dcf_calculator.py` 和 `app/services/dcf_calculator.py` 的 DCF 數值。

初步結果：

- `intrinsic_value` 與 `upside_potential` 數值一致。
- Legacy 回傳 `dict`，並包含 `cash_flows`、`present_values`。
- Layered 回傳 `DCFResult`，目前不包含 `cash_flows`、`present_values`。
- 因輸出契約尚未等價，暫不將 Layered 直接接到所有既有 views。

## 暫定模組決策

| 模組 | 暫定決策 | 理由 | 下一個證據 |
|:---|:---|:---|:---|
| DCF 數值核心 | Layered 優先 | 固定輸入下數值一致，且已有型別模型與測試 | 補齊詳細現金流欄位或建立 adapter 後回歸 |
| DCF 輸出契約 | Legacy 相容 adapter | 既有 views 依賴 `dict`、`cash_flows`、`present_values` | Golden Master 回歸測試 |
| 市場資料來源 | 待判定 | 尚未在相同 API 條件下量測 MOPS/FinLab 完整度與失敗率 | Task 3.3 實測表 |
| 市場掃描 | 待判定 | Legacy 與 Layered 的資料模型與快取邊界不同 | Task 3.4 fixture 比對 |
| 快取層 | 待判定 | Layered 已有 DI/SQLite 測試，但尚未比對 Legacy snapshot 行為 | Task 3.4 fixture 比對 |

## 離線 fixture 探針結果

2026-08-20 使用暫存 SQLite 資料庫執行，不需要 API 金鑰或網路：

- MOPS `get_stock_price()` 與 `get_financial_data()` 均回傳 `None`，因此不能作為完整股價/財報來源。
- Legacy cache 成功寫入並讀回 `stock_info`。
- Layered cache 成功寫入並讀回 `market_snapshot`，並額外回傳 `stale` 狀態。
- Legacy schema 為 `stock_info`、`financial_data`、`price_data`。
- Layered schema 為 `market_snapshot`、`chip_data`、`trade_signals`、`paper_trades`。

據此更新暫定決策：

- **資料來源：保留 MOPS 作為股本異動/公司資訊輔助來源，不作為完整財報或股價 Canonical source；FinLab 作為 Layered 的主要市場資料來源，仍需補 live-source 品質量測。**
- **快取層：Layered 優先，但以 adapter 保留 Legacy 的 `stock_info`/`financial_data`/`price_data` 讀取能力；不可直接共用同一 schema。**

## 限制

本次 baseline 是 deterministic local input，不代表即時 API 品質判定；因此不應據此刪除
MOPS、FinLab 或任何 Legacy 資料來源。`market_scan` 與 `cache` 欄位明確標記為尚未捕獲，
等待 Task 3.3/3.4 的可重現 fixture。