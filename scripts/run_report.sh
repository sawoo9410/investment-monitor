#!/bin/bash
# 국내 종가 리포트 실행 (WSL cron용)
# crontab: 45 15 * * 1-5 /mnt/c/Users/sawoo/investment-monitor/scripts/run_report.sh

cd /mnt/c/Users/sawoo/investment-monitor
export PYTHONIOENCODING=utf-8
/mnt/c/Users/sawoo/investment-monitor/.venv/Scripts/python.exe main.py >> /mnt/c/Users/sawoo/investment-monitor/logs/cron_$(date +\%Y\%m\%d).log 2>&1
