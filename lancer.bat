@echo off
cd /d "%~dp0"
python -m pip install -q -U flask yt-dlp
start "" http://127.0.0.1:5050
python app.py
pause
