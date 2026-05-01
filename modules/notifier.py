"""이메일 알림 모듈"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Union

# 지수 ETF 타입 목록 (이 type은 다기간 수익률 테이블로 표시)
INDEX_TYPES = ('core', 'isa_core', 'isa_core_hedged')

def send_email(from_addr: str, password: str, to_addrs: Union[str, List[str]], subject: str, html_content: str) -> bool:
    """Gmail SMTP를 통한 HTML 이메일 발송 (복수 수신자 지원)"""
    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = ', '.join(to_addrs)

        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(from_addr, password)
            server.sendmail(from_addr, to_addrs, msg.as_string())
            print(f"이메일 발송 성공: {', '.join(to_addrs)}")
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

    # ── 모든 monthly_trigger ETF에 대해 통합 트리거 기준표 표시 ──────
    trigger_etfs = [s for s in index_stocks if s.get('monthly_trigger')]
    if trigger_etfs:
        html += _render_trigger_summary_table(trigger_etfs, spym_fx_rate)

    html += "</div>"
    return html


def _render_trigger_summary_table(trigger_etfs, spym_fx_rate=1420):
    """모든 지수 ETF의 매수 트리거 기준가를 한 표로 통합 표시 (전월/2달 전 -5%/-10%)"""
    rows = []
    for s in trigger_etfs:
        ticker = s['price_data']['ticker']
        multi = s.get('multi_period_data') or {}
        periods = multi.get('periods', {}) or {}
        monthly = periods.get('monthly')
        two_month = periods.get('2month')
        is_usd = not (ticker.endswith('.KS') or ticker.endswith('.KRX'))

        current_native = s['price_data']['current_price']
        # SPYM은 원화 환산 기준 비교 (KRW 트리거)
        current_for_compare = current_native * spym_fx_rate if is_usd else current_native

        def fmt_price(p, native=True):
            if p is None:
                return "-"
            if is_usd and native:
                return f"${p:.2f}"
            return f"₩{p:,.0f}"

        def cell(baseline, pct):
            if baseline is None:
                return "-", '#333', False
            trig = baseline * (1 + pct / 100.0)
            trig_compare = trig * spym_fx_rate if is_usd else trig
            triggered = current_for_compare <= trig_compare
            color = '#dc3545' if triggered else '#333'
            label = fmt_price(trig, native=True)
            if is_usd:
                label += f" / ₩{trig * spym_fx_rate:,.0f}"
            return label, color, triggered

        m_base = monthly['price'] if monthly else None
        m_date = monthly['date'] if monthly else '-'
        tm_base = two_month['price'] if two_month else None
        tm_date = two_month['date'] if two_month else '-'

        m_5,  c_m5,  t_m5  = cell(m_base,  -5)
        m_10, c_m10, t_m10 = cell(m_base,  -10)
        t_5,  c_t5,  t_t5  = cell(tm_base, -5)
        t_10, c_t10, t_t10 = cell(tm_base, -10)

        any_trig = any([t_m5, t_m10, t_t5, t_t10])
        status = '🚨' if any_trig else '✅'

        cur_label = f"${current_native:.2f}" if is_usd else f"₩{current_native:,.0f}"
        base_label = f"전월 {fmt_price(m_base)} ({m_date}) / 2달 전 {fmt_price(tm_base)} ({tm_date})"

        rows.append(f"""
                <tr>
                    <td style="padding:6px;"><strong>{ticker}</strong><br><span style='color:#888;font-size:11px;'>{base_label}</span></td>
                    <td style="padding:6px;">{cur_label}</td>
                    <td style="padding:6px; color:{c_m5};">{m_5}</td>
                    <td style="padding:6px; color:{c_m10};">{m_10}</td>
                    <td style="padding:6px; color:{c_t5};">{t_5}</td>
                    <td style="padding:6px; color:{c_t10};">{t_10}</td>
                    <td style="padding:6px;">{status}</td>
                </tr>""")

    return f"""
        <div style="margin-top:10px; padding:10px; background-color:#f8f9fa; border-radius:5px; font-size:12px;">
            <strong>🎯 지수 ETF 매수 트리거 기준</strong>
            <span style="color:#888; margin-left:8px;">SPYM은 원화 환산 비교 (₩{spym_fx_rate:,})</span>
            <table style="margin-top:8px; width:100%;">
                <tr>
                    <th style="padding:6px;">종목</th>
                    <th style="padding:6px;">현재가</th>
                    <th style="padding:6px;">전월 -5%</th>
                    <th style="padding:6px;">전월 -10%</th>
                    <th style="padding:6px;">2달 -5%</th>
                    <th style="padding:6px;">2달 -10%</th>
                    <th style="padding:6px;">상태</th>
                </tr>
                {''.join(rows)}
            </table>
        </div>
"""

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
    isa_triggers     = report_data.get("isa_triggers", [])
    isa_2month_triggers = report_data.get("isa_2month_triggers", [])
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
    if isa_triggers or isa_2month_triggers:
        html += '<div class="section"><h2>🚨 중요 알림</h2>'

        for t in isa_triggers:
            html += f"""
            <div class="warning">
                <strong>📉 매수 트리거 발동! (전월 대비)</strong><br>
                {t['ticker']}: 전월 대비 {t['change_pct']:.2f}%<br>
                트리거 레벨: {t['trigger_level']}<br>
                <strong>액션:</strong> {t['action']}
            </div>
"""

        for t in isa_2month_triggers:
            html += f"""
            <div class="warning" style="border-left-color:#6f42c1; background-color:#f3f0ff;">
                <strong>📉 매수 트리거 발동! (2달 전 대비, slowly melting 방지)</strong><br>
                {t['ticker']}: 2달 전 대비 {t['change_pct']:.2f}%<br>
                기준일: {t['baseline_date']} (₩{t['baseline_price']:,.0f})<br>
                트리거 레벨: {t['trigger_level']}<br>
                <strong>액션:</strong> {t['action']}
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