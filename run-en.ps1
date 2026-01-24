# Stock Valuation Tool - Launcher (English Version)
# Encoding: UTF-8

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Stock Valuation Tool Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python installation
Write-Host "[1/3] Checking Python environment..." -NoNewline
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
        Write-Host "      Version: $pythonVersion" -ForegroundColor Gray
    }
    else {
        throw "Python not found"
    }
}
catch {
    Write-Host " Failed" -ForegroundColor Red
    Write-Host ""
    Write-Host "[ERROR] Python not found. Please install Python 3.8 or higher" -ForegroundColor Red
    Write-Host "Download: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""

# Check dependencies
Write-Host "[2/3] Checking dependencies..." -NoNewline
try {
    python -c "import streamlit" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host " Installed" -ForegroundColor Green
    }
    else {
        Write-Host " Need installation" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "[INFO] First run. Installing dependencies..." -ForegroundColor Yellow
        Write-Host ""
        
        # Step 1: Upgrade pip, setuptools, wheel
        Write-Host "[Step 1/2] Upgrading pip, setuptools, and wheel..." -ForegroundColor Cyan
        python -m pip install --upgrade pip setuptools wheel
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Host "[WARNING] Failed to upgrade build tools. Continuing anyway..." -ForegroundColor Yellow
        }
        else {
            Write-Host "[SUCCESS] Build tools upgraded successfully" -ForegroundColor Green
        }
        Write-Host ""
        
        # Step 2: Install dependencies
        Write-Host "[Step 2/2] Installing project dependencies..." -ForegroundColor Cyan
        $reqPath = Join-Path $PSScriptRoot "requirements.txt"
        pip install -r $reqPath
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "[SUCCESS] Dependencies installed successfully" -ForegroundColor Green
        }
        else {
            Write-Host ""
            Write-Host "[ERROR] Failed to install dependencies" -ForegroundColor Red
            Write-Host ""
            Read-Host "Press Enter to exit"
            exit 1
        }
    }
}
catch {
    Write-Host " Check failed" -ForegroundColor Red
}

Write-Host ""

# Start application
Write-Host "[3/3] Starting Streamlit application..." -ForegroundColor Cyan
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Application is starting..." -ForegroundColor Green
Write-Host "   Browser will open at http://localhost:8501" -ForegroundColor Green
Write-Host ""
Write-Host "   Press Ctrl+C to stop the application" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to app directory and start
# Navigate to app directory and start
Set-Location (Join-Path $PSScriptRoot "app")
streamlit run main.py

Write-Host ""
Write-Host "Application closed" -ForegroundColor Yellow
Read-Host "Press Enter to exit"
