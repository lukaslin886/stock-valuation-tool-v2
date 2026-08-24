# Stock Valuation Tool - Mobile Tunnel Launcher
# Using Cloudflare Tunnel to expose local Streamlit (Port 8501)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Mobile Testing Tunnel (Cloudflare)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (!(Test-Path ".\cloudflared.exe")) {
    Write-Host "[ERROR] cloudflared.exe not found in current directory." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[1/2] Checking if application is running..." -ForegroundColor Gray
Write-Host "      Make sure you have started the tool via run-en.ps1 first!" -ForegroundColor Yellow
Write-Host ""

Write-Host "[2/2] Starting Secure Tunnel to port 8501..." -ForegroundColor Cyan
Write-Host "      Please wait for the 'https://xxx.trycloudflare.com' link to appear below." -ForegroundColor Green
Write-Host "      You can then scan the QR code or type the URL on your phone." -ForegroundColor White
Write-Host ""
Write-Host "      Press Ctrl+C to stop the tunnel" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

.\cloudflared.exe tunnel --url http://127.0.0.1:8501
