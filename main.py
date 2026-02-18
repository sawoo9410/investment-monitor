"""투자 모니터링 시스템 - 메인 스크립트"""
import os
import yaml
from datetime import datetime
import pytz
import time

from modules.market_data import (
    get_fx_rate,
    get_kr_etf_price,
    get_kr_etf_monthly_baseline
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
    
    if not all([exchangerate_api_key, gmail_address, gmail_app_password]):
        print("❌ 필수 환경변수가 설정되지 않았습니다.")
        return
    
    # 1. 환율 조회
    print("\n[1/4] 환율 조회 중...")
    fx_rate = get_fx_rate(exchangerate_api_key)
    if fx_rate:
        print(f"✅ USD/KRW: {fx_rate:.2f}원")
        fx_zone_info = check_fx_zone(fx_rate, config['fx_rules'])
        print(f"   현재 구간: {fx_zone_info['zone_name']} - {fx_zone_info['action']}")
    else:
        print("❌ 환율 조회 실패")
        fx_zone_info = None
    
    # 2. 주식/ETF 데이터 수집 (한국 ETF만)
    print("\n[2/4] 주식 데이터 수집 중...")
    stock_data = []
    isa_trigger_data = None
    qcom_condition_data = None
    
    for stock_config in config['watchlist']:
        ticker = stock_config['ticker']
        
        # 한국 ETF만 처리
        if ticker.endswith('.KS') or ticker.endswith('.KRX'):
            print(f"  - {ticker} 조회 중...")
            
            price_data = get_kr_etf_price(ticker)
            if not price_data:
                print(f"    ❌ {ticker} 가격 조회 실패")
                continue
            
            stock_info = {
                'ticker': ticker,
                'type': stock_config['type'],
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
            # 미국 주식 - 아직 주석 처리 (Alpha Vantage 절약)
            print(f"  - {ticker} (미국 주식 - 비활성화됨)")
            # ========== Alpha Vantage 호출 주석 시작 ==========
            # from modules.market_data import get_stock_price, get_stock_fundamentals
            # price_data = get_stock_price(ticker, alphavantage_api_key)
            # if not price_data:
            #     print(f"    ❌ {ticker} 가격 조회 실패")
            #     continue
            # 
            # stock_info = {
            #     'ticker': ticker,
            #     'type': stock_config['type'],
            #     'price_data': price_data
            # }
            # 
            # # QCOM 매수 조건 체크
            # if stock_config['type'] == 'conditional':
            #     fundamentals = get_stock_fundamentals(ticker, alphavantage_api_key)
            #     if fundamentals:
            #         stock_info['fundamentals'] = fundamentals
            #         # ... 조건 체크 로직
            # 
            # stock_data.append(stock_info)
            # print(f"    ✅ {ticker}: ${price_data['current_price']} ({price_data['change_pct']:+.2f}%)")
            # time.sleep(1)
            # ========== Alpha Vantage 호출 주석 끝 ==========
    
    # 3. 포트폴리오 한도 체크 (비활성화)
    print("\n[3/4] 포트폴리오 한도 체크 (비활성화됨)")
    limit_warnings = []
    
    # 4. AI 거시경제 요약 생성
    print("\n[4/4] AI 거시경제 요약 생성 중...")
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
    
    # 5. 이메일 리포트 발송
    print("\n[5/4] 이메일 리포트 발송 중...")
    
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

if __name__ == "__main__":
    main()