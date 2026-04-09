# Investment Monitor

개인 투자 모니터링 + 자동매매 시스템. 매일 시장 데이터를 수집하고, 투자 룰에 따른 트리거를 판정하여 이메일/텔레그램 리포트를 발송하고, 한투 API로 자동매매를 실행한다.

## 핵심 원칙
- 급락 트리거 매수는 **449180(환헤지)만**, **한투 종합계좌**에서 실행
- ISA는 **순수 정기매수(DCA)만** (월 100만 전액, 트리거 없음)
- 자동매매 대상: 지수 ETF만 (개별주는 모니터링만)
- config.yaml의 현금(`cash`) 및 급락 버퍼(`trigger_buffer_krw`) 매달 1일 수동 업데이트
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
@docs/auto-trading-plan.md
@docs/db-schema.md
@docs/references/investment-philosophy.md
