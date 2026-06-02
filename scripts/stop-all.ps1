# Stop all NanoClaw services

$OneCLICompose = "$env:USERPROFILE\.onecli\docker-compose.yml"

Write-Host "Stopping NanoClaw services..." -ForegroundColor Cyan

# Stop NanoClaw and MCP server
Write-Host "`n[1/2] Stopping NanoClaw host and MCP server..." -ForegroundColor Yellow
Get-Process -Name "node","bun","python" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "nanoclaw|server\.py" } |
    Stop-Process -Force -ErrorAction SilentlyContinue
# Fallback: stop by window title / any tsx process
Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "      Done." -ForegroundColor Green

# Stop OneCLI
Write-Host "`n[2/2] Stopping OneCLI..." -ForegroundColor Yellow
if (Test-Path $OneCLICompose) {
    docker compose -p onecli -f $OneCLICompose down
    Write-Host "      Done." -ForegroundColor Green
} else {
    Write-Host "      OneCLI compose file not found, skipping." -ForegroundColor Gray
}

Write-Host "`nAll services stopped." -ForegroundColor Cyan
