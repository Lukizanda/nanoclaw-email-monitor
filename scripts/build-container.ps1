# Build the NanoClaw agent container image with the correct Windows slug.
# Use this instead of bash ./container/build.sh on Windows.

$ProjectRoot = Split-Path $PSScriptRoot -Parent

# Compute slug the same way TypeScript does — sha1(projectRoot)[:8]
$sha1 = [System.Security.Cryptography.SHA1]::Create()
$bytes = [System.Text.Encoding]::UTF8.GetBytes($ProjectRoot)
$hash = $sha1.ComputeHash($bytes)
$slug = ($hash | ForEach-Object { $_.ToString("x2") }) -join "" | Select-Object -First 1
$slug = (($hash | ForEach-Object { $_.ToString("x2") }) -join "").Substring(0, 8)

$ImageName = "nanoclaw-agent-v2-$slug"
$Tag = if ($args[0]) { $args[0] } else { "latest" }

Write-Host "Building NanoClaw agent container image..." -ForegroundColor Cyan
Write-Host "Image: ${ImageName}:${Tag}"
Write-Host "Slug: $slug (from Windows path: $ProjectRoot)"

Set-Location (Join-Path $ProjectRoot "container")
docker build -t "${ImageName}:${Tag}" .

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild complete! Image: ${ImageName}:${Tag}" -ForegroundColor Green
} else {
    Write-Host "`nBuild failed." -ForegroundColor Red
    exit 1
}
