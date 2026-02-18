"""시장 데이터 수집 모듈 (Alpha Vantage API 사용)"""
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
import pytz
import time

def get_fx_rate(api_key: str, retry=3, delay=2) -> Optional[float]:
    """USD/KRW 환율 조회"""
    for attempt in range(retry):
        try:
            url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/USD"
            response = requests.get(url, timeout=10)
            data = response.json()
            return data['conversion_rates']['KRW']
        except Exception as e:
            print(f"환율 조회 실패 (시도 {attempt+1}/{retry}): {e}")
            if attempt < retry - 1:
                time.sleep(delay * (attempt + 1))
            else:
                return None

def get_stock_price(ticker: str, av_api_key: str, retry=3, delay=3) -> Optional[Dict]:
    """주식/ETF 현재가 및 전일 등락 조회 (Alpha Vantage)"""
    for attempt in range(retry):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={av_api_key}"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if 'Global Quote' not in data:
                print(f"{ticker} 데이터 없음 (시도 {attempt+1}/{retry}): {data}")
                if attempt < retry - 1:
                    continue
                return None
            
            quote = data['Global Quote']
            current_price = float(quote.get('05. price', 0))
            prev_close = float(quote.get('08. previous close', 0))
            
            if current_price == 0 or prev_close == 0:
                print(f"{ticker} 가격 데이터 없음")
                if attempt < retry - 1:
                    continue
                return None
            
            change_pct = ((current_price - prev_close) / prev_close) * 100
            
            time.sleep(1)  # API rate limit 방지
            
            return {
                'ticker': ticker,
                'current_price': round(current_price, 2),
                'prev_price': round(prev_close, 2),
                'change_pct': round(change_pct, 2)
            }
        except Exception as e:
            print(f"{ticker} 조회 실패 (시도 {attempt+1}/{retry}): {e}")
            if attempt < retry - 1:
                time.sleep(delay * (attempt + 1))
            else:
                return None

def get_monthly_baseline_price(ticker: str, av_api_key: str, retry=3, delay=3) -> Optional[Dict]:
    """이번 달 첫 거래일 가격 조회 (ISA 트리거용)"""
    for attempt in range(retry):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&apikey={av_api_key}&outputsize=compact"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if 'Time Series (Daily)' not in data:
                print(f"{ticker} 일별 데이터 없음 (시도 {attempt+1}/{retry}): {data}")
                if attempt < retry - 1:
                    continue
                return None
            
            time_series = data['Time Series (Daily)']
            dates = sorted(time_series.keys(), reverse=True)
            
            if not dates:
                return None
            
            # 이번 달 첫 거래일 찾기
            kst = pytz.timezone('Asia/Seoul')
            today = datetime.now(kst)
            first_day = today.replace(day=1)
            
            baseline_date = None
            baseline_price = None
            
            for date_str in reversed(dates):  # 오래된 날짜부터
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                if date_obj.year == today.year and date_obj.month == today.month:
                    baseline_date = date_str
                    baseline_price = float(time_series[date_str]['4. close'])
                    break
            
            if baseline_date is None:
                # 이번 달 데이터 없으면 가장 최근 날짜 사용
                baseline_date = dates[0]
                baseline_price = float(time_series[baseline_date]['4. close'])
            
            current_price = float(time_series[dates[0]]['4. close'])
            change_pct = ((current_price - baseline_price) / baseline_price) * 100
            
            time.sleep(1)
            
            return {
                'ticker': ticker,
                'baseline_date': baseline_date,
                'baseline_price': round(baseline_price, 2),
                'current_price': round(current_price, 2),
                'change_pct': round(change_pct, 2)
            }
        except Exception as e:
            print(f"{ticker} 월간 기준 조회 실패 (시도 {attempt+1}/{retry}): {e}")
            if attempt < retry - 1:
                time.sleep(delay * (attempt + 1))
            else:
                return None

def get_stock_fundamentals(ticker: str, av_api_key: str, retry=3, delay=3) -> Optional[Dict]:
    """PER, 52주 고가 등 기본 지표 조회 (QCOM용)"""
    for attempt in range(retry):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            
            url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={av_api_key}"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if not data or 'Symbol' not in data:
                print(f"{ticker} OVERVIEW 데이터 없음 (시도 {attempt+1}/{retry}): {data}")
                if attempt < retry - 1:
                    continue
                return None
            
            current_price = float(data.get('50DayMovingAverage', 0))  # 근사치
            high_52week = float(data.get('52WeekHigh', 0))
            per = data.get('PERatio')
            
            if high_52week > 0 and current_price > 0:
                drop_from_high = ((current_price - high_52week) / high_52week) * 100
            else:
                drop_from_high = 0
            
            time.sleep(1)
            
            return {
                'ticker': ticker,
                'per': float(per) if per and per != 'None' else None,
                'current_price': current_price,
                'high_52week': high_52week,
                'drop_from_high_pct': round(drop_from_high, 2),
                'roe': data.get('ReturnOnEquityTTM'),
                'debt_equity': data.get('DebtToEquity'),
                'profit_margin': data.get('ProfitMargin')
            }
        except Exception as e:
            print(f"{ticker} 펀더멘털 조회 실패 (시도 {attempt+1}/{retry}): {e}")
            if attempt < retry - 1:
                time.sleep(delay * (attempt + 1))
            else:
                return None

# ========== 버핏 스타일 심화 지표 (주석 처리 - 테스트 후 활성화) ==========

# def get_buffett_advanced_metrics(ticker: str, av_api_key: str) -> Optional[Dict]:
#     """버핏 5지표 심화 분석 (재무제표 포함)"""
#     try:
#         # OVERVIEW는 위에서 이미 조회했으므로 재무제표만 추가
#         
#         # 1. 손익계산서 (ROIC 계산용)
#         income_url = f"https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol={ticker}&apikey={av_api_key}"
#         time.sleep(12)  # Rate limit
#         income_resp = requests.get(income_url, timeout=10)
#         income_data = income_resp.json()
#         
#         # 2. 재무상태표 (자사주 추적용)
#         balance_url = f"https://www.alphavantage.co/query?function=BALANCE_SHEET&symbol={ticker}&apikey={av_api_key}"
#         time.sleep(12)
#         balance_resp = requests.get(balance_url, timeout=10)
#         balance_data = balance_resp.json()
#         
#         # 3. 현금흐름표 (FCF 계산용)
#         cashflow_url = f"https://www.alphavantage.co/query?function=CASH_FLOW&symbol={ticker}&apikey={av_api_key}"
#         time.sleep(12)
#         cashflow_resp = requests.get(cashflow_url, timeout=10)
#         cashflow_data = cashflow_resp.json()
#         
#         # ROIC, FCF, 자사주 변화 계산 로직 추가 필요
#         
#         return {
#             'ticker': ticker,
#             'roic': None,  # 계산 로직 구현 필요
#             'fcf': None,
#             'shares_outstanding_change': None
#         }
#     except Exception as e:
#         print(f"{ticker} 심화 지표 조회 실패: {e}")
#         return None