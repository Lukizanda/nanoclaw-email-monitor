# Start all NanoClaw services
# Run this after a PC restart to bring everything back up.
#
# Services started:
#   1. OneCLI credential vault (Docker)
#   2. LangChain email classifier MCP server (Python, port 8765)
#   3. NanoClaw host (Node.js)
#   4. Ensure the recurring email-check schedule (idempotent re-seed)

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$OneCLICompose = "$env:USERPROFILE\.onecli\docker-compose.yml"

Write-Host "Starting NanoClaw services..." -ForegroundColor Cyan

# --- 1. OneCLI ---
Write-Host "`n[1/4] Starting OneCLI credential vault..." -ForegroundColor Yellow
if (Test-Path $OneCLICompose) {
    docker compose -p onecli -f $OneCLICompose up -d
    if ($LASTEXITCODE -eq 0) {
        Write-Host "      OneCLI started at http://127.0.0.1:10254" -ForegroundColor Green
    } else {
        Write-Host "      ERROR: OneCLI failed to start. Check Docker is running." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "      ERROR: OneCLI compose file not found at $OneCLICompose" -ForegroundColor Red
    Write-Host "      Run /init-onecli to set it up first." -ForegroundColor Red
    exit 1
}

# Wait for OneCLI to be ready
Write-Host "      Waiting for OneCLI gateway..." -ForegroundColor Gray
for ($i = 1; $i -le 15; $i++) {
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:10254" -UseBasicParsing -ErrorAction Stop
        Write-Host "      Gateway ready." -ForegroundColor Green
        break
    } catch {
        Start-Sleep 1
    }
    if ($i -eq 15) {
        Write-Host "      WARNING: Gateway not responding after 15s. Check OneCLI logs." -ForegroundColor Yellow
    }
}

# --- 2. LangChain MCP Server ---
Write-Host "`n[2/4] Starting LangChain email classifier MCP server (port 8765)..." -ForegroundColor Yellow
$ServerScript = Join-Path $ProjectRoot "email-filter\server.py"
if (Test-Path $ServerScript) {
    Start-Process -FilePath "python" -ArgumentList $ServerScript `
        -WorkingDirectory (Join-Path $ProjectRoot "email-filter") `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $ProjectRoot "logs\mcp-server.log") `
        -RedirectStandardError  (Join-Path $ProjectRoot "logs\mcp-server.error.log")
    Write-Host "      MCP server started (logs: logs/mcp-server.log)" -ForegroundColor Green
} else {
    Write-Host "      WARNING: email-filter/server.py not found. Skipping." -ForegroundColor Yellow
}

# --- 3. NanoClaw Host ---
Write-Host "`n[3/4] Starting NanoClaw host..." -ForegroundColor Yellow
$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# pnpm is a .cmd shim on Windows — Start-Process needs the resolved .cmd path,
# not the bare name (which fails with "not a valid Win32 application").
$pnpmCmd = (Get-Command pnpm.cmd -ErrorAction SilentlyContinue).Source
if (-not $pnpmCmd) { $pnpmCmd = "pnpm.cmd" }
Start-Process -FilePath $pnpmCmd -ArgumentList "run", "dev" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogDir "nanoclaw.log") `
    -RedirectStandardError  (Join-Path $LogDir "nanoclaw.error.log")

Write-Host "      NanoClaw host started (logs: logs/nanoclaw.log)" -ForegroundColor Green

# --- 4. Ensure the recurring email-check schedule exists ---
# The schedule is a kind=task row in the session's inbound.db; if the session
# was ever rebuilt or data wiped, the row is gone. This idempotently re-seeds it
# into the agent group's CURRENT active session. No-op if already present.
# See wiki/schedule-durability.md.
Write-Host "`n[4/4] Ensuring recurring email-check schedule..." -ForegroundColor Yellow
Start-Sleep -Seconds 6   # let the host finish DB init / migrations
Push-Location $ProjectRoot   # pnpm exec must resolve tsx from the project root
try {
    & $pnpmCmd exec tsx scripts/ensure-schedule.ts 2>&1 | ForEach-Object { Write-Host "      $_" }
    Write-Host "      Schedule ensured." -ForegroundColor Green
} catch {
    Write-Host "      WARNING: ensure-schedule failed: $_" -ForegroundColor Yellow
} finally {
    Pop-Location
}

Write-Host "`nAll services started." -ForegroundColor Cyan
Write-Host ""
Write-Host "  OneCLI dashboard:  http://127.0.0.1:10254"
Write-Host "  NanoClaw logs:     logs/nanoclaw.log"
Write-Host "  MCP server logs:   logs/mcp-server.log"
Write-Host ""
Write-Host "To stop all services, run: .\scripts\stop-all.ps1"
