-- 투자 모니터링 DB 스키마 (SQLite)
-- 매 실행 시 _init_tables()에서 호출 — IF NOT EXISTS로 안전

-- 1. 일별 종가
CREATE TABLE IF NOT EXISTS daily_price (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    ticker        TEXT NOT NULL,
    close_price   REAL NOT NULL,
    change_pct    REAL,
    volume        INTEGER,
    source        TEXT DEFAULT 'fdr',
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_daily_price_ticker_date ON daily_price(ticker, date DESC);

-- 2. 일별 환율
CREATE TABLE IF NOT EXISTS daily_fx (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL UNIQUE,
    usd_krw       REAL NOT NULL,
    fx_zone       TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

-- 3. 트리거 발동 이력
CREATE TABLE IF NOT EXISTS trigger_event (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_month   TEXT NOT NULL,
    trigger_type    TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    baseline_date   TEXT,
    baseline_price  REAL,
    current_price   REAL,
    change_pct      REAL,
    action_amount   INTEGER,
    executed        INTEGER DEFAULT 0,
    is_dry_run      INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(trigger_month, trigger_type, ticker)
);

-- 4. 급락 버퍼 잔액
CREATE TABLE IF NOT EXISTS trigger_buffer (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    buffer_type     TEXT DEFAULT 'krw_crash',
    initial_amount  INTEGER NOT NULL,
    remaining       INTEGER NOT NULL,
    last_updated    TEXT DEFAULT (datetime('now'))
);

-- 초기 데이터 (이미 있으면 무시)
INSERT OR IGNORE INTO trigger_buffer (id, buffer_type, initial_amount, remaining)
VALUES (1, 'krw_crash', 3000000, 3000000);

-- 5. 주문 체결 이력
CREATE TABLE IF NOT EXISTS order_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    action          TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    price           REAL NOT NULL,
    amount          REAL NOT NULL,
    currency        TEXT DEFAULT 'KRW',
    account         TEXT NOT NULL,
    trigger_type    TEXT,
    order_type      TEXT,
    status          TEXT NOT NULL,
    is_dry_run      INTEGER DEFAULT 0,
    error_message   TEXT,
    executed_at     TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_order_history_date ON order_history(date DESC);
CREATE INDEX IF NOT EXISTS idx_order_history_ticker ON order_history(ticker, date DESC);

-- 6. 일별 포트폴리오 스냅샷
CREATE TABLE IF NOT EXISTS portfolio_snapshot (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL UNIQUE,
    total_assets        REAL,
    total_value         REAL,
    total_cash          REAL,
    cash_allocation_pct REAL,
    holdings_json       TEXT,
    sector_json         TEXT,
    warnings_json       TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);

-- 7. ISA 정기매수 이력
CREATE TABLE IF NOT EXISTS dca_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    price           REAL NOT NULL,
    amount          INTEGER NOT NULL,
    cumulative_qty  INTEGER,
    cumulative_cost INTEGER,
    avg_price       REAL,
    fx_rate         REAL,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dca_record_date ON dca_record(date DESC);

-- 8. 시스템 실행 로그
CREATE TABLE IF NOT EXISTS execution_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mode            TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,
    api_calls_kis   INTEGER DEFAULT 0,
    api_calls_av    INTEGER DEFAULT 0,
    summary         TEXT,
    error_message   TEXT
);
