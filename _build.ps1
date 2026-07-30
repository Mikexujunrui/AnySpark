$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

$version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
if ($LASTEXITCODE -ne 0) { throw "Unable to read project version" }

Write-Host "[1/5] Installing build dependencies..."
python -m pip install -r requirements-desktop.txt

Write-Host "[2/5] Building frontend..."
npm ci --prefix frontend
npm run build --prefix frontend

Write-Host "[3/5] Building AnySpark.exe..."
python -m PyInstaller --noconfirm --clean novel.spec

Write-Host "[4/5] Creating portable ZIP..."
$portableZip = "$projectDir\dist\AnySpark_${version}_Windows_x64_portable.zip"
if (Test-Path $portableZip) { Remove-Item $portableZip -Force }
Compress-Archive -Path "$projectDir\dist\AnySpark\*" -DestinationPath $portableZip

Write-Host "[5/5] Creating installer when Inno Setup is available..."
$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $defaultIscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $defaultIscc) { $iscc = Get-Item $defaultIscc }
}
if ($iscc) {
    & $iscc.FullName "/DMyAppVersion=$version" "$projectDir\packaging\windows\AnySpark.iss"
} else {
    Write-Host "  Inno Setup not found; portable ZIP was still created." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Build complete:"
Write-Host "  EXE:       dist\AnySpark\AnySpark.exe"
Write-Host "  Portable:  dist\AnySpark_${version}_Windows_x64_portable.zip"
Write-Host "  Installer: dist\installer\AnySpark_${version}_Windows_x64_Setup.exe (when ISCC is installed)"
Write-Host ""
Write-Host "User data is stored outside the installation directory in %APPDATA%\AnySpark."
