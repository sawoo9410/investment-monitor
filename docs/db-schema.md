# 데이터베이스 설계

> 로컬 PostgreSQL | 종가 기준 일 1회 적재

## 설계 원칙

- 매일 종가 기준으로 데이터 적재 (실시간 X)
- 시간이 쌓일수록 가치가 커지는 데이터 중심
- ISA 순수 DCA 수익률 추적 가능
- 향후 전종목 수집 확장 대비 (별도 프로젝트)

## 테이블 구조

### 1. daily_price — 일별 종가

매일 수집하는 종목 가격. 시간이 쌓이면 자체 시계열 DB가 됨.

```sql
CREATE TABLE daily_price (
    id            SERIAL PRIMARY KEY,
    date          DATE NOT NULL,
    ticker        VARCHAR(20) NOT NULL,
    close_price   DECIMAL(12,4) NOT NULL,    -- 종가
    change_pct    DECIMAL(8,4),              -- 전일 대비 등락률
    volume        BIGINT,                     -- 거래량
    source        VARCHAR(20) DEFAULT 'kis',  -- kis / fdr / alphavantage
    created_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, ticker)
);

CREATE INDEX idx_daily_price_ticker_date ON daily_price(ticker, date DESC);
```

**활용**: 전월 말일 종가 조회, 다기간 수익률 계산, 백테스트, 차트

### 2. daily_fx — 일별 환율

```sql
CREATE TABLE daily_fx (
    id            SERIAL PRIMARY KEY,
    date          DATE NOT NULL UNIQUE,
    usd_krw       DECIMAL(10,4) NOT NULL,
    fx_zone       VARCHAR(20),               -- full_convert / normal_full / normal_half / pause
    created_at    TIMESTAMP DEFAULT NOW()
);
```

**활용**: 환전 이력 추적, 환율 구간 변동 분석, ISA 활성 종목 이력

### 3. trigger_event — 트리거 발동 이력

```sql
CREATE TABLE trigger_event (
    id              SERIAL PRIMARY KEY,
    trigger_month   VARCHAR(7) NOT NULL,      -- '2026-04' (월별 중복 방지용)
    trigger_type    VARCHAR(30) NOT NULL,      -- monthly_5pct / monthly_10pct / 2month_5pct / 2month_10pct
    ticker          VARCHAR(20) NOT NULL,
    baseline_date   DATE,
    baseline_price  DECIMAL(12,4),
    current_price   DECIMAL(12,4),
    change_pct      DECIMAL(8,4),
    action_amount   INTEGER,                   -- 집행 금액 (원)
    executed        BOOLEAN DEFAULT FALSE,     -- 실제 주문 실행 여부
    is_dry_run      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(trigger_month, trigger_type, ticker)
);
```

**활용**: 월별 중복 발동 방지, 트리거 효과 분석

### 4. trigger_buffer — 급락 버퍼 잔액

```sql
CREATE TABLE trigger_buffer (
    id              SERIAL PRIMARY KEY,
    buffer_type     VARCHAR(20) DEFAULT 'krw_crash',
    initial_amount  INTEGER NOT NULL,          -- 초기 한도 (300만원)
    remaining       INTEGER NOT NULL,          -- 잔액
    last_updated    TIMESTAMP DEFAULT NOW()
);

-- 초기 데이터
INSERT INTO trigger_buffer (buffer_type, initial_amount, remaining)
VALUES ('krw_crash', 3000000, 3000000);
```

### 5. order_history — 주문 체결 이력

```sql
CREATE TABLE order_history (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    ticker          VARCHAR(20) NOT NULL,
    action          VARCHAR(10) NOT NULL,      -- buy / sell
    quantity        INTEGER NOT NULL,
    price           DECIMAL(12,4) NOT NULL,
    amount          DECIMAL(14,2) NOT NULL,    -- 총 금액
    currency        VARCHAR(3) DEFAULT 'KRW',  -- KRW / USD
    account         VARCHAR(20) NOT NULL,      -- kis / isa / toss
    trigger_type    VARCHAR(30),               -- 어떤 트리거로 실행됐는지 (NULL이면 정기매수)
    order_type      VARCHAR(10),               -- market / limit
    status          VARCHAR(10) NOT NULL,      -- executed / failed / simulated
    is_dry_run      BOOLEAN DEFAULT FALSE,
    error_message   TEXT,
    executed_at     TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_order_history_date ON order_history(date DESC);
CREATE INDEX idx_order_history_ticker ON order_history(ticker, date DESC);
```

**활용**: 매매 이력 추적, 세금 신고, 수익률 계산

### 6. portfolio_snapshot — 일별 포트폴리오 스냅샷

```sql
CREATE TABLE portfolio_snapshot (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL UNIQUE,
    total_assets        DECIMAL(14,2),          -- 총 자산
    total_value         DECIMAL(14,2),          -- 평가액
    total_cash          DECIMAL(14,2),          -- 현금 합계
    cash_allocation_pct DECIMAL(6,2),
    holdings_json       JSONB,                   -- 종목별 상세 {ticker: {qty, price, value, pct}}
    sector_json         JSONB,                   -- 섹터별 비중
    warnings_json       JSONB,                   -- 한도 초과 경고
    created_at          TIMESTAMP DEFAULT NOW()
);
```

**활용**: 자산 증가 추이, 비중 변화 추적, 리밸런싱 판단

### 7. dca_record — ISA 정기매수 이력

ISA 순수 DCA 수익률 추적 전용.

```sql
CREATE TABLE dca_record (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    ticker          VARCHAR(20) NOT NULL,      -- 449180 or 360750
    quantity        INTEGER NOT NULL,
    price           DECIMAL(12,4) NOT NULL,
    amount          INTEGER NOT NULL,           -- 매수 금액 (원)
    cumulative_qty  INTEGER,                    -- 누적 수량
    cumulative_cost INTEGER,                    -- 누적 투자금
    avg_price       DECIMAL(12,4),             -- 평단가
    fx_rate         DECIMAL(10,4),             -- 매수 시점 환율
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_dca_record_date ON dca_record(date DESC);
```

**활용**: DCA 평단가 추적, 누적 투자금 vs 평가액, 정기매수 수익률 분석

### 8. execution_log — 시스템 실행 로그

```sql
CREATE TABLE execution_log (
    id              SERIAL PRIMARY KEY,
    mode            VARCHAR(10) NOT NULL,       -- report / trade / full
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP,
    status          VARCHAR(10) NOT NULL,       -- success / failed / partial
    api_calls_kis   INTEGER DEFAULT 0,
    api_calls_av    INTEGER DEFAULT 0,
    summary         TEXT,
    error_message   TEXT
);
```

## 데이터 흐름

```
07:00 KST (--mode report)
  ├─ daily_price      ← 전일 종가 적재 (한투 API)
  ├─ daily_fx         ← 환율 적재
  ├─ portfolio_snapshot ← 포트폴리오 스냅샷
  ├─ trigger_event    ← 트리거 판정 결과 기록 (실행은 안 함)
  └─ execution_log    ← 실행 로그

23:40 KST (--mode trade)
  ├─ daily_price      ← 미국 종가 업데이트 (장 마감 후)
  ├─ trigger_event    ← 트리거 재판정 + executed=true
  ├─ trigger_buffer   ← 버퍼 차감
  ├─ order_history    ← 주문 결과 기록
  └─ execution_log    ← 실행 로그

ISA 수동 매수 시 (텔레그램 안내 후)
  └─ dca_record       ← 수동 입력 or 별도 스크립트
```

## 데이터 보존 정책

| 테이블 | 보존 기간 | 이유 |
|--------|----------|------|
| daily_price | 영구 | 시계열 축적, 백테스트 |
| daily_fx | 영구 | 환율 이력 |
| trigger_event | 영구 | 트리거 효과 분석 |
| order_history | 영구 | 세금, 수익률 |
| portfolio_snapshot | 영구 | 자산 추이 |
| dca_record | 영구 | DCA 수익률 분석 |
| trigger_buffer | 최신 1건 | 현재 잔액만 필요 |
| execution_log | 1년 | 디버깅용, 오래된 건 삭제 가능 |

## 향후 확장

전종목 수집 프로젝트 시 추가 테이블:
```sql
-- 전종목 일별 종가 (별도 테이블, daily_price와 분리)
market_daily_price (date, ticker, open, high, low, close, volume, market_cap)

-- 종목 메타 정보
stock_info (ticker, name, market, sector, listing_date, ...)
```

기존 daily_price는 포트폴리오 종목 전용으로 유지, 전종목은 별도 테이블로 분리.
