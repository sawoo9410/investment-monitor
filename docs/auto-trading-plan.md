# 자동매매 전환 구현 계획

> 작성일: 2026-04-08 | 브랜치: feature/auto-trading
> 최종 수정: 2026-04-09 (실행 환경 로컬 이전 + DB 도입)

## Context

현재 시스템은 모니터링+이메일 알림만 수행하고 매매는 수동. 룰 베이스 트리거를 실제 주문으로 연결하여 자동매매로 확장한다.

- **한국투자증권 OpenAPI**: SPYM 정기매수 + 449180 급락 트리거 + 환전 자동화
- **ISA 계좌**: 순수 DCA (월 100만 전액 매수, 트리거 없음), 133690 매도만 텔레그램 안내
- **개별주**: 자동매매 대상 아님 (모니터링 + 텔레그램 안내만)
- **토스증권**: 청산 예정 (신규 투자 없음, 기존 보유분 점진적 정리)
- **2027-08-09 이후**: ISA 해지 → 키움증권 REST API로 ISA 자동매매 이전

### 브랜치 전략

| 브랜치 | 역할 | 실행 환경 |
|--------|------|----------|
| `main` | 이메일 리포팅 전용 | GitHub Actions (평일 07:00 KST) |
| `feature/auto-trading` | 자동매매 시스템 | 로컬 (스케줄러로 실행) |

### 증권사 API 선정 근거

| | 한국투자증권 | 키움증권 REST | 토스증권 |
|--|:-----------:|:-----------:|:-------:|
| REST API | O | O | **미제공** |
| 해외주식 | O | X | - |
| 국내주식/ETF | O | O | - |
| 환전 API | O | - | - |
| ISA 계좌 | 미지원 | **O** | - |
| Python 생태계 | 최우수 | 신규 | - |

## 아키텍처

```
로컬 실행 (Windows 작업 스케줄러 or WSL cron)
  ├─ 07:00 KST: 리포트 (데이터 수집 + 이메일 + 텔레그램 안내)
  └─ 23:40 KST: 매매 (트리거 재판정 + 449180 국내주문 + SPYM 해외주문 + 환전)

main.py --mode report|trade|full
  ├─ market_data.py      (기존, 데이터 수집)
  ├─ fx_checker.py        (기존, 환율 구간)
  ├─ notifier.py          (기존, 이메일)
  ├─ telegram.py          (신규, 텔레그램 알림)
  ├─ trading.py           (신규, 한투 API 클라이언트)
  ├─ trade_executor.py    (신규, 트리거→주문 실행+안전장치)
  └─ db.py                (신규, PostgreSQL 연동)
          │
     로컬 PostgreSQL ← 매매 상태, 주문 이력, 포트폴리오 스냅샷
```

## 실행 환경 (로컬)

| 항목 | 설명 |
|------|------|
| 실행 | 로컬 PC (Windows 작업 스케줄러 or WSL cron) |
| 코드 관리 | git push (코드만, 민감 정보 제외) |
| DB | 로컬 PostgreSQL |
| 민감 정보 | `.env` 파일 (git 외부) — API 키, DB 접속 정보 |
| 로그 | 별도 로컬 경로 |

**민감 정보 분리:**
```
git repo (investment-monitor/)
├── main.py, modules/, docs/ ...     ← git 관리
├── .env                              ← .gitignore (API 키, DB URL)
└── config.yaml                       ← git 관리 (민감 정보 제외)

별도 로컬 경로 (예: ~/investment-data/)
├── logs/                             ← 실행 로그
└── backups/                          ← DB 백업
```

## 매매 타이밍 설계

| 시간 | 모드 | 동작 |
|------|------|------|
| 07:00 KST | `--mode report` | 데이터 수집 + 이메일 + ISA/개별주 텔레그램 안내 |
| 23:40 KST | `--mode trade` | 실시간 데이터로 트리거 재판정 + 주문 실행 |

## 자동매매 범위

| 항목 | 자동매매 | 방식 |
|------|:--------:|------|
| SPYM 정기매수 | O | 한투 API (해외주식 주문) |
| 449180 급락 트리거 | O | 한투 API (국내주식 주문) |
| 환전 (원화→달러) | O | 한투 API (외화매매) |
| ISA 정기매수 | X | 수동 (향후 키움 REST로 자동화) |
| 133690 매도 | X | 텔레그램 안내 → 수동 실행 |
| QCOM 조건부 매수 | X | 텔레그램 안내만 |
| 개별주 매매 | X | 모니터링만 |

## 데이터베이스 (로컬 PostgreSQL)

### 테이블 설계

```sql
-- 트리거 발동 이력 (월별 중복 방지)
trigger_state (
  id, trigger_type, ticker, trigger_month,
  change_pct, baseline_price, executed_at, amount_krw
)

-- 급락 버퍼 잔액 추적
trigger_buffer (
  id, buffer_type, initial_amount, remaining_amount,
  last_updated
)

-- 주문 체결 이력
order_history (
  id, ticker, action, quantity, price, amount,
  trigger_type, order_type, status, executed_at,
  is_dry_run, error_message
)

-- 일별 포트폴리오 스냅샷
daily_portfolio (
  id, date, total_assets, total_value, total_cash,
  cash_allocation_pct, snapshot_json
)

-- 일별 종목 가격
daily_price (
  id, date, ticker, price, change_pct, baseline_price
)

-- 실행 로그
execution_log (
  id, mode, started_at, finished_at, status,
  summary, error_message
)
```

### DB 연동 모듈 (`modules/db.py`)

```python
class InvestmentDB:
    def __init__(self, db_url)
    def record_trigger(self, trigger_type, ticker, month, ...) -> bool
    def is_trigger_fired(self, trigger_type, ticker, month) -> bool
    def get_buffer_remaining(self, buffer_type) -> int
    def deduct_buffer(self, buffer_type, amount) -> int
    def record_order(self, order_data) -> bool
    def save_daily_portfolio(self, snapshot) -> bool
    def save_daily_price(self, ticker, price_data) -> bool
    def get_daily_orders_count(self, date) -> int
    def log_execution(self, mode, status, summary) -> bool
```

---

## 선행 버그 수정 (완료)

| # | 위치 | 수정 | 상태 |
|---|------|------|:----:|
| 1 | `main.py:103` | 트리거 대상 `'449180.KS'` 고정 | ✅ |
| 2 | `notifier.py` | SPYM 트리거 참조 테이블 제거 | ✅ |
| 3 | `main.py` | 개별 종목 20% + speculative 5% 한도 체크 | ✅ |
| 4 | `notifier.py:112` | 기준가 테이블 `'449180.KS'` 고정 | ✅ |
| 5 | `config.yaml` | SOUN speculative 변경, 한도 설정 추가 | ✅ |
| 6 | `main.py` | 변수명/주석 정리 (한투 종합계좌 반영) | ✅ |
| 7 | `notifier.py` | 알림 텍스트 업데이트 | ✅ |

---

## 세션별 구현 계획

### 세션 2: 로컬 환경 + DB + 한투 API 모듈

**Part A — 로컬 실행 환경 구축**

- `.env` 파일 생성 (API 키, DB URL)
- `.gitignore`에 `.env` 추가
- `python-dotenv` 의존성 추가
- main.py에서 `os.getenv()` → `.env` 로드 방식으로 전환

**Part B — PostgreSQL 연동 (`modules/db.py`)**

- `psycopg2` 의존성 추가
- `InvestmentDB` 클래스 구현
- 테이블 마이그레이션 스크립트 (`scripts/init_db.sql`)
- config.yaml의 `trigger_buffer_krw` → DB `trigger_buffer` 테이블로 이전

**Part C — 한투 API 모듈 (`modules/trading.py`)**

```python
class KISClient:
    def __init__(self, app_key, app_secret, account_no, is_paper=True)
    def get_access_token(self, retry=3, delay=2) -> Optional[str]
    def get_us_stock_price(self, ticker, exchange='NAS') -> Optional[Dict]
    def get_us_stock_balance(self) -> Optional[Dict]
    def buy_us_stock(self, ticker, quantity, price, exchange, order_type) -> Optional[Dict]
    def sell_us_stock(self, ticker, quantity, price, exchange, order_type) -> Optional[Dict]
    def buy_kr_stock(self, ticker, quantity, price, order_type) -> Optional[Dict]
    def exchange_currency(self, from_currency, to_currency, amount) -> Optional[Dict]

def calculate_buy_quantity(budget, current_price, max_quantity=100) -> int
def is_us_market_open() -> bool
def is_kr_market_open() -> bool
```

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

**`.env` (git 미포함):**
```
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=...
DATABASE_URL=postgresql://user:pass@localhost:5432/investment
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
EXCHANGERATE_API_KEY=...
ALPHAVANTAGE_API_KEY=...
GMAIL_ADDRESS=...
GMAIL_APP_PASSWORD=...
```

**수정:** `main.py`, `config.yaml`, `requirements.txt`, `.gitignore`
**생성:** `modules/db.py`, `modules/trading.py`, `.env.example`, `scripts/init_db.sql`

---

### 세션 3: 텔레그램 알림 모듈

**생성:** `modules/telegram.py`

```python
class TelegramNotifier:
    def __init__(self, bot_token, chat_id)
    def send_message(self, text, parse_mode='HTML', retry=3) -> bool
    def send_trigger_alert(self, trigger_type, trigger_data) -> bool
    def send_order_notification(self, order_result, is_dry_run=False) -> bool
    def send_isa_action_required(self, trigger_data) -> bool
    def send_daily_summary(self, report_data) -> bool
    def send_error_alert(self, error_msg) -> bool
    def send_portfolio_warning(self, warnings) -> bool
```

- `python-telegram-bot==20.8` 이미 requirements.txt에 있음
- Telegram 실패 시 이메일 발송 차단하지 않음 (독립 실행)

**수정:** `main.py`

---

### 세션 4: 자동매수 로직 (449180 급락 + SPYM 정기 + 환전)

**생성:** `modules/trade_executor.py`

```python
class TradeExecutor:
    def __init__(self, kis_client, telegram, db, config)
    def _safety_check(self, order_amount, currency='KRW') -> tuple[bool, str]
    def _check_trigger_buffer(self, amount) -> tuple[bool, int]
    def execute_449180_trigger(self, trigger_data) -> Optional[Dict]
    def execute_spym_regular_buy(self, fx_zone, monthly_budget) -> Optional[Dict]
    def execute_fx_conversion(self, fx_zone, amount) -> Optional[Dict]
    def execute_isa_notification(self, trigger_data) -> bool
    def execute_133690_sell_notification(self, trigger_data) -> bool
    def get_execution_summary(self) -> Dict
```

안전장치 체크 순서:
1. `trading.enabled` == True?
2. `dry_run` 모드?
3. `max_single_order` 초과?
4. `max_daily_orders` 초과? (DB에서 오늘 주문 수 조회)
5. 시장 개장 여부?
6. 급락 버퍼 잔액? (DB에서 조회)
7. 이번 달 트리거 이미 발동? (DB에서 중복 체크)

**main.py `--mode` 인자 추가:**
- `report`: 기존 파이프라인 (데이터+이메일+텔레그램 알림)
- `trade`: 데이터 수집 → 트리거 판정 → 주문 실행 → 텔레그램 결과
- `full`: report + trade

**수정:** `main.py`, `config.yaml`

---

### 세션 5: ISA 텔레그램 안내 연동

ISA는 자동매매 불가 → 트리거 발동 시 텔레그램으로 구체적 안내 발송.

**133690 매도 안내 예시:**
```
📈 133690 매도 조건 충족!
TIGER 미국나스닥100 (133690.KS)
전월 대비: +6.2% ✓ (기준: +5%)
평단 대비: +16.8% ✓ (기준: +15%, 평단 ₩143,723)
현재가: ₩167,868
액션: 10주 매도
→ ISA 계좌에서 직접 매도하세요
```

**QCOM 조건부 매수 안내:**
```
🎯 QCOM 매수 조건 충족!
PER: 22.3 (기준 25 이하) ✓
52주 고점 대비: -17.2% (기준 -15%) ✓
→ 한투 앱에서 직접 매수 검토하세요
```

**수정:** `main.py`, `modules/telegram.py`

---

### 세션 6: 모의투자 테스트 + dry-run

**생성:**
- `tests/test_trading.py` — 토큰 발급, 주문, 안전장치, 버퍼 차감
- `tests/test_integration.py` — 트리거→주문 전체 흐름
- `tests/test_telegram.py` — 메시지 전송
- `tests/test_db.py` — DB CRUD, 중복 방지, 버퍼 차감

**main.py에 `--force-trigger` 추가:**
```bash
python main.py --mode trade --force-trigger 449180_5pct
python main.py --mode trade --force-trigger 449180_2m_10pct
```

**dry-run 동작:**
- 주문 상세 계산 (종목, 수량, 금액)
- 실제 API 호출 안 함
- DB에 `is_dry_run=True`로 기록
- 텔레그램에 `[DRY-RUN]` 접두어로 시뮬 결과 발송

---

### 세션 7: 실전 전환 + 로컬 스케줄러

**config 전환:**
```yaml
kis_api:
  is_paper: false
trading:
  enabled: true
  dry_run: false
```

**로컬 스케줄러 설정 (Windows 작업 스케줄러 or WSL cron):**
```
07:00 KST → python main.py --mode report
23:40 KST → python main.py --mode trade
```

**Kill switch:**
- 1차: `trading.enabled: false` (config 변경)
- 2차: `.env`에서 `KIS_APP_KEY` 제거 (즉시 차단)

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
│   ├── market_data.py                 # (기존)
│   ├── fx_checker.py                  # (기존)
│   ├── notifier.py                    # (버그 수정 완료)
│   ├── db.py                          # 신규: PostgreSQL 연동
│   ├── telegram.py                    # 신규: 텔레그램 알림
│   ├── trading.py                     # 신규: 한투 API 클라이언트
│   └── trade_executor.py             # 신규: 매매 실행+안전장치
├── tests/
│   ├── test_trading.py
│   ├── test_integration.py
│   ├── test_telegram.py
│   └── test_db.py
└── docs/
    ├── auto-trading-plan.md
    └── ...

~/investment-data/                     ← git 외부, 로컬 전용
├── logs/                              # 실행 로그
└── backups/                           # DB 백업
```

## 환경변수 (`.env`)

| 변수 | 용도 |
|------|------|
| `DATABASE_URL` | PostgreSQL 접속 URL |
| `KIS_APP_KEY` / `KIS_APP_SECRET` / `KIS_ACCOUNT_NO` | 한투 API |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 텔레그램 |
| `EXCHANGERATE_API_KEY` | 환율 API |
| `ALPHAVANTAGE_API_KEY` | Alpha Vantage |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` | 이메일 |

## 검증 방법

1. **세션 2**: DB 연결 + 테이블 생성 확인, 한투 토큰 발급 테스트
2. **세션 3**: 텔레그램 봇 생성 후 `send_message()` 테스트
3. **세션 4**: `--mode trade` + `dry_run: true` → DB 기록 + 중복 방지 확인
4. **세션 6**: 한투 모의투자 + `--force-trigger` → 모의 주문 체결 + DB 이력 확인
5. **세션 7**: 로컬 스케줄러 등록 + 소액 실전 주문 → 텔레그램 + DB 확인
