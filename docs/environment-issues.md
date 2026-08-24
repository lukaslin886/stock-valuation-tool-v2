# 環境問題處理紀錄

## SSL 憑證錯誤（curl_cffi / yfinance）

### 問題
yfinance 1.5.1 使用 `curl_cffi`（libcurl 綁定）抓取股價，在 Windows + Hermes venv 環境下報錯：
```
curl: (77) error setting certificate verify locations:
CAfile: ...certifi\cacert.pem CApath: none
```

### 原因
- `curl_cffi` 使用 libcurl，需要同時指定 CAfile + CApath
- Hermes venv 的 certifi 路徑可以找到 CAfile
- 但 Windows 上 OpenSSL 預設的 CApath（`C:\Program Files\Common Files\SSL\certs`）不存在
- 設定 `SSL_CERT_FILE` 和 `CURL_CA_BUNDLE` 環境變數對 libcurl 無效

### 解決方案
不要用 yfinance 內建的 curl_cffi，改用 standard `requests` 直接抓 Yahoo Finance API：

```python
import requests
H = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}', headers=H)
price = r.json()['chart']['result'][0]['meta']['regularMarketPrice']
```

### 受影響的工具
- `E:\OneDrive\CLINE_PROJECT\projects\Finance\stock-valuation-tool\` 的 `update_market_snapshot_finlab()` 方法
- 已寫入 `fix_prices.py` 作為替代方案
- 每週日 cron 會跑 `stock_update.py`（內部呼叫 fix_prices.py）

### 驗證
```bash
cd /e/OneDrive/CLINE_PROJECT/projects/Finance/stock-valuation-tool
python -c "import requests; r=requests.get('https://query1.finance.yahoo.com/v8/finance/chart/2330.TW',headers={'User-Agent':'Mozilla/5.0'}); print(r.json()['chart']['result'][0]['meta']['regularMarketPrice'])"
# 應輸出：2470.0（台積電股價）
```
