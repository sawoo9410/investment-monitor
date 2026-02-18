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
    get_stock_price,
    get_monthly_baseline_price,
    get_stock_fundamentals
)
from modules.fx_checker import check_fx_zone
from modules.ai_summary import generate_macro_summary
from modules.notifier import send_email, format_email_report

def load_config():
    """config.yaml 로드"""
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def main():
    """메인 실행 함수"""
    print(f"=== 투자 모니터링 리포트 생성 시작 ({datetime.now()}) ===")
    
    # 설정 로드
    config = load_config()
    
    # 환경변수에서 API 키 로드
    exchangerate_api_key = os.getenv('EXCHANGERATE_API_KEY')
    alphavantage_api_key = os.getenv('ALPHAVANTAGE_API_KEY')
    anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
    telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
    gmail_address = os.getenv('GMAIL_ADDRESS')
    gmail_app_password = os.getenv('GMAIL_APP_PASSWORD')
    
    if not all([exchangerate_api_key, alphavantage_api_key, gmail_address, gmail_app_password]):
        print("❌ 필수 환경변수가 설정되지 않았습니다.")
        return
    
    # 1. 환율 조회
    print("\n[1/6] 환율 조회 중...")
    fx_rate = get_fx_rate(exchangerate_api_key)
    if fx_rate:
        print(f"✅ USD/KRW: {fx_rate:.2f}원")
        fx_zone_info = check_fx_zone(fx_rate, config['fx_rules'])
        print(f"   현재 구간: {fx_zone_info['zone_name']} - {fx_zone_info['action']}")
    else:
        print("❌ 환율 조회 실패")
        fx_zone_info = None
    
    # 2. 주식/ETF 데이터 수집 (한국 + 미국)
    print("\n[2/6] 주식 데이터 수집 중...")
    stock_data = []
    isa_trigger_data = None
    qcom_condition_data = None
    
    for stock_config in config['watchlist']:
        ticker = stock_config['ticker']
        
        # 한국 ETF 처리
        if ticker.endswith('.KS') or ticker.endswith('.KRX'):
            print(f"  - {ticker} 조회 중...")
            
            price_data = get_kr_etf_price(ticker)
            if not price_data:
                print(f"    ❌ {ticker} 가격 조회 실패")
                continue
            
            stock_info = {
                'ticker': ticker,
                'type': stock_config['type'],
                'name': stock_config.get('name', ticker),
                'holdings': stock_config.get('holdings', 0),
                'price_data': price_data
            }
            
            # ISA 트리거 체크
            if stock_config.get('monthly_trigger'):
                baseline_data = get_kr_etf_monthly_baseline(ticker)
                if baseline_data:
                    stock_info['baseline_data'] = baseline_data
                    
                    change_pct = baseline_data['change_pct']
                    if change_pct <= -10:
                        isa_trigger_data = {
                            'ticker': ticker,
                            'change_pct': change_pct,
                            'baseline_date': baseline_data['baseline_date'],
                            'baseline_price': baseline_data['baseline_price'],
                            'current_price': baseline_data['current_price'],
                            'trigger_level': '-10% 이상 하락',
                            'action': '예비 현금의 60% 추가 매수'
                        }
                        print(f"    🚨 ISA 트리거 발동! ({change_pct:.2f}%)")
                    elif change_pct <= -5:
                        isa_trigger_data = {
                            'ticker': ticker,
                            'change_pct': change_pct,
                            'baseline_date': baseline_data['baseline_date'],
                            'baseline_price': baseline_data['baseline_price'],
                            'current_price': baseline_data['current_price'],
                            'trigger_level': '-5% 이상 하락',
                            'action': '예비 현금의 30% 추가 매수'
                        }
                        print(f"    ⚠️  ISA 트리거 접근 중 ({change_pct:.2f}%)")
            
            stock_data.append(stock_info)
            print(f"    ✅ {ticker}: ₩{price_data['current_price']:,} ({price_data['change_pct']:+.2f}%)")
            
            time.sleep(1)  # Rate limit 방어
        
        else:
            # 미국 주식 처리
            print(f"  - {ticker} 조회 중...")
            
            price_data = get_stock_price(ticker, alphavantage_api_key)
            if not price_data:
                print(f"    ❌ {ticker} 가격 조회 실패")
                continue
            
            stock_info = {
                'ticker': ticker,
                'type': stock_config['type'],
                'name': stock_config.get('name', ticker),
                'holdings': stock_config.get('holdings', 0),
                'sector': stock_config.get('sector'),
                'price_data': price_data
            }
            
            # 전월 1일 대비 조회 (모든 미국 주식)
            baseline_data = get_monthly_baseline_price(ticker, alphavantage_api_key)
            if baseline_data:
                stock_info['baseline_data'] = baseline_data
                print(f"    📊 전월 대비: {baseline_data['change_pct']:+.2f}%")
            
            # 개별주는 모두 펀더멘탈 조회 (ETF 제외)
            if stock_config['type'] != 'core':  # SPYM 제외
                fundamentals = get_stock_fundamentals(ticker, alphavantage_api_key)
                
                if fundamentals:
                    stock_info['fundamentals'] = fundamentals
                    
                    # 주요 지표 파싱
                    per = fundamentals.get('per')
                    roe = fundamentals.get('roe')
                    debt_equity = fundamentals.get('debt_equity')
                    profit_margin = fundamentals.get('profit_margin')
                    drop_from_high = fundamentals.get('drop_from_high_pct', 0)
                    
                    # 로그 출력
                    per_str = f"{per:.1f}" if per else "N/A"
                    roe_str = f"{float(roe)*100:.1f}%" if roe and roe != 'None' else "N/A"
                    de_str = f"{float(debt_equity):.2f}" if debt_equity and debt_equity != 'None' else "N/A"
                    pm_str = f"{float(profit_margin)*100:.1f}%" if profit_margin and profit_margin != 'None' else "N/A"
                    
                    print(f"    📈 PER: {per_str} | ROE: {roe_str} | D/E: {de_str} | Margin: {pm_str} | 52주 고점 대비: {drop_from_high:+.1f}%")
                    
                    # QCOM만 매수 조건 체크
                    if stock_config['type'] == 'conditional':
                        buy_condition = stock_config.get('buy_condition', {})
                        
                        per_max = buy_condition.get('per_max', 25)
                        drop_min = buy_condition.get('drop_pct_min', 15)
                        
                        # 조건 충족 여부
                        per_ok = per is not None and per <= per_max
                        drop_ok = drop_from_high <= -drop_min
                        
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
                                reason.append(f"PER {per:.1f} > {per_max}")
                            if not drop_ok:
                                reason.append(f"하락폭 {drop_from_high:.1f}% < {drop_min}%")
                            print(f"    ⏸️  {ticker} 매수 조건 미충족: {', '.join(reason)}")
            
            stock_data.append(stock_info)
            print(f"    ✅ {ticker}: ${price_data['current_price']} ({price_data['change_pct']:+.2f}%)")
            
            time.sleep(2)  # Alpha Vantage Rate limit 방어
    
    # 3. holdings_only 종목 가격 조회 (비중 계산용)
    print("\n[3/6] 기타 보유 종목 가격 조회 중...")
    holdings_only_data = []
    
    for holding_config in config.get('holdings_only', []):
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
    
    # 4. 포트폴리오 비중 계산
    print("\n[4/6] 포트폴리오 비중 계산 중...")
    
    portfolio_config = config.get('portfolio', {})
    cash_krw = portfolio_config.get('cash_krw', 0)
    
    # 총 평가액 계산
    total_value = 0
    sector_values = {}
    individual_values = {}
    
    # watchlist 종목
    for stock_info in stock_data:
        ticker = stock_info['ticker']
        holdings = stock_info.get('holdings', 0)
        price = stock_info['price_data']['current_price']
        
        # 원화 환산
        if ticker.endswith('.KS') or ticker.endswith('.KRX'):
            value_krw = holdings * price
        else:
            value_krw = holdings * price * fx_rate
        
        total_value += value_krw
        individual_values[ticker] = {
            'value': value_krw,
            'holdings': holdings,
            'price': price,
            'name': stock_info.get('name', ticker)
        }
        
        # 섹터별 집계
        sector = stock_info.get('sector')
        if sector:
            if sector not in sector_values:
                sector_values[sector] = 0
            sector_values[sector] += value_krw
    
    # holdings_only 종목
    for holding_data in holdings_only_data:
        ticker = holding_data['ticker']
        value_krw = holding_data['holdings'] * holding_data['price']
        total_value += value_krw
        
        individual_values[ticker] = {
            'value': value_krw,
            'holdings': holding_data['holdings'],
            'price': holding_data['price'],
            'name': holding_data.get('name', ticker)
        }
    
    # 총 자산 (평가액 + 현금)
    total_assets = total_value + cash_krw
    
    # 비중 계산
    allocations = {}
    for ticker, data in individual_values.items():
        allocations[ticker] = {
            **data,
            'allocation_pct': (data['value'] / total_assets) * 100
        }
    
    cash_allocation_pct = (cash_krw / total_assets) * 100
    
    # 섹터 비중 계산
    sector_allocations = {}
    for sector, value in sector_values.items():
        sector_allocations[sector] = (value / total_assets) * 100
    
    print(f"    ✅ 총 자산: ₩{total_assets:,.0f} (평가액 ₩{total_value:,.0f} + 현금 ₩{cash_krw:,.0f})")
    print(f"    📊 현금 비중: {cash_allocation_pct:.1f}%")
    
    # 5. 포트폴리오 한도 체크
    print("\n[5/6] 포트폴리오 한도 체크 중...")
    limit_warnings = []
    
    limits = portfolio_config.get('limits', {})
    sectors_config = portfolio_config.get('sectors', {})
    
    # AI·테크 섹터 체크
    ai_tech_max = limits.get('ai_tech_sector_max', 0.30)
    ai_tech_pct = sector_allocations.get('ai_tech', 0)
    
    if ai_tech_pct > ai_tech_max * 100:
        limit_warnings.append({
            'type': 'sector',
            'sector': 'AI·테크',
            'current_pct': ai_tech_pct,
            'limit_pct': ai_tech_max * 100,
            'message': f"AI·테크 섹터 {ai_tech_pct:.1f}% (한도 {ai_tech_max*100:.0f}% 초과)"
        })
        print(f"    ⚠️  AI·테크 섹터 한도 초과: {ai_tech_pct:.1f}%")
    else:
        print(f"    ✅ AI·테크 섹터: {ai_tech_pct:.1f}% (한도 {ai_tech_max*100:.0f}% 이내)")
    
    # OXY 개별 종목 체크
    oxy_max = limits.get('oxy_max', 0.10)
    oxy_pct = allocations.get('OXY', {}).get('allocation_pct', 0)
    
    if oxy_pct > oxy_max * 100:
        limit_warnings.append({
            'type': 'individual',
            'ticker': 'OXY',
            'current_pct': oxy_pct,
            'limit_pct': oxy_max * 100,
            'message': f"OXY {oxy_pct:.1f}% (한도 {oxy_max*100:.0f}% 초과)"
        })
        print(f"    ⚠️  OXY 한도 초과: {oxy_pct:.1f}%")
    else:
        print(f"    ✅ OXY: {oxy_pct:.1f}% (한도 {oxy_max*100:.0f}% 이내)")
    
    # 현금 비중 체크
    cash_min = limits.get('cash_min', 0.15)
    cash_max = limits.get('cash_max', 0.25)
    
    if cash_allocation_pct < cash_min * 100:
        limit_warnings.append({
            'type': 'cash',
            'current_pct': cash_allocation_pct,
            'limit_pct': cash_min * 100,
            'message': f"현금 {cash_allocation_pct:.1f}% (최소 {cash_min*100:.0f}% 미달)"
        })
        print(f"    ⚠️  현금 부족: {cash_allocation_pct:.1f}%")
    elif cash_allocation_pct > cash_max * 100:
        limit_warnings.append({
            'type': 'cash',
            'current_pct': cash_allocation_pct,
            'limit_pct': cash_max * 100,
            'message': f"현금 {cash_allocation_pct:.1f}% (최대 {cash_max*100:.0f}% 초과)"
        })
        print(f"    ⚠️  현금 과다: {cash_allocation_pct:.1f}%")
    else:
        print(f"    ✅ 현금: {cash_allocation_pct:.1f}% (목표 범위 {cash_min*100:.0f}~{cash_max*100:.0f}% 이내)")
    
    # 6. AI 거시경제 요약 생성
    print("\n[6/6] AI 거시경제 요약 생성 중...")
    macro_keywords = ['FOMC', 'CPI', '금리', '인플레이션', 'S&P500', '반도체']
    macro_summary = None
    
    if anthropic_api_key:
        macro_summary = generate_macro_summary(anthropic_api_key, macro_keywords)
        if macro_summary:
            print("    ✅ AI 요약 생성 완료")
        else:
            print("    ⚠️  AI 요약 생성 실패")
    else:
        print("    ⚠️  Anthropic API 키 없음 - AI 요약 생략")
    
    # 7. 이메일 리포트 발송
    print("\n[7/6] 이메일 리포트 발송 중...")
    
    report_data = {
        'timestamp': datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S KST'),
        'fx_rate': fx_rate,
        'fx_zone_info': fx_zone_info,
        'stock_data': stock_data,
        'isa_trigger': isa_trigger_data,
        'qcom_condition': qcom_condition_data,
        'portfolio_summary': {
            'total_assets': total_assets,
            'total_value': total_value,
            'cash': cash_krw,
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
    
    if email_sent:
        print("    ✅ 이메일 발송 완료")
    else:
        print("    ❌ 이메일 발송 실패")
    
    print("\n=== 리포트 생성 완료 ===")
    
    # API 사용량 요약
    try:
        from modules.market_data import AV_API_CALLS, AV_DAILY_LIMIT
        if AV_API_CALLS > 0:
            usage_pct = (AV_API_CALLS / AV_DAILY_LIMIT) * 100
            print(f"\n📊 오늘 Alpha Vantage API 사용량: {AV_API_CALLS}/{AV_DAILY_LIMIT} ({usage_pct:.1f}%)")
            print(f"   남은 호출 수: {AV_DAILY_LIMIT - AV_API_CALLS}회")
    except ImportError:
        print("\n⚠️  API 카운터를 불러올 수 없습니다.")

if __name__ == "__main__":
    main()