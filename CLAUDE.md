# Investment Monitor

개인 투자 모니터링 자동화 시스템. 매일 아침 시장 데이터를 수집하고 투자 룰에 따른 트리거를 판정하여 이메일 리포트를 발송한다.

## 핵심 원칙
- 룰 베이스 매수는 **449180(환헤지)만** 실행 (환율 고려 불필요)
- 정기매수는 ISA 활성 종목(환율 기준 360750/449180 전환)으로 진행
- config.yaml의 현금(`cash`) 값은 매달 1일 수동 업데이트 필요
- Alpha Vantage API는 일 25회 제한 — 호출 최소화 필수

## 코딩 규칙
- 한국어 주석/출력 사용
- 모든 외부 API 호출에 retry 로직 포함 (기본 3회)
- 금액 표시: 한국 ETF는 `₩`, 미국 주식은 `$`
- API 응답에 `Note` 또는 `Information` 키가 있으면 한도 초과 처리

## 문서
@docs/architecture.md
@docs/investment-rules.md
@docs/api-reference.md
