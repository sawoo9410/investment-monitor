@echo off
chcp 65001 >nul
cd /d C:\Users\sawoo\investment-monitor
set PYTHONIOENCODING=utf-8
C:\Users\sawoo\investment-monitor\.venv\Scripts\python.exe main.py >> logs\cron_%date:~0,4%%date:~5,2%%date:~8,2%.log 2>&1
