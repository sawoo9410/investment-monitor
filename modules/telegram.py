"""텔레그램 알림 모듈

Telegram Bot API를 직접 호출 (requests).
python-telegram-bot v20+는 async 전용이라 동기 파이프라인에 맞지 않음.
"""
import time
import requests
from datetime import date
from typing import List

API_BASE = "https://api.telegram.org/bot{token}"

# ISA 만기일 (2027-08-09)
ISA_MATURITY = date(2027, 8, 9)


class TelegramNotifier:
    """텔레그램 봇 알림 발송기.

    실패해도 파이프라인을 차단하지 않는다 — 모든 public 메서드는 bool 반환.
    """

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = API_BASE.format(token=bot_token)

    # =========================================================================
    # 기본 발송
    # =========================================================================

    def send_message(self, text: str, parse_mode: str = 'HTML', retry: int = 3) -> bool:
        """메시지 전송. 실패 시 retry회 재시도."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        for attempt in range(1, retry + 1):
            try:
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True
                if resp.status_code == 429:
                    wait = resp.json().get("parameters", {}).get("retry_after", 5)
                    print(f"    ⚠️  텔레그램 rate limit, {wait}초 대기 ({attempt}/{retry})")
                    time.sleep(wait)
                    continue
                print(f"    ⚠️  텔레그램 전송 실패 (HTTP {resp.status_code}): {resp.text[:200]}")
            except requests.RequestException as e:
                print(f"    ⚠️  텔레그램 전송 오류 ({attempt}/{retry}): {e}")
            if attempt < retry:
                time.sleep(2)
        return False

    # =========================================================================
    # 트리거 알림
    # =========================================================================

    def send_trigger_alert(self, trigger_type: str, trigger_data: dict) -> bool:
        """449180 급락 트리거 발동 알림.

        trigger_type: 'monthly_5pct' / 'monthly_10pct' / '2month_5pct' / '2month_10pct'
        """
        change_pct = trigger_data['change_pct']
        baseline_date = trigger_data.get('baseline_date', '?')
        baseline_price = trigger_data.get('baseline_price', 0)
        current_price = trigger_data.get('current_price', 0)
        action = trigger_data.get('action', '')

        is_2month = trigger_type.startswith('2month')
        label = "2달 전 대비" if is_2month else "전월 대비"
        emoji = "📉" if is_2month else "🚨"

        buffer_remaining = trigger_data.get('buffer_remaining')
        buffer_total = trigger_data.get('buffer_total', 3000000)

        text = (
            f"{emoji} <b>449180 급락 트리거 발동! ({label})</b>\n"
            f"\n"
            f"종목: 449180.KS (KODEX 미국S&amp;P500(H))\n"
            f"변동: {label} <b>{change_pct:+.2f}%</b>\n"
            f"기준가: ₩{baseline_price:,.0f} ({baseline_date})\n"
            f"현재가: ₩{current_price:,.0f}\n"
            f"액션: {action}\n"
        )
        if buffer_remaining is not None:
            text += f"버퍼 잔액: ₩{buffer_remaining:,.0f} / ₩{buffer_total:,.0f}\n"
        text += f"\n→ 한투 앱에서 직접 매수하세요 (API 연동 전)"
        return self.send_message(text)

    def send_isa_action_required(self, trigger_data: dict) -> bool:
        """ISA 수동 액션 필요 안내 (일반)."""
        ticker = trigger_data.get('ticker', '?')
        action = trigger_data.get('action', '')
        reason = trigger_data.get('reason', '')

        text = (
            f"📋 <b>ISA 수동 액션 필요</b>\n"
            f"\n"
            f"종목: {ticker}\n"
            f"액션: {action}\n"
        )
        if reason:
            text += f"사유: {reason}\n"
        text += "\n→ 신한 ISA 앱에서 처리하세요"
        return self.send_message(text)

    def send_133690_sell_alert(self, trigger_data: dict, remaining_qty: int) -> bool:
        """133690 매도 조건 충족 알림 + 잔여 수량."""
        change_pct = trigger_data['change_pct']
        current_price = trigger_data.get('current_price', 0)
        action = trigger_data.get('action', '')
        avg_price = trigger_data.get('avg_price', 0)
        gain_from_avg = trigger_data.get('gain_from_avg_pct', 0)
        sell_qty = trigger_data.get('sell_qty', 10)

        text = (
            f"📈 <b>133690 매도 조건 충족!</b>\n"
            f"\n"
            f"종목: TIGER 미국나스닥100 (133690.KS)\n"
            f"전월 대비: <b>{change_pct:+.2f}%</b> ✓ (기준: +5%)\n"
            f"평단 대비: <b>{gain_from_avg:+.1f}%</b> ✓ (기준: +15%, 평단 ₩{avg_price:,.0f})\n"
            f"현재가: ₩{current_price:,.0f}\n"
            f"액션: {sell_qty}주 매도\n"
            f"매도 후 잔여: {remaining_qty}주\n"
            f"\n"
            f"→ 신한 ISA 앱에서 직접 매도하세요"
        )
        return self.send_message(text)

    def send_qcom_alert(self, condition_data: dict) -> bool:
        """QCOM 매수 조건 충족 알림."""
        per = condition_data.get('per', 0)
        drop_pct = condition_data.get('drop_pct', 0)
        current_price = condition_data.get('current_price', 0)
        high_52week = condition_data.get('high_52week', 0)

        text = (
            f"🎯 <b>QCOM 매수 조건 충족!</b>\n"
            f"\n"
            f"PER: {per:.1f} (기준 ≤ 25)\n"
            f"52주 고점: ${high_52week:.2f}\n"
            f"현재가: ${current_price:.2f} (고점 대비 {drop_pct:+.1f}%)\n"
            f"\n"
            f"→ 매수 검토하세요"
        )
        return self.send_message(text)

    def send_portfolio_warning(self, warnings: List[dict]) -> bool:
        """포트폴리오 한도 초과 경고."""
        if not warnings:
            return True

        lines = ["⚠️ <b>포트폴리오 한도 경고</b>\n"]
        for w in warnings:
            lines.append(f"• {w['message']}")

        return self.send_message("\n".join(lines))

    # =========================================================================
    # 환율 / 버퍼
    # =========================================================================

    def send_fx_zone_change(self, prev_zone: str, new_zone: str, fx_rate: float) -> bool:
        """환율 구간 변경 알림."""
        zone_names = {
            'full_convert': '전액환전 (~1,380)',
            'normal_full': '정상-전액 (1,380~1,420)',
            'normal_half': '정상-절반 (1,420~1,450)',
            'pause': '보류 (1,450~)',
        }
        prev_name = zone_names.get(prev_zone, prev_zone)
        new_name = zone_names.get(new_zone, new_zone)

        # ISA 활성 종목 변경 여부
        isa_note = ""
        prev_hedged = prev_zone != 'full_convert'
        new_hedged = new_zone != 'full_convert'
        if prev_hedged != new_hedged:
            if new_hedged:
                isa_note = "\n🔄 ISA 활성 종목: 360750 → <b>449180</b> (환헤지)"
            else:
                isa_note = "\n🔄 ISA 활성 종목: 449180 → <b>360750</b> (환노출)"

        text = (
            f"💱 <b>환율 구간 변경</b>\n"
            f"\n"
            f"환율: {fx_rate:,.2f}원\n"
            f"이전: {prev_name}\n"
            f"현재: <b>{new_name}</b>"
            f"{isa_note}"
        )
        return self.send_message(text)

    def send_buffer_warning(self, remaining: int, threshold: int = 1000000) -> bool:
        """급락 버퍼 잔액 경고 (threshold 이하 시)."""
        if remaining > threshold:
            return True

        if remaining <= 0:
            emoji = "🔴"
            status = "소진"
        else:
            emoji = "🟡"
            status = "부족"

        text = (
            f"{emoji} <b>급락 버퍼 잔액 {status}</b>\n"
            f"\n"
            f"잔액: ₩{remaining:,.0f} / ₩3,000,000\n"
            f"\n"
            f"→ config.yaml trigger_buffer_krw 충전 검토"
        )
        return self.send_message(text)

    # =========================================================================
    # 보유 종목 급변
    # =========================================================================

    def send_price_alert(self, ticker: str, name: str, change_pct: float,
                         current_price: float, is_krw: bool = True) -> bool:
        """보유 종목 일간 ±5% 이상 변동 알림 (정보만, 액션 안내 없음)."""
        emoji = "📈" if change_pct > 0 else "📉"
        price_str = f"₩{current_price:,.0f}" if is_krw else f"${current_price:.2f}"

        text = (
            f"{emoji} <b>{ticker} 일간 {change_pct:+.2f}%</b>\n"
            f"\n"
            f"{name}\n"
            f"현재가: {price_str}"
        )
        return self.send_message(text)

    # =========================================================================
    # 정기 리마인더
    # =========================================================================

    def send_monthly_checklist(self, day_type: str, fx_rate: float,
                               isa_ticker: str) -> bool:
        """매달 체크리스트 리마인더.

        day_type: 'first' (1일) / 'mid' (중순)
        """
        if day_type == 'first':
            isa_label = "449180 (환헤지)" if isa_ticker == '449180.KS' else "360750 (환노출)"
            text = (
                f"📅 <b>월초 체크리스트</b>\n"
                f"\n"
                f"환율: {fx_rate:,.2f}원\n"
                f"\n"
                f"☐ ISA 100만원 정기매수 ({isa_label})\n"
                f"☐ 한투 80만원 입금 확인\n"
                f"☐ config.yaml cash 값 업데이트\n"
                f"☐ 환율 구간 → 환전 금액 확인"
            )
        else:
            text = (
                f"📅 <b>월중 비중 점검</b>\n"
                f"\n"
                f"☐ AI·테크 섹터 ≤ 20%\n"
                f"☐ 개별 종목 ≤ 20%\n"
                f"☐ speculative ≤ 5%\n"
                f"☐ 현금 15% ~ 25%"
            )
        return self.send_message(text)

    def send_isa_countdown(self, days_remaining: int) -> bool:
        """ISA 만기 카운트다운 (D-90, D-30, D-7)."""
        text = (
            f"⏰ <b>ISA 만기 D-{days_remaining}</b>\n"
            f"\n"
            f"만기일: 2027-08-09\n"
            f"→ 키움증권 ISA 개설 준비"
        )
        return self.send_message(text)

    # =========================================================================
    # 종가 리포트 (국내 15:45 / 미국 06:15)
    # =========================================================================

    def send_kr_market_close(self, report_data: dict,
                             weekly_data: dict = None) -> bool:
        """국내 종가 리포트 (15:45 KST). 금요일이면 주간 요약 포함.

        report_data: main.py의 report_data (전체)
        weekly_data: 금요일 주간 요약 {'total_change': int, 'total_change_pct': float,
                                       'triggers_fired': list}
        """
        from datetime import datetime as _dt
        import pytz as _tz
        now = _dt.now(_tz.timezone('Asia/Seoul'))
        weekday_kr = ['월', '화', '수', '목', '금', '토', '일'][now.weekday()]
        date_str = now.strftime(f'%m/%d({weekday_kr})')

        portfolio = report_data.get('portfolio_summary', {})
        total_assets = portfolio.get('total_assets', 0)
        cash_pct = portfolio.get('cash_allocation_pct', 0)
        fx_rate = report_data.get('fx_rate')
        fx_zone = report_data.get('fx_zone_info', {})
        stock_data = report_data.get('stock_data', [])
        isa_trigger = report_data.get('isa_trigger')
        isa_2month = report_data.get('isa_2month_trigger')
        isa_sell = report_data.get('isa_sell_trigger')
        warnings = report_data.get('portfolio_warnings', [])

        # 1억 목표 진행률
        target = 100_000_000
        progress_pct = (total_assets / target * 100) if total_assets else 0
        days_to_target = (ISA_MATURITY - now.date()).days

        kr_value = portfolio.get('kr_value', 0)
        us_value = portfolio.get('us_value', 0)

        lines = [
            f"📊 <b>{date_str} 국내 장 마감</b>",
            f"",
            f"💰 총자산: ₩{total_assets:,.0f} (현금 {cash_pct:.1f}%)",
            f"   🇰🇷 ₩{kr_value:,.0f} | 🇺🇸 ₩{us_value:,.0f}",
            f"🎯 1억 목표: {progress_pct:.1f}% (D-{days_to_target})",
            f"",
            f"🇰🇷 <b>국내 ETF</b>",
        ]

        # 국내 ETF만
        allocations = portfolio.get('allocations', {})
        for s in stock_data:
            pd = s.get('price_data')
            if not pd:
                continue
            ticker = pd['ticker']
            if not (ticker.endswith('.KS') or ticker.endswith('.KRX')):
                continue
            change = pd['change_pct']
            alloc = allocations.get(ticker, {})
            holdings = alloc.get('holdings', s.get('holdings', 0))
            value = alloc.get('value', 0)
            pct = alloc.get('allocation_pct', 0)
            lines.append(
                f" {ticker.replace('.KS',''):>6}  ₩{pd['current_price']:,.0f}  {change:+.1f}%"
                f"\n         {holdings}주 ₩{value:,.0f} ({pct:.1f}%)"
            )

        # 환율 + 현금 + 버퍼
        lines.append("")
        if fx_rate:
            zone_name = fx_zone.get('zone_name', '') if fx_zone else ''
            lines.append(f"💵 환율: ₩{fx_rate:,.0f} ({zone_name})")

        buffer_remaining = report_data.get('buffer_remaining')
        if buffer_remaining is not None:
            lines.append(f"💰 현금: {cash_pct:.1f}% | 버퍼: ₩{buffer_remaining:,.0f}")
        else:
            lines.append(f"💰 현금: {cash_pct:.1f}%")

        # 트리거
        triggers = []
        if isa_trigger:
            triggers.append(f"🚨 449180 급락 (전월 {isa_trigger['change_pct']:+.2f}%)")
        if isa_2month:
            triggers.append(f"📉 449180 급락 (2달전 {isa_2month['change_pct']:+.2f}%)")
        if isa_sell:
            triggers.append(f"📈 133690 매도 ({isa_sell['change_pct']:+.2f}%)")

        lines.append("")
        if triggers:
            lines.append("<b>트리거:</b>")
            lines.extend(triggers)
        else:
            lines.append("⚠️ 트리거: 없음")

        # 경고
        if warnings:
            lines.append("")
            for w in warnings:
                lines.append(f"⚠️ {w['message']}")

        # 금요일 주간 요약
        if weekly_data:
            change = weekly_data.get('total_change', 0)
            change_pct_w = weekly_data.get('total_change_pct', 0)
            sign = "+" if change >= 0 else ""
            triggers_w = weekly_data.get('triggers_fired', [])

            lines.extend([
                "",
                f"📅 <b>주간 요약</b>",
                f" 총자산: {sign}₩{change:,.0f} ({change_pct_w:+.1f}%)",
                f" 트리거 발동: {', '.join(triggers_w) if triggers_w else '없음'}",
            ])

        return self.send_message("\n".join(lines))

    def send_us_market_close(self, report_data: dict) -> bool:
        """미국 종가 리포트 (06:15 KST)."""
        from datetime import datetime as _dt
        import pytz as _tz
        now = _dt.now(_tz.timezone('Asia/Seoul'))
        weekday_kr = ['월', '화', '수', '목', '금', '토', '일'][now.weekday()]
        date_str = now.strftime(f'%m/%d({weekday_kr})')

        stock_data = report_data.get('stock_data', [])
        qcom = report_data.get('qcom_condition')

        portfolio = report_data.get('portfolio_summary', {})
        us_value = portfolio.get('us_value', 0)

        lines = [
            f"📊 <b>{date_str} 미국 장 마감</b>",
            f"",
            f"🇺🇸 미국 평가액: ₩{us_value:,.0f}",
            f"",
            f"🇺🇸 <b>미국 종목</b>",
        ]

        allocations = portfolio.get('allocations', {})
        for s in stock_data:
            pd = s.get('price_data')
            if not pd:
                continue
            ticker = pd['ticker']
            if ticker.endswith('.KS') or ticker.endswith('.KRX'):
                continue
            change = pd['change_pct']
            per_str = ""
            fundamentals = s.get('fundamentals')
            if fundamentals and fundamentals.get('per'):
                per_str = f"  PER {fundamentals['per']:.1f}"
            alloc = allocations.get(ticker, {})
            holdings = alloc.get('holdings', s.get('holdings', 0))
            value = alloc.get('value', 0)
            pct = alloc.get('allocation_pct', 0)
            lines.append(
                f" {ticker:<7} ${pd['current_price']:<8.2f} {change:+.1f}%{per_str}"
                f"\n         {holdings}주 ₩{value:,.0f} ({pct:.1f}%)"
            )

        # 트리거
        triggers = []
        if qcom:
            triggers.append(f"🎯 QCOM 매수 (PER {qcom['per']:.1f})")

        lines.append("")
        if triggers:
            lines.append("<b>트리거:</b>")
            lines.extend(triggers)
        else:
            lines.append("⚠️ 트리거: 없음")

        return self.send_message("\n".join(lines))

    # =========================================================================
    # 시스템
    # =========================================================================

    def send_error_alert(self, error_msg: str) -> bool:
        """시스템 에러 알림."""
        text = (
            f"❌ <b>시스템 에러</b>\n"
            f"\n"
            f"<code>{_escape_html(error_msg[:500])}</code>"
        )
        return self.send_message(text)

    # =========================================================================
    # 주문 결과 (한투 연동 후)
    # =========================================================================

    def send_order_notification(self, order_result: dict, is_dry_run: bool = False) -> bool:
        """주문 체결/실패 알림."""
        ticker = order_result.get('ticker', '?')
        action = order_result.get('action', 'buy')
        quantity = order_result.get('quantity', 0)
        price = order_result.get('price', 0)
        amount = order_result.get('amount', 0)
        currency = order_result.get('currency', 'KRW')
        status = order_result.get('status', 'unknown')
        trigger_type = order_result.get('trigger_type', '')

        prefix = "[DRY-RUN] " if is_dry_run else ""
        action_kr = "매수" if action == 'buy' else "매도"

        if currency == 'KRW':
            amount_str = f"₩{amount:,.0f}"
            price_str = f"₩{price:,.0f}"
        else:
            amount_str = f"${amount:,.2f}"
            price_str = f"${price:.2f}"

        if status == 'executed':
            emoji = "✅"
            status_kr = "체결 완료"
        elif status == 'simulated':
            emoji = "🔄"
            status_kr = "시뮬레이션"
        else:
            emoji = "❌"
            status_kr = "실패"

        reason = f" ({trigger_type})" if trigger_type else ""

        text = (
            f"{emoji} <b>{prefix}{ticker} {action_kr} {status_kr}</b>{reason}\n"
            f"\n"
            f"수량: {quantity}주 × {price_str}\n"
            f"금액: {amount_str}"
        )

        if status == 'failed':
            error = order_result.get('error_message', '알 수 없는 오류')
            text += f"\n오류: <code>{_escape_html(error)}</code>"

        return self.send_message(text)


def _escape_html(text: str) -> str:
    """텔레그램 HTML 모드용 이스케이프."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
