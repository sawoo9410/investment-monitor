"""투자 모니터링 시스템 - 메인 스크립트"""
import os
import yaml
from datetime import datetime
import pytz

from modules.market_data import (
    get_fx_rate,
    get_stock_price,
    get_monthly_baseline_price,
    get_stock_fundamentals
)
from modules.fx_checker import check_fx_zone, detect_fx_zone_change
from modules.ai_summary import generate_macro_summary, check_portfolio_limits
from modules.notifier import send_email, send_telegram, format_email_report

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
    
    # API 키 체크
    if not all([exchangerate_api_key, alphavantage_api_key, gmail_address, gmail_app_password]):
        print("❌ 필수 환경변수가 설정되지 않았습니다.")
        return
    
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
    
    # 2. 주식/ETF 데이터 수집
    print("\n[2/5] 주식 데이터 수집 중...")
    stock_data = []
    isa_trigger_data = None
    qcom_condition_data = None
    
    for stock_config in config['watchlist']:
        ticker = stock_config['ticker']
        print(f"  - {ticker} 조회 중...")
        
        # 기본 가격 정보
        price_data = get_stock_price(ticker, alphavantage_api_key)
        if not price_data:
            print(f"    ❌ {ticker} 가격 조회 실패")
            continue
        
        stock_info = {
            'ticker': ticker,
            'type': stock_config['type'],
            'price_data': price_data
        }
        
        # ISA 트리거 체크 (360750.KS)
        if stock_config.get('monthly_trigger'):
            baseline_data = get_monthly_baseline_price(ticker, alphavantage_api_key)
            if baseline_data:
                stock_info['baseline_data'] = baseline_data
                
                # 트리거 조건 체크
                change_pct = baseline_data['change_pct']
                if change_pct <= -10:
                    isa_trigger_data = {
                        'ticker': ticker,
                        'change_pct': change_pct,
                        'trigger_level': '-10% 이상 하락',
                        'action': '예비 현금의 60% 추가 매수'
                    }
                    print(f"    🚨 ISA 트리거 발동! ({change_pct:.2f}%)")
                elif change_pct <= -5:
                    isa_trigger_data = {
                        'ticker': ticker,
                        'change_pct': change_pct,
                        'trigger_level': '-5% 이상 하락',
                        'action': '예비 현금의 30% 추가 매수'
                    }
                    print(f"    ⚠️  ISA 트리거 접근 중 ({change_pct:.2f}%)")
        
        # QCOM 매수 조건 체크
        if stock_config['type'] == 'conditional':
            fundamentals = get_stock_fundamentals(ticker, alphavantage_api_key)
            if fundamentals:
                stock_info['fundamentals'] = fundamentals
                
                per = fundamentals.get('per')
                drop_pct = fundamentals.get('drop_from_high_pct', 0)
                
                buy_condition = stock_config.get('buy_condition', {})
                per_max = buy_condition.get('per_max', 25)
                drop_min = buy_condition.get('drop_pct_min', 15)
                
                if per and per <= per_max and drop_pct <= -drop_min:
                    qcom_condition_data = {
                        'ticker': ticker,
                        'per': per,
                        'drop_pct': drop_pct,
                        'action': f'매수 조건 충족 (PER {per:.1f} ≤ {per_max}, 하락 {drop_pct:.1f}% ≥ {drop_min}%)'
                    }
                    print(f"    ✅ QCOM 매수 조건 충족!")
        
        stock_data.append(stock_info)
        print(f"    ✅ {ticker}: ${price_data['current_price']} ({price_data['change_pct']:+.2f}%)")
    
    # 3. 포트폴리오 한도 체크
    print("\n[3/5] 포트폴리오 한도 체크 중...")
    # 간단한 더미 포트폴리오 (실제로는 계좌 데이터 연동 필요)
    dummy_portfolio = {
        'total_value': 3000000,  # 3천만원
        'ai_tech_value': 800000,  # AI/테크 800만원
        'oxy_value': 250000,     # OXY 250만원
        'cash_krw': 500000,      # 원화 현금 50만원
        'cash_usd': 200000       # 달러 현금 20만원
    }
    
    limit_warnings = check_portfolio_limits(dummy_portfolio, config)
    if limit_warnings:
        print("    ⚠️  포트폴리오 한도 경고:")
        for warning in limit_warnings:
            print(f"      - {warning}")
    else:
        print("    ✅ 모든 한도 정상")
    
    # 4. AI 거시경제 요약 생성
    print("\n[4/5] AI 거시경제 요약 생성 중...")
    macro_keywords = ['FOMC', 'CPI', '금리', '인플레이션', 'S&P500', '반도체']
    macro_summary = None
    
    if anthropic_api_key:
        macro_summary = generate_macro_summary(anthropic_api_key, macro_keywords)
        if macro_summary:
            print("    ✅ AI 요약 생성 완료")
        else:
            print("    ⚠️  AI 요약 생성 실패 (크레딧 부족 가능)")
    else:
        print("    ⚠️  Anthropic API 키 없음 - AI 요약 생략")
    
    # 5. 이메일 리포트 발송
    print("\n[5/5] 이메일 리포트 발송 중...")
    
    # 리포트 데이터 구성
    report_data = {
        'timestamp': datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S KST'),
        'fx_rate': fx_rate,
        'fx_zone_info': fx_zone_info,
        'stock_data': stock_data,
        'isa_trigger': isa_trigger_data,
        'qcom_condition': qcom_condition_data,
        'portfolio_warnings': limit_warnings,
        'macro_summary': macro_summary
    }
    
    # HTML 이메일 생성
    email_html = format_email_report(report_data)
    
    # 이메일 발송
    email_sent = send_email(
        gmail_address,
        gmail_app_password,
        gmail_address,  # 자기 자신에게 발송
        "📊 투자 모니터링 데일리 리포트",
        email_html
    )
    
    if email_sent:
        print("    ✅ 이메일 발송 완료")
    else:
        print("    ❌ 이메일 발송 실패")
    
    # 텔레그램 알림 (중요 이벤트만)
    if telegram_bot_token and telegram_chat_id:
        alerts = []
        
        if isa_trigger_data:
            alerts.append(f"🚨 ISA 트리거: {isa_trigger_data['ticker']} {isa_trigger_data['change_pct']:.2f}% - {isa_trigger_data['action']}")
        
        if qcom_condition_data:
            alerts.append(f"✅ QCOM 매수 조건 충족: PER {qcom_condition_data['per']:.1f}, 하락 {qcom_condition_data['drop_pct']:.1f}%")
        
        for alert in alerts:
            send_telegram(telegram_bot_token, telegram_chat_id, alert)
            print(f"    📱 텔레그램 알림: {alert}")
    
    print("\n=== 리포트 생성 완료 ===")

if __name__ == "__main__":
    main()