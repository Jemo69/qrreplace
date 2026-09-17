@echo off
cd /d %~dp0
pip install -r requirements.txt
set PORT=3200
python server.py
pause
