# 프로젝트 아키텍처

## 개요
GitHub Actions로 평일 오전 7시(KST)에 자동 실행되는 개인 투자 모니터링 시스템.
시장 데이터를 수집하고, 투자 룰에 따른 트리거를 판정한 뒤, HTML 이메일 리포트를 발송한다.

## 디렉토리 구조

```
investment-monitor/
├── main.py                  # 메인 오케스트레이터 (5단계 파이프라인)
├── config.yaml              # 포트폴리오/전략 설정 (종목, 환율 구간, 비중 한도)
├── requirements.txt         # Python 의존성
├── modules/
│   ├── market_data.py       # 시장 데이터 수집 (Alpha Vantage + FinanceDataReader)
│   ├── fx_checker.py        # 환율 구간 판정 및 변경 감지
│   ├── notifier.py          # HTML 이메일 리포트 생성 및 Gmail SMTP 발송
│   ├── ai_summary.py        # AI 거시경제 요약 (Claude API + 웹검색, 비활성화 상태)
│   └── perplexity_summary.py # Perplexity Sonar 요약 (미구현, TODO)
├── docs/                    # 프로젝트 문서
└── .github/workflows/
    └── daily_report.yml     # 평일 자동 실행 (cron: UTC 22:00 = KST 07:00)
```

## 실행 파이프라인 (main.py)

```
[1/5] 환율 조회 → ExchangeRate API
  └─ ISA 활성 종목 결정 (환율 >= 1380 → 449180, 미만 → 360750)

[2/5] 주식 데이터 수집
  ├─ 한국 ETF → FinanceDataReader (360750, 449180, 133690)
  │   ├─ 지수 ETF: 다기간 수익률 (전월/3M/6M/1Y)
  │   ├─ ISA 매수 트리거 판정 (-5%, -10%)
  │   └─ ISA 매도 트리거 판정 (133690: +5%, +10%)
  └─ 미국 주식 → Alpha Vantage (SPYM, GOOGL, OXY, QCOM, SOUN, NVDA)
      ├─ 지수 ETF(SPYM): 다기간 수익률
      ├─ 개별주: 전월 baseline + 펀더멘탈 (PER/ROE/D/E/Margin)
      └─ QCOM 조건부 매수 판정 (PER <= 25 && 52주 고점 -15%)

[3/5] holdings_only 종목 가격 조회 (현재 비어 있음)

[4/5] 포트폴리오 비중 계산
  ├─ 현금: ISA 원화 + 토스 원화 + 토스 달러(환산)
  ├─ 종목별 평가액 및 비중
  └─ 섹터별 비중 집계

[5/5] 포트폴리오 한도 체크
  ├─ AI/테크 섹터 <= 20%
  ├─ OXY <= 10%
  └─ 현금 15% ~ 25%
```

## 모듈별 역할

### market_data.py
- **한국 ETF**: FinanceDataReader로 가격/다기간 baseline 조회 (API 제한 없음)
- **미국 주식**: Alpha Vantage로 실시간 가격, 일별 시계열, 펀더멘탈 조회
- API 호출 카운터 내장 (`AV_API_CALLS` / `AV_DAILY_LIMIT=25`)
- 모든 함수에 retry 로직 포함 (기본 3회)

### fx_checker.py
- 환율을 4개 구간(전액환전/정상전액/정상절반/보류)으로 분류
- 구간 변경 감지 함수 제공 (`detect_fx_zone_change`)

### notifier.py
- HTML 이메일 리포트 생성 (CSS 인라인 스타일)
- 섹션: 환율 → 중요 알림 → 포트폴리오 비중 → 현금 현황 → 지수 ETF 테이블 → 개별주 테이블
- 지수 ETF 테이블 하단에 매수 트리거 기준가 표시 (ISA 활성 종목 + SPYM)
- Gmail SMTP SSL (포트 465) 사용

### ai_summary.py (비활성화)
- Claude API + 웹검색으로 거시경제 요약 생성
- 주요 지수, 투자자 심리(VIX, Fear & Greed), 종목별 뉴스, 이벤트 캘린더 포함
- main.py에서 import 주석 처리됨

## 데이터 흐름

```
ExchangeRate API  ─┐
FinanceDataReader ─┤─→ main.py ─→ notifier.py ─→ Gmail SMTP ─→ 이메일
Alpha Vantage     ─┘      │
                    config.yaml
                    (종목/전략/현금)
```
