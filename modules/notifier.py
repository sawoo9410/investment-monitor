"""이메일 및 텔레그램 알림 모듈"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from typing import Dict, Optional

def send_email(gmail_address: str, gmail_password: str, recipient: str, subject: str, body_html: str) -> bool:
    """Gmail SMTP로 이메일 발송"""
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = gmail_address
        msg['To'] = recipient
        msg['Subject'] = subject
        
        html_part = MIMEText(body_html, 'html')
        msg.attach(html_part)
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_address, gmail_password)
            server.send_message(msg)
        
        print(f"이메일 발송 성공: {recipient}")
        return True
        
    except Exception as e:
        print(f"이메일 발송 실패: {e}")
        return False

def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    """텔레그램 메시지 발송"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            print("텔레그램 발송 성공")
            return True
        else:
            print(f"텔레그램 발송 실패: {response.text}")
            return False
            
    except Exception as e:
        print(f"텔레그램 발송 실패: {e}")
        return False

def format_email_report(data: Dict) -> str:
    """이메일 리포트 HTML 생성"""
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .header {{ background-color: #2c3e50; color: white; padding: 20px; }}
            .section {{ margin: 20px 0; padding: 15px; border-left: 4px solid #3498db; }}
            .metric {{ margin: 10px 0; }}
            .alert {{ background-color: #fff3cd; padding: 10px; margin: 10px 0; }}
            .success {{ background-color: #d4edda; padding: 10px; margin: 10px 0; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #3498db; color: white; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 투자 모니터링 리포트</h1>
            <p>{data['date']}</p>
        </div>
        
        <div class="section">
            <h2>📈 오늘의 대시보드</h2>
            <table>
                <tr>
                    <th>항목</th>
                    <th>현재값</th>
                    <th>변동</th>
                </tr>
                <tr>
                    <td>USD/KRW 환율</td>
                    <td>{data['fx']['current_rate']:.2f}원</td>
                    <td>{data['fx']['zone_name']}</td>
                </tr>
                {data['stocks_table']}
            </table>
        </div>
        
        <div class="section">
            <h2>⚡ 액션 트리거</h2>
            {data['triggers']}
        </div>
        
        <div class="section">
            <h2>🌍 거시경제 이슈</h2>
            <p>{data['macro_summary']}</p>
        </div>
        
        {data['portfolio_check']}
        
    </body>
    </html>
    """
    return html

def format_telegram_alert(alert_type: str, data: Dict) -> str:
    """텔레그램 알림 메시지 포맷"""
    if alert_type == 'fx_zone_change':
        return f"""🚨 <b>환율 구간 변경</b>

USD/KRW {data['current_rate']:.2f}원
[{data['prev_zone']}] → [{data['current_zone']}]

<b>액션:</b> {data['action']}"""
    
    elif alert_type == 'isa_trigger':
        return f"""📉 <b>ISA 매수 트리거 발동</b>

TIGER S&P500 전월比 {data['change_pct']:.1f}%
→ 예비현금의 {data['buy_pct']}% 추가매수 검토

현재 예비현금: 약 {data['reserve_amount']}만원"""
    
    elif alert_type == 'qcom_condition':
        return f"""🎯 <b>QCOM 매수 조건 진입</b>

PER {data['per']:.1f}배 (기준: 25배↓) ✅
고점比 {data['drop_pct']:.1f}% (기준: -15%↓) ✅

→ 매수 검토 구간 진입"""
    
    elif alert_type == 'stock_drop':
        return f"""⚠️ <b>{data['ticker']} 급락 감지</b>

전일比 {data['change_pct']:.1f}%
현재가: ${data['current_price']:.2f}

검토가 필요할 수 있습니다."""
    
    return "알림"