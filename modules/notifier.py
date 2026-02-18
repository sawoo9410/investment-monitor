"""이메일 알림 모듈"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict

def send_email(from_addr: str, password: str, to_addr: str, subject: str, html_content: str) -> bool:
    """Gmail SMTP를 통한 HTML 이메일 발송"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = to_addr
        
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(from_addr, password)
            server.sendmail(from_addr, to_addr, msg.as_string())
            print(f"이메일 발송 성공: {to_addr}")
            return True
    except Exception as e:
        print(f"이메일 발송 실패: {e}")
        return False

def format_email_report(report_data: Dict) -> str:
    """이메일 리포트 HTML 생성"""
    timestamp = report_data['timestamp']
    fx_rate = report_data.get('fx_rate')
    fx_zone_info = report_data.get('fx_zone_info')
    stock_data = report_data.get('stock_data', [])
    isa_trigger = report_data.get('isa_trigger')
    qcom_condition = report_data.get('qcom_condition')
    portfolio_summary = report_data.get('portfolio_summary', {})
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
            th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; font-size: 13px; }}
            th {{ background-color: #f2f2f2; font-weight: bold; }}
            .positive {{ color: #28a745; }}
            .negative {{ color: #dc3545; }}
            .portfolio-item {{ margin: 8px 0; padding: 8px; background-color: #f9f9f9; border-radius: 3px; }}
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
    
    # 포트폴리오 비중 요약
    if portfolio_summary:
        total_assets = portfolio_summary.get('total_assets', 0)
        total_value = portfolio_summary.get('total_value', 0)
        cash = portfolio_summary.get('cash', 0)
        allocations = portfolio_summary.get('allocations', {})
        sector_allocations = portfolio_summary.get('sector_allocations', {})
        cash_allocation_pct = portfolio_summary.get('cash_allocation_pct', 0)
        
        html += f"""
        <div class="section">
            <h2>📊 포트폴리오 비중</h2>
            <p><strong>총 자산:</strong> ₩{total_assets:,.0f}</p>
            <p style="font-size: 14px; color: #666;">
                ├─ 평가액: ₩{total_value:,.0f}<br>
                └─ 현금: ₩{cash:,.0f} ({cash_allocation_pct:.1f}%)
            </p>
            
            <h3 style="margin-top: 20px;">종목별 비중</h3>
"""
        
        # tracking 종목만 표시
        for stock_info in stock_data:
            ticker = stock_info['ticker']
            if ticker in allocations:
                alloc = allocations[ticker]
                html += f"""
            <div class="portfolio-item">
                <strong>{ticker}</strong> ({alloc['name']})<br>
                비중: {alloc['allocation_pct']:.1f}% | 
                평가액: ₩{alloc['value']:,.0f} | 
                보유: {alloc['holdings']}주
            </div>
"""
        
        # 섹터별 비중
        if sector_allocations:
            html += "<h3 style='margin-top: 20px;'>섹터별 분석</h3>"
            
            ai_tech_pct = sector_allocations.get('ai_tech', 0)
            if ai_tech_pct > 0:
                html += f"""
            <div class="portfolio-item">
                <strong>AI·테크 섹터:</strong> {ai_tech_pct:.1f}%
            </div>
"""
        
        # 포트폴리오 경고
        if portfolio_warnings:
            html += "<h3 style='margin-top: 20px; color: #dc3545;'>⚠️ 포트폴리오 경고</h3>"
            for warning in portfolio_warnings:
                html += f"<div class='alert'>{warning['message']}</div>"
        
        html += "</div>"
    
    # 주식 데이터
    html += """
        <div class="section">
            <h2>📈 종목 현황 (tracking)</h2>
            <table>
                <tr>
                    <th>종목</th>
                    <th>현재가</th>
                    <th>전일비</th>
                    <th>전월 1일 대비</th>
                    <th>PER</th>
                    <th>ROE</th>
                    <th>D/E</th>
                    <th>Margin</th>
                    <th>등락</th>
                </tr>
"""
    
    for stock_info in stock_data:
        price_data = stock_info.get('price_data')
        baseline_data = stock_info.get('baseline_data')
        fundamentals = stock_info.get('fundamentals')
        
        if price_data:
            ticker = price_data['ticker']
            current = price_data['current_price']
            change_pct = price_data['change_pct']
            color_class = 'positive' if change_pct >= 0 else 'negative'
            
            # 한국 종목 vs 미국 종목 단위 구분
            if ticker.endswith('.KS') or ticker.endswith('.KRX'):
                price_display = f"₩{current:,.0f}"
            else:
                price_display = f"${current:.2f}"
            
            # 전월 1일 대비
            if baseline_data:
                monthly_change = baseline_data['change_pct']
                monthly_color = 'positive' if monthly_change >= 0 else 'negative'
                monthly_display = f"<span class='{monthly_color}'>{monthly_change:+.2f}%</span>"
                
                if monthly_change <= -10:
                    monthly_display += "<br><strong style='color:#dc3545;'>🚨 -10% 트리거</strong>"
                elif monthly_change <= -5:
                    monthly_display += "<br><strong style='color:#ffc107;'>⚠️ -5% 트리거</strong>"
            else:
                monthly_display = "-"
            
            # 펀더멘탈 표시
            if fundamentals:
                per = fundamentals.get('per')
                roe = fundamentals.get('roe')
                debt_equity = fundamentals.get('debt_equity')
                profit_margin = fundamentals.get('profit_margin')
                
                # PER
                per_display = f"{per:.1f}" if per else "-"
                
                # ROE (15% 기준)
                if roe and roe != 'None':
                    roe_val = float(roe) * 100
                    roe_color = 'positive' if roe_val >= 15 else 'negative'
                    roe_display = f"<span class='{roe_color}'>{roe_val:.1f}%</span>"
                else:
                    roe_display = "-"
                
                # Debt/Equity (1.0 기준)
                if debt_equity and debt_equity != 'None':
                    de_val = float(debt_equity)
                    de_color = 'positive' if de_val <= 1.0 else 'negative'
                    de_display = f"<span class='{de_color}'>{de_val:.2f}</span>"
                else:
                    de_display = "-"
                
                # Profit Margin (퍼센트 표시)
                if profit_margin and profit_margin != 'None':
                    pm_val = float(profit_margin) * 100
                    margin_display = f"{pm_val:.1f}%"
                else:
                    margin_display = "-"
            else:
                per_display = "-"
                roe_display = "-"
                de_display = "-"
                margin_display = "-"
            
            html += f"""
                <tr>
                    <td><strong>{ticker}</strong></td>
                    <td>{price_display}</td>
                    <td class="{color_class}">{change_pct:+.2f}%</td>
                    <td>{monthly_display}</td>
                    <td>{per_display}</td>
                    <td>{roe_display}</td>
                    <td>{de_display}</td>
                    <td>{margin_display}</td>
                    <td class="{color_class}">{'▲' if change_pct >= 0 else '▼'}</td>
                </tr>
"""
    
    html += "</table></div>"
    
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