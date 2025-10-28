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
