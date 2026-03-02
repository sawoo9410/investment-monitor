"""시장 데이터 수집 모듈 (Alpha Vantage + FinanceDataReader)"""
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
import pytz
import time

# Alpha Vantage API 호출 카운터
AV_API_CALLS = 0
AV_DAILY_LIMIT = 25

# FinanceDataReader 추가
try:
    import FinanceDataReader as fdr
    FDR_AVAILABLE = True
    print("✅ FinanceDataReader 로드 성공")
except ImportError as e:
    FDR_AVAILABLE = False
    print(f"⚠️  FinanceDataReader import 실패: {e}")
except Exception as e:
    FDR_AVAILABLE = False
    print(f"⚠️  FinanceDataReader 예상치 못한 에러: {e}")

def log_av_api_call():
    """Alpha Vantage API 호출 카운트 및 로깅"""
    global AV_API_CALLS
    AV_API_CALLS += 1
    remaining = AV_DAILY_LIMIT - AV_API_CALLS
    print(f"    📊 Alpha Vantage API: {AV_API_CALLS}/{AV_DAILY_LIMIT} 사용 (남은 호출: {remaining})")
    
    if remaining <= 5:
        print(f"    ⚠️  API 한도가 {remaining}회만 남았습니다!")
    
    return remaining

def _get_target_year_month(today: datetime, months_back: int):
    """오늘 기준 N개월 전의 (year, month) 반환"""
    month = today.month - months_back
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    return year, month

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

def get_kr_etf_price(ticker: str, retry=3, delay=2) -> Optional[Dict]:
    """한국 ETF 현재가 및 전일 등락 조회 (FinanceDataReader)"""
    if not FDR_AVAILABLE:
        print(f"{ticker} 조회 실패: FinanceDataReader 미설치")
        return None
    
    clean_ticker = ticker.replace('.KS', '').replace('.KRX', '')
    
    for attempt in range(retry):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            
            today = datetime.now()
            start_date = (today - timedelta(days=10)).strftime('%Y-%m-%d')
            
            df = fdr.DataReader(clean_ticker, start_date)
            
            if df.empty or len(df) < 2:
                print(f"{ticker} 데이터 부족 (시도 {attempt+1}/{retry})")
                if attempt < retry - 1:
                    continue
                return None
            
            current_price = df['Close'].iloc[-1]
            prev_price = df['Close'].iloc[-2]
            change_pct = ((current_price - prev_price) / prev_price) * 100
            
            time.sleep(2)
            
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

def get_kr_etf_monthly_baseline(ticker: str, retry=3, delay=2) -> Optional[Dict]:
    """한국 ETF 전월 첫 거래일 가격 조회 (ISA 트리거용)
    
    전월 1일이 주말/휴일이면 가장 가까운 이후 거래일 사용
    """
    if not FDR_AVAILABLE:
        return None
    
    clean_ticker = ticker.replace('.KS', '').replace('.KRX', '')
    
    for attempt in range(retry):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            
            kst = pytz.timezone('Asia/Seoul')
            today = datetime.now(kst)

            # 전월 계산
            prev_month = today.month - 1 if today.month > 1 else 12
            prev_year = today.year if today.month > 1 else today.year - 1

            # 전월 1일 기준 조회 (여유 3일 포함)
            start_date = datetime(prev_year, prev_month, 1) - timedelta(days=3)
            start_date_str = start_date.strftime('%Y-%m-%d')
            
            df = fdr.DataReader(clean_ticker, start_date_str)
            
            if df.empty:
                print(f"{ticker} 월간 데이터 없음 (시도 {attempt+1}/{retry})")
                if attempt < retry - 1:
                    continue
                return None
            
            # 전월의 첫 거래일 찾기
            baseline_row = None
            for idx, row in df.iterrows():
                if idx.year == prev_year and idx.month == prev_month:
                    baseline_row = (idx, row)
                    break
            
            if baseline_row is None:
                print(f"{ticker} 전월 거래 데이터 없음")
                return None
            
            baseline_date = baseline_row[0].strftime('%Y-%m-%d')
            baseline_price = baseline_row[1]['Close']
            current_price = df['Close'].iloc[-1]
            change_pct = ((current_price - baseline_price) / baseline_price) * 100
            
            # 1일이 아닌 경우 로그
            if baseline_row[0].day != 1:
                print(f"    📅 전월 1일 휴장, {baseline_date} (첫 거래일) 사용")
            
            time.sleep(2)
            
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

def get_kr_etf_multi_period_baselines(ticker: str, retry=3, delay=2) -> Optional[Dict]:
    """한국 ETF 다기간 기준가 조회 (전월 1일, 3개월, 6개월, 1년 전 1일)
    
    지수 ETF 전용. FDR로 1년치 데이터 한 번에 가져와 모든 기간 추출.
    각 기간의 1일이 주말/휴일이면 해당 월의 첫 거래일 사용.
    """
    if not FDR_AVAILABLE:
        return None
    
    clean_ticker = ticker.replace('.KS', '').replace('.KRX', '')
    
    for attempt in range(retry):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            
            kst = pytz.timezone('Asia/Seoul')
            today = datetime.now(kst)
            
            # 1년치 + 여유 데이터 로드
            start_date = (today - timedelta(days=400)).strftime('%Y-%m-%d')
            df = fdr.DataReader(clean_ticker, start_date)
            
            if df.empty:
                print(f"{ticker} 다기간 데이터 없음 (시도 {attempt+1}/{retry})")
                if attempt < retry - 1:
                    continue
                return None
            
            current_price = df['Close'].iloc[-1]
            
            def find_first_trading_day(year, month):
                """특정 연월의 첫 거래일 가격 반환 (주말/휴일 자동 대응)"""
                target_rows = df[(df.index.year == year) & (df.index.month == month)]
                if target_rows.empty:
                    return None, None
                first_date = target_rows.index[0].strftime('%Y-%m-%d')
                first_price = target_rows['Close'].iloc[0]
                return first_date, float(first_price)
            
            # ✅ 수정: monthly를 1(전월)로 변경
            # 실행 시점(오전 7시 KST)에는 이번 달 데이터가 아직 없으므로
            # 전월 첫 거래일을 기준으로 삼아야 함
            period_defs = [
                ('monthly', 1),   # 전월 1일 (기존 0 → 1 수정)
                ('3month', 3),
                ('6month', 6),
                ('1year', 12),
            ]
            
            periods = {}
            for period_name, months_back in period_defs:
                year, month = _get_target_year_month(today, months_back)
                date_str, price = find_first_trading_day(year, month)
                if date_str and price:
                    change_pct = ((float(current_price) - price) / price) * 100
                    periods[period_name] = {
                        'date': date_str,
                        'price': round(price, 2),
                        'change_pct': round(change_pct, 2)
                    }
                else:
                    periods[period_name] = None
                    print(f"    ⚠️  {ticker}: {period_name} 기간 데이터 없음")
            
            time.sleep(2)
            
            return {
                'ticker': ticker,
                'current_price': round(float(current_price), 2),
                'periods': periods
            }
        except Exception as e:
            print(f"{ticker} 다기간 기준 조회 실패 (시도 {attempt+1}/{retry}): {e}")
            if attempt < retry - 1:
                time.sleep(delay * (attempt + 1))
            else:
                return None

def get_stock_price(ticker: str, av_api_key: str, retry=3, delay=3) -> Optional[Dict]:
    """주식/ETF 현재가 및 전일 등락 조회 (Alpha Vantage)"""
    log_av_api_call()
    
    for attempt in range(retry):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={av_api_key}"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if 'Note' in data or 'Information' in data:
                error_msg = data.get('Note') or data.get('Information')
                print(f"    🚨 Alpha Vantage API 한도 초과!")
                print(f"    📝 {error_msg}")
                return None
            
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
            
            time.sleep(1)
            
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
    """전월 첫 거래일 가격 조회 - 개별주용 (Alpha Vantage)
    
    전월 1일이 주말/휴일이면 가장 가까운 이후 거래일 사용.
    실행 시점(오전 7시 KST)에는 이번 달 데이터가 없으므로 전월 기준 사용.
    """
    log_av_api_call()
    
    for attempt in range(retry):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&apikey={av_api_key}&outputsize=compact"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if 'Note' in data or 'Information' in data:
                error_msg = data.get('Note') or data.get('Information')
                print(f"    🚨 Alpha Vantage API 한도 초과!")
                print(f"    📝 {error_msg}")
                return None
            
            if 'Time Series (Daily)' not in data:
                print(f"{ticker} 일별 데이터 없음 (시도 {attempt+1}/{retry}): {data}")
                if attempt < retry - 1:
                    continue
                return None
            
            time_series = data['Time Series (Daily)']
            dates = sorted(time_series.keys(), reverse=True)
            
            if not dates:
                return None
            
            kst = pytz.timezone('Asia/Seoul')
            today = datetime.now(kst)

            # ✅ 수정: 전월 계산
            prev_month = today.month - 1 if today.month > 1 else 12
            prev_year = today.year if today.month > 1 else today.year - 1
            
            # 전월의 첫 거래일 찾기 (날짜 오름차순으로 순회)
            baseline_date = None
            baseline_price = None
            
            for date_str in reversed(dates):
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                if date_obj.year == prev_year and date_obj.month == prev_month:
                    baseline_date = date_str
                    baseline_price = float(time_series[date_str]['4. close'])
                    
                    if date_obj.day != 1:
                        print(f"    📅 전월 1일 휴장, {baseline_date} (첫 거래일) 사용")
                    
                    break
            
            # 전월 데이터가 없으면 조회 실패 처리 (compact=100일치이므로 거의 없음)
            if baseline_date is None:
                print(f"    ⚠️  {ticker} 전월 데이터 없음 - 조회 실패")
                return None
            
            # current_price는 가장 최근 종가 (main.py에서 실시간 가격으로 덮어씀)
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

def get_us_etf_multi_period_baselines(ticker: str, av_api_key: str, retry=3, delay=3) -> Optional[Dict]:
    """미국 지수 ETF 다기간 기준가 조회 (전월 1일, 3개월, 6개월, 1년 전 1일)
    
    지수 ETF 전용. outputsize=full로 1년치 데이터를 1회 호출로 처리.
    각 기간의 1일이 주말/휴일이면 해당 월의 첫 거래일 사용.
    """
    log_av_api_call()
    
    for attempt in range(retry):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            
            # full 사이즈로 1년치 이상 데이터 가져오기 (1회 호출)
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&apikey={av_api_key}&outputsize=full"
            response = requests.get(url, timeout=15)
            data = response.json()
            
            if 'Note' in data or 'Information' in data:
                print(f"    🚨 Alpha Vantage API 한도 초과!")
                return None
            
            if 'Time Series (Daily)' not in data:
                print(f"{ticker} 일별 데이터 없음 (시도 {attempt+1}/{retry})")
                if attempt < retry - 1:
                    continue
                return None
            
            time_series = data['Time Series (Daily)']
            dates = sorted(time_series.keys(), reverse=True)
            
            if not dates:
                return None
            
            kst = pytz.timezone('Asia/Seoul')
            today = datetime.now(kst)
            current_price = float(time_series[dates[0]]['4. close'])
            
            def find_first_trading_day(year, month):
                """특정 연월의 첫 거래일 가격 반환 (주말/휴일 자동 대응)"""
                for date_str in reversed(dates):
                    d = datetime.strptime(date_str, '%Y-%m-%d')
                    if d.year == year and d.month == month:
                        return date_str, float(time_series[date_str]['4. close'])
                return None, None
            
            # ✅ 수정: monthly를 1(전월)로 변경
            period_defs = [
                ('monthly', 1),   # 전월 1일 (기존 0 → 1 수정)
                ('3month', 3),
                ('6month', 6),
                ('1year', 12),
            ]
            
            periods = {}
            for period_name, months_back in period_defs:
                year, month = _get_target_year_month(today, months_back)
                date_str, price = find_first_trading_day(year, month)
                if date_str and price:
                    change_pct = ((current_price - price) / price) * 100
                    periods[period_name] = {
                        'date': date_str,
                        'price': round(price, 2),
                        'change_pct': round(change_pct, 2)
                    }
                else:
                    periods[period_name] = None
                    print(f"    ⚠️  {ticker}: {period_name} 기간 데이터 없음")
            
            time.sleep(1)
            
            return {
                'ticker': ticker,
                'current_price': round(current_price, 2),
                'periods': periods
            }
        except Exception as e:
            print(f"{ticker} 다기간 기준 조회 실패 (시도 {attempt+1}/{retry}): {e}")
            if attempt < retry - 1:
                time.sleep(delay * (attempt + 1))
            else:
                return None

def get_stock_fundamentals(ticker: str, av_api_key: str, retry=3, delay=3) -> Optional[Dict]:
    """PER, ROE, D/E 등 기본 지표 조회 - 개별주 전용 (Alpha Vantage)"""
    log_av_api_call()
    
    for attempt in range(retry):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            
            url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={av_api_key}"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if 'Note' in data or 'Information' in data:
                error_msg = data.get('Note') or data.get('Information')
                print(f"    🚨 Alpha Vantage API 한도 초과!")
                print(f"    📝 {error_msg}")
                return None
            
            if not data or 'Symbol' not in data:
                print(f"{ticker} OVERVIEW 데이터 없음 (시도 {attempt+1}/{retry}): {data}")
                if attempt < retry - 1:
                    continue
                return None
            
            current_price = float(data.get('50DayMovingAverage', 0))
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