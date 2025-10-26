# 台股 DCF 估值工具 - PowerShell 啟動腳本
# 編碼: UTF-8

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   台股 DCF 估值工具啟動器" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 檢查 Python 是否安裝
Write-Host "[1/3] 檢查 Python 環境..." -NoNewline
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
        Write-Host "      版本: $pythonVersion" -ForegroundColor Gray
    } else {
        throw "Python not found"
    }
} catch {
    Write-Host " 失敗" -ForegroundColor Red
    Write-Host ""
    Write-Host "[錯誤] 找不到 Python，請先安裝 Python 3.8 或更高版本" -ForegroundColor Red
    Write-Host "下載網址: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "按 Enter 鍵退出"
    exit 1
}

Write-Host ""

# 檢查是否已安裝依賴
Write-Host "[2/3] 檢查依賴套件..." -NoNewline
try {
    python -c "import streamlit" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host " 已安裝" -ForegroundColor Green
    } else {
        Write-Host " 需要安裝" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "[提示] 首次運行，正在安裝依賴套件..." -ForegroundColor Yellow
        Write-Host ""
        
        pip install -r requirements.txt
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "[完成] 依賴套件安裝成功" -ForegroundColor Green
        } else {
            Write-Host ""
            Write-Host "[錯誤] 依賴套件安裝失敗" -ForegroundColor Red
            Write-Host ""
            Read-Host "按 Enter 鍵退出"
            exit 1
        }
    }
} catch {
    Write-Host " 檢查失敗" -ForegroundColor Red
}

Write-Host ""

# 啟動應用
Write-Host "[3/3] 啟動 Streamlit 應用..." -ForegroundColor Cyan
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   應用正在啟動中..." -ForegroundColor Green
Write-Host "   瀏覽器將自動開啟 http://localhost:8501" -ForegroundColor Green
Write-Host ""
Write-Host "   按 Ctrl+C 可以停止應用" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 切換到 app 目錄並啟動
Set-Location app
streamlit run main.py

# 如果 Streamlit 正常結束，返回原目錄
Set-Location ..

Write-Host ""
Write-Host "應用已關閉" -ForegroundColor Yellow
Read-Host "按 Enter 鍵退出"
