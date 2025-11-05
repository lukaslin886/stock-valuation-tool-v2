@echo off
REM ========================================
REM pytest 測試執行腳本 (Windows)
REM ========================================

echo.
echo ========================================
echo   Stock Valuation Tool - pytest 測試
echo ========================================
echo.

REM 檢查是否安裝 pytest
python -c "import pytest" 2>nul
if errorlevel 1 (
    echo [錯誤] 未安裝 pytest，正在安裝...
    pip install pytest pytest-cov pytest-html pytest-timeout
    if errorlevel 1 (
        echo [錯誤] 安裝失敗！
        pause
        exit /b 1
    )
)

REM 建立報告目錄
if not exist "reports" mkdir reports
if not exist "htmlcov" mkdir htmlcov

echo.
echo [資訊] 開始執行測試...
echo.

REM 切換到腳本所在目錄
cd /d "%~dp0"

REM 執行測試
python -m pytest tests\ -v --cov=app --cov-report=html --cov-report=term-missing --html=reports\test_report.html --self-contained-html

set TEST_RESULT=%ERRORLEVEL%

echo.
echo ========================================
if %TEST_RESULT% equ 0 (
    echo   測試完成！
    echo   - HTML 報告: reports\test_report.html
    echo   - 覆蓋率報告: htmlcov\index.html
) else (
    echo   測試失敗！請檢查錯誤訊息。
)
echo ========================================
echo.

pause
exit /b %TEST_RESULT%
