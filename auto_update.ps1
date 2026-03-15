$cd = "C:\Stock_test"
Set-Location $cd
$env:PYTHONUTF8 = 1
$logFile = "C:\Stock_test\logs\auto_update.log"

if (-not (Test-Path "C:\Stock_test\logs")) { New-Item -Path "C:\Stock_test\logs" -ItemType Directory -Force | Out-Null }

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Out-File -Append -Encoding utf8 $logFile
}

# Use -C to explicitly specify repo path for all git commands
# Trim output to avoid whitespace/newline causing false mismatch
$before = (git -C $cd rev-parse HEAD 2>$null) | Out-String
$before = $before.Trim()
git -C $cd pull gitee main 2>$null
$after = (git -C $cd rev-parse HEAD 2>$null) | Out-String
$after = $after.Trim()

# Safety: if either is empty, skip restart (git command failed)
if ([string]::IsNullOrEmpty($before) -or [string]::IsNullOrEmpty($after)) {
    Log "WARN: git rev-parse failed (before=$before, after=$after), skipping restart"
    # Only do health check — never restart
    $proc = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
    if (-not $proc) {
        Log "Streamlit not running, starting..."
        Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -Command cd C:\Stock_test; `$env:PYTHONUTF8=1; streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true" -WindowStyle Hidden
        Log "Streamlit started (was down)"
    }
    exit
}

if ($before -eq $after) {
    # No change, just health check
    $proc = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
    if (-not $proc) {
        Log "Streamlit not running, starting..."
        Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -Command cd C:\Stock_test; `$env:PYTHONUTF8=1; streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true" -WindowStyle Hidden
        Log "Streamlit started (was down)"
    }
    exit
}

# Code actually changed -> log and restart
$changes = git -C $cd log --oneline $before..$after 2>$null
Log "Code updated: $before -> $after"
Log "Changes: $changes"

$listening = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    $pid = $listening.OwningProcess
    Log "Stopping Streamlit (PID: $pid)..."
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Start-Sleep 2
}

Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -Command cd C:\Stock_test; `$env:PYTHONUTF8=1; streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true" -WindowStyle Hidden
Start-Sleep 3
Log "Streamlit restarted successfully"
