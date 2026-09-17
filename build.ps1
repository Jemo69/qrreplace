# Build the single QRReplace.exe — everything inside, no installers.
Set-Location $PSScriptRoot
pip install -r requirements.txt pyinstaller
pyinstaller qrreplace.spec --noconfirm
Write-Host ""
Write-Host "DONE: dist\QRReplace.exe  (double-click to run)"
