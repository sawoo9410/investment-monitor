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
    # anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')  # 비활성화
    gmail_address = os.getenv('GMAIL_ADDRESS')
    gmail_app_password = os.getenv('GMAIL_APP_PASSWORD')

    if not all([exchangerate_api_key, alphavantage_api_key, gmail_address, gmail_app_password]):
        print("❌ 필수 환경변수가 설정되지 않았습니다.")
        return

    api_limit_exceeded = False

    # 1. 환율 조회
    print("\n[1/5] 환율 조회 중...")
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
    print("\n[2/5] 주식 데이터 수집 중...")
    stock_data = []
    isa_trigger_data = None      # ISA 매수 트리거 (전월 대비)
    isa_2month_trigger_data = None  # ISA 매수 트리거 (2달 전 대비, slowly melting 방지)
    isa_sell_trigger_data = None # ISA 매도 트리거 (133690.KS)
    qcom_condition_data = None

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

                    # QCOM 매수 조건 체크
                    if stock_config['type'] == 'conditional':
                        buy_condition = stock_config.get('buy_condition', {})
                        per_max  = buy_condition.get('per_max', 25)
                        drop_min = buy_condition.get('drop_pct_min', 15)
                        per_ok   = per is not None and per <= per_max
                        drop_ok  = drop_from_high <= -drop_min

                        if per_ok and drop_ok:
                            qcom_condition_data = {
                                'ticker': ticker,
                                'per': per,
                                'drop_pct': drop_from_high,
                                'high_52week': fundamentals['high_52week'],
                                'current_price': fundamentals['current_price'],
                                'action': f'매수 적기 - PER {per:.1f} (기준 {per_max} 이하), 52주 고점 대비 {drop_from_high:.1f}% (기준 {drop_min}% 이상 하락)'
                            }
                            print(f"    🎯 {ticker} 매수 조건 충족!")
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

    # 총 평가액 계산
    total_value       = 0
    sector_values     = {}
    individual_values = {}

    for stock_info in stock_data:
        ticker   = stock_info.get('ticker', stock_info.get('price_data', {}).get('ticker', ''))
        holdings = stock_info.get('holdings', 0)
        price    = stock_info['price_data']['current_price']

        if ticker.endswith('.KS') or ticker.endswith('.KRX'):
            value_krw = holdings * price
        else:
            value_krw = holdings * price * (fx_rate or 1)

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
            'allocations': allocations,
            'sector_allocations': sector_allocations,
            'cash_allocation_pct': cash_allocation_pct
        },
        'portfolio_warnings': limit_warnings,
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