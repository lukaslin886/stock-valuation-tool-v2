# 台股 DCF 估值工具 - 開發日誌歷史歸檔

> **本檔案包含專案早期版本 (v1.0.0 - v1.5.3) 的詳細開發記錄。**  
> **最新版本請參閱**: [DEVELOPMENT_LOG.md](./DEVELOPMENT_LOG.md)

---

## v1.5.3 (2025-10-28) - MOPS 資料源整合（方案 B+ 簡化版）

**實作目標**: 整合 MOPS（公開資訊觀測站）作為輔助資料源，專注於股本異動表

**實作成果**:

1. **完成 MOPSSource 類別實作** (`app/data/sources/mops_source.py`)
   - 簡化版策略：專注於股本異動表與公司資訊
   - 不處理財報數據（交由 FinMind）
   - 完整的快取機制（7天過期）
   - 民國年 ↔ 西元年轉換函式

2. **整合到 DataManagerV2** (`app/data/manager.py`)
   - 新增 `get_shares_outstanding()` 方法
   - 優先序：**MOPS（第一優先）** → FinMind → 預設值
   - 記憶體與 SQLite 雙層快取

3. **建立測試工具**:
   - `test_mops_source.py` - 完整測試套件
   - `debug_mops_response.py` - API 回應調試工具

**已知限制**: MOPS API 端點目前不可用（HTTP 404）

**架構價值**: 完整的程式架構已建立，可隨時啟用（當 API 可用時）

---

## v1.5.2 (2025-10-28) - 報告功能優化

**核心成果**:
- ✅ PDF/Excel 檔案名稱加入投資建議
- ✅ 實作 `get_recommendation_short_name()` 函式
- ✅ 檔案命名格式：`{股票代碼}_{股票名稱}_{投資建議簡稱}_{日期}`

**技術實現**:

**投資建議簡稱對應表**:
- "強烈推薦買入" → "強烈推薦"
- "推薦買入" → "推薦買入"
- "可考慮" → "可考慮"
- "不建議投資" → "不建議"

**使用者價值**:
1. 從檔名直接看出投資建議
2. 便於依投資建議整理檔案
3. 追蹤同一股票不同時期的建議變化

**檔案範例**:
- `2330_台積電_強烈推薦_20251028.pdf`
- `2330_台積電_強烈推薦_20251028.xlsx`

---

## v1.5.0 (2025-10-28) - 負成長率支援

**核心成果**:
- ✅ 調整成長率輸入範圍：-50% 到 50%
- ✅ 負成長時顯示警告訊息（黃色）
- ✅ 添加輸入提示 `help="可輸入負值表示衰退"`

**問題**: 輸入「中鋼」等負成長股票時，出現 `StreamlitValueBelowMinError` 錯誤

**解決方案**:
1. 調整 `min_value` 允許負值
2. 加入值範圍保護機制
3. 視覺提示區分正常成長與衰退

**影響範圍**:
- DCF 估值頁面（4 個 number_input）
- 歷史回測頁面（2 個 number_input）

---

## v1.4.0 (2025-10-28) - 資料層模組化重構

**重構目標**: 將單一的 `data_manager.py`（~900行）重構為清晰的模組化架構

**設計模式**: Strategy Pattern（策略模式）

**新架構**:
```
app/data/
├── sources/                    # 資料來源模組
│   ├── __init__.py
│   ├── base.py                 # DataSource 抽象基礎類別
│   ├── yfinance_source.py      # YFinance 資料源實作
│   └── finmind_source.py       # FinMind 資料源實作
├── cache/                      # 快取後端模組
│   ├── __init__.py
│   ├── base.py                 # CacheBackend 抽象基礎類別
│   └── sqlite_cache.py         # SQLite 快取實作
└── __init__.py                 # 統一匯出介面
```

**核心設計**:

1. **DataSource 抽象類別** - 統一介面規範
2. **YFinanceSource** - 完整的 yfinance 實作
3. **FinMindSource** - 完整的 FinMind 實作
4. **CacheBackend 抽象類別** - 快取後端介面
5. **SQLiteCache** - SQLite 快取實作

**技術優勢**:
- ✅ 清晰的職責分離
- ✅ 高度可擴展性
- ✅ 未來擴展容易 (TWSE OpenAPI, XBRL)
- ✅ 統一的錯誤處理
- ✅ 完整的向下相容

**測試驗證**: 所有模組測試通過（100% 成功率）

---

## v1.3.0 (2025-10-28) - yfinance 整合增強

**核心成果**:
- ✅ 修復 PDF 中文顯示問題（字型支援）
- ✅ 增強 yfinance 整合為主要 EPS 資料源
- ✅ 實作多層備援資料獲取機制

**實作細節**:

**三個新輔助方法**:
1. `_normalize_yfinance_ticker()` - 台股代碼轉換
2. `_fetch_eps_from_yfinance()` - EPS 多來源獲取
3. `_fetch_financial_from_yfinance()` - 完整財務數據

**資料獲取優先序**:

**get_latest_eps()**:
```
1️⃣ yfinance (主要) 
2️⃣ FinMind (備援)
3️⃣ 預設值/0
```

**get_financial_data()**:
```
1️⃣ yfinance (主要)
2️⃣ FinMind (備援)
3️⃣ 快取資料
```

**技術優勢**:
- ✅ 覆蓋率提升 - yfinance 支援更多股票
- ✅ 多欄位嘗試 - 5種不同的 EPS 欄位來源
- ✅ 向下相容 - API 介面完全不變

---

## v1.2.0 (2025-10-28) - 報告匯出功能

**核心成果**:
- ✅ 新增報告匯出功能
- ✅ 支援 Excel 格式匯出（含多工作表）
- ✅ 支援 PDF 格式匯出（含圖表）
- ✅ 實作 ReportGenerator 模組

**技術實現**:

**新模組: report_generator.py**
- 使用 openpyxl 生成 Excel 報告
- 使用 reportlab 生成 PDF 報告
- 支援 Plotly 圖表轉圖片功能

**Excel 報告功能**:
- 多工作表架構：摘要、DCF詳細分析、風險分析
- 完整的格式化：標題樣式、表格邊框、顏色填充
- 自動欄寬調整與對齊設定
- 數值格式化（千分位、百分比）

**PDF 報告功能**:
- A4 頁面大小，專業排版
- 包含所有關鍵數據表格
- 支援圖表嵌入（現金流預測圖）
- 自定義樣式與顏色配置

**依賴套件更新**:
```
reportlab>=4.0.0       # PDF 生成
kaleido>=0.2.1         # Plotly 圖表轉圖片
Pillow>=10.0.0         # 圖片處理
```

---

## v1.1.0 (2025-10-28) - FinLab 整合

**核心成果**:
- ✅ 整合 FinLab 作為主要資料源
- ✅ 實作多層備援機制（FinLab → FinMind → yfinance）
- ✅ 修復 DataFrame merge 類型錯誤（8處）
- ✅ 識別 FinLab 免費版限制（不支援財務數據）

**挑戰與解決**:

1. **環境配置**
   - 安裝 finlab 套件 (v1.5.3)
   - 配置 FINLAB_API_TOKEN

2. **DataFrame 類型錯誤**
   - 問題: merge 操作時出現類型不一致錯誤
   - 解決: 統一使用 `pd.to_datetime()` 轉換

3. **免費版限制發現**
   - FinLab 免費版無法存取財務數據
   - 決策: 財務數據改用 FinMind，價格數據可用 FinLab

**最終架構**:
```
資料類型       主要來源    備援1      備援2
----------------------------------------
財務數據       FinMind    yfinance   N/A
價格數據       FinLab     FinMind    yfinance
```

---

## v1.0.0 (2025-10-27) - 初始版本發布

**專案資訊**:
- **專案名稱**: 台股 DCF 估值工具 (Taiwan Stock DCF Valuation Tool)
- **開發日期**: 2025年10月26-27日
- **開發者**: AI協作開發
- **專案目的**: 為台股散戶投資者提供基於 DCF（現金流折現）模型的股票估值分析工具

**技術棧**:

### 後端
- **Python 3.13**
- **數據來源**: FinMind API（主要）、yfinance（備用）
- **數據庫**: SQLite 3（本地快取）
- **科學計算**: NumPy, Pandas, SciPy

### 前端
- **Streamlit 1.30+**: Web 應用框架
- **Plotly 5.18+**: 互動式圖表

**核心功能模組**:

1. **DCF 估值計算** (dcf_calculator.py)
   - 基於現金流折現模型計算股票內在價值
   - 敏感性分析、多情境模擬

2. **數據管理系統** (data_manager.py)
   - 整合多數據源，提供統一的數據介面
   - 主要數據源: FinMind API
   - 備用數據源: yfinance
   - 本地快取: SQLite 資料庫

3. **歷史回測引擎** (backtest.py)
   - 驗證 DCF 模型的歷史預測準確度
   - 分析指標：預測準確率、平均預測誤差、相關係數

4. **風險分析模組** (risk_analysis.py)
   - VaR 分析：參數法、歷史模擬法、CVaR
   - Monte Carlo 模擬：價格路徑模擬與機率分析
   - 技術指標：波動率、Beta 係數

5. **Web 應用介面** (main.py)
   - Streamlit 多頁面應用
   - 頁面：DCF 估值分析、歷史回測、風險分析、綜合報告

**開發時間軸**:

### 2025-10-26
- **階段 1**: 專案規劃與初始設置
- **階段 2**: 技術選型困難
  - 原計劃使用 FinLab 套件
  - 發現版本問題，改用 FinMind + yfinance 雙數據源架構
- **階段 3**: 核心功能開發

### 2025-10-27 凌晨
- **階段 4**: 依賴套件安裝問題
  - 問題: setuptools.build_meta 導入失敗
  - 原因: Python 3.13 兼容性問題
  - 解決: 更新 requirements.txt，使用 `>=` 版本限制

- **階段 5**: 功能測試與問題診斷
  - 測試股票: 2330（台積電）
  - 發現多處問題：日期型態、欄位映射、EPS 獲取

- **階段 6**: 問題修復
  1. **日期型態轉換** (backtest.py)
  2. **FinMind API 欄位映射** (data_manager.py)
  3. **EPS 數據獲取優化** - 三層備援機制
  4. **錯誤處理與日誌增強**

**技術決策記錄**:

### 決策 1: 數據源選擇
- **決策**: 採用 FinMind + yfinance
- **理由**: FinLab 版本問題、雙數據源提高穩定性

### 決策 2: 本地快取策略
- **決策**: 使用 SQLite 本地快取
- **理由**: 減少 API 請求、提升響應速度

### 決策 3: Python 版本選擇
- **決策**: 保持 Python 3.13 並更新套件
- **理由**: 使用最新版本長期更有利

### 決策 4: 前端框架選擇
- **決策**: Streamlit
- **理由**: 快速開發、Python 原生支援、無需前端知識

**測試結果**:

| 功能頁面 | 狀態 | 備註 |
|---------|------|------|
| DCF 估值 | ✅ | 修復後正常 |
| 歷史回測 | ✅ | 修復後正常 |
| 風險分析 | ✅ | 完全正常 |
| 綜合報告 | ✅ | 修復後正常 |

**效能指標**:

### 首次執行（無快取）
- 總啟動時間: ~10-15 秒

### 後續執行（有快取）
- 總啟動時間: ~2-3 秒

**已知限制**:

1. **數據源限制**
   - FinMind 免費版有請求次數限制
   - 部分財務指標可能不完整

2. **功能限制**
   - 僅支援台股（.TW）
   - DCF 模型假設較簡化

3. **使用體驗**
   - 首次載入需要時間（建立快取）
   - 錯誤訊息對一般用戶不夠友善

**檔案結構**:
```
stock-valuation-tool/
├── .env                    # 環境變數
├── .env.example            # 環境變數範本
├── .gitignore              # Git 忽略檔案清單
├── README.md               # 專案說明文檔
├── DEVELOPMENT_LOG.md      # 開發日誌
├── requirements.txt        # Python 依賴套件
├── run.ps1                 # PowerShell 啟動腳本
├── run.bat                 # Batch 啟動腳本
├── app/                    # 應用程式主目錄
│   ├── main.py             # Streamlit 主程式
│   ├── dcf_calculator.py   # DCF 估值計算引擎
│   ├── data_manager.py     # 數據管理器
│   ├── backtest.py         # 歷史回測引擎
│   └── risk_analysis.py    # 風險分析模組
└── data/                   # 數據目錄（快取）
    └── cache.db            # SQLite 快取資料庫
```

**套件依賴**:
```
FinMind>=0.4.0          # 台股數據 API
yfinance>=0.2.36        # Yahoo Finance API（備援）
streamlit>=1.30.0       # Web 框架
pandas>=2.2.0           # 數據處理
numpy>=1.26.0           # 數值計算
plotly>=5.18.0          # 互動圖表
scipy>=1.12.0           # 科學計算
```

**授權與使用**:
- **專案性質**: 個人使用工具
- **免責聲明**: 本工具僅供教育和研究用途

---

**最後更新**: 2025-10-28  
**歸檔版本**: v1.0.0 - v1.5.3  
**維護者**: AI 協作開發

> 📌 **回到最新版本**: [DEVELOPMENT_LOG.md](./DEVELOPMENT_LOG.md)
