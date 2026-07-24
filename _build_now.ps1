$projectDir = "D:\总\小说\写作辅助\自研高级时间线辅助写作agent"
Set-Location $projectDir

Write-Host "[1/2] Building PyInstaller EXE..."
& "C:\Python313\python.exe" -m PyInstaller novel.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PyInstaller build failed!" -ForegroundColor Red
    exit 1
}

Write-Host "[2/2] Copying runtime config files to dist..."
$distDir = Join-Path $projectDir "dist\NovelAgent"

# Copy .env to dist root (needed at runtime for API key fallback)
if (Test-Path (Join-Path $projectDir ".env")) {
    Copy-Item (Join-Path $projectDir ".env") (Join-Path $distDir ".env") -Force
    Write-Host "  OK: .env copied"
} else {
    Write-Host "  WARN: .env not found at project root" -ForegroundColor Yellow
}

# Copy data/settings.json to dist data/ (needed for provider config)
$distDataDir = Join-Path $distDir "data"
if (-not (Test-Path $distDataDir)) {
    New-Item -ItemType Directory -Path $distDataDir -Force | Out-Null
}
$srcSettings = Join-Path $projectDir "data\settings.json"
if (Test-Path $srcSettings) {
    Copy-Item $srcSettings (Join-Path $distDataDir "settings.json") -Force
    Write-Host "  OK: data/settings.json copied"
} else {
    Write-Host "  WARN: data/settings.json not found, LLM will need manual config" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================="
Write-Host "  Build complete! dist/NovelAgent/ is ready."
Write-Host "  Run: .\dist\NovelAgent\NovelAgent.exe"
Write-Host "==========================================="
