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
                    "content": f"""당신은 투자자를 위한 거시경제 분석가입니다. 
다음 키워드와 관련된 최근 주요 경제 이슈를 간결하게 요약해주세요:

키워드: {keyword_str}

요구사항:
1. 최근 1주일 이내의 주요 경제 이벤트 중심
2. S&P 500, 반도체, AI 섹터에 미칠 영향 분석
3. 개인 투자자 관점에서 유의할 점
4. 3-5문단으로 작성
5. 마크다운 문법(#, **, -, |) 사용 금지 - 순수 텍스트만 사용
6. 문단 구분은 빈 줄 하나로만 표시
7. 한글로 작성

이메일로 읽기 편한 평문 형식으로 작성해주세요."""
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