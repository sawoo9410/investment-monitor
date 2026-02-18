"""AI 요약 및 포트폴리오 분석 모듈"""
from anthropic import Anthropic
from typing import List, Optional, Dict

def generate_macro_summary(api_key: str, keywords: List[str]) -> Optional[str]:
    """거시경제 주요 이슈 요약 생성 (Claude Opus 4.5)"""
    try:
        client = Anthropic(api_key=api_key)
        
        keyword_str = ", ".join(keywords)
        
        message = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": f"""당신은 워런 버핏의 투자 철학을 따르는 개인 투자자를 위한 거시경제 분석가입니다.

이 투자자의 전략:
- S&P 500 ETF 코어 70-100% (장기 보유)
- 개별주 20-30% (AI 엔지니어, GOOGL/OXY/QCOM 소량 보유)
- 급락 시에만 규칙 기반 추가 매수
- 단기 뉴스에 흔들리지 않고 장기 관점 유지
- 배당률보다 총수익, 모트(경제적 해자) 중심 사고

최근 주요 거시경제 이슈를 다음 관점에서 요약해주세요:

1. S&P 500 장기 관점: 지금의 이슈가 향후 3-5년 S&P 총수익에 미칠 구조적 영향
2. 급락 매수 판단: 현재 조정이 추가 매수 기회인지, 아니면 기다려야 할 국면인지
3. 감정 관리: 단기 변동성에 흔들리지 않기 위해 기억해야 할 핵심
4. AI/테크 섹터 모트: GOOGL, QCOM 같은 개별주의 장기 경쟁력 변화 여부

키워드: {keyword_str}

작성 규칙:
- 3-4문단, 평문으로 작성 (마크다운 금지)
- "지금 당장" 행동보다 "장기 관점" 강조
- 버핏이 이 상황을 어떻게 볼지 언급
- 한글로 작성"""
                }
            ]
        )
        
        if message.content and len(message.content) > 0:
            return message.content[0].text
        else:
            return None
            
    except Exception as e:
        print(f"AI 요약 생성 실패: {e}")
        return "📌 AI 거시경제 요약을 생성할 수 없습니다.\n주요 경제 이슈는 직접 확인해주세요."

def check_portfolio_limits(portfolio: Dict, config: Dict) -> List[str]:
    """포트폴리오 한도 체크"""
    warnings = []
    
    total_value = portfolio.get('total_value', 0)
    if total_value == 0:
        return ["포트폴리오 데이터 없음"]
    
    # AI/테크 섹터 한도 체크 (30%)
    ai_tech_value = portfolio.get('ai_tech_value', 0)
    ai_tech_pct = (ai_tech_value / total_value) * 100
    
    if ai_tech_pct > 30:
        warnings.append(f"AI/테크 섹터 {ai_tech_pct:.1f}% (한도 30% 초과)")
    
    # OXY 비중 체크 (10%)
    oxy_value = portfolio.get('oxy_value', 0)
    oxy_pct = (oxy_value / total_value) * 100
    
    if oxy_pct > 10:
        warnings.append(f"OXY {oxy_pct:.1f}% (한도 10% 초과)")
    
    # 현금 비중 체크 (15-25%)
    cash_total = portfolio.get('cash_krw', 0) + portfolio.get('cash_usd', 0)
    cash_pct = (cash_total / total_value) * 100
    
    if cash_pct < 15:
        warnings.append(f"현금 {cash_pct:.1f}% (최소 15% 미만)")
    elif cash_pct > 25:
        warnings.append(f"현금 {cash_pct:.1f}% (최대 25% 초과)")
    
    return warnings