@echo off
echo ========================================
echo   台股 DCF 估值工具啟動器
echo ========================================
echo.

REM 檢查 Python 是否安裝
python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.8 或更高版本
    echo 下載網址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] 檢查 Python 環境... OK
echo.

REM 檢查是否已安裝依賴
echo [2/3] 檢查依賴套件...
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo [提示] 首次運行，需要安裝依賴套件...
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [錯誤] 依賴套件安裝失敗
        pause
        exit /b 1
    )
    echo [完成] 依賴套件安裝成功
) else (
    echo [完成] 依賴套件已安裝
)
echo.

REM 啟動應用
echo [3/3] 啟動 Streamlit 應用...
echo.
echo ========================================
echo   應用正在啟動中...
echo   瀏覽器將自動開啟 http://localhost:8501
echo   
echo   按 Ctrl+C 可以停止應用
echo ========================================
echo.

cd app
streamlit run main.py

pause
