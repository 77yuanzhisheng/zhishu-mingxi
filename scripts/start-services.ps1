# start-services.ps1 — 一键启动（或恢复）前后端服务，由 watchdog 守护
# 用法: powershell -ExecutionPolicy Bypass -File scripts\start-services.ps1
# 说明: 启动 scripts/watchdog.py（脱离当前会话），watchdog 负责拉起并守护
#       8000(后端) 与 5500(前端)，服务挂掉会自动重启。

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
$pythonPrefix = @()
if (-not (Test-Path $venvPy)) {
    # Prefer the project-supported Python version when no virtualenv exists.
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $venvPy = $launcher.Source
        $pythonPrefix = @("-3.11")
    } else {
        $python = Get-Command python.exe -ErrorAction Stop
        $venvPy = $python.Source
    }
}

# 端口占用检查
$busy = netstat -ano | Select-String "LISTENING" | Select-String ":8000\s|:5500\s"
if ($busy) {
    Write-Host "以下端口已被占用，先处理再启动守护:" -ForegroundColor Yellow
    $busy | ForEach-Object { Write-Host "  $($_.Line.Trim())" }
}

$logDir = Join-Path $repo "scripts"
$watchdog = Join-Path $repo "scripts\watchdog.py"
# Start-Process receives one command-line string; quote paths because the workspace path contains spaces.
$watchdogArgs = "-u `"$watchdog`""
if ($pythonPrefix.Count -gt 0) { $watchdogArgs = (($pythonPrefix -join " ") + " " + $watchdogArgs) }
Start-Process -FilePath $venvPy -ArgumentList $watchdogArgs -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "watchdog.out.log") -RedirectStandardError (Join-Path $logDir "watchdog.err.log")

Write-Host "watchdog 已启动（后台），正在拉起 8000(后端)/5500(前端)..."
Write-Host "查看状态: Get-Content scripts\services.log -Tail 20"
