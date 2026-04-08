# 자동매매 전환 구현 계획

> 작성일: 2026-04-08 | 브랜치: feature/auto-trading
> 최종 수정: 2026-04-08 (세션 1 룰 변경 반영)

## Context

현재 시스템은 모니터링+이메일 알림만 수행하고 매매는 수동. 룰 베이스 트리거를 실제 주문으로 연결하여 자동매매로 확장한다.

- **한국투자증권 OpenAPI**: SPYM 정기매수 + 449180 급락 트리거 + 환전 자동화
- **ISA 계좌**: 순수 DCA (월 100만 전액 매수, 트리거 없음), 133690 매도만 텔레그램 안내
- **개별주**: 자동매매 대상 아님 (모니터링 + 텔레그램 안내만)
- **토스증권**: 청산 예정 (신규 투자 없음, 기존 보유분 점진적 정리)
- **2027-08-09 이후**: ISA 해지 → 키움증권 REST API로 ISA 자동매매 이전

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
GitHub Actions
  ├─ 07:00 KST: 리포트 전용 (데이터 수집 + 이메일 + 텔레그램 안내)
  └─ 23:40 KST: 매매 전용 (트리거 재판정 + 449180 국내주문 + SPYM 해외주문 + 환전)

main.py --mode report|trade|full
  ├─ market_data.py      (기존, 데이터 수집)
  ├─ fx_checker.py        (기존, 환율 구간)
  ├─ notifier.py          (기존, 이메일)
  ├─ telegram.py          (신규, 텔레그램 알림)
  ├─ trading.py           (신규, 한투 API 클라이언트)
  └─ trade_executor.py    (신규, 트리거→주문 실행+안전장치)
```

## 매매 타이밍 설계

| 시간 | 모드 | 동작 |
|------|------|------|
| 07:00 KST | `--mode report` | 데이터 수집 + 이메일 + ISA/개별주 텔레그램 안내 |
| 23:40 KST | `--mode trade` | 실시간 데이터로 트리거 재판정 + 주문 실행 |

23:40에 재판정하는 이유: 07:00에 -5%였더라도 미국 개장 시 반등할 수 있음. 주문 시점 데이터로 확인해야 변수 최소화.

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

---

## 선행 버그 수정 (세션 2에서 처리)

| # | 위치 | 문제 | 수정 |
|---|------|------|------|
| 1 | `main.py:103` | ISA 트리거가 `isa_active_ticker` 기준 | `ticker == '449180.KS'`로 고정 |
| 2 | `main.py:224-238` | SPYM 트리거 판정 로직 | SPYM 급락 트리거 삭제 (룰 변경), 참조 테이블만 유지 |
| 3 | `main.py:395-425` | 개별 종목 비중 한도 체크 없음 | 전 종목 **20%** 한도 + speculative 5% 한도 체크 추가 |
| 4 | `notifier.py:112` | ISA 기준가 테이블이 활성 종목 기준 | `'449180.KS'` 고정 |

---

## 세션별 구현 계획

### 세션 2: 버그 수정 + 한투 API 모듈

**Part A — 버그 수정**

1. `main.py:103` — `ticker == isa_active_ticker` → `ticker == '449180.KS'`
2. `main.py:224-238` — SPYM 급락 트리거 관련 코드 정리 (삭제됨, 참조 테이블은 유지)
3. `main.py:395-425` — `allocations` 순회 20% 초과 경고 + speculative 5% 한도, `config.yaml`에 `individual_stock_max: 0.20`, `speculative_max: 0.05` 추가
4. `notifier.py:112-113` — ISA 기준가 테이블 `'449180.KS'` 고정 (★ 배지는 기존 유지)

**Part B — 한투 API 모듈 (`modules/trading.py`)**

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

- 국내주식 주문 (449180 급락 트리거), 해외주식 주문 (SPYM), 환전 API 모두 포함
- 기존 패턴 준수: retry=3, exponential backoff, Optional 반환, 한국어 로그
- 모의투자/실전 base URL 자동 전환
- OAuth 토큰 24시간 유효, 필요시 자동 재발급

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
  trigger_buffer_krw: 3000000  # 급락 트리거 버퍼 (계좌 잔액과 별도 추적)

exchange_map:
  SPYM: NAS
  GOOGL: NAS
  OXY: NYS
  QCOM: NAS
```

**새 GitHub Secrets:** `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`

**수정:** `main.py`, `modules/notifier.py`, `config.yaml`
**생성:** `modules/trading.py`

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
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 이미 GitHub Secrets에 있음
- Telegram 실패 시 이메일 발송 차단하지 않음 (독립 실행)

**수정:** `main.py`

---

### 세션 4: 자동매수 로직 (449180 급락 + SPYM 정기 + 환전)

**생성:** `modules/trade_executor.py`

```python
class TradeExecutor:
    def __init__(self, kis_client, telegram, config)
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
4. `max_daily_orders` 초과?
5. 시장 개장 여부? (`is_us_market_open()` / `is_kr_market_open()`)
6. 급락 버퍼 잔액 확인? (`trigger_buffer_krw`)

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

- 포트폴리오 한도 경고 (20% 초과, speculative 5% 초과)

**수정:** `main.py`, `modules/telegram.py`

---

### 세션 6: 모의투자 테스트 + dry-run

**생성:**
- `tests/test_trading.py` — 토큰 발급, 주문, 안전장치, 버퍼 차감
- `tests/test_integration.py` — 트리거→주문 전체 흐름
- `tests/test_telegram.py` — 메시지 전송
- `.github/workflows/test_trading.yml` — 수동 실행 전용

**main.py에 `--force-trigger` 추가:**
```bash
python main.py --mode trade --force-trigger 449180_5pct
python main.py --mode trade --force-trigger 449180_2m_10pct
```

**dry-run 동작:**
- 주문 상세 계산 (종목, 수량, 금액)
- 실제 API 호출 안 함
- 버퍼 차감 시뮬레이션
- 텔레그램에 `[DRY-RUN]` 접두어로 시뮬 결과 발송

---

### 세션 7: 실전 전환 + GitHub Actions

**config 전환:**
```yaml
kis_api:
  is_paper: false
trading:
  enabled: true
  dry_run: false
```

**워크플로우 추가:** `.github/workflows/trading.yml`
```yaml
# 매매 전용 (화-토 23:40 KST = 14:40 UTC)
on:
  schedule:
    - cron: "40 14 * * 1-5"
```

**Kill switch:**
- 1차: `trading.enabled: false` (config 변경)
- 2차: GitHub Secrets에서 `KIS_APP_KEY` 삭제 (즉시 차단)

---

## 최종 파일 구조

```
investment-monitor/
├── main.py                      # --mode report|trade|full
├── config.yaml                  # 매매 안전장치 + 급락 버퍼 포함
├── modules/
│   ├── market_data.py           # (기존)
│   ├── fx_checker.py            # (기존)
│   ├── notifier.py              # (버그 수정)
│   ├── telegram.py              # 신규: 텔레그램 알림
│   ├── trading.py               # 신규: 한투 API 클라이언트 (국내+해외+환전)
│   └── trade_executor.py        # 신규: 매매 실행+안전장치+버퍼 관리
├── tests/
│   ├── test_trading.py
│   ├── test_integration.py
│   └── test_telegram.py
└── .github/workflows/
    ├── daily_report.yml         # 07:00 KST 리포트
    ├── trading.yml              # 23:40 KST 매매
    └── test_trading.yml         # 수동 테스트
```

## GitHub Secrets 최종

| Secret | 용도 | 상태 |
|--------|------|------|
| `EXCHANGERATE_API_KEY` | 환율 API | 기존 |
| `ALPHAVANTAGE_API_KEY` | Alpha Vantage | 기존 |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` | 이메일 | 기존 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 텔레그램 | 기존(미사용→활성화) |
| `KIS_APP_KEY` / `KIS_APP_SECRET` / `KIS_ACCOUNT_NO` | 한투 API | 신규 |

## 검증 방법

1. **세션 2**: `python main.py` 로컬 실행 → 버그 수정 확인
2. **세션 3**: 텔레그램 봇 생성 후 `send_message()` 테스트
3. **세션 4**: `--mode trade` + `dry_run: true` → 시뮬레이션 로그 + 버퍼 차감 확인
4. **세션 6**: 한투 모의투자 + `--force-trigger` → 모의 주문 체결 확인
5. **세션 7**: `is_paper: false` + 소액 실전 주문 → 텔레그램 체결 알림 확인
