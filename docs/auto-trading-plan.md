# 자동매매 전환 구현 계획

> 작성일: 2026-04-08 | 브랜치: feature/auto-trading
> 최종 수정: 2026-04-09 (세션 2 완료 — SQLite DB + .env 환경 구축)

## Context

현재 시스템은 모니터링+이메일 알림만 수행하고 매매는 수동. 룰 베이스 트리거를 실제 주문으로 연결하여 자동매매로 확장한다.

**현재 상태:** 한투 계좌 미개설, API 미신청. 한투 없이 할 수 있는 것부터 진행.

### 증권사 구조

| 증권사 | 역할 | 방식 | 상태 |
|--------|------|------|:----:|
| **한투** | 해외주식 + 국내 ETF + 환전 + 시세 | API 전용 (앱 안 씀) | 미개설 |
| **신한투자증권** | ISA 정기매수 | 앱 수동 | 사용 중 |
| **키움** | ISA 자동매매 (2027-08-09 이후) | API | 향후 |
| **토스** | 청산 예정 | 수동 | 청산 중 |

### 브랜치 전략

| 브랜치 | 역할 | 실행 환경 |
|--------|------|----------|
| `main` | 이메일 리포팅 전용 | GitHub Actions (평일 07:00 KST) |
| `feature/auto-trading` | 자동매매 시스템 | 로컬 (스케줄러) |

## 아키텍처

```
로컬 실행 (Windows 작업 스케줄러 or WSL cron)
  ├─ 07:00 KST: 데이터 수집 + DB 적재 + 이메일 리포트
  ├─ 15:45 KST: 장 마감 후 텔레그램 데일리 리포트
  └─ 23:40 KST: 매매 (트리거 재판정 + 주문 실행) ← 한투 API 연동 후

main.py --mode report|trade|telegram|full
  ├─ market_data.py      (기존, 데이터 수집)
  ├─ fx_checker.py        (기존, 환율 구간)
  ├─ notifier.py          (기존, 이메일)
  ├─ db.py                (신규, SQLite 연동)
  ├─ telegram.py          (신규, 텔레그램 알림)
  ├─ trading.py           (신규, 한투 API 클라이언트) ← 한투 개설 후
  └─ trade_executor.py    (신규, 트리거→주문 실행)   ← 한투 개설 후
          │
     로컬 SQLite (data/investment.db)
```

## 자동매매 범위

| 항목 | 자동매매 | 방식 | 단계 |
|------|:--------:|------|:----:|
| SPYM 정기매수 | O | 한투 API | 한투 후 |
| 449180 급락 트리거 | O | 한투 API | 한투 후 |
| 환전 (원화→달러) | O | 한투 API | 한투 후 |
| 449180 트리거 안내 | O | 텔레그램 | **지금** |
| 133690 매도 안내 | O | 텔레그램 | **지금** |
| QCOM 조건부 매수 안내 | O | 텔레그램 | **지금** |
| 포트폴리오 경고 | O | 텔레그램 | **지금** |
| ISA 정기매수 | X | 수동 (신한 앱) | - |
| 개별주 매매 | X | 모니터링만 | - |

---

## 선행 버그 수정 (완료 ✅)

| # | 수정 내용 | 상태 |
|---|----------|:----:|
| 1 | 트리거 대상 `'449180.KS'` 고정 | ✅ |
| 2 | SPYM 트리거 참조 테이블 제거 | ✅ |
| 3 | 개별 종목 20% + speculative 5% 한도 체크 | ✅ |
| 4 | notifier 기준가 테이블 `'449180.KS'` 고정 | ✅ |
| 5 | SOUN speculative 변경, 한도 설정 추가 | ✅ |

---

## 세션별 구현 계획

### 세션 2: 로컬 환경 + SQLite + DB 모듈 (완료 ✅)

**PostgreSQL → SQLite 변경**: 크로스 플랫폼(Windows/Mac), 설치 불필요, 데이터량 충분.
향후 서버 이전 시 PostgreSQL로 마이그레이션 가능.

- `.env` + `python-dotenv`로 로컬 환경변수 관리 (GitHub Actions 호환)
- `modules/db.py` — `InvestmentDB` 클래스 (SQLite, 테이블 8개)
- `scripts/init_db.sql` — SQLite DDL
- `main.py` 파이프라인에 DB 적재 삽입 (환율/가격/포트폴리오/실행로그)
- DB는 optional — 초기화 실패해도 기존 리포트 정상 동작

**수정:** `main.py`, `requirements.txt`, `.gitignore`
**생성:** `modules/db.py`, `scripts/init_db.sql`, `.env.example`

---

### 세션 3: 텔레그램 알림 모듈

**한투 API 불필요. 텔레그램 봇 토큰만 필요.**

#### 스케줄

| 시간 | 채널 | 내용 |
|------|------|------|
| 07:00 KST | 이메일 | HTML 상세 리포트 (기존 유지) |
| 15:45 KST | 텔레그램 | 간단 데일리 리포트 (장 마감 후) |
| 즉시 | 텔레그램 | 트리거 발동, 에러 등 긴급 알림 |

#### 알림 역할 분담

| | 이메일 (07:00) | 텔레그램 (15:45 + 즉시) |
|--|:-:|:-:|
| 일일 상세 리포트 | O | X |
| 일일 간단 리포트 | X | O (15:45) |
| 트리거 발동 | O (리포트 내) | O (즉시) |
| 환율 구간 변경 | X | O (즉시) |
| 매달 체크리스트 | X | O (1일, 중순) |
| 급락 버퍼 잔액 경고 | X | O |
| 보유 종목 일간 ±5% | X | O (15:45) |
| 시스템 에러 | X | O (즉시) |
| ISA 만기 카운트다운 | X | O (D-90, D-30, D-7) |
| 주간 요약 (금요일) | X | O (15:45) |
| 133690 매도 후 잔여 추적 | X | O |

#### 텔레그램 데일리 리포트 (15:45 KST, 장 마감 후)

```
📊 04/09(수) 데일리 리포트

💰 총자산: ₩32,450,000 (+0.8%)
🎯 1억 목표: 32.5% (D-487)

📈 지수 ETF
 SPYM      $77.23  +1.2%
 360750   ₩18,450  +0.9%
 449180   ₩13,200  -0.3%
 133690   ₩163,095 +1.5%

📉 개별주
 GOOGL  $178.5  +0.5%  PER 22.1
 OXY    $52.3   -1.2%
 QCOM   $165.8  +2.1%  PER 18.3
 SOUN   $8.72   +3.4%

💵 환율: ₩1,395 (정상·전액)
💰 현금: 18.2% | 버퍼: ₩300만

⚠️ 트리거: 없음
```

금요일에는 하단에 주간 요약 추가:
```
📅 주간 요약
 총자산: +₩285,000 (+0.9%)
 트리거 발동: 없음
```

#### 알림 상세

**트리거 알림 (즉시):**
- 449180 급락 트리거 (전월 -5%/-10%, 2달 전 -5%/-10%)
- 133690 매도 조건 충족 (전월+5% AND 평단+15%) + 잔여 수량 표시
- QCOM 조건부 매수 (PER ≤ 25 AND 52주 -15%)
- 포트폴리오 한도 초과 (개별 20%, AI·테크 20%, speculative 5%, 현금 15-25%)

**환율 알림:**
- 환율 구간 변경 시 알림 (ISA 활성 종목 전환 필요: 449180↔360750)

**급락 버퍼:**
- 잔액 100만원 이하 시 충전 안내
- 트리거 집행 후 잔액 상태 알림

**보유 종목 급변:**
- 하루 ±5% 이상 변동 시 알림 (정보 제공만, 액션 안내 없음 — 감정 매매 방지)

**정기 리마인더:**
- 매달 1일: "ISA 100만 정기매수 확인 / config.yaml 업데이트 / 환율 구간 확인"
- 매달 중순: "비중 점검 (개별 20%, AI·테크 20%, 현금 15-25%)"
- ISA 만기 카운트다운: D-90 (2027-05-11), D-30 (2027-07-10), D-7 (2027-08-02)

**주간 요약 (금요일):**
- 이번 주 총자산 변화 (₩ / %)
- 주요 비중 변화
- 트리거 상태 요약

**시스템:**
- API 실패 (Alpha Vantage 한도 초과, FinanceDataReader 에러 등)
- DB 에러
- 실행 실패

**주문 결과 (한투 연동 후):**
- 자동매수 체결 결과
- dry-run 시뮬레이션 결과

**생성:** `modules/telegram.py`

```python
class TelegramNotifier:
    def __init__(self, bot_token, chat_id)

    # 기본 발송
    def send_message(self, text, parse_mode='HTML', retry=3) -> bool

    # 트리거 알림
    def send_trigger_alert(self, trigger_type, trigger_data) -> bool
    def send_isa_action_required(self, trigger_data) -> bool
    def send_133690_sell_alert(self, trigger_data, remaining_qty) -> bool
    def send_qcom_alert(self, condition_data) -> bool
    def send_portfolio_warning(self, warnings) -> bool

    # 환율/버퍼
    def send_fx_zone_change(self, prev_zone, new_zone, fx_rate) -> bool
    def send_buffer_warning(self, remaining, threshold=1000000) -> bool

    # 보유 종목 급변
    def send_price_alert(self, ticker, change_pct, threshold=5.0) -> bool

    # 정기 리마인더
    def send_monthly_checklist(self, day_of_month, fx_rate, isa_ticker) -> bool
    def send_isa_countdown(self, days_remaining) -> bool

    # 주간/일일 요약
    def send_weekly_summary(self, weekly_data) -> bool
    def send_daily_summary(self, report_data) -> bool

    # 시스템
    def send_error_alert(self, error_msg) -> bool

    # 주문 결과 (한투 연동 후)
    def send_order_notification(self, order_result, is_dry_run=False) -> bool
```

**수정:** `main.py` (텔레그램 초기화 + 각 이벤트 후 알림 호출)

---

### 세션 4: 트리거→텔레그램 연동 + DB 기반 중복 방지

**한투 API 불필요. 세션 2, 3 완료 후 진행.**

트리거 발동 → DB 기록 + 텔레그램 발송 연결.

- 449180 급락 트리거 → 텔레그램 안내 ("한투 앱에서 수동 매수하세요" — 한투 개설 전까지)
- 133690 매도 트리거 (전월+5% AND 평단+15%) → 텔레그램 안내
- QCOM 조건부 매수 → 텔레그램 안내
- 포트폴리오 한도 초과 → 텔레그램 경고
- DB 기반 월별 트리거 중복 방지 (`trigger_event` 테이블)
- DB 기반 급락 버퍼 잔액 추적 (`trigger_buffer` 테이블)
- 일일 요약 텔레그램 메시지

**텔레그램 메시지 예시:**
```
🚨 449180 급락 트리거 발동! (전월 대비)
449180.KS: 전월 대비 -5.23%
기준가: ₩13,450 (2026-03-31)
현재가: ₩12,747
액션: 급락 버퍼에서 100만원 매수
버퍼 잔액: ₩200만 / ₩300만
→ 한투 앱에서 직접 매수하세요 (API 연동 전)
```

```
📈 133690 매도 조건 충족!
TIGER 미국나스닥100 (133690.KS)
전월 대비: +6.2% ✓ (기준: +5%)
평단 대비: +16.8% ✓ (기준: +15%, 평단 ₩143,723)
현재가: ₩167,868
액션: 10주 매도
→ 신한 ISA 앱에서 직접 매도하세요
```

**수정:** `main.py`

---

### 세션 5: 한투 API 모듈 (계좌 개설 후)

**한투 계좌 + API 키 필요.**

**생성:** `modules/trading.py`

```python
class KISClient:
    def __init__(self, app_key, app_secret, account_no, is_paper=True)
    def get_access_token(self, retry=3, delay=2) -> Optional[str]
    def get_us_stock_price(self, ticker, exchange='NAS') -> Optional[Dict]
    def get_kr_stock_price(self, ticker) -> Optional[Dict]
    def get_us_stock_balance(self) -> Optional[Dict]
    def buy_us_stock(self, ticker, quantity, price, exchange, order_type) -> Optional[Dict]
    def sell_us_stock(self, ticker, quantity, price, exchange, order_type) -> Optional[Dict]
    def buy_kr_stock(self, ticker, quantity, price, order_type) -> Optional[Dict]
    def exchange_currency(self, from_currency, to_currency, amount) -> Optional[Dict]

def calculate_buy_quantity(budget, current_price, max_quantity=100) -> int
def is_us_market_open() -> bool
def is_kr_market_open() -> bool
```

- 시세 조회를 한투로 전환 (FinanceDataReader/Alpha Vantage → 한투 API)
- Alpha Vantage는 펀더멘탈(PER/ROE) 전용으로 유지
- `.env`에 `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO` 추가

**config.yaml 추가:**
```yaml
kis_api:
  is_paper: true

trading:
  enabled: false
  dry_run: true
  max_single_order_usd: 500
  max_single_order_krw: 1500000
  max_daily_orders: 5

exchange_map:
  SPYM: NAS
  GOOGL: NAS
  OXY: NYS
  QCOM: NAS
```

**수정:** `main.py`, `modules/market_data.py`, `config.yaml`, `requirements.txt`
**생성:** `modules/trading.py`

---

### 세션 6: 자동매수 로직 + trade executor

**한투 API 필요. 세션 5 완료 후.**

**생성:** `modules/trade_executor.py`

```python
class TradeExecutor:
    def __init__(self, kis_client, telegram, db, config)
    def _safety_check(self, order_amount, currency='KRW') -> tuple[bool, str]
    def execute_449180_trigger(self, trigger_data) -> Optional[Dict]
    def execute_spym_regular_buy(self, fx_zone, monthly_budget) -> Optional[Dict]
    def execute_fx_conversion(self, fx_zone, amount) -> Optional[Dict]
    def get_execution_summary(self) -> Dict
```

안전장치: enabled → dry_run → 금액 한도 → 일일 건수(DB) → 시장 개장 → 버퍼 잔액(DB) → 월별 중복(DB)

**main.py `--mode` 인자:**
- `report`: 데이터 수집 + DB 적재 + 이메일 + 텔레그램
- `trade`: 트리거 재판정 + 주문 실행
- `full`: report + trade

텔레그램 안내 메시지를 주문 결과 알림으로 전환:
- 한투 개설 전: "한투 앱에서 직접 매수하세요"
- 한투 개설 후: "✅ 449180 75주 매수 완료 (₩990,000)"

---

### 세션 7: 모의투자 테스트 + dry-run

**생성:**
- `tests/test_db.py`
- `tests/test_trading.py`
- `tests/test_integration.py`
- `tests/test_telegram.py`

**`--force-trigger` 지원:**
```bash
python main.py --mode trade --force-trigger 449180_5pct
```

**dry-run**: DB에 `is_dry_run=True`로 기록, 텔레그램에 `[DRY-RUN]` 접두어

---

### 세션 8: 실전 전환 + 로컬 스케줄러

**config 전환:**
```yaml
kis_api:
  is_paper: false
trading:
  enabled: true
  dry_run: false
```

**로컬 스케줄러:**
```
07:00 KST → python main.py --mode report
23:40 KST → python main.py --mode trade
```

**Kill switch:**
- 1차: `trading.enabled: false`
- 2차: `.env`에서 `KIS_APP_KEY` 제거

---

## 최종 파일 구조

```
investment-monitor/                    ← git repo
├── main.py                            # --mode report|trade|full
├── config.yaml                        # 매매 안전장치 (민감 정보 제외)
├── .env.example                       # 환경변수 템플릿 (git 포함)
├── .env                               # 실제 환경변수 (git 제외)
├── .gitignore
├── requirements.txt
├── scripts/
│   └── init_db.sql                    # DB 테이블 생성
├── modules/
│   ├── market_data.py                 # 기존 (→ 한투 전환 후 수정)
│   ├── fx_checker.py                  # 기존
│   ├── notifier.py                    # 기존 (버그 수정 완료)
│   ├── db.py                          # 신규: PostgreSQL (세션 2)
│   ├── telegram.py                    # 신규: 텔레그램 (세션 3)
│   ├── trading.py                     # 신규: 한투 API (세션 5)
│   └── trade_executor.py             # 신규: 매매 실행 (세션 6)
├── tests/
│   ├── test_db.py
│   ├── test_trading.py
│   ├── test_integration.py
│   └── test_telegram.py
└── docs/
    ├── auto-trading-plan.md
    ├── db-schema.md
    └── ...
```

## 검증 방법

1. **세션 2**: DB 연결 + 테이블 생성 + 기존 파이프라인에서 DB 적재 확인
2. **세션 3**: 텔레그램 봇 생성 + 메시지 발송 테스트
3. **세션 4**: 트리거 발동 → DB 기록 + 텔레그램 발송 + 중복 방지 확인
4. **세션 5**: 한투 토큰 발급 + 시세 조회 테스트
5. **세션 6**: `--mode trade` + `dry_run: true` → DB 기록 + 텔레그램 시뮬
6. **세션 7**: 한투 모의투자 + `--force-trigger` → 모의 주문 체결
7. **세션 8**: 로컬 스케줄러 + 소액 실전 주문
