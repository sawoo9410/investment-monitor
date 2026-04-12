"""투자 모니터링 시스템 - 메인 스크립트"""
import os
import yaml
from datetime import datetime
import pytz
import time

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
from modules.fx_checker import check_fx_zone
# from modules.ai_summary import generate_macro_summary  # 비활성화 (Perplexity 전환 예정)
from modules.notifier import send_email, format_email_report

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
    gmail_address = os.getenv('GMAIL_ADDRESS')
    gmail_app_password = os.getenv('GMAIL_APP_PASSWORD')

    if not all([exchangerate_api_key, alphavantage_api_key, gmail_address, gmail_app_password]):
        print("❌ 필수 환경변수가 설정되지 않았습니다.")
        return

    api_limit_exceeded = False

    # 1. 환율 조회
    print("\n[1/3] 환율 조회 중...")
    fx_rate = get_fx_rate(exchangerate_api_key)
    if fx_rate:
        print(f"✅ USD/KRW: {fx_rate:.2f}원")
        fx_zone_info = check_fx_zone(fx_rate, config['fx_rules'])
        print(f"   현재 구간: {fx_zone_info['zone_name']} - {fx_zone_info['action']}")
    else:
        print("❌ 환율 조회 실패")
        fx_zone_info = None

    # ── ISA 활성 종목 결정 (환율 기준) ──────────────────────────────
    isa_switch_threshold = config.get('isa_fx_switch', {}).get('threshold', 1380)
    isa_active_ticker = '449180.KS' if (fx_rate and fx_rate >= isa_switch_threshold) else '360750.KS'
    print(f"   ISA 활성 종목: {isa_active_ticker} (기준 {isa_switch_threshold}원)")

    # 2. 주식/ETF 데이터 수집
    print("\n[2/3] 주식 데이터 수집 중...")
    stock_data = []
    isa_trigger_data = None      # ISA 매수 트리거 (전월 대비)
    isa_2month_trigger_data = None  # ISA 매수 트리거 (2달 전 대비, slowly melting 방지)
    isa_sell_trigger_data = None # ISA 매도 트리거 (133690.KS)

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

                    # ── ISA 매수 트리거 (449180 전용) ──────────
                    if stock_config.get('monthly_trigger') and monthly and ticker == '449180.KS':
                        change_pct = monthly['change_pct']
                        if change_pct <= -10:
                            isa_trigger_data = {
                                'ticker': ticker,
                                'change_pct': change_pct,
                                'baseline_date': monthly['date'],
                                'baseline_price': monthly['price'],
                                'current_price': multi_data['current_price'],
                                'trigger_level': '-10% 이상 하락',
                                'action': '현금 버퍼에서 100만원 추가 매수'
                            }
                            print(f"    🚨 ISA 매수 트리거 발동! ({change_pct:.2f}%)")
                        elif change_pct <= -5:
                            isa_trigger_data = {
                                'ticker': ticker,
                                'change_pct': change_pct,
                                'baseline_date': monthly['date'],
                                'baseline_price': monthly['price'],
                                'current_price': multi_data['current_price'],
                                'trigger_level': '-5% 이상 하락',
                                'action': '현금 버퍼에서 100만원 추가 매수'
                            }
                            print(f"    ⚠️  ISA 매수 트리거 접근 중 ({change_pct:.2f}%)")

                    # ── ISA 2달 전 매수 트리거 (449180 전용, slowly melting 방지) ──
                    two_month = periods.get('2month')
                    if ticker == '449180.KS' and two_month:
                        change_2m = two_month['change_pct']
                        if change_2m <= -10:
                            isa_2month_trigger_data = {
                                'ticker': ticker,
                                'change_pct': change_2m,
                                'baseline_date': two_month['date'],
                                'baseline_price': two_month['price'],
                                'current_price': multi_data['current_price'],
                                'trigger_level': '2달 전 대비 -10% 이상 하락',
                                'action': '현금 버퍼에서 50만원 추가 매수'
                            }
                            print(f"    🚨 ISA 2달 전 트리거 발동! ({change_2m:.2f}%)")
                        elif change_2m <= -5:
                            isa_2month_trigger_data = {
                                'ticker': ticker,
                                'change_pct': change_2m,
                                'baseline_date': two_month['date'],
                                'baseline_price': two_month['price'],
                                'current_price': multi_data['current_price'],
                                'trigger_level': '2달 전 대비 -5% 이상 하락',
                                'action': '현금 버퍼에서 50만원 추가 매수'
                            }
                            print(f"    ⚠️  ISA 2달 전 트리거 접근 중 ({change_2m:.2f}%)")

                    # ── ISA 매도 트리거 (133690.KS) ──────────────────
                    sell_trigger = stock_config.get('sell_trigger')
                    if sell_trigger and monthly:
                        change_pct = monthly['change_pct']
                        rise_all  = sell_trigger.get('rise_all_sell', 10)
                        rise_half = sell_trigger.get('rise_50pct_sell', 5)

                        if change_pct >= rise_all:
                            isa_sell_trigger_data = {
                                'ticker': ticker,
                                'change_pct': change_pct,
                                'baseline_date': monthly['date'],
                                'baseline_price': monthly['price'],
                                'current_price': multi_data['current_price'],
                                'trigger_level': f'+{rise_all}% 이상 상승',
                                'action': f'전량 매도 ({stock_config.get("holdings", 0)}주)'
                            }
                            print(f"    🚨 ISA 매도 트리거 발동! 전량 ({change_pct:.2f}%)")
                        elif change_pct >= rise_half:
                            holdings = stock_config.get('holdings', 0)
                            isa_sell_trigger_data = {
                                'ticker': ticker,
                                'change_pct': change_pct,
                                'baseline_date': monthly['date'],
                                'baseline_price': monthly['price'],
                                'current_price': multi_data['current_price'],
                                'trigger_level': f'+{rise_half}% 이상 상승',
                                'action': f'50% 매도 ({holdings // 2}주)'
                            }
                            print(f"    ⚠️  ISA 매도 트리거 접근 중 50% ({change_pct:.2f}%)")

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
            time.sleep(1)

        # ── 미국 주식 ────────────────────────────────────────────
        else:
            print(f"  - {ticker} 조회 중...")

            price_data = get_stock_price(ticker, alphavantage_api_key)
            if not price_data:
                api_limit_exceeded = True
                print(f"    ❌ {ticker} 가격 조회 실패")
                continue

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
                else:
                    api_limit_exceeded = True

            stock_data.append(stock_info)
            print(f"    ✅ {ticker}: ${price_data['current_price']} ({price_data['change_pct']:+.2f}%)")
            time.sleep(2)

    # 3. 이메일 발송
    print("\n[3/3] 이메일 리포트 발송 중...")

    report_data = {
        'timestamp': datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S KST'),
        'isa_active_ticker': isa_active_ticker,
        'stock_data': stock_data,
        'isa_trigger': isa_trigger_data,
        'isa_2month_trigger': isa_2month_trigger_data,
        'isa_sell_trigger': isa_sell_trigger_data,
        'spym_fx_rate': config.get('spym_fx_rate', 1420),
    }

    email_html = format_email_report(report_data)

    recipients = config.get('email_report', {}).get('recipients', [gmail_address])

    email_sent = send_email(
        gmail_address,
        gmail_app_password,
        recipients,
        "📊 투자 모니터링 데일리 리포트",
        email_html
    )

    print("    ✅ 이메일 발송 완료" if email_sent else "    ❌ 이메일 발송 실패")
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
        pass

if __name__ == "__main__":
    main()
