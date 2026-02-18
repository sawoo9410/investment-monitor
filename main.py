"""메인 실행 스크립트 - 매일 아침 이메일 리포트 생성"""
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
from modules.fx_checker import check_fx_zone
from modules.ai_summary import generate_macro_summary, check_portfolio_limits
from modules.notifier import send_email, format_email_report

def load_config():
    """config.yaml 로드"""
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def main():
    """메인 실행 함수"""
    print("=" * 50)
    print("투자 모니터링 리포트 생성 시작")
    print("=" * 50)
    
    # 설정 로드
    config = load_config()
    
    # 환경변수에서 API 키 가져오기
    exchangerate_key = os.environ.get('EXCHANGERATE_API_KEY')
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
    gmail_address = os.environ.get('GMAIL_ADDRESS')
    gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
    
    # 현재 시각
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    date_str = now.strftime('%Y년 %m월 %d일 %A')
    
    print(f"\n📅 {date_str}\n")
    
    # 1. 환율 데이터
    print("환율 조회 중...")
    fx_rate = get_fx_rate(exchangerate_key)
    fx_info = check_fx_zone(fx_rate, config) if fx_rate else None
    
    # 2. 주식 데이터
    print("주식 데이터 조회 중...")
    stocks_data = {}
    stocks_table = ""
    
    for item in config['watchlist']:
        ticker = item['ticker']
        print(f"  - {ticker}")
        data = get_stock_price(ticker)
        if data:
            stocks_data[ticker] = data
            stocks_table += f"""
                <tr>
                    <td>{item['name']}</td>
                    <td>${data['current_price']}</td>
                    <td style="color: {'red' if data['change_pct'] < 0 else 'green'}">
                        {data['change_pct']:+.2f}%
                    </td>
                </tr>
            """
    
    # 3. ISA 트리거 체크
    print("\nISA 트리거 체크 중...")
    isa_trigger = get_monthly_baseline_price("360750.KS")
    
    # 4. QCOM 매수 조건 체크
    print("QCOM 조건 체크 중...")
    qcom_data = get_stock_fundamentals("QCOM")
    
    # 5. 트리거 요약 생성
    triggers_html = ""
    
    if fx_info:
        triggers_html += f'<div class="metric">✅ 환율 구간: {fx_info["zone_name"]}</div>'
    
    if isa_trigger:
        change = isa_trigger['change_pct']
        if change <= -10:
            triggers_html += f'<div class="alert">📉 ISA 매수 트리거: 전월比 {change:.1f}% → 예비현금 60% 추가매수</div>'
        elif change <= -5:
            triggers_html += f'<div class="alert">📉 ISA 매수 트리거: 전월比 {change:.1f}% → 예비현금 30% 추가매수</div>'
        else:
            triggers_html += f'<div class="metric">✅ ISA 매수 트리거: 전월比 {change:.1f}% (해당없음)</div>'
    
    if qcom_data:
        per = qcom_data.get('per', 0)
        drop = qcom_data.get('drop_from_high_pct', 0)
        
        if per and per <= 25 and drop <= -15:
            triggers_html += f'<div class="alert">🎯 QCOM 매수 조건 충족: PER {per:.1f}배, 고점比 {drop:.1f}%</div>'
        else:
            triggers_html += f'<div class="metric">✅ QCOM 매수 조건: 미충족 (PER {per:.1f}배, 고점比 {drop:.1f}%)</div>'
    
    # 6. AI 거시경제 요약
    print("\nAI 거시경제 요약 생성 중...")
    macro_summary = generate_macro_summary(anthropic_key, config['macro_keywords'])
    
    # 7. 포트폴리오 비중 체크 (월요일만)
    portfolio_check_html = ""
    if now.weekday() == 0:  # 월요일
        print("포트폴리오 비중 체크 중...")
        # 실제 보유 비중은 수동으로 업데이트하거나 증권사 API 연동 필요
        # 여기서는 예시만
        portfolio_check_html = """
        <div class="section">
            <h2>💼 포트폴리오 비중 점검</h2>
            <p><em>수동 업데이트 필요 또는 증권사 API 연동 시 자동화</em></p>
        </div>
        """
    
    # 8. 이메일 데이터 구성
    email_data = {
        'date': date_str,
        'fx': fx_info or {'current_rate': 0, 'zone_name': '조회 실패'},
        'stocks_table': stocks_table,
        'triggers': triggers_html,
        'macro_summary': macro_summary or "요약 생성 실패",
        'portfolio_check': portfolio_check_html
    }
    
    # 9. 이메일 발송
    print("\n이메일 발송 중...")
    email_html = format_email_report(email_data)
    
    success = send_email(
        gmail_address=gmail_address,
        gmail_password=gmail_password,
        recipient=config['email_report']['recipient'],
        subject=f"📊 투자 모니터링 리포트 - {date_str}",
        body_html=email_html
    )
    
    if success:
        print("\n✅ 리포트 발송 완료!")
    else:
        print("\n❌ 리포트 발송 실패")
    
    print("=" * 50)

if __name__ == "__main__":
    main()