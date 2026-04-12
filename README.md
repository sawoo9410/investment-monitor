# Investment Monitor

개인 투자 모니터링 자동화 시스템.
매일 아침 시장 데이터를 수집하고, 투자 룰에 따른 트리거를 판정하여 이메일 리포트를 발송한다.

## 주요 기능

- **지수 ETF 다기간 수익률** 추적 (전월/3M/6M/1Y)
- **449180 급락 트리거** 판정 (전월 -5%/-10%, 2달 전 -5%/-10%)
- **133690 매도 트리거** 판정 (전월 +5% AND 평단 +15%)
- **개별주 펀더멘탈 트래킹** (PER/ROE/D/E/Margin)
- **포트폴리오 비중 한도** 체크 (섹터/개별/현금)
- **이메일 데일리 리포트** 발송 (Gmail SMTP)

## 실행 환경

- **GitHub Actions**: 평일 KST 07:00 자동 실행 (`cron: "0 22 * * 0-4"`)
- **수동 실행**: GitHub Actions 탭에서 `workflow_dispatch`

## 설치

```bash
pip install -r requirements.txt
```

## 환경변수

| 변수명 | 필수 | 용도 |
|--------|:----:|------|
| `EXCHANGERATE_API_KEY` | O | ExchangeRate API 키 |
| `ALPHAVANTAGE_API_KEY` | O | Alpha Vantage API 키 |
| `GMAIL_ADDRESS` | O | 발신/수신 Gmail 주소 |
| `GMAIL_APP_PASSWORD` | O | Gmail 앱 비밀번호 |

## 실행

```bash
python main.py
```

## 프로젝트 구조

```
investment-monitor/
├── main.py                  # 메인 오케스트레이터 (5단계 파이프라인)
├── config.yaml              # 포트폴리오/전략 설정
├── requirements.txt
├── modules/
│   ├── market_data.py       # 시장 데이터 수집 (Alpha Vantage + FinanceDataReader)
│   ├── fx_checker.py        # 환율 구간 판정
│   └── notifier.py          # HTML 이메일 리포트 생성 및 발송
├── docs/                    # 프로젝트 문서
└── .github/workflows/
    └── daily_report.yml     # GitHub Actions 워크플로우
```

## 데이터 소스

| API | 용도 | 제한 |
|-----|------|------|
| ExchangeRate API | USD/KRW 환율 | 월 1,500회 |
| Alpha Vantage | 미국 주식 가격/펀더멘탈 | 일 25회 |
| FinanceDataReader | 한국 ETF 가격 | 제한 없음 |
