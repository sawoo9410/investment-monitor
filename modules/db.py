"""투자 모니터링 DB 모듈 (SQLite)"""
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, Dict


class InvestmentDB:
    """SQLite 기반 투자 데이터 저장소.

    DB 실패가 리포트 파이프라인을 차단하면 안 되므로
    모든 write 메서드는 try/except로 감싸고 bool을 반환한다.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.getenv('DB_PATH', 'data/investment.db')
        # DB 디렉토리 생성
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        """init_db.sql 실행 (테이블 없으면 생성)"""
        script_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'init_db.sql')
        with open(script_path, 'r', encoding='utf-8') as f:
            self.conn.executescript(f.read())

    # =========================================================================
    # 가격
    # =========================================================================

    def save_daily_price(self, date: str, ticker: str, price_data: dict) -> bool:
        """일별 종가 저장. date='2026-04-08', price_data는 market_data 반환값."""
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO daily_price (date, ticker, close_price, change_pct, source)
                   VALUES (?, ?, ?, ?, ?)""",
                (date, ticker,
                 price_data.get('current_price'),
                 price_data.get('change_pct'),
                 'fdr' if ticker.endswith('.KS') or ticker.endswith('.KRX') else 'alphavantage')
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"    ⚠️  DB 가격 저장 실패 ({ticker}): {e}")
            return False

    def get_price(self, ticker: str, date: str) -> Optional[Dict]:
        """특정 종목의 특정 날짜 가격 조회."""
        row = self.conn.execute(
            "SELECT * FROM daily_price WHERE ticker = ? AND date = ?",
            (ticker, date)
        ).fetchone()
        return dict(row) if row else None

    def get_month_end_price(self, ticker: str, year: int, month: int) -> Optional[Dict]:
        """특정 월 마지막 거래일 가격 조회."""
        month_prefix = f"{year}-{month:02d}"
        row = self.conn.execute(
            """SELECT * FROM daily_price
               WHERE ticker = ? AND date LIKE ?
               ORDER BY date DESC LIMIT 1""",
            (ticker, f"{month_prefix}%")
        ).fetchone()
        return dict(row) if row else None

    # =========================================================================
    # 환율
    # =========================================================================

    def save_daily_fx(self, date: str, usd_krw: float, fx_zone: str) -> bool:
        """일별 환율 저장."""
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO daily_fx (date, usd_krw, fx_zone)
                   VALUES (?, ?, ?)""",
                (date, usd_krw, fx_zone)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"    ⚠️  DB 환율 저장 실패: {e}")
            return False

    # =========================================================================
    # 트리거
    # =========================================================================

    def record_trigger(self, trigger_type: str, ticker: str, month: str,
                       baseline_date: str = None, baseline_price: float = None,
                       current_price: float = None, change_pct: float = None,
                       action_amount: int = None) -> bool:
        """트리거 발동 기록. month='2026-04'."""
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO trigger_event
                   (trigger_month, trigger_type, ticker, baseline_date, baseline_price,
                    current_price, change_pct, action_amount)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (month, trigger_type, ticker, baseline_date, baseline_price,
                 current_price, change_pct, action_amount)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"    ⚠️  DB 트리거 기록 실패: {e}")
            return False

    def is_trigger_fired(self, trigger_type: str, ticker: str, month: str) -> bool:
        """해당 월에 이미 발동된 트리거인지 확인."""
        row = self.conn.execute(
            """SELECT id FROM trigger_event
               WHERE trigger_type = ? AND ticker = ? AND trigger_month = ?""",
            (trigger_type, ticker, month)
        ).fetchone()
        return row is not None

    # =========================================================================
    # 버퍼
    # =========================================================================

    def get_buffer_remaining(self, buffer_type: str = 'krw_crash') -> int:
        """급락 버퍼 잔액 조회. 없으면 0."""
        row = self.conn.execute(
            "SELECT remaining FROM trigger_buffer WHERE buffer_type = ?",
            (buffer_type,)
        ).fetchone()
        return row['remaining'] if row else 0

    def deduct_buffer(self, buffer_type: str, amount: int) -> int:
        """버퍼에서 amount 차감. 잔액 부족 시 남은 만큼만 차감. 실제 차감액 반환."""
        remaining = self.get_buffer_remaining(buffer_type)
        if remaining <= 0:
            return 0
        deducted = min(amount, remaining)
        try:
            self.conn.execute(
                """UPDATE trigger_buffer
                   SET remaining = remaining - ?, last_updated = datetime('now')
                   WHERE buffer_type = ?""",
                (deducted, buffer_type)
            )
            self.conn.commit()
            return deducted
        except Exception as e:
            print(f"    ⚠️  DB 버퍼 차감 실패: {e}")
            return 0

    # =========================================================================
    # 주문
    # =========================================================================

    def record_order(self, order_data: dict) -> bool:
        """주문 체결 기록."""
        try:
            self.conn.execute(
                """INSERT INTO order_history
                   (date, ticker, action, quantity, price, amount, currency,
                    account, trigger_type, order_type, status, is_dry_run, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (order_data['date'], order_data['ticker'], order_data['action'],
                 order_data['quantity'], order_data['price'], order_data['amount'],
                 order_data.get('currency', 'KRW'), order_data['account'],
                 order_data.get('trigger_type'), order_data.get('order_type'),
                 order_data['status'], order_data.get('is_dry_run', 0),
                 order_data.get('error_message'))
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"    ⚠️  DB 주문 기록 실패: {e}")
            return False

    def get_daily_orders_count(self, date: str) -> int:
        """특정 날짜의 주문 건수 조회."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM order_history WHERE date = ? AND status = 'executed'",
            (date,)
        ).fetchone()
        return row['cnt'] if row else 0

    # =========================================================================
    # 포트폴리오
    # =========================================================================

    def save_portfolio_snapshot(self, snapshot: dict) -> bool:
        """일별 포트폴리오 스냅샷 저장."""
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO portfolio_snapshot
                   (date, total_assets, total_value, total_cash, cash_allocation_pct,
                    holdings_json, sector_json, warnings_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (snapshot['date'],
                 snapshot.get('total_assets'),
                 snapshot.get('total_value'),
                 snapshot.get('total_cash'),
                 snapshot.get('cash_allocation_pct'),
                 json.dumps(snapshot.get('holdings'), ensure_ascii=False) if snapshot.get('holdings') else None,
                 json.dumps(snapshot.get('sectors'), ensure_ascii=False) if snapshot.get('sectors') else None,
                 json.dumps(snapshot.get('warnings'), ensure_ascii=False) if snapshot.get('warnings') else None)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"    ⚠️  DB 포트폴리오 저장 실패: {e}")
            return False

    # =========================================================================
    # DCA
    # =========================================================================

    def record_dca(self, dca_data: dict) -> bool:
        """ISA 정기매수 기록."""
        try:
            self.conn.execute(
                """INSERT INTO dca_record
                   (date, ticker, quantity, price, amount,
                    cumulative_qty, cumulative_cost, avg_price, fx_rate)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (dca_data['date'], dca_data['ticker'], dca_data['quantity'],
                 dca_data['price'], dca_data['amount'],
                 dca_data.get('cumulative_qty'), dca_data.get('cumulative_cost'),
                 dca_data.get('avg_price'), dca_data.get('fx_rate'))
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"    ⚠️  DB DCA 기록 실패: {e}")
            return False

    # =========================================================================
    # 실행 로그
    # =========================================================================

    def log_execution(self, mode: str, status: str, summary: str = None,
                      started_at: str = None, api_calls_av: int = 0,
                      error_message: str = None) -> bool:
        """시스템 실행 로그 기록."""
        try:
            now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            self.conn.execute(
                """INSERT INTO execution_log
                   (mode, started_at, finished_at, status, api_calls_av, summary, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (mode, started_at or now, now, status, api_calls_av,
                 summary, error_message)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"    ⚠️  DB 실행 로그 저장 실패: {e}")
            return False

    # =========================================================================
    # 연결 관리
    # =========================================================================

    def close(self):
        """DB 연결 종료."""
        if self.conn:
            self.conn.close()
