# 台股智慧估值器 📈

一個基於現金流量折現法（DCF）的台股估值工具，專為散戶投資人設計。

## ✨ 功能特色

- **DCF 股票估值** - 基於巴菲特價值投資理念的精準計算
- **即時台股數據** - 整合 FinLab、FinMind、yfinance 多數據源
- **歷史回測** - 驗證投資策略的歷史表現
- **風險分析** - 提供風險評估和壓力測試
- **視覺化報表** - 直觀的圖表展示分析結果
- **智慧報告匯出** - PDF/Excel 報告自動包含投資建議，方便檔案管理 ✨ **NEW**

## 🛠️ 技術架構

- **FinLab** - 台股數據源
- **Python** - 後端計算引擎
- **Streamlit** - Web 應用介面
- **SQLite** - 本地數據庫
- **Plotly** - 數據視覺化

## 📡 數據源與 API 限制

本專案整合多個台股數據源，確保數據的可靠性與完整性：

### 主要數據源

1. **FinMind API** ⭐ 主要來源
   - 台股基本資訊、每日股價、本益比等
   - 歷史數據深度：**10年以上**
   - 請求頻率：建議間隔 0.5-1 秒
   - Token 設定：在 `.env` 中設定 `FINMIND_TOKEN`

2. **yfinance** - 備援來源
   - 提供 EPS、財務報表等數據
   - 國際股市也支援
   - 無需 API Token

3. **FinLab** - 輔助來源（價格數據）
   - 台股價格數據
   - 免費版功能有限
   - Token 設定：在 `.env` 中設定 `FINLAB_API_TOKEN`

### API 權限檢查

我們提供了完整的 API 權限檢查工具，可以幫助您了解當前 Token 的功能範圍：

```bash
# 執行權限檢查
python test_finmind_permissions.py
```

檢查結果會生成詳細報告：[finmind_api_permissions_report.md](finmind_api_permissions_report.md)

**報告內容包含**：
- ✅ Token 有效性驗證
- ✅ 可用資料集清單（共8種）
- ✅ 請求頻率限制測試
- ✅ 歷史資料深度測試（1/3/5/10年）
- ✅ 使用建議與限制說明

### 建議配置

**最佳配置**（推薦）：
- FinMind Token（付費版）
- FinLab Token（可選）
- 自動備援到 yfinance

**最低配置**（免費）：
- FinMind Token（免費版）
- 使用 yfinance 作為主要 EPS 來源

### 數據來源優先序

系統會自動按照以下優先序獲取數據：

**EPS 數據**：yfinance → FinMind → 預設值  
**財務數據**：yfinance → FinMind → 快取  
**價格數據**：FinLab → FinMind → yfinance

### 常見問題

**Q: 為什麼有些股票無法獲取數據？**  
A: 某些小型股或新上市股票可能在部分數據源中沒有完整數據。系統會自動嘗試其他數據源。

**Q: 如何提升數據獲取成功率？**  
A: 
1. 設定 FinMind API Token（免費申請）
2. 確保網路連線穩定
3. 檢查股票代碼是否正確（4位數字）

**Q: API 請求次數有限制嗎？**  
A: 免費版有較嚴格的限制，建議使用本地快取減少請求次數。付費版限制較寬鬆。

更多詳細資訊請參閱 [finmind_api_permissions_report.md](finmind_api_permissions_report.md)

## 🚀 快速開始

### 環境需求
- Python 3.8+
- FinLab 帳戶
- 4GB RAM 以上

### 安裝步驟

1. **複製專案**
```bash
git clone <repository-url>
cd stock-valuation-tool
```

2. **安裝依賴**
```bash
pip install -r requirements.txt
```

3. **設定環境變數**
編輯 `.env` 文件，填入您的 FinLab API 金鑰：
```env
FINLAB_API_KEY=your_api_key_here
FINLAB_SECRET=your_secret_here
```

4. **運行應用**

**Windows 用戶（推薦）:**

使用**英文版 PowerShell 腳本**（避免編碼問題）：
```powershell
.\run-en.ps1
```

或右鍵點擊 `run-en.ps1` → 選擇「以 PowerShell 執行」

系統會自動：
- 檢查 Python 環境
- 安裝必要的依賴套件（FinMind + yfinance）
- 啟動應用並開啟瀏覽器
- **純英文顯示，無編碼問題**

**手動啟動:**
```bash
cd stock-valuation-tool
pip install -r requirements.txt
cd app
streamlit run main.py
```

5. **開啟瀏覽器**
前往 `http://localhost:8501` 開始使用

## 📚 計算方法說明

本工具使用多種財務計算方法進行股票估值與風險分析。詳細的計算公式、原理說明與實務範例，請參閱：

📖 **[完整計算方法說明文件](CALCULATION_METHODS.md)** - 深入理解計算原理與理論推導  
⚡ **[公式速查表](FORMULA_REFERENCE.md)** - 快速查詢所有計算公式與參數 ✨ **NEW**

該文件包含：

### 第一章：DCF 估值方法
- **DCF 折現現金流模型** - 巴菲特推崇的內在價值計算法
- **折現率計算** - CAPM 模型與無風險利率、風險溢價
- **現金流預測** - 兩階段成長模型（高成長期 + 穩定期）
- **終值計算** - Gordon Growth Model 永續價值
- **敏感性分析** - 多變數敏感性矩陣

### 第二章：風險分析方法
- **VaR (Value at Risk)** - 參數法與歷史模擬法
- **CVaR (條件風險值)** - Expected Shortfall 進階風險指標
- **Monte Carlo 模擬** - 幾何布朗運動隨機模擬
- **波動率分析** - 日波動率與年化波動率
- **Beta 係數** - 系統性風險衡量指標

### 雙層級內容設計
- 🟢 **基礎版** - 適合一般投資人，白話文解釋核心概念
- 🔵 **進階版** - 提供完整數學推導，適合專業用戶深入研究

### 實務範例
文件中包含使用台積電 (2330) 的實際數據進行完整計算示範。

---

## 📊 使用說明

### DCF 估值計算
1. 輸入股票代碼或選擇股票
2. 調整成長率和折現率參數
3. 查看計算結果和潛在獲利率
4. 參考建議進行投資決策

### 歷史回測
1. 選擇股票和時間區間
2. 系統自動計算歷史估值
3. 查看回測結果和績效指標

### 風險分析
1. 選擇風險評估模型
2. 調整參數進行模擬
3. 查看風險指標和建議

### 報告匯出 ✨ **NEW**
1. 在「綜合報告」頁面完成分析
2. 點擊「下載 PDF 報告」或「下載 Excel 報告」
3. 檔案名稱自動包含投資建議（例：`2330_台積電_強烈推薦_20251028.pdf`）
4. 方便依投資建議分類管理報告檔案

## 📁 專案結構

```
stock-valuation-tool/
├── app/                    # 應用程式核心
│   ├── main.py            # Streamlit 主程式
│   ├── dcf_calculator.py  # DCF 計算引擎
│   ├── data_manager.py    # 數據管理模組
│   ├── backtest.py        # 回測系統
│   └── risk_analysis.py   # 風險分析
├── data/                  # 數據文件
│   ├── cache.db          # SQLite 數據庫
│   └── config.yaml       # 設定文件
├── requirements.txt      # Python 依賴
├── .env                  # 環境變數
└── README.md            # 專案說明
```

## 🔧 開發說明

### 主要模組

- **DCF Calculator** - 實現現金流量折現計算
- **Data Manager** - 負責數據獲取和緩存
- **Backtest Engine** - 歷史數據回測
- **Risk Analysis** - 風險評估和模擬

### 數據流程

1. FinLab API → 原始數據
2. Data Manager → 數據處理和緩存
3. Calculator → 計算分析
4. Streamlit → 結果展示

## 🤝 貢獻指南

歡迎提交 Issue 和 Pull Request！

## 📄 授權

MIT License

## 📞 聯絡資訊

如有問題請透過 GitHub Issues 聯絡。

---

**注意**：本工具僅供學習和測試用途，投資決策請謹慎評估風險。
