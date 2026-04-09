# Investment Monitor

개인 투자 모니터링 + 자동매매 시스템. 매일 시장 데이터를 수집하고, 투자 룰에 따른 트리거를 판정하여 이메일/텔레그램 리포트를 발송한다.

## 브랜치 구조

| 브랜치 | 역할 | 실행 환경 |
|--------|------|----------|
| `main` | 이메일 리포팅 전용 | GitHub Actions (평일 07:00 KST) |
| `feature/auto-trading` | 자동매매 시스템 | 로컬 (Windows 작업 스케줄러) |

## 로컬 실행 (feature/auto-trading)

### 1. 가상환경 설치

```bash
bash scripts/setup_venv.sh
```

또는 수동:
```bash
python -m venv .venv
.venv/Scripts/pip install lxml
.venv/Scripts/pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env.example`을 복사해서 `.env` 생성 후 값 입력:

```bash
cp .env.example .env
```

필수 변수:
| 변수 | 용도 |
|------|------|
| `EXCHANGERATE_API_KEY` | 환율 API |
| `ALPHAVANTAGE_API_KEY` | Alpha Vantage (미국 주식) |
| `GMAIL_ADDRESS` | 이메일 발신/수신 |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 |
| `DB_PATH` | SQLite 경로 (기본: `data/investment.db`) |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 |
| `TELEGRAM_CHAT_ID` | 텔레그램 채팅 ID |

### 3. 수동 실행

```bash
.venv/Scripts/python main.py
```

### 4. 자동 실행 (Windows 작업 스케줄러)

스케줄 등록:
```cmd
schtasks /create /tn "InvestmentMonitor_KR" /tr "C:\Users\sawoo\investment-monitor\scripts\run_report.bat" /sc weekly /d MON,TUE,WED,THU,FRI /st 15:45 /f
```

확인:
```cmd
schtasks /query /tn "InvestmentMonitor_KR" /fo LIST
```

삭제:
```cmd
schtasks /delete /tn "InvestmentMonitor_KR" /f
```

### 스케줄

| 시간 | 내용 | 상태 |
|------|------|:----:|
| 07:00 | 이메일 상세 리포트 | GitHub Actions (main) |
| 15:45 | 국내 종가 텔레그램 리포트 | Windows 스케줄러 |
| 향후 | 08:50 국내 주문 / 22:20 미국 주문 | 한투 API 연동 후 |

## 프로젝트 구조

```
investment-monitor/
├── main.py                  # 메인 오케스트레이터
├── config.yaml              # 포트폴리오/전략 설정
├── .env                     # 환경변수 (git 제외)
├── .env.example             # 환경변수 템플릿
├── requirements.txt         # Python 의존성
├── modules/
│   ├── market_data.py       # 시장 데이터 수집 (Alpha Vantage + FDR)
│   ├── fx_checker.py        # 환율 구간 판정
│   ├── notifier.py          # HTML 이메일 리포트
│   ├── db.py                # SQLite DB 연동
│   ├── telegram.py          # 텔레그램 알림
│   ├── ai_summary.py        # AI 요약 (비활성화)
│   └── perplexity_summary.py # Perplexity (미구현)
├── scripts/
│   ├── setup_venv.sh        # 가상환경 설치
│   ├── run_report.sh        # WSL cron용 (미사용)
│   ├── run_report.bat       # Windows 스케줄러용
│   └── init_db.sql          # DB 테이블 생성
├── data/
│   └── investment.db        # SQLite DB (git 제외)
├── docs/
│   ├── architecture.md      # 아키텍처
│   ├── investment-rules.md  # 투자 룰
│   ├── api-reference.md     # API 레퍼런스
│   ├── auto-trading-plan.md # 자동매매 구현 계획
│   ├── db-schema.md         # DB 스키마
│   └── devlog.md            # 개발 로그
└── .github/workflows/
    └── daily_report.yml     # GitHub Actions (main 브랜치)
```

## 문서

- [투자 룰](docs/investment-rules.md) - 매매 트리거, 비중 한도, 체크리스트
- [자동매매 계획](docs/auto-trading-plan.md) - 세션별 구현 로드맵
- [DB 스키마](docs/db-schema.md) - 테이블 설계
- [아키텍처](docs/architecture.md) - 모듈별 역할, 데이터 흐름
- [API 레퍼런스](docs/api-reference.md) - 외부 API, 환경변수
- [개발 로그](docs/devlog.md) - 작업 기록
