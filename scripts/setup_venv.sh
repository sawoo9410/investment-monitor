#!/bin/bash
# 가상환경 생성 + 의존성 설치
# 사용법: bash scripts/setup_venv.sh

set -e

cd "$(dirname "$0")/.."

echo "=== 가상환경 생성 ==="
python -m venv .venv

echo "=== 의존성 설치 ==="
.venv/Scripts/pip install --upgrade pip -q
.venv/Scripts/pip install lxml -q
.venv/Scripts/pip install -r requirements.txt -q

echo "=== 설치 완료 ==="
echo "활성화: source .venv/Scripts/activate (Git Bash)"
echo "실행: .venv/Scripts/python main.py"
