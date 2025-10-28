@echo off
chcp 65001 >nul
title 持股分析工具
color 0A

echo.
echo ========================================
echo           持股分析工具 v1.0
echo ========================================
echo.
echo [系統] 正在啟動分析程式...
echo.

cd /d "%~dp0"

python analyze_my_stocks.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================
    echo [錯誤] 分析過程發生錯誤
    echo ========================================
) else (
    echo.
    echo ========================================
    echo [完成] 分析已完成！
    echo [提示] 請查看 reports 資料夾中的 Excel 報告
    echo ========================================
)

echo.
pause
