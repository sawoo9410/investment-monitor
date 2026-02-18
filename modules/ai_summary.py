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
            max_tokens=1500,
            messages=[
                {
                    "role": "user",
                    "content": f"""당신은 워런 버핏의 투자 철학을 따르는 개인 투자자를 위한 거시경제 분석가입니다.

이 투자자의 전략:
- S&P 500 ETF 코어 70-100% (장기 보유)
- 개별주 20-30% (AI 엔지니어, GOOGL/OXY/QCOM 소량 보유)
- 급락 시에만 규칙 기반 추가 매수 (-5%, -10% 트리거)
- 단기 뉴스에 흔들리지 않고 장기 관점 유지

최근 주요 거시경제 이슈를 다음 구조로 요약해주세요:

키워드: {keyword_str}

[작성 구조]

1. 거시경제 현황 (2-3문장)
   • 주요 경제지표 (CPI, 금리, GDP 등)
   • 시장 분위기 요약

2. S&P 500 장기 관점 (3-4문장 서술형)
   - 향후 3-5년 구조적 영향
   - 버핏이라면 어떻게 볼지

3. 급락 매수 판단
   • 현재 시장 상태: (고평가/적정/저평가)
   • 추천 액션: (현금 유지 / 매수 대기 / 추가 매수)
   • 근거: (1-2문장)
   • **중요**: S&P 500 PER 평가 시 "역사적 평균"이 아닌 "최근 5년 평균"과 비교하세요. 현재 PER이 최근 5년 평균보다 높으면 고평가, 낮으면 저평가로 판단.

4. AI/테크 모트 점검 (개조식)
   • GOOGL: 모트 상태
   • QCOM: 모트 상태
   • 섹터 리스크: 주요 이슈

[작성 규칙]
- 개조식(•)과 서술형 적절히 혼합
- 마크다운 금지 (#, **, -, |)
- 명확하고 실용적인 톤
- PER 판단은 반드시 "최근 5년 평균" 기준
- 한글로 작성
"""
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