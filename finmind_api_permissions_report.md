# FinMind API 權限檢查報告

**檢查日期**: 2025-10-30 15:25:10  
**Token 狀態**: ✅ 已設定

---

## 1. Token 有效性

✅ **Token 有效且可正常使用**

---

## 2. 可用資料集

**可用**: 4 個資料集

| 資料集 | 說明 | 測試結果 |
|--------|------|----------|
| `taiwan_stock_info` | 台股基本資訊 | ✅ 3992 筆 |
| `taiwan_stock_price` | 台股每日股價 | ✅ 5 筆 |
| `taiwan_stock_per_pbr` | 台股本益比、股價淨值比 | ✅ 19 筆 |
| `taiwan_stock_margin_purchase_short_sale` | 台股融資融券 | ✅ 19 筆 |


**不可用**: 4 個資料集

| 資料集 | 說明 | 原因 |
|--------|------|------|
| `taiwan_stock_financial_statement` | 台股財務報表 | ❌ DataLoader.taiwan_stock_financial_statement() got an unexpected keyword argument 'date' |
| `taiwan_stock_dividend` | 台股股利政策表 | ❌ {"msg":"start_date parameter is missing.","status":400} |
| `taiwan_stock_month_revenue` | 台股月營收 | ❌ 'NaTType' object has no attribute 'asfreq' |
| `taiwan_stock_holding_shares_per` | 台股股權分散表 | ❌ DataLoader.taiwan_stock_holding_shares_per() got an unexpected keyword argument 'date' |

---

## 3. 請求頻率限制

**測試結果**:
- 總請求數: 10
- 成功: 10
- 失敗: 0
- 總耗時: 10.86秒
- 平均每次: 1.09秒

✅ **未遇到明顯的頻率限制**

---

## 4. 歷史資料深度

| 時間範圍 | 狀態 | 筆數 | 實際範圍 |
|----------|------|------|----------|
| 1年 | ✅ 可用 | 244 | 2024-10-30 ~ 2025-10-30 |
| 3年 | ✅ 可用 | 726 | 2022-10-31 ~ 2025-10-30 |
| 5年 | ✅ 可用 | 1215 | 2020-11-02 ~ 2025-10-30 |
| 10年 | ✅ 可用 | 2439 | 2015-11-02 ~ 2025-10-30 |

---

## 5. 限制與建議

### ✅ 付費版優勢

- 更高的請求頻率限制
- 完整的資料集存取
- 更深的歷史資料

### 💡 使用建議

1. **快取策略**: 使用本地快取減少 API 請求
2. **請求延遲**: 請求之間加入適當延遲（0.5-1秒）
3. **錯誤處理**: 實作完整的錯誤處理與重試機制
4. **備援方案**: 考慮整合其他資料源（如 yfinance）

---

**報告生成時間**: 2025-10-30 15:25:10
