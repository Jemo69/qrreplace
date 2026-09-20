# Build the single QRReplace.exe — everything inside, no installers.
Set-Location $PSScriptRoot
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run pyinstaller qrreplace.spec --noconfirm
} else {
    pip install -r requirements.txt pyinstaller
    pyinstaller qrreplace.spec --noconfirm
}
Write-Host ""
Write-Host "DONE: dist\QRReplace.exe  (double-click to run)"
