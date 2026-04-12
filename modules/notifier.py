"""이메일 알림 모듈"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict

# 지수 ETF 타입 목록 (이 type은 다기간 수익률 테이블로 표시)
INDEX_TYPES = ('core', 'isa_core', 'isa_core_hedged')

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

def _change_cell(change_pct, suffix='%', decimal=2):
    """등락률 셀 HTML (색상 + 화살표)"""
    color = 'positive' if change_pct >= 0 else 'negative'
    arrow = '▲' if change_pct >= 0 else '▼'
    return f"<span class='{color}'>{arrow} {change_pct:+.{decimal}f}{suffix}</span>"

def _trigger_badge(change_pct):
    """ISA 트리거 배지 HTML"""
    if change_pct <= -10:
        return "<br><strong style='color:#dc3545;'>🚨 -10% 트리거</strong>"
    elif change_pct <= -5:
        return "<br><strong style='color:#ffc107;'>⚠️ -5% 트리거</strong>"
    return ""

def _render_index_etf_table(stock_data, isa_active_ticker='360750.KS', spym_fx_rate=1420):
    """지수 ETF 테이블: 전일비 + 다기간 수익률 (전월 / 3M / 6M / 1Y)"""
    html = """
        <div class="section">
            <h2>📈 지수 ETF 현황</h2>
            <table>
                <tr>
                    <th>종목</th>
                    <th>현재가</th>
                    <th>전일비</th>
                    <th>전월 말일</th>
                    <th>3개월 전</th>
                    <th>6개월 전</th>
                    <th>1년 전</th>
                </tr>
"""

    index_stocks = [s for s in stock_data if s.get('type') in INDEX_TYPES]

    for stock_info in index_stocks:
        price_data = stock_info.get('price_data')
        if not price_data:
            continue

        ticker = price_data['ticker']
        current = price_data['current_price']
        change_pct = price_data['change_pct']

        # 가격 표시 (원화 / 달러)
        if ticker.endswith('.KS') or ticker.endswith('.KRX'):
            price_display = f"₩{current:,.0f}"
        else:
            price_display = f"${current:.2f}"

        # 다기간 수익률
        multi = stock_info.get('multi_period_data')
        period_cells = {}
        for key in ('monthly', '3month', '6month', '1year'):
            if multi and multi.get('periods', {}).get(key):
                p = multi['periods'][key]
                cell = _change_cell(p['change_pct'])
                cell += _trigger_badge(p['change_pct'])
            else:
                cell = "-"
            period_cells[key] = cell

        # 활성 ISA 종목 표시 (★ 배지)
        is_active_isa = ticker == isa_active_ticker
        name_display = stock_info.get('name', '')
        if ticker in ('360750.KS', '449180.KS'):
            active_badge = " <span style='color:#28a745;font-size:11px;'>★ 매수중</span>" if is_active_isa else " <span style='color:#aaa;font-size:11px;'>대기</span>"
            name_display += active_badge

        html += f"""
                <tr>
                    <td><strong>{ticker}</strong><br><span style='color:#666;font-size:12px;'>{name_display}</span></td>
                    <td>{price_display}</td>
                    <td>{_change_cell(change_pct)}</td>
                    <td>{period_cells['monthly']}</td>
                    <td>{period_cells['3month']}</td>
                    <td>{period_cells['6month']}</td>
                    <td>{period_cells['1year']}</td>
                </tr>
"""

    html += "</table>"

    # ── 449180 매수 트리거 기준가 표시 (449180 전용) ─────────────────
    trigger_449180 = next(
        (s for s in index_stocks if s.get('price_data', {}).get('ticker') == '449180.KS'),
        None
    )
    if trigger_449180:
        multi = trigger_449180.get('multi_period_data')
        monthly = multi.get('periods', {}).get('monthly') if multi else None
        if monthly:
            baseline_price = monthly['price']
            baseline_date  = monthly['date']
            price_5pct  = baseline_price * 0.95
            price_10pct = baseline_price * 0.90
            current_price = trigger_449180['price_data']['current_price']

            color_5  = '#dc3545' if current_price <= price_5pct  else '#333'
            color_10 = '#dc3545' if current_price <= price_10pct else '#333'

            fmt = lambda p: f"₩{p:,.0f}"

            html += f"""
        <div style="margin-top:10px; padding:10px; background-color:#f8f9fa; border-radius:5px; font-size:13px;">
            <strong>🎯 449180.KS 매수 트리거 기준 (전월 대비)</strong>
            <span style="color:#888; margin-left:8px;">(전월 말일 기준가: {fmt(baseline_price)} | {baseline_date})</span>
            <table style="margin-top:8px; width:auto;">
                <tr>
                    <th style="padding:6px 16px 6px 6px;">구간</th>
                    <th style="padding:6px 16px 6px 6px;">트리거 가격</th>
                    <th style="padding:6px 16px 6px 6px;">액션</th>
                    <th style="padding:6px 6px 6px 6px;">상태</th>
                </tr>
                <tr>
                    <td style="padding:6px 16px 6px 6px; color:{color_5};"><strong>-5%</strong></td>
                    <td style="padding:6px 16px 6px 6px; color:{color_5};">{fmt(price_5pct)}</td>
                    <td style="padding:6px 16px 6px 6px;">현금 버퍼에서 100만원 추가 매수</td>
                    <td style="padding:6px 6px 6px 6px;">{'🚨 트리거 발동' if current_price <= price_5pct else '✅ 미도달'}</td>
                </tr>
                <tr>
                    <td style="padding:6px 16px 6px 6px; color:{color_10};"><strong>-10%</strong></td>
                    <td style="padding:6px 16px 6px 6px; color:{color_10};">{fmt(price_10pct)}</td>
                    <td style="padding:6px 16px 6px 6px;">현금 버퍼에서 100만원 추가 매수</td>
                    <td style="padding:6px 6px 6px 6px;">{'🚨 트리거 발동' if current_price <= price_10pct else '✅ 미도달'}</td>
                </tr>
            </table>
        </div>
"""

    # ── 449180 2달 전 대비 트리거 기준가 표시 (slowly melting 방지) ────
    hedged_449180 = next(
        (s for s in index_stocks if s.get('price_data', {}).get('ticker') == '449180.KS'),
        None
    )
    if hedged_449180:
        multi = hedged_449180.get('multi_period_data')
        two_month = multi.get('periods', {}).get('2month') if multi else None
        if two_month:
            baseline_2m_price = two_month['price']
            baseline_2m_date  = two_month['date']
            price_2m_5pct  = baseline_2m_price * 0.95
            price_2m_10pct = baseline_2m_price * 0.90
            current_price_449 = hedged_449180['price_data']['current_price']

            color_2m_5  = '#6f42c1' if current_price_449 <= price_2m_5pct  else '#333'
            color_2m_10 = '#6f42c1' if current_price_449 <= price_2m_10pct else '#333'

            html += f"""
        <div style="margin-top:10px; padding:10px; background-color:#f3f0ff; border-radius:5px; font-size:13px;">
            <strong>🎯 449180.KS 매수 트리거 기준 (2달 전 대비, slowly melting 방지)</strong>
            <span style="color:#888; margin-left:8px;">(2달 전 말일 기준가: ₩{baseline_2m_price:,.0f} | {baseline_2m_date})</span>
            <table style="margin-top:8px; width:auto;">
                <tr>
                    <th style="padding:6px 16px 6px 6px;">구간</th>
                    <th style="padding:6px 16px 6px 6px;">트리거 가격</th>
                    <th style="padding:6px 16px 6px 6px;">액션</th>
                    <th style="padding:6px 6px 6px 6px;">상태</th>
                </tr>
                <tr>
                    <td style="padding:6px 16px 6px 6px; color:{color_2m_5};"><strong>-5%</strong></td>
                    <td style="padding:6px 16px 6px 6px; color:{color_2m_5};">₩{price_2m_5pct:,.0f}</td>
                    <td style="padding:6px 16px 6px 6px;">현금 버퍼에서 50만원 추가 매수</td>
                    <td style="padding:6px 6px 6px 6px;">{'🚨 트리거 발동' if current_price_449 <= price_2m_5pct else '✅ 미도달'}</td>
                </tr>
                <tr>
                    <td style="padding:6px 16px 6px 6px; color:{color_2m_10};"><strong>-10%</strong></td>
                    <td style="padding:6px 16px 6px 6px; color:{color_2m_10};">₩{price_2m_10pct:,.0f}</td>
                    <td style="padding:6px 16px 6px 6px;">현금 버퍼에서 50만원 추가 매수</td>
                    <td style="padding:6px 6px 6px 6px;">{'🚨 트리거 발동' if current_price_449 <= price_2m_10pct else '✅ 미도달'}</td>
                </tr>
            </table>
        </div>
"""

    # ── SPYM 매수 트리거 기준가 표시 (원화 환산) ────────────────────
    trigger_spym = next(
        (s for s in index_stocks if s.get('price_data', {}).get('ticker') == 'SPYM'),
        None
    )
    if trigger_spym:
        multi = trigger_spym.get('multi_period_data')
        monthly = multi.get('periods', {}).get('monthly') if multi else None
        if monthly:
            baseline_usd = monthly['price']
            baseline_date = monthly['date']
            baseline_krw = baseline_usd * spym_fx_rate
            price_5pct_krw = baseline_krw * 0.95
            price_10pct_krw = baseline_krw * 0.90
            current_usd = trigger_spym['price_data']['current_price']
            current_krw = current_usd * spym_fx_rate

            color_5 = '#dc3545' if current_krw <= price_5pct_krw else '#333'
            color_10 = '#dc3545' if current_krw <= price_10pct_krw else '#333'

            fmt = lambda p: f"₩{p:,.0f}"

            html += f"""
        <div style="margin-top:10px; padding:10px; background-color:#e8f4f8; border-radius:5px; font-size:13px;">
            <strong>🎯 SPYM 매수 트리거 기준 (전월 대비, 원화 환산)</strong>
            <span style="color:#888; margin-left:8px;">(전월 말일: ${baseline_usd:.2f} × ₩{spym_fx_rate:,} = {fmt(baseline_krw)} | {baseline_date})</span>
            <table style="margin-top:8px; width:auto;">
                <tr>
                    <th style="padding:6px 16px 6px 6px;">구간</th>
                    <th style="padding:6px 16px 6px 6px;">트리거 가격 (원화)</th>
                    <th style="padding:6px 16px 6px 6px;">트리거 가격 (달러)</th>
                    <th style="padding:6px 6px 6px 6px;">상태</th>
                </tr>
                <tr>
                    <td style="padding:6px 16px 6px 6px; color:{color_5};"><strong>-5%</strong></td>
                    <td style="padding:6px 16px 6px 6px; color:{color_5};">{fmt(price_5pct_krw)}</td>
                    <td style="padding:6px 16px 6px 6px; color:{color_5};">${baseline_usd * 0.95:.2f}</td>
                    <td style="padding:6px 6px 6px 6px;">{'🚨 트리거 발동' if current_krw <= price_5pct_krw else '✅ 미도달'}</td>
                </tr>
                <tr>
                    <td style="padding:6px 16px 6px 6px; color:{color_10};"><strong>-10%</strong></td>
                    <td style="padding:6px 16px 6px 6px; color:{color_10};">{fmt(price_10pct_krw)}</td>
                    <td style="padding:6px 16px 6px 6px; color:{color_10};">${baseline_usd * 0.90:.2f}</td>
                    <td style="padding:6px 6px 6px 6px;">{'🚨 트리거 발동' if current_krw <= price_10pct_krw else '✅ 미도달'}</td>
                </tr>
            </table>
            <p style="color:#888; font-size:11px; margin-top:6px;">현재가: ${current_usd:.2f} (₩{spym_fx_rate:,} 기준 {fmt(current_krw)})</p>
        </div>
"""

    html += "</div>"
    return html

def _render_individual_stock_table(stock_data):
    """개별주 테이블: 전일비 + 전월 말일 + 펀더멘탈"""
    html = """
        <div class="section">
            <h2>📊 개별주 현황</h2>
            <table>
                <tr>
                    <th>종목</th>
                    <th>현재가</th>
                    <th>전일비</th>
                    <th>전월 말일</th>
                    <th>PER</th>
                    <th>ROE</th>
                    <th>D/E</th>
                    <th>Margin</th>
                </tr>
"""

    individual_stocks = [s for s in stock_data if s.get('type') not in INDEX_TYPES]

    for stock_info in individual_stocks:
        price_data = stock_info.get('price_data')
        if not price_data:
            continue

        ticker = price_data['ticker']
        current = price_data['current_price']
        change_pct = price_data['change_pct']
        price_display = f"${current:.2f}"

        # 전월 말일 대비
        baseline_data = stock_info.get('baseline_data')
        if baseline_data:
            monthly_change = baseline_data['change_pct']
            monthly_display = _change_cell(monthly_change)
        else:
            monthly_display = "-"

        # 펀더멘탈
        fundamentals = stock_info.get('fundamentals')
        if fundamentals:
            per = fundamentals.get('per')
            roe = fundamentals.get('roe')
            debt_equity = fundamentals.get('debt_equity')
            profit_margin = fundamentals.get('profit_margin')

            per_display = f"{per:.1f}" if per else "-"

            if roe and roe != 'None':
                roe_val = float(roe) * 100
                roe_color = 'positive' if roe_val >= 15 else 'negative'
                roe_display = f"<span class='{roe_color}'>{roe_val:.1f}%</span>"
            else:
                roe_display = "-"

            if debt_equity and debt_equity != 'None':
                de_val = float(debt_equity)
                de_color = 'positive' if de_val <= 1.0 else 'negative'
                de_display = f"<span class='{de_color}'>{de_val:.2f}</span>"
            else:
                de_display = "-"

            if profit_margin and profit_margin != 'None':
                pm_val = float(profit_margin) * 100
                margin_display = f"{pm_val:.1f}%"
            else:
                margin_display = "-"
        else:
            per_display = roe_display = de_display = margin_display = "-"

        html += f"""
                <tr>
                    <td><strong>{ticker}</strong><br><span style='color:#666;font-size:12px;'>{stock_info.get('name', '')}</span></td>
                    <td>{price_display}</td>
                    <td>{_change_cell(change_pct)}</td>
                    <td>{monthly_display}</td>
                    <td>{per_display}</td>
                    <td>{roe_display}</td>
                    <td>{de_display}</td>
                    <td>{margin_display}</td>
                </tr>
"""

    html += "</table></div>"
    return html

def format_email_report(report_data: Dict) -> str:
    """이메일 리포트 HTML 생성"""
    timestamp        = report_data['timestamp']
    isa_active_ticker = report_data.get('isa_active_ticker', '360750.KS')
    stock_data       = report_data.get('stock_data', [])
    isa_trigger      = report_data.get("isa_trigger")
    isa_2month_trigger = report_data.get("isa_2month_trigger")
    isa_sell_trigger = report_data.get("isa_sell_trigger")
    spym_fx_rate     = report_data.get('spym_fx_rate', 1420)
    macro_summary    = report_data.get('macro_summary', '')

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
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 투자 모니터링 데일리 리포트</h1>
            <p>{timestamp}</p>
        </div>

"""

    # 중요 알림
    if isa_trigger or isa_2month_trigger or isa_sell_trigger:
        html += '<div class="section"><h2>🚨 중요 알림</h2>'

        if isa_trigger:
            html += f"""
            <div class="warning">
                <strong>📉 ISA 매수 트리거 발동! (전월 대비)</strong><br>
                {isa_trigger['ticker']}: 전월 대비 {isa_trigger['change_pct']:.2f}%<br>
                트리거 레벨: {isa_trigger['trigger_level']}<br>
                <strong>액션:</strong> {isa_trigger['action']}
            </div>
"""

        if isa_2month_trigger:
            html += f"""
            <div class="warning" style="border-left-color:#6f42c1; background-color:#f3f0ff;">
                <strong>📉 ISA 매수 트리거 발동! (2달 전 대비, slowly melting 방지)</strong><br>
                {isa_2month_trigger['ticker']}: 2달 전 대비 {isa_2month_trigger['change_pct']:.2f}%<br>
                기준일: {isa_2month_trigger['baseline_date']} (₩{isa_2month_trigger['baseline_price']:,.0f})<br>
                트리거 레벨: {isa_2month_trigger['trigger_level']}<br>
                <strong>액션:</strong> {isa_2month_trigger['action']}
            </div>
"""

        if isa_sell_trigger:
            html += f"""
            <div class="warning" style="border-left-color:#e67e22; background-color:#fef9f0;">
                <strong>📈 ISA 매도 트리거 발동!</strong><br>
                {isa_sell_trigger['ticker']}: 전월 대비 {isa_sell_trigger['change_pct']:.2f}%<br>
                트리거 레벨: {isa_sell_trigger['trigger_level']}<br>
                <strong>액션:</strong> {isa_sell_trigger['action']}
            </div>
"""

        html += "</div>"

    # 지수 ETF 테이블 (트리거 기준가 포함)
    html += _render_index_etf_table(stock_data, isa_active_ticker, spym_fx_rate)

    # 개별주 테이블
    html += _render_individual_stock_table(stock_data)

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