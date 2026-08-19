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

## 限制

本次 baseline 是 deterministic local input，不代表即時 API 品質判定；因此不應據此刪除
MOPS、FinLab 或任何 Legacy 資料來源。`market_scan` 與 `cache` 欄位明確標記為尚未捕獲，
等待 Task 3.3/3.4 的可重現 fixture。