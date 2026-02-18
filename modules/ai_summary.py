"""Claude API를 사용한 거시경제 요약 모듈"""
from anthropic import Anthropic
from datetime import datetime
from typing import List, Optional

def generate_macro_summary(api_key: str, keywords: List[str]) -> Optional[str]:
    """거시경제 주요 이슈 요약 생성"""
    try:
        client = Anthropic(api_key=api_key)
        
        today = datetime.now().strftime('%Y년 %m월 %d일')
        keywords_str = ", ".join(keywords)
        
        prompt = f"""오늘은 {today}입니다.

다음 키워드와 관련된 최근 1주일간의 주요 거시경제 이슈를 간단히 요약해주세요:
{keywords_str}

요약 형식:
- 3~5개 주요 이슈만 간결하게
- 각 이슈는 1~2문장으로
- 투자자 관점에서 중요한 것 위주
- 날짜 명시

예시:
- 2월 15일 - 미국 1월 CPI 3.2%, 예상치 상회. 금리인하 기대 후퇴.
- 2월 13일 - 연준 의장 발언: "인플레이션 둔화 확인 필요". 긴축 기조 유지 시사.
"""
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return message.content[0].text
        
    except Exception as e:
        print(f"AI 요약 생성 실패: {e}")
        return "거시경제 요약을 생성할 수 없습니다."

def check_portfolio_limits(holdings: dict, config: dict) -> str:
    """포트폴리오 비중 한계선 체크"""
    warnings = []
    
    # AI/테크 섹터 합계 체크 (GOOGL, QCOM 등)
    tech_tickers = ['GOOGL', 'QCOM']
    tech_total = sum(holdings.get(t, 0) for t in tech_tickers)
    
    if tech_total > 30:
        warnings.append(f"⚠️ AI/테크 섹터 {tech_total:.1f}% (한계: 30%)")
    
    # OXY 비중 체크
    oxy_pct = holdings.get('OXY', 0)
    if oxy_pct > 10:
        warnings.append(f"⚠️ OXY {oxy_pct:.1f}% (한계: 10%)")
    
    # 현금 비율 체크
    cash_pct = holdings.get('CASH', 0)
    if cash_pct < 15:
        warnings.append(f"⚠️ 현금 {cash_pct:.1f}% (최소: 15%)")
    elif cash_pct > 25:
        warnings.append(f"⚠️ 현금 {cash_pct:.1f}% (최대: 25%)")
    
    if warnings:
        return "\n".join(warnings)
    else:
        return "✅ 모든 비중 한계선 내"