# status.ps1 — 查看前后端服务与守护状态
# 用法: powershell -ExecutionPolicy Bypass -File scripts\status.ps1

$repo = Split-Path -Parent $PSScriptRoot

Write-Host "=== 端口监听 ===" -ForegroundColor Cyan
$p8000 = netstat -ano | Select-String "LISTENING" | Select-String ":8000\s"
$p5500 = netstat -ano | Select-String "LISTENING" | Select-String ":5500\s"
if ($p8000) { Write-Host "  8000 后端: OK" -ForegroundColor Green } else { Write-Host "  8000 后端: 未运行" -ForegroundColor Red }
if ($p5500) { Write-Host "  5500 前端: OK" -ForegroundColor Green } else { Write-Host "  5500 前端: 未运行" -ForegroundColor Red }

Write-Host "=== 健康检查 ===" -ForegroundColor Cyan
try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 5
    Write-Host "  后端 health: $($h.status)" -ForegroundColor Green
} catch {
    Write-Host "  后端 health: 不可达" -ForegroundColor Red
}

Write-Host "=== 守护进程 ===" -ForegroundColor Cyan
$wd = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "watchdog" }
if ($wd) {
    $wd | ForEach-Object { Write-Host "  watchdog pid=$($_.ProcessId)" -ForegroundColor Green }
} else {
    Write-Host "  watchdog 未运行（用 start-services.ps1 启动）" -ForegroundColor Yellow
}

Write-Host "=== 服务日志尾部 ===" -ForegroundColor Cyan
Get-Content (Join-Path $repo "scripts\services.log") -Tail 5 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
