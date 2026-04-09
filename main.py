"""투자 모니터링 시스템 - 메인 스크립트"""
import os
import yaml
from datetime import datetime, date
import pytz
import time
from dotenv import load_dotenv

load_dotenv()  # .env 파일이 있으면 로드, 없으면 무시 (GitHub Actions 호환)

from modules.market_data import (
    get_fx_rate,
    get_kr_etf_price,
    get_kr_etf_monthly_baseline,
    get_kr_etf_multi_period_baselines,
    get_stock_price,
    get_monthly_baseline_price,
    get_us_etf_multi_period_baselines,
    get_stock_fundamentals
)
from modules.fx_checker import check_fx_zone, detect_fx_zone_change
# from modules.ai_summary import generate_macro_summary  # 비활성화 (Perplexity 전환 예정)
from modules.notifier import send_email, format_email_report
from modules.db import InvestmentDB
from modules.telegram import TelegramNotifier

# 지수 ETF 타입 목록
INDEX_TYPES = ('core', 'isa_core', 'isa_core_hedged')

def load_config():
    """config.yaml 로드"""
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def main():
    """메인 실행 함수"""
    print(f"=== 투자 모니터링 리포트 생성 시작 ({datetime.now()}) ===")

    config = load_config()

    exchangerate_api_key = os.getenv('EXCHANGERATE_API_KEY')
    alphavantage_api_key = os.getenv('ALPHAVANTAGE_API_KEY')
    # anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')  # 비활성화
    gmail_address = os.getenv('GMAIL_ADDRESS')
    gmail_app_password = os.getenv('GMAIL_APP_PASSWORD')

    if not all([exchangerate_api_key, alphavantage_api_key, gmail_address, gmail_app_password]):
        print("❌ 필수 환경변수가 설정되지 않았습니다.")
        return

    # DB 초기화 (실패해도 리포트는 계속 진행)
    db = None
    try:
        db = InvestmentDB()
        print("✅ DB 연결 완료")
    except Exception as e:
        print(f"⚠️  DB 초기화 실패 (리포트는 계속 진행): {e}")

    # 텔레그램 초기화 (실패해도 리포트는 계속 진행)
    tg = None
    tg_token = os.getenv('TELEGRAM_BOT_TOKEN')
    tg_chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if tg_token and tg_chat_id:
        tg = TelegramNotifier(tg_token, tg_chat_id)
        print("✅ 텔레그램 봇 초기화 완료")
    else:
        print("⚠️  텔레그램 환경변수 미설정 (알림 비활성화)")

    kst = pytz.timezone('Asia/Seoul')
    today = datetime.now(kst).strftime('%Y-%m-%d')
    execution_started = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    api_limit_exceeded = False

    # 1. 환율 조회
    print("\n[1/5] 환율 조회 중...")
    fx_rate = get_fx_rate(exchangerate_api_key)
    if fx_rate:
        print(f"✅ USD/KRW: {fx_rate:.2f}원")
        fx_zone_info = check_fx_zone(fx_rate, config['fx_rules'])
        print(f"   현재 구간: {fx_zone_info['zone_name']} - {fx_zone_info['action']}")

        # 환율 구간 변경 감지 (DB에서 전일 환율 조회)
        if db and tg:
            prev_fx = db.get_previous_fx(today)
            if prev_fx:
                prev_zone_info = check_fx_zone(prev_fx['usd_krw'], config['fx_rules'])
                if prev_zone_info['zone'] != fx_zone_info['zone']:
                    tg.send_fx_zone_change(prev_zone_info['zone'], fx_zone_info['zone'], fx_rate)
                    print(f"   💱 환율 구간 변경! {prev_zone_info['zone_name']} → {fx_zone_info['zone_name']}")

        # DB 환율 적재
        if db:
            db.save_daily_fx(today, fx_rate, fx_zone_info.get('zone', ''))
    else:
        print("❌ 환율 조회 실패")
        fx_zone_info = None

    # ── ISA 활성 종목 결정 (환율 기준) ──────────────────────────────
    isa_switch_threshold = config.get('isa_fx_switch', {}).get('threshold', 1380)
    isa_active_ticker = '449180.KS' if (fx_rate and fx_rate >= isa_switch_threshold) else '360750.KS'
    print(f"   ISA 활성 종목: {isa_active_ticker} (기준 {isa_switch_threshold}원)")

    # 2. 주식/ETF 데이터 수집
    print("\n[2/5] 주식 데이터 수집 중...")
    stock_data = []
    isa_trigger_data = None      # 449180 급락 트리거 (전월 대비, 한투 종합계좌)
    isa_2month_trigger_data = None  # 449180 급락 트리거 (2달 전 대비, slowly melting 방지)
    isa_sell_trigger_data = None # 133690 매도 트리거 (ISA)
    qcom_condition_data = None

    # 현재 월 (트리거 중복 방지용)
    current_month = datetime.now(kst).strftime('%Y-%m')

    # 급락 버퍼 잔액 조회
    buffer_remaining = None
    if db:
        buffer_remaining = db.get_buffer_remaining('krw_crash')
        print(f"    💰 급락 버퍼 잔액: ₩{buffer_remaining:,.0f}")

    for stock_config in config['watchlist']:
        ticker = stock_config['ticker']
        stock_type = stock_config['type']
        is_index = stock_type in INDEX_TYPES

        # ── 한국 ETF ──────────────────────────────────────────────
        if ticker.endswith('.KS') or ticker.endswith('.KRX'):
            print(f"  - {ticker} 조회 중...")

            price_data = get_kr_etf_price(ticker)
            if not price_data:
                print(f"    ❌ {ticker} 가격 조회 실패")
                continue

            # DB 가격 적재
            if db:
                db.save_daily_price(today, ticker, price_data)

            stock_info = {
                'ticker': ticker,
                'type': stock_type,
                'name': stock_config.get('name', ticker),
                'holdings': stock_config.get('holdings', 0),
                'price_data': price_data
            }

            if is_index:
                # 지수 ETF: 다기간 baseline 조회
                multi_data = get_kr_etf_multi_period_baselines(ticker)
                if multi_data:
                    stock_info['multi_period_data'] = multi_data
                    periods = multi_data.get('periods', {})
                    monthly = periods.get('monthly')

                    # ── 449180 급락 트리거 (449180 전용, 한투 종합계좌에서 매수) ──
                    if stock_config.get('monthly_trigger') and monthly and ticker == '449180.KS':
                        change_pct = monthly['change_pct']
                        trigger_type = None
                        action_amount = 0
                        if change_pct <= -10:
                            trigger_type = 'monthly_10pct'
                            action_amount = 1000000
                        elif change_pct <= -5:
                            trigger_type = 'monthly_5pct'
                            action_amount = 1000000

                        if trigger_type:
                            # DB 중복 방지: 이번 달 이미 발동 여부 확인
                            already_fired = db.is_trigger_fired(trigger_type, ticker, current_month) if db else False
                            if already_fired:
                                print(f"    ⏭️  449180 {trigger_type} 이번 달 이미 발동됨 (스킵)")
                            else:
                                # 버퍼 잔액 확인
                                actual_amount = action_amount
                                if buffer_remaining is not None and buffer_remaining <= 0:
                                    print(f"    🔴 급락 버퍼 소진 — 트리거 발동하지만 매수 불가")
                                    actual_amount = 0
                                elif buffer_remaining is not None and buffer_remaining < action_amount:
                                    actual_amount = buffer_remaining
                                    print(f"    🟡 급락 버퍼 부족 — 잔액 ₩{buffer_remaining:,.0f} 전액 집행")

                                isa_trigger_data = {
                                    'ticker': ticker,
                                    'change_pct': change_pct,
                                    'baseline_date': monthly['date'],
                                    'baseline_price': monthly['price'],
                                    'current_price': multi_data['current_price'],
                                    'trigger_level': '-10% 이상 하락' if '10' in trigger_type else '-5% 이상 하락',
                                    'action': f'급락 버퍼에서 ₩{actual_amount:,.0f} 매수',
                                    'buffer_remaining': buffer_remaining,
                                }
                                print(f"    🚨 449180 급락 트리거 발동! ({change_pct:.2f}%)")

                                # DB 기록 + 버퍼 차감
                                if db:
                                    db.record_trigger(trigger_type, ticker, current_month,
                                                      baseline_date=monthly['date'],
                                                      baseline_price=monthly['price'],
                                                      current_price=multi_data['current_price'],
                                                      change_pct=change_pct,
                                                      action_amount=actual_amount)
                                    if actual_amount > 0:
                                        deducted = db.deduct_buffer('krw_crash', actual_amount)
                                        buffer_remaining = db.get_buffer_remaining('krw_crash')
                                        print(f"    💰 버퍼 차감: ₩{deducted:,.0f} → 잔액 ₩{buffer_remaining:,.0f}")

                                if tg:
                                    tg.send_trigger_alert(trigger_type, isa_trigger_data)
                                    if buffer_remaining is not None:
                                        tg.send_buffer_warning(buffer_remaining)

                    # ── 449180 2달 전 급락 트리거 (slowly melting 방지) ──
                    two_month = periods.get('2month')
                    if ticker == '449180.KS' and two_month:
                        change_2m = two_month['change_pct']
                        trigger_type_2m = None
                        action_amount_2m = 0
                        if change_2m <= -10:
                            trigger_type_2m = '2month_10pct'
                            action_amount_2m = 500000
                        elif change_2m <= -5:
                            trigger_type_2m = '2month_5pct'
                            action_amount_2m = 500000

                        if trigger_type_2m:
                            already_fired_2m = db.is_trigger_fired(trigger_type_2m, ticker, current_month) if db else False
                            if already_fired_2m:
                                print(f"    ⏭️  449180 {trigger_type_2m} 이번 달 이미 발동됨 (스킵)")
                            else:
                                actual_amount_2m = action_amount_2m
                                if buffer_remaining is not None and buffer_remaining <= 0:
                                    print(f"    🔴 급락 버퍼 소진 — 2달 전 트리거 발동하지만 매수 불가")
                                    actual_amount_2m = 0
                                elif buffer_remaining is not None and buffer_remaining < action_amount_2m:
                                    actual_amount_2m = buffer_remaining

                                isa_2month_trigger_data = {
                                    'ticker': ticker,
                                    'change_pct': change_2m,
                                    'baseline_date': two_month['date'],
                                    'baseline_price': two_month['price'],
                                    'current_price': multi_data['current_price'],
                                    'trigger_level': '2달 전 대비 -10% 이상 하락' if '10' in trigger_type_2m else '2달 전 대비 -5% 이상 하락',
                                    'action': f'급락 버퍼에서 ₩{actual_amount_2m:,.0f} 매수',
                                    'buffer_remaining': buffer_remaining,
                                }
                                print(f"    🚨 449180 2달 전 트리거 발동! ({change_2m:.2f}%)")

                                if db:
                                    db.record_trigger(trigger_type_2m, ticker, current_month,
                                                      baseline_date=two_month['date'],
                                                      baseline_price=two_month['price'],
                                                      current_price=multi_data['current_price'],
                                                      change_pct=change_2m,
                                                      action_amount=actual_amount_2m)
                                    if actual_amount_2m > 0:
                                        deducted = db.deduct_buffer('krw_crash', actual_amount_2m)
                                        buffer_remaining = db.get_buffer_remaining('krw_crash')
                                        print(f"    💰 버퍼 차감: ₩{deducted:,.0f} → 잔액 ₩{buffer_remaining:,.0f}")

                                if tg:
                                    tg.send_trigger_alert(trigger_type_2m, isa_2month_trigger_data)
                                    if buffer_remaining is not None:
                                        tg.send_buffer_warning(buffer_remaining)

                    # ── 133690 매도 트리거 (두 조건 모두 충족 필요) ──
                    sell_trigger = stock_config.get('sell_trigger')
                    if sell_trigger and monthly:
                        change_pct = monthly['change_pct']
                        monthly_rise_pct = sell_trigger.get('monthly_rise_pct', 5)
                        avg_price = sell_trigger.get('avg_price', 0)
                        gain_from_avg_pct = sell_trigger.get('gain_from_avg_pct', 15)
                        sell_qty_config = sell_trigger.get('sell_qty', 10)

                        current_price_133 = multi_data['current_price']
                        gain_from_avg = ((current_price_133 - avg_price) / avg_price * 100) if avg_price > 0 else 0
                        cond_monthly = change_pct >= monthly_rise_pct
                        cond_avg = gain_from_avg >= gain_from_avg_pct

                        if cond_monthly and cond_avg:
                            sell_trigger_type = '133690_sell'
                            already_sold = db.is_trigger_fired(sell_trigger_type, ticker, current_month) if db else False
                            if already_sold:
                                print(f"    ⏭️  133690 매도 트리거 이번 달 이미 발동됨 (스킵)")
                            else:
                                holdings = stock_config.get('holdings', 0)
                                sell_qty = min(sell_qty_config, holdings)
                                remaining = max(0, holdings - sell_qty)
                                isa_sell_trigger_data = {
                                    'ticker': ticker,
                                    'change_pct': change_pct,
                                    'baseline_date': monthly['date'],
                                    'baseline_price': monthly['price'],
                                    'current_price': current_price_133,
                                    'avg_price': avg_price,
                                    'gain_from_avg_pct': gain_from_avg,
                                    'sell_qty': sell_qty,
                                    'action': f'{sell_qty}주 매도 (잔여 {remaining}주)'
                                }
                                print(f"    📈 133690 매도 조건 충족! (전월 {change_pct:+.2f}%, 평단 대비 {gain_from_avg:+.1f}%)")

                                if db:
                                    db.record_trigger(sell_trigger_type, ticker, current_month,
                                                      baseline_date=monthly['date'],
                                                      baseline_price=monthly['price'],
                                                      current_price=current_price_133,
                                                      change_pct=change_pct,
                                                      action_amount=0)

                                if tg:
                                    tg.send_133690_sell_alert(isa_sell_trigger_data, remaining_qty=remaining)
                        else:
                            reasons = []
                            if not cond_monthly:
                                reasons.append(f"전월 {change_pct:+.2f}% < +{monthly_rise_pct}%")
                            if not cond_avg:
                                reasons.append(f"평단 대비 {gain_from_avg:+.1f}% < +{gain_from_avg_pct}%")
                            if reasons:
                                print(f"    ⏸️  133690 매도 조건 미충족: {', '.join(reasons)}")

                    # 기간별 수익률 로그
                    m  = periods.get('monthly')
                    m3 = periods.get('3month')
                    m6 = periods.get('6month')
                    y1 = periods.get('1year')
                    if m and m3 and m6 and y1:
                        print(f"    📊 전월:{m['change_pct']:+.2f}% | 3M:{m3['change_pct']:+.2f}% | "
                              f"6M:{m6['change_pct']:+.2f}% | 1Y:{y1['change_pct']:+.2f}%")
                    else:
                        print("    ⚠️  일부 기간 데이터 없음")
            else:
                baseline_data = get_kr_etf_monthly_baseline(ticker)
                if baseline_data:
                    stock_info['baseline_data'] = baseline_data

            stock_data.append(stock_info)
            print(f"    ✅ {ticker}: ₩{price_data['current_price']:,} ({price_data['change_pct']:+.2f}%)")

            # 보유 종목 일간 ±5% 알림
            if tg and stock_config.get('holdings', 0) > 0 and abs(price_data['change_pct']) >= 5.0:
                tg.send_price_alert(ticker, stock_config.get('name', ticker),
                                    price_data['change_pct'], price_data['current_price'], is_krw=True)

            time.sleep(1)

        # ── 미국 주식 ────────────────────────────────────────────
        else:
            print(f"  - {ticker} 조회 중...")

            price_data = get_stock_price(ticker, alphavantage_api_key)
            if not price_data:
                api_limit_exceeded = True
                print(f"    ❌ {ticker} 가격 조회 실패")
                continue

            # DB 가격 적재
            if db:
                db.save_daily_price(today, ticker, price_data)

            stock_info = {
                'ticker': ticker,
                'type': stock_type,
                'name': stock_config.get('name', ticker),
                'holdings': stock_config.get('holdings', 0),
                'sector': stock_config.get('sector'),
                'price_data': price_data
            }

            if is_index:
                # SPYM: 다기간 baseline
                multi_data = get_us_etf_multi_period_baselines(ticker, alphavantage_api_key)
                if multi_data:
                    stock_info['multi_period_data'] = multi_data
                    periods = multi_data.get('periods', {})
                    m  = periods.get('monthly')
                    m3 = periods.get('3month')
                    m6 = periods.get('6month')
                    y1 = periods.get('1year')
                    if m and m3 and m6 and y1:
                        print(f"    📊 전월:{m['change_pct']:+.2f}% | 3M:{m3['change_pct']:+.2f}% | "
                              f"6M:{m6['change_pct']:+.2f}% | 1Y:{y1['change_pct']:+.2f}%")
                    else:
                        print("    ⚠️  일부 기간 데이터 없음")
                else:
                    api_limit_exceeded = True
            else:
                # 개별주: 전월 말일 baseline + 펀더멘탈
                baseline_data = get_monthly_baseline_price(ticker, alphavantage_api_key)
                if baseline_data:
                    baseline_data['current_price'] = price_data['current_price']
                    baseline_data['change_pct'] = (
                        (price_data['current_price'] - baseline_data['baseline_price'])
                        / baseline_data['baseline_price'] * 100
                    )
                    stock_info['baseline_data'] = baseline_data
                    print(f"    📊 전월 대비: {baseline_data['change_pct']:+.2f}%")
                else:
                    api_limit_exceeded = True

                fundamentals = get_stock_fundamentals(ticker, alphavantage_api_key)
                if fundamentals:
                    stock_info['fundamentals'] = fundamentals

                    per           = fundamentals.get('per')
                    roe           = fundamentals.get('roe')
                    debt_equity   = fundamentals.get('debt_equity')
                    profit_margin = fundamentals.get('profit_margin')
                    drop_from_high = fundamentals.get('drop_from_high_pct', 0)

                    per_str = f"{per:.1f}" if per else "N/A"
                    roe_str = f"{float(roe)*100:.1f}%" if roe and roe != 'None' else "N/A"
                    de_str  = f"{float(debt_equity):.2f}" if debt_equity and debt_equity != 'None' else "N/A"
                    pm_str  = f"{float(profit_margin)*100:.1f}%" if profit_margin and profit_margin != 'None' else "N/A"
                    print(f"    📈 PER: {per_str} | ROE: {roe_str} | D/E: {de_str} | Margin: {pm_str} | 52주 고점 대비: {drop_from_high:+.1f}%")

                    # QCOM 매수 조건 체크
                    if stock_config['type'] == 'conditional':
                        buy_condition = stock_config.get('buy_condition', {})
                        per_max  = buy_condition.get('per_max', 25)
                        drop_min = buy_condition.get('drop_pct_min', 15)
                        per_ok   = per is not None and per <= per_max
                        drop_ok  = drop_from_high <= -drop_min

                        if per_ok and drop_ok:
                            # DB 중복 방지
                            qcom_trigger_type = 'qcom_buy'
                            already_alerted = db.is_trigger_fired(qcom_trigger_type, ticker, current_month) if db else False
                            if already_alerted:
                                print(f"    ⏭️  {ticker} 매수 조건 이번 달 이미 안내됨 (스킵)")
                            else:
                                qcom_condition_data = {
                                    'ticker': ticker,
                                    'per': per,
                                    'drop_pct': drop_from_high,
                                    'high_52week': fundamentals['high_52week'],
                                    'current_price': fundamentals['current_price'],
                                    'action': f'매수 적기 - PER {per:.1f} (기준 {per_max} 이하), 52주 고점 대비 {drop_from_high:.1f}% (기준 {drop_min}% 이상 하락)'
                                }
                                print(f"    🎯 {ticker} 매수 조건 충족!")

                                if db:
                                    db.record_trigger(qcom_trigger_type, ticker, current_month,
                                                      current_price=fundamentals['current_price'],
                                                      change_pct=drop_from_high)
                                if tg:
                                    tg.send_qcom_alert(qcom_condition_data)
                        else:
                            reason = []
                            if not per_ok:
                                reason.append(f"PER {per:.1f} > {per_max}" if per else "PER 없음")
                            if not drop_ok:
                                reason.append(f"하락폭 {drop_from_high:.1f}% < {drop_min}%")
                            print(f"    ⏸️  {ticker} 매수 조건 미충족: {', '.join(reason)}")
                else:
                    api_limit_exceeded = True

            stock_data.append(stock_info)
            print(f"    ✅ {ticker}: ${price_data['current_price']} ({price_data['change_pct']:+.2f}%)")

            # 보유 종목 일간 ±5% 알림
            if tg and stock_config.get('holdings', 0) > 0 and abs(price_data['change_pct']) >= 5.0:
                tg.send_price_alert(ticker, stock_config.get('name', ticker),
                                    price_data['change_pct'], price_data['current_price'], is_krw=False)

            time.sleep(2)

    # 3. holdings_only 종목 가격 조회
    print("\n[3/5] 기타 보유 종목 가격 조회 중...")
    holdings_only_data = []

    for holding_config in (config.get('holdings_only') or []):
        ticker = holding_config['ticker']
        print(f"  - {ticker} 조회 중...")

        price_data = get_kr_etf_price(ticker)
        if price_data:
            holdings_only_data.append({
                'ticker': ticker,
                'name': holding_config.get('name', ticker),
                'holdings': holding_config.get('holdings', 0),
                'price': price_data['current_price']
            })
            print(f"    ✅ {ticker}: ₩{price_data['current_price']:,}")
        else:
            print(f"    ❌ {ticker} 가격 조회 실패")
        time.sleep(1)

    # 4. 현금 계산 (ISA / 토스 분리)
    print("\n[4/5] 포트폴리오 비중 계산 중...")

    portfolio_config = config.get('portfolio', {})
    cash_config = portfolio_config.get('cash', {})

    isa_krw      = cash_config.get('isa_krw', 0)
    toss_krw     = cash_config.get('toss_krw', 0)
    toss_usd     = cash_config.get('toss_usd', 0)
    toss_usd_krw = round(toss_usd * fx_rate) if fx_rate and toss_usd else 0
    total_cash   = isa_krw + toss_krw + toss_usd_krw

    print(f"    💰 ISA 현금:   ₩{isa_krw:,.0f}")
    print(f"    💰 토스 원화:  ₩{toss_krw:,.0f}")
    print(f"    💰 토스 달러:  ${toss_usd:,.0f} (₩{toss_usd_krw:,.0f})")
    print(f"    💰 현금 합계:  ₩{total_cash:,.0f}")

    # 총 평가액 계산 (국내/미국 분리)
    total_value       = 0
    kr_value          = 0
    us_value          = 0
    sector_values     = {}
    individual_values = {}

    for stock_info in stock_data:
        ticker   = stock_info.get('ticker', stock_info.get('price_data', {}).get('ticker', ''))
        holdings = stock_info.get('holdings', 0)
        price    = stock_info['price_data']['current_price']

        if ticker.endswith('.KS') or ticker.endswith('.KRX'):
            value_krw = holdings * price
            kr_value += value_krw
        else:
            value_krw = holdings * price * (fx_rate or 1)
            us_value += value_krw

        total_value += value_krw
        individual_values[ticker] = {
            'value': value_krw,
            'holdings': holdings,
            'price': price,
            'name': stock_info.get('name', ticker),
            'type': stock_info.get('type', '')
        }

        sector = stock_info.get('sector')
        if sector:
            sector_values[sector] = sector_values.get(sector, 0) + value_krw

    for holding_data in holdings_only_data:
        ticker    = holding_data['ticker']
        value_krw = holding_data['holdings'] * holding_data['price']
        total_value += value_krw
        individual_values[ticker] = {
            'value': value_krw,
            'holdings': holding_data['holdings'],
            'price': holding_data['price'],
            'name': holding_data.get('name', ticker)
        }

    total_assets = total_value + total_cash

    allocations = {
        ticker: {**data, 'allocation_pct': (data['value'] / total_assets) * 100 if total_assets > 0 else 0}
        for ticker, data in individual_values.items()
    }

    cash_allocation_pct = (total_cash / total_assets) * 100 if total_assets > 0 else 0
    sector_allocations  = {
        sector: (value / total_assets) * 100 if total_assets > 0 else 0
        for sector, value in sector_values.items()
    }

    print(f"    ✅ 총 자산: ₩{total_assets:,.0f} (평가액 ₩{total_value:,.0f} + 현금 ₩{total_cash:,.0f})")
    print(f"    📊 국내: ₩{kr_value:,.0f} | 미국: ₩{us_value:,.0f} (환산)")
    print(f"    📊 현금 비중: {cash_allocation_pct:.1f}%")

    # 5. 포트폴리오 한도 체크
    print("\n[5/5] 포트폴리오 한도 체크 중...")
    limit_warnings = []
    limits = portfolio_config.get('limits', {})

    ai_tech_max = limits.get('ai_tech_sector_max', 0.30)
    ai_tech_pct = sector_allocations.get('ai_tech', 0)
    if ai_tech_pct > ai_tech_max * 100:
        limit_warnings.append({'type': 'sector', 'message': f"AI·테크 섹터 {ai_tech_pct:.1f}% (한도 {ai_tech_max*100:.0f}% 초과)"})
        print(f"    ⚠️  AI·테크 섹터 한도 초과: {ai_tech_pct:.1f}%")
    else:
        print(f"    ✅ AI·테크 섹터: {ai_tech_pct:.1f}% (한도 {ai_tech_max*100:.0f}% 이내)")

    oxy_max = limits.get('oxy_max', 0.10)
    oxy_pct = allocations.get('OXY', {}).get('allocation_pct', 0)
    if oxy_pct > oxy_max * 100:
        limit_warnings.append({'type': 'individual', 'message': f"OXY {oxy_pct:.1f}% (한도 {oxy_max*100:.0f}% 초과)"})
        print(f"    ⚠️  OXY 한도 초과: {oxy_pct:.1f}%")
    else:
        print(f"    ✅ OXY: {oxy_pct:.1f}% (한도 {oxy_max*100:.0f}% 이내)")

    # ── 개별 종목 비중 한도 체크 ──────────────────────────────────
    individual_max = limits.get('individual_stock_max', 0.20)
    for ticker, alloc_data in allocations.items():
        pct = alloc_data.get('allocation_pct', 0)
        if pct > individual_max * 100:
            limit_warnings.append({'type': 'individual', 'message': f"{ticker} {pct:.1f}% (한도 {individual_max*100:.0f}% 초과)"})
            print(f"    ⚠️  {ticker} 한도 초과: {pct:.1f}%")

    # ── speculative 종목 비중 한도 체크 ──────────────────────────
    speculative_max = limits.get('speculative_max', 0.05)
    speculative_pct = sum(
        alloc_data.get('allocation_pct', 0)
        for alloc_data in allocations.values()
        if alloc_data.get('type') == 'speculative'
    )
    if speculative_pct > speculative_max * 100:
        limit_warnings.append({'type': 'speculative', 'message': f"베팅/speculative {speculative_pct:.1f}% (한도 {speculative_max*100:.0f}% 초과)"})
        print(f"    ⚠️  베팅/speculative 한도 초과: {speculative_pct:.1f}%")
    else:
        print(f"    ✅ 베팅/speculative: {speculative_pct:.1f}% (한도 {speculative_max*100:.0f}% 이내)")

    cash_min = limits.get('cash_min', 0.15)
    cash_max = limits.get('cash_max', 0.25)
    if cash_allocation_pct < cash_min * 100:
        limit_warnings.append({'type': 'cash', 'message': f"현금 {cash_allocation_pct:.1f}% (최소 {cash_min*100:.0f}% 미달)"})
        print(f"    ⚠️  현금 부족: {cash_allocation_pct:.1f}%")
    elif cash_allocation_pct > cash_max * 100:
        limit_warnings.append({'type': 'cash', 'message': f"현금 {cash_allocation_pct:.1f}% (최대 {cash_max*100:.0f}% 초과)"})
        print(f"    ⚠️  현금 과다: {cash_allocation_pct:.1f}%")
    else:
        print(f"    ✅ 현금: {cash_allocation_pct:.1f}% (목표 범위 {cash_min*100:.0f}~{cash_max*100:.0f}% 이내)")

    # DB 포트폴리오 스냅샷 적재
    if db:
        db.save_portfolio_snapshot({
            'date': today,
            'total_assets': total_assets,
            'total_value': total_value,
            'total_cash': total_cash,
            'cash_allocation_pct': cash_allocation_pct,
            'holdings': allocations,
            'sectors': sector_allocations,
            'warnings': limit_warnings
        })

    # ── AI 거시경제 요약 비활성화 (Perplexity 전환 예정) ──────────────
    macro_summary = None
    # ───────────────────────────────────────────────────────────────────

    # 이메일 발송
    print("\n이메일 리포트 발송 중...")

    report_data = {
        'timestamp': datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S KST'),
        'fx_rate': fx_rate,
        'fx_zone_info': fx_zone_info,
        'isa_active_ticker': isa_active_ticker,
        'stock_data': stock_data,
        'isa_trigger': isa_trigger_data,
        'isa_2month_trigger': isa_2month_trigger_data,
        'isa_sell_trigger': isa_sell_trigger_data,
        'qcom_condition': qcom_condition_data,
        'cash_info': {
            'isa_krw': isa_krw,
            'toss_krw': toss_krw,
            'toss_usd': toss_usd,
            'toss_usd_krw': toss_usd_krw,
            'total_cash': total_cash,
            'cash_allocation_pct': cash_allocation_pct
        },
        'portfolio_summary': {
            'total_assets': total_assets,
            'total_value': total_value,
            'total_cash': total_cash,
            'kr_value': kr_value,
            'us_value': us_value,
            'allocations': allocations,
            'sector_allocations': sector_allocations,
            'cash_allocation_pct': cash_allocation_pct
        },
        'portfolio_warnings': limit_warnings,
        'buffer_remaining': buffer_remaining,
        'macro_summary': macro_summary
    }

    email_html = format_email_report(report_data)

    email_sent = send_email(
        gmail_address,
        gmail_app_password,
        gmail_address,
        "📊 투자 모니터링 데일리 리포트",
        email_html
    )

    print("    ✅ 이메일 발송 완료" if email_sent else "    ❌ 이메일 발송 실패")

    # ── 텔레그램 알림 ──────────────────────────────────────────────────
    if tg:
        print("\n텔레그램 알림 발송 중...")

        # 포트폴리오 한도 경고
        if limit_warnings:
            tg.send_portfolio_warning(limit_warnings)
            print("    ✅ 포트폴리오 경고 발송")

        # 국내 종가 리포트 (금요일이면 주간 요약 포함)
        today_date = datetime.now(kst)
        is_friday = today_date.weekday() == 4
        weekly_data = None
        if is_friday and db:
            from datetime import timedelta
            monday = (today_date - timedelta(days=today_date.weekday())).strftime('%Y-%m-%d')
            mon_snapshot = db.get_nearest_snapshot(monday, direction='after')
            if mon_snapshot and mon_snapshot.get('total_assets'):
                week_change = total_assets - mon_snapshot['total_assets']
                week_change_pct = (week_change / mon_snapshot['total_assets']) * 100
                week_triggers = db.get_triggers_since(monday)
                weekly_data = {
                    'total_change': week_change,
                    'total_change_pct': week_change_pct,
                    'triggers_fired': [t['trigger_type'] for t in week_triggers]
                }
                print(f"    📅 주간 요약: {week_change:+,.0f}원 ({week_change_pct:+.1f}%)")
        tg.send_kr_market_close(report_data, weekly_data=weekly_data)
        print("    ✅ 국내 종가 리포트 발송")

        # 미국 종가 리포트
        tg.send_us_market_close(report_data)
        print("    ✅ 미국 종가 리포트 발송")

        # 정기 리마인더 (매달 1일 / 15일)
        day = today_date.day
        if day == 1:
            tg.send_monthly_checklist('first', fx_rate or 0, isa_active_ticker)
            print("    ✅ 월초 체크리스트 발송")
        elif day == 15:
            tg.send_monthly_checklist('mid', fx_rate or 0, isa_active_ticker)
            print("    ✅ 월중 비중점검 리마인더 발송")

        # ISA 만기 카운트다운 (D-90, D-30, D-7)
        days_to_isa = (date(2027, 8, 9) - today_date.date()).days
        if days_to_isa in (90, 30, 7):
            tg.send_isa_countdown(days_to_isa)
            print(f"    ✅ ISA 만기 D-{days_to_isa} 알림 발송")

        # 이메일 실패 시 에러 알림
        if not email_sent:
            tg.send_error_alert("이메일 발송 실패 — Gmail SMTP 확인 필요")

    print("\n=== 리포트 생성 완료 ===")

    if api_limit_exceeded:
        print("\n" + "="*50)
        print("⚠️  Alpha Vantage API 한도 초과 - 일부 데이터 조회 실패")
        print("="*50)

    try:
        from modules.market_data import AV_API_CALLS, AV_DAILY_LIMIT
        if AV_API_CALLS > 0:
            usage_pct = (AV_API_CALLS / AV_DAILY_LIMIT) * 100
            print(f"\n📊 오늘 Alpha Vantage API 사용량: {AV_API_CALLS}/{AV_DAILY_LIMIT} ({usage_pct:.1f}%)")
            print(f"   남은 호출 수: {AV_DAILY_LIMIT - AV_API_CALLS}회")
    except ImportError:
        AV_API_CALLS = 0

    # DB 실행 로그 기록 및 연결 종료
    if db:
        db.log_execution(
            mode='report',
            status='success' if email_sent else 'partial',
            summary=f"종목 {len(stock_data)}개 수집, 이메일 {'성공' if email_sent else '실패'}",
            started_at=execution_started,
            api_calls_av=AV_API_CALLS
        )
        db.close()
        print("✅ DB 기록 완료")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 예기치 않은 오류: {e}")
        # 텔레그램으로 에러 알림 시도
        try:
            from dotenv import load_dotenv
            load_dotenv()
            token = os.getenv('TELEGRAM_BOT_TOKEN')
            chat_id = os.getenv('TELEGRAM_CHAT_ID')
            if token and chat_id:
                TelegramNotifier(token, chat_id).send_error_alert(
                    f"main.py 실행 중 크래시:\n{type(e).__name__}: {e}"
                )
        except Exception:
            pass
        raise