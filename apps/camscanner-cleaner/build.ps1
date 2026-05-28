$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --noconsole `
  --name "camscanner_cleaner" `
  --specpath "build" `
  --workpath "build\pyinstaller" `
  --distpath "dist" `
  --paths "src" `
  --exclude-module "PyQt5" `
  --exclude-module "PyQt6" `
  --exclude-module "PySide2" `
  --exclude-module "pytest" `
  --exclude-module "IPython" `
  --exclude-module "matplotlib" `
  --exclude-module "pandas" `
  --exclude-module "scipy" `
  --exclude-module "pyarrow" `
  "run_app.py"

$targetName = -join @(
  [char]0x626B,
  [char]0x63CF,
  [char]0x5168,
  [char]0x80FD,
  [char]0x738B,
  [char]0x6C34,
  [char]0x5370,
  [char]0x6E05,
  [char]0x7406,
  [char]0x5668
) + ".exe"
$asciiExe = Join-Path $projectRoot "dist\camscanner_cleaner.exe"
$targetExe = Join-Path (Join-Path $projectRoot "dist") $targetName
if (Test-Path -LiteralPath $targetExe) {
  Remove-Item -LiteralPath $targetExe -Force
}
Move-Item -LiteralPath $asciiExe -Destination $targetExe -Force
Copy-Item -LiteralPath "README.txt" -Destination "dist\README.txt" -Force

Write-Host "Build complete: dist\$targetName"
