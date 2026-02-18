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

def format_email_report(report_data: Dict) -> str:
    """이메일 리포트 HTML 생성"""
    timestamp = report_data['timestamp']
    fx_rate = report_data.get('fx_rate')
    fx_zone_info = report_data.get('fx_zone_info')
    stock_data = report_data.get('stock_data', [])
    isa_trigger = report_data.get('isa_trigger')
    qcom_condition = report_data.get('qcom_condition')
    portfolio_warnings = report_data.get('portfolio_warnings', [])
    macro_summary = report_data.get('macro_summary', '')
    
    # HTML 템플릿
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
            .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
            .alert {{ background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin: 10px 0; }}
            .success {{ background-color: #d4edda; border-left: 4px solid #28a745; padding: 10px; margin: 10px 0; }}
            .warning {{ background-color: #f8d7da; border-left: 4px solid #dc3545; padding: 10px; margin: 10px 0; }}
            table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
            th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #f2f2f2; font-weight: bold; }}
            .positive {{ color: #28a745; }}
            .negative {{ color: #dc3545; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 투자 모니터링 데일리 리포트</h1>
            <p>{timestamp}</p>
        </div>
        
        <!-- 환율 정보 -->
        <div class="section">
            <h2>💵 USD/KRW 환율</h2>
"""
    
    if fx_rate and fx_zone_info:
        html += f"""
            <p><strong>현재 환율:</strong> {fx_rate:.2f}원</p>
            <p><strong>구간:</strong> {fx_zone_info['zone_name']}</p>
            <div class="alert">
                <strong>액션:</strong> {fx_zone_info['action']}
            </div>
"""
    else:
        html += "<p>환율 조회 실패</p>"
    
    html += "</div>"
    
    # 중요 알림
    if isa_trigger or qcom_condition:
        html += '<div class="section"><h2>🚨 중요 알림</h2>'
        
        if isa_trigger:
            html += f"""
            <div class="warning">
                <strong>ISA 트리거 발동!</strong><br>
                {isa_trigger['ticker']}: 전월 대비 {isa_trigger['change_pct']:.2f}%<br>
                트리거 레벨: {isa_trigger['trigger_level']}<br>
                <strong>액션:</strong> {isa_trigger['action']}
            </div>
"""
        
        if qcom_condition:
            html += f"""
            <div class="success">
                <strong>QCOM 매수 조건 충족!</strong><br>
                PER: {qcom_condition['per']:.1f}<br>
                52주 고점 대비: {qcom_condition['drop_pct']:.1f}%<br>
                <strong>액션:</strong> {qcom_condition['action']}
            </div>
"""
        
        html += "</div>"
    
    # 주식 데이터
    html += """
        <div class="section">
            <h2>📈 종목 현황</h2>
            <table>
                <tr>
                    <th>종목</th>
                    <th>현재가</th>
                    <th>전일비</th>
                    <th>등락률</th>
                </tr>
"""
    
    for stock_info in stock_data:
        price_data = stock_info.get('price_data')
        if price_data:
            ticker = price_data['ticker']
            current = price_data['current_price']
            change_pct = price_data['change_pct']
            color_class = 'positive' if change_pct >= 0 else 'negative'
            
            html += f"""
                <tr>
                    <td><strong>{ticker}</strong></td>
                    <td>${current:.2f}</td>
                    <td class="{color_class}">{change_pct:+.2f}%</td>
                    <td class="{color_class}">{'▲' if change_pct >= 0 else '▼'}</td>
                </tr>
"""
    
    html += "</table></div>"
    
    # 포트폴리오 경고
    if portfolio_warnings:
        html += '<div class="section"><h2>⚠️ 포트폴리오 한도 경고</h2><ul>'
        for warning in portfolio_warnings:
            html += f"<li>{warning}</li>"
        html += "</ul></div>"
    
    # AI 거시경제 요약
    if macro_summary:
        html += f"""
        <div class="section">
            <h2>🤖 AI 거시경제 요약</h2>
            <div style="white-space: pre-wrap; line-height: 1.8;">{macro_summary}</div>
        </div>
"""
    
    html += """
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