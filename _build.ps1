$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

Write-Host "[1/3] Building frontend..."
Set-Location "$projectDir\frontend"
npx vite build
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Frontend build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  OK"
Set-Location $projectDir

Write-Host "[2/3] Building PyInstaller EXE..."
& "C:\Python313\python.exe" -m PyInstaller novel.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PyInstaller build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  OK"

Write-Host "[3/3] Creating release ZIP..."
Compress-Archive -Path "$projectDir\dist\NovelAgent\*" -DestinationPath "$projectDir\dist\NovelAgent_$((Get-Date).ToString('yyyyMMdd')).zip" -Force
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: ZIP creation failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  OK"

Write-Host ""
Write-Host "==========================================="
Write-Host "  Build complete!"
Write-Host "  EXE:  dist\NovelAgent\NovelAgent.exe"
Write-Host "  ZIP:  dist\NovelAgent_$(Get-Date -Format yyyyMMdd).zip"
Write-Host ""
Write-Host "  Note: .env and data/settings.json are NOT bundled."
Write-Host "  User must provide their own API key on first launch."
Write-Host "==========================================="
