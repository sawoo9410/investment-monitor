# 개발 로그 (2026)

## 2026-04-06

### 논의 사항
- 449180(환헤지) slowly melting 방지를 위한 2달 전 대비 트리거 도입 논의
- 룰 베이스 매수는 449180만 하기로 결정 → 환율 고려 불필요
- 2달 전 트리거 금액: 처음 -5% 50만/-10% 100만으로 설계했으나, 손실 부담 고려해 둘 다 50만원으로 통일
- CLAUDE.md + docs/ 문서 체계 구축 논의 (architecture, investment-rules, api-reference)
- 투자 철학 원문을 docs/references/에 보존하기로 결정
- CHANGELOG.md 도입 — 커밋마다 함께 업데이트
- devlog.md 도입 — 작업 로그 기록, 1년 단위 갱신

### 코드 변경
- `market_data.py`: 다기간 baseline에 `2month` 기간 추가
- `main.py`: 449180 전용 2달 전 매수 트리거 로직 추가
- `notifier.py`: 이메일 리포트에 2달 전 트리거 알림 및 기준가 테이블 추가 (보라색 배경)
- `config.yaml`: 449180 보유수량 0→70, ISA 현금 190만→90만원

### 문서 변경
- `CLAUDE.md` 생성 (메인 진입점, @import로 하위 문서 연결)
- `docs/architecture.md` — 프로젝트 구조, 파이프라인, 모듈별 역할
- `docs/investment-rules.md` — 투자 룰 + 버핏식 원칙/계좌 구조/체크리스트 통합
- `docs/api-reference.md` — API 제한, 환경변수, 의존성
- `docs/references/investment-philosophy.md` — 투자 철학 원문
- `CHANGELOG.md` 생성
- `docs/devlog.md` 생성

### 결정 사항
- git push는 사용자가 직접 실행 (인증 문제)
- 커밋마다 CHANGELOG.md 업데이트 필수

### 버핏 관점 리뷰 (미반영, 추후 검토)
- 133690 매도 트리거 (+5%/+10%)가 너무 공격적일 수 있음
- SOUN은 speculative 타입이 더 적절할 수 있음
- QCOM 매수 조건에 ROE 기준 추가 고려
- 전체 포트폴리오 벤치마크 대비 수익률 추적 기능 없음
