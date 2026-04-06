# API 및 환경변수 레퍼런스

## 외부 API

### ExchangeRate API
- **용도**: USD/KRW 실시간 환율 조회
- **엔드포인트**: `https://v6.exchangerate-api.com/v6/{key}/latest/USD`
- **제한**: 월 1,500회 (무료 플랜)
- **호출 수**: 실행당 1회

### Alpha Vantage
- **용도**: 미국 주식 실시간 가격, 일별 시계열, 펀더멘탈(PER/ROE 등)
- **엔드포인트**:
  - `GLOBAL_QUOTE` — 실시간 가격 + 전일 등락
  - `TIME_SERIES_DAILY` — 일별 종가 시계열 (전월 baseline, 다기간 수익률)
  - `OVERVIEW` — 펀더멘탈 지표 (PER, ROE, D/E, Margin, 52주 고가)
- **제한**: 일 25회, 분당 5회
- **호출 수**: 종목당 2~3회 (가격 + baseline + 펀더멘탈)
- **주의사항**:
  - 분당 5회 제한 때문에 `time.sleep()` 필수
  - SPYM 다기간 조회 시 15초 대기 하드코딩됨
  - API 한도 초과 시 `Note` 또는 `Information` 키로 응답
  - 호출 카운터: `market_data.AV_API_CALLS` / `AV_DAILY_LIMIT`

### FinanceDataReader
- **용도**: 한국 ETF 가격 및 다기간 시계열 조회
- **특징**: API 키 불필요, 호출 제한 없음
- **사용 종목**: 360750, 449180, 133690 (`.KS` 접미사 제거 후 조회)
- **호출 패턴**: `fdr.DataReader(ticker, start_date)`

### Gmail SMTP
- **용도**: HTML 이메일 리포트 발송
- **서버**: `smtp.gmail.com:465` (SSL)
- **인증**: Gmail 앱 비밀번호 사용

### Claude API (비활성화)
- **용도**: 거시경제 AI 요약 (웹검색 포함)
- **모델**: claude-sonnet-4-6 + web_search tool
- **상태**: main.py에서 import 주석 처리, Perplexity 전환 예정

## 환경변수 (GitHub Secrets)

| 변수명 | 필수 | 용도 |
|--------|------|------|
| `EXCHANGERATE_API_KEY` | Y | ExchangeRate API 키 |
| `ALPHAVANTAGE_API_KEY` | Y | Alpha Vantage API 키 |
| `GMAIL_ADDRESS` | Y | 발신/수신 Gmail 주소 |
| `GMAIL_APP_PASSWORD` | Y | Gmail 앱 비밀번호 |
| `ANTHROPIC_API_KEY` | N | Claude API 키 (현재 비활성화) |
| `TELEGRAM_BOT_TOKEN` | N | 텔레그램 봇 토큰 (미구현) |
| `TELEGRAM_CHAT_ID` | N | 텔레그램 채팅 ID (미구현) |

## 실행 방법

### GitHub Actions (자동)
- **스케줄**: 평일(월~금) KST 07:00 (`cron: "0 22 * * 0-4"`)
- **수동 실행**: GitHub Actions 탭에서 `workflow_dispatch`

### 로컬 실행
```bash
# 환경변수 설정 후
python main.py
```

## 의존성 (requirements.txt)
| 패키지 | 용도 |
|--------|------|
| requests | HTTP API 호출 |
| pyyaml | config.yaml 파싱 |
| pytz | KST 타임존 처리 |
| pandas | 데이터 처리 (FinanceDataReader 의존) |
| beautifulsoup4 + lxml | HTML 파싱 (FinanceDataReader 의존) |
| finance-datareader | 한국 ETF 데이터 조회 |
| anthropic | Claude API (비활성화 상태) |
| sendgrid | 이메일 (미사용, Gmail SMTP로 대체됨) |
| python-telegram-bot | 텔레그램 알림 (미구현) |
