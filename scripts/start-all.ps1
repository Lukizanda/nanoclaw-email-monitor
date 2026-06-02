# Start all NanoClaw services
# Run this after a PC restart to bring everything back up.
#
# Services started:
#   1. OneCLI credential vault (Docker)
#   2. LangChain email classifier MCP server (Python, port 8765)
#   3. NanoClaw host (Node.js)

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$OneCLICompose = "$env:USERPROFILE\.onecli\docker-compose.yml"

Write-Host "Starting NanoClaw services..." -ForegroundColor Cyan

# --- 1. OneCLI ---
Write-Host "`n[1/3] Starting OneCLI credential vault..." -ForegroundColor Yellow
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
Write-Host "`n[2/3] Starting LangChain email classifier MCP server (port 8765)..." -ForegroundColor Yellow
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
Write-Host "`n[3/3] Starting NanoClaw host..." -ForegroundColor Yellow
$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

Start-Process -FilePath "pnpm" -ArgumentList "run", "dev" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogDir "nanoclaw.log") `
    -RedirectStandardError  (Join-Path $LogDir "nanoclaw.error.log")

Write-Host "      NanoClaw host started (logs: logs/nanoclaw.log)" -ForegroundColor Green

Write-Host "`nAll services started." -ForegroundColor Cyan
Write-Host ""
Write-Host "  OneCLI dashboard:  http://127.0.0.1:10254"
Write-Host "  NanoClaw logs:     logs/nanoclaw.log"
Write-Host "  MCP server logs:   logs/mcp-server.log"
Write-Host ""
Write-Host "To stop all services, run: .\scripts\stop-all.ps1"
