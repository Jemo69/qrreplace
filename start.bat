@echo off
cd /d %~dp0
where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
  set PORT=3200
  uv run server.py
) else (
  pip install -r requirements.txt
  set PORT=3200
  python server.py
)
pause
