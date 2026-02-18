"""시장 데이터 수집 모듈 (재시도 로직 포함)"""
import yfinance as yf
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
import pytz
import time

def get_fx_rate(api_key: str, retry=3, delay=2) -> Optional[float]:
    """USD/KRW 환율 조회 (재시도 로직 포함)"""
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

def get_stock_price(ticker: str, retry=3, delay=3) -> Optional[Dict]:
    """주식/ETF 현재가 및 전일 등락 조회 (재시도 로직 포함)"""
    for attempt in range(retry):
        try:
            # 딜레이 먼저 (rate limit 방지)
            if attempt > 0:
                time.sleep(delay * attempt)
            
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            
            if len(hist) < 2:
                print(f"{ticker} 데이터 부족 (시도 {attempt+1}/{retry})")
                if attempt < retry - 1:
                    continue
                return None
                
            current_price = hist['Close'].iloc[-1]
            prev_price = hist['Close'].iloc[-2]
            change_pct = ((current_price - prev_price) / prev_price) * 100
            
            # 성공하면 약간의 딜레이 후 반환 (다음 요청 준비)
            time.sleep(1)
            
            return {
                'ticker': ticker,
                'current_price': round(current_price, 2),
                'prev_price': round(prev_price, 2),
                'change_pct': round(change_pct, 2)
            }
        except Exception as e:
            print(f"{ticker} 조회 실패 (시도 {attempt+1}/{retry}): {e}")
            if attempt < retry - 1:
                time.sleep(delay * (attempt + 1))
            else:
                return None

def get_monthly_baseline_price(ticker: str, retry=3, delay=3) -> Optional[Dict]:
    """이번 달 첫 거래일 가격 조회 (ISA 트리거용, 재시도 로직 포함)"""
    for attempt in range(retry):
        try:
            # 딜레이 먼저
            if attempt > 0:
                time.sleep(delay * attempt)
            
            kst = pytz.timezone('Asia/Seoul')
            today = datetime.now(kst)
            
            # 이번 달 1일
            first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # 첫 거래일 찾기 (주말 건너뛰기)
            while first_day.weekday() >= 5:  # 토(5), 일(6)
                first_day += timedelta(days=1)
            
            # 해당 월의 데이터 가져오기
            stock = yf.Ticker(ticker)
            hist = stock.history(start=first_day.strftime('%Y-%m-%d'))
            
            if hist.empty:
                print(f"{ticker} 월간 데이터 없음 (시도 {attempt+1}/{retry})")
                if attempt < retry - 1:
                    continue
                return None
                
            baseline_price = hist['Close'].iloc[0]
            current_price = hist['Close'].iloc[-1]
            change_pct = ((current_price - baseline_price) / baseline_price) * 100
            
            # 성공 시 딜레이
            time.sleep(1)
            
            return {
                'ticker': ticker,
                'baseline_date': hist.index[0].strftime('%Y-%m-%d'),
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

def get_stock_fundamentals(ticker: str, retry=3, delay=3) -> Optional[Dict]:
    """PER 등 기본 지표 조회 (QCOM용, 재시도 로직 포함)"""
    for attempt in range(retry):
        try:
            # 딜레이 먼저
            if attempt > 0:
                time.sleep(delay * attempt)
            
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 52주 최고가 대비 하락률 계산
            current_price = info.get('currentPrice', 0)
            high_52week = info.get('fiftyTwoWeekHigh', 0)
            
            if high_52week > 0:
                drop_from_high = ((current_price - high_52week) / high_52week) * 100
            else:
                drop_from_high = 0
            
            # 성공 시 딜레이
            time.sleep(1)
            
            return {
                'ticker': ticker,
                'per': info.get('trailingPE'),
                'current_price': current_price,
                'high_52week': high_52week,
                'drop_from_high_pct': round(drop_from_high, 2)
            }
        except Exception as e:
            print(f"{ticker} 펀더멘털 조회 실패 (시도 {attempt+1}/{retry}): {e}")
            if attempt < retry - 1:
                time.sleep(delay * (attempt + 1))
            else:
                return None