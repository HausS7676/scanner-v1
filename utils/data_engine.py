import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from io import StringIO
import FinanceDataReader as fdr

try:
    from pykrx import stock
    PYKRX_AVAILABLE = True
except Exception:
    PYKRX_AVAILABLE = False

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

@st.cache_data(ttl=600)
def get_latest_valid_date():
    try:
        now = datetime.now()
        df = fdr.DataReader("005930", (now - timedelta(days=10)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'))
        if not df.empty: return df.index[-1].strftime('%Y%m%d')
    except: pass
    return (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

def yahoo_chart(symbol: str, range_: str = "3mo", interval: str = "1d") -> dict | None:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        j = res.json()
        return j["chart"]["result"][0]
    except Exception:
        return None

@st.cache_data(ttl=3600)
def get_exchange_rate() -> float:
    try:
        url = "https://finance.naver.com/marketindex/exchangeList.naver"
        res = requests.get(url, timeout=8, headers=HEADERS)
        res.encoding = "euc-kr"
        df = pd.read_html(StringIO(res.text))[0]
        val = str(df.iloc[0, 1]).replace(",", "")
        return float(val)
    except Exception:
        pass
    try:
        result = yahoo_chart("USDKRW=X", range_="5d")
        if result:
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
            return float(closes[-1])
    except Exception:
        pass
    return 1350.0

@st.cache_data(ttl=3600)
def get_us_treasury() -> float:
    try:
        result = yahoo_chart("^TNX", range_="5d")
        if result:
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
            return round(float(closes[-1]), 2)
    except Exception:
        pass
    return 4.2

@st.cache_data(ttl=3600)
def get_kospi_series() -> pd.DataFrame:
    try:
        result = yahoo_chart("^KS11", range_="6mo")
        if result:
            ts = result["timestamp"]
            closes = result["indicators"]["quote"][0]["close"]
            df = pd.DataFrame({"date": pd.to_datetime(ts, unit="s"), "Close": closes})
            df = df.dropna(subset=["Close"]).set_index("date")
            df["MA20"] = df["Close"].rolling(20).mean()
            df["MA60"] = df["Close"].rolling(60).mean()
            return df.tail(70)
    except Exception:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_market_flow() -> dict:
    default = {"f_sum": 0, "i_sum": 0, "score": 0, "status": "데이터 없음"}
    try:
        # KODEX 200 거래량 흐름으로 시장 전체 수급 간접 추정
        result = yahoo_chart("069500.KS", range_="1mo")
        if not result: return default
        closes  = result["indicators"]["quote"][0]["close"]
        volumes = result["indicators"]["quote"][0]["volume"]
        data = [(c, v) for c, v in zip(closes, volumes) if c and v]
        if len(data) < 5: return default
        
        df = pd.DataFrame(data, columns=["close", "volume"])
        df["ma5"] = df["close"].rolling(5).mean()
        
        recent = df.tail(5)
        curr_close = recent["close"].iloc[-1]
        ma5_close  = recent["ma5"].iloc[-1]
        
        prev5_vol = df.iloc[-10:-5]["volume"].mean() if len(df) >= 10 else df["volume"].mean()
        curr5_vol = recent["volume"].mean()
        vol_ratio = curr5_vol / prev5_vol if prev5_vol > 0 else 1.0
        
        price_up = curr_close > ma5_close
        vol_surge = vol_ratio > 1.1
        
        flow_score = 0
        if price_up:   flow_score += 20
        if vol_surge:  flow_score += 20
        
        if price_up and vol_surge: status = "강한 매수세 (가격↑ + 거래량↑)"
        elif price_up: status = "완만한 매수세 (가격↑)"
        elif vol_surge: status = "거래량 급증 (방향 불확실)"
        else: status = "매도/관망 우세"
        
        return {
            "score": flow_score, "status": status,
            "vol_ratio": round(vol_ratio, 2), "price_up": price_up
        }
    except Exception:
        return default

@st.cache_data(ttl=1800)
def load_ohlcv(ticker, base_date, days=300, engine="자동"):
    end = datetime.strptime(base_date, '%Y%m%d')
    start = end - timedelta(days=days)
    
    df = None
    use_pykrx = ("pykrx" in engine or "자동" in engine) and PYKRX_AVAILABLE
    use_fdr = "Naver" in engine or "자동" in engine
    
    if use_pykrx:
        try:
            df = stock.get_market_ohlcv_by_date(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
        except: pass
            
    if (df is None or df.empty) and use_fdr:
        try:
            df = fdr.DataReader(ticker, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
            if not df.empty:
                df = df.rename(columns={'Open': '시가', 'High': '고가', 'Low': '저가', 'Close': '종가', 'Volume': '거래량'})
        except: pass
            
    return df if df is not None else pd.DataFrame()

@st.cache_data(ttl=3600)
def get_investor_flow(ticker, base_date, days=20, engine="자동"):
    end = datetime.strptime(base_date, '%Y%m%d')
    start = end - timedelta(days=days * 2)
    
    use_pykrx = ("pykrx" in engine or "자동" in engine) and PYKRX_AVAILABLE
    use_fdr = "Naver" in engine or "자동" in engine
    
    if use_pykrx:
        try:
            df = stock.get_market_trading_value_by_date(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker)
            if not df.empty and ('기관합계' in df.columns or '외국인합계' in df.columns):
                return df.tail(days)
        except: pass
        
    if use_fdr:
        try:
            url = f'https://finance.naver.com/item/frgn.naver?code={ticker}'
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.encoding = 'euc-kr'
            dfs = pd.read_html(StringIO(r.text), encoding='euc-kr')
            
            df_target = None
            for df in dfs:
                if len(df.columns) >= 7:
                    dates = pd.to_datetime(df.iloc[:, 0], format='%Y.%m.%d', errors='coerce').dropna()
                    if len(dates) >= 10:
                        df_target = df.copy()
                        break
                        
            if df_target is None: return pd.DataFrame()
                
            dfclean = pd.DataFrame()
            dfclean['날짜'] = pd.to_datetime(df_target.iloc[:, 0], format='%Y.%m.%d', errors='coerce')
            dfclean['종가'] = pd.to_numeric(df_target.iloc[:, 1].astype(str).str.replace(',', ''), errors='coerce')
            dfclean['기관_순매매량'] = pd.to_numeric(df_target.iloc[:, 5].astype(str).str.replace(',', ''), errors='coerce')
            dfclean['외국인_순매매량'] = pd.to_numeric(df_target.iloc[:, 6].astype(str).str.replace(',', ''), errors='coerce')
            
            dfclean = dfclean.dropna(subset=['날짜'])
            dfclean['기관합계'] = dfclean['기관_순매매량'] * dfclean['종가']
            dfclean['외국인합계'] = dfclean['외국인_순매매량'] * dfclean['종가']
            dfclean['개인'] = -(dfclean['기관합계'] + dfclean['외국인합계'])
            dfclean = dfclean.set_index('날짜').sort_index()
            return dfclean.tail(days)
        except: pass
            
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def scan_hybrid_flow(min_mktcap=500, min_trading=10):
    try:
        import FinanceDataReader as fdr
        df_krx = fdr.StockListing('KRX')
        
        # KOSPI, KOSDAQ 종목만 필터링 (스팩, 리츠 등 제외 가능하지만 우선 시장으로 필터링)
        df = df_krx[df_krx['Market'].isin(['KOSPI', 'KOSDAQ', 'KOSPI200'])].copy()
        
        df['시가총액(억)'] = df['Marcap'] / 100000000
        df['거래대금(억)'] = df['Amount'] / 100000000
        
        # 필터링
        df = df[(df['시가총액(억)'] >= min_mktcap) & (df['거래대금(억)'] >= min_trading)].copy()
        
        if df.empty:
            return pd.DataFrame(), get_latest_valid_date()
            
        df['현재가'] = df['Close']
        df['등락률(%)'] = df['ChagesRatio']
        df['티커'] = df['Code']
        df['종목명'] = df['Name']
        
        # 수급점수 = (거래량 / 상장주식수) * abs(등락률) * 100
        df['수급점수'] = (df['Volume'] / df['Stocks'].replace(0, 1)) * df['등락률(%)'].abs() * 100
        df['수급점수'] = df['수급점수'].round(2)
        df['거래대금(억)'] = df['거래대금(억)'].round(1)
        
        df_result = df[['티커', '종목명', '현재가', '등락률(%)', '시가총액(억)', '거래대금(억)', '수급점수']].copy()
        df_result = df_result.sort_values('거래대금(억)', ascending=False).head(200)
        df_result.sort_values('수급점수', ascending=False, inplace=True)
        
        return df_result, get_latest_valid_date()
    except Exception as e:
        print("scan error:", e)
        return pd.DataFrame(), ""

@st.cache_data(ttl=1800)
def get_recent_news(ticker):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        news_list = []
        for li in soup.select('.news_section li'):
            a_tag = li.select_one('a')
            if a_tag:
                title = a_tag.text.strip()
                href = a_tag.get('href', '')
                link = f"https://finance.naver.com{href}" if href.startswith('/') else href
                if title and ticker in link:
                    news_list.append({"title": title, "link": link})
            if len(news_list) >= 5: break
        return news_list
    except:
        return []

@st.cache_data(ttl=86399)
def get_company_info(ticker):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        info = {
            "summary": "기업 개요 정보를 불러올 수 없습니다.",
            "per": "N/A",
            "pbr": "N/A",
            "dividend": "N/A"
        }
        
        # 기업 개요
        summary_div = soup.select_one('.summary_info p')
        if summary_div:
            info["summary"] = summary_div.text.strip()
            
        # 펀더멘털 지표
        for tr in soup.select('table.per_table tr'):
            text = tr.text
            if 'PER' in text and 'EPS' in text:
                em = tr.select_one('em#_per')
                if em: info["per"] = em.text
            elif 'PBR' in text and 'BPS' in text:
                em = tr.select_one('em#_pbr')
                if em: info["pbr"] = em.text
            elif '배당수익률' in text:
                em = tr.select_one('em#_dvr')
                if em: info["dividend"] = em.text + "%"
                
        return info
    except:
        return {}

@st.cache_data(ttl=86399)
def get_financial_trends(ticker):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        tables = soup.select('div.section.cop_analysis table')
        if not tables: return pd.DataFrame()
        
        df = pd.read_html(StringIO(str(tables[0])), encoding='utf-8')[0]
        
        # '주요재무정보'(항목명)와 '최근 연간 실적' 컬럼만 추출 (분기 실적 제외)
        cols_to_keep = [c for c in df.columns if c[0] in ['주요재무정보', '최근 연간 실적']]
        df = df[cols_to_keep].copy()
        
        try:
            df.columns = df.columns.droplevel([0, 2])
        except:
            df.columns = df.columns.get_level_values(1)
            
        # Unnamed 컬럼(빈 공간) 제거
        df = df.loc[:, ~df.columns.str.contains('Unnamed')]
        
        df.set_index(df.columns[0], inplace=True)
        df.index.name = '항목'
        
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3599)
def get_consensus_and_valuation(ticker):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        data = {
            'target_price': 'N/A', 'opinion': 'N/A', 'high52': 'N/A', 'low52': 'N/A',
            'foreign_ratio': 'N/A', 'market_cap': 'N/A', 'same_sector_per': 'N/A'
        }
        
        for tr in soup.find_all('tr'):
            text = tr.text
            if '목표주가' in text and '투자의견' in text:
                em = tr.select_one('em')
                if em: data['target_price'] = em.text.strip()
                span = tr.select_one('.f_up') or tr.select_one('.f_down') or tr.select_one('span')
                if span: data['opinion'] = span.text.strip()
            elif '52주최고' in text:
                tds = tr.select('td')
                if tds: 
                    hl = tds[0].text.strip().split('l')
                    if len(hl) >= 2:
                        data['high52'] = hl[0].strip()
                        data['low52'] = hl[1].strip()
            elif '외국인소진율' in text:
                td = tr.select_one('td')
                if td: data['foreign_ratio'] = td.text.strip()
            elif '동일업종 PER' in text:
                em = tr.select_one('em')
                if em: data['same_sector_per'] = em.text.strip() + "배"
            elif '시가총액' in text and data['market_cap'] == 'N/A':
                tds = tr.select('td')
                if tds: data['market_cap'] = tds[0].text.strip().replace('\n', ' ').replace('\t', '')
        return data
    except:
        return {}
@st.cache_data(ttl=1800)
def get_recent_disclosures(ticker):
    try:
        url = f"https://finance.naver.com/item/news_notice.naver?code={ticker}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')
        disclosures = []
        for tr in soup.select('table.type6 tr'):
            tds = tr.select('td')
            if len(tds) >= 3:
                a_tag = tds[0].select_one('a')
                if a_tag:
                    title = a_tag.text.strip()
                    date = tds[2].text.strip()
                    href = a_tag.get('href', '')
                    link = f"https://finance.naver.com{href}" if href.startswith('/') else href
                    if title:
                        disclosures.append({"title": title, "date": date, "link": link})
            if len(disclosures) >= 10: break
        return disclosures
    except:
        return []

@st.cache_data(ttl=3600)
def get_detailed_investor_flow(ticker, base_date):
    try:
        end = datetime.strptime(base_date, '%Y%m%d')
        start = end - timedelta(days=300)
        
        dfclean = pd.DataFrame()
        
        # Try KIS API First if available (Removed per user request)

        if dfclean.empty:
            if PYKRX_AVAILABLE:
                try:
                    df = stock.get_market_trading_value_by_date(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), ticker, detail=True)
                    if not df.empty and '개인' in df.columns:
                        dfclean = df.copy()
                except: pass
                
            if dfclean.empty:
                rows = []
                for page in range(1, 11):
                    url = f'https://finance.naver.com/item/frgn.naver?code={ticker}&page={page}'
                    r = requests.get(url, headers=HEADERS, timeout=5)
                    r.encoding = 'euc-kr'
                    dfs = pd.read_html(StringIO(r.text), encoding='euc-kr')
                    for d in dfs:
                        if len(d.columns) >= 7:
                            dates = pd.to_datetime(d.iloc[:, 0], format='%Y.%m.%d', errors='coerce').dropna()
                            if len(dates) >= 10:
                                for idx, row in d.iterrows():
                                    if pd.isna(pd.to_datetime(row.iloc[0], format='%Y.%m.%d', errors='coerce')): continue
                                    rows.append({
                                        '날짜': pd.to_datetime(row.iloc[0], format='%Y.%m.%d'),
                                        '종가': pd.to_numeric(str(row.iloc[1]).replace(',', ''), errors='coerce'),
                                        '기관_순매매량': pd.to_numeric(str(row.iloc[5]).replace(',', ''), errors='coerce'),
                                        '외국인_순매매량': pd.to_numeric(str(row.iloc[6]).replace(',', ''), errors='coerce'),
                                    })
                                break
                if rows:
                    dfclean = pd.DataFrame(rows).dropna(subset=['날짜']).set_index('날짜').sort_index()
                    dfclean['기관합계'] = dfclean['기관_순매매량'] * dfclean['종가']
                    dfclean['외국인합계'] = dfclean['외국인_순매매량'] * dfclean['종가']
                    dfclean['개인'] = -(dfclean['기관합계'] + dfclean['외국인합계'])

        if dfclean.empty: return pd.DataFrame()
        
        # We need cumulative sums
        dfclean['개인_누적'] = dfclean.get('개인', pd.Series(dtype=float)).cumsum()
        dfclean['외국인_누적'] = dfclean.get('외국인합계', dfclean.get('외국인', pd.Series(dtype=float))).cumsum()
        if '외국인' in dfclean.columns and '외국인합계' not in dfclean.columns: dfclean['외국인합계'] = dfclean['외국인']
        dfclean['기관_누적'] = dfclean.get('기관합계', pd.Series(dtype=float)).cumsum()
        if '연기금' in dfclean.columns: dfclean['연기금_누적'] = dfclean['연기금'].cumsum()
        
        return dfclean.tail(200)
    except Exception as e:
        print(f"Error in get_detailed_investor_flow: {e}")
        return pd.DataFrame()

# ==========================================
# ETF 전용 데이터 스크래핑 추가 (네이버 금융 기준)
# ==========================================

@st.cache_data(ttl=86400)
def check_is_etf(ticker):
    """주어진 티커가 ETF인지 판별합니다 (pykrx 활용)."""
    try:
        dt = get_latest_valid_date()
        from pykrx import stock
        etf_list = stock.get_etf_ticker_list(dt)
        return ticker in etf_list
    except:
        return False

@st.cache_data(ttl=3600)
def get_etf_basic_info(ticker):
    """ETF 기본 정보(NAV, 기초지수, 펀드보수, 상장일 등)를 추출합니다."""
    info = {
        'nav': 'N/A',
        'index': 'N/A',
        'fee': 'N/A',
        'listing_date': 'N/A',
        'manager': 'N/A',
        'dividend_yield': 'N/A'
    }
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.content, 'html.parser')
        
        for tr in soup.select('table tr'):
            th = tr.select_one('th')
            td = tr.select_one('td')
            if th and td:
                th_text = th.text.strip()
                td_text = td.text.strip().replace('\t', '').replace('\n', ' ')
                if th_text.startswith('기초지수'): info['index'] = td_text
                elif th_text.startswith('펀드보수'): info['fee'] = td_text.split()[0] if td_text else 'N/A'
                elif th_text.startswith('자산운용사'): info['manager'] = td_text
                elif th_text.startswith('상장일'): info['listing_date'] = td_text
                elif th_text.startswith('NAV'): info['nav'] = td_text

        try:
            co_url = f"https://finance.naver.com/item/coinfo.naver?code={ticker}"
            co_res = requests.get(co_url, headers=HEADERS, timeout=10)
            co_soup = BeautifulSoup(co_res.content, 'html.parser')
            for tr in co_soup.select('table tr'):
                if '배당수익률' in tr.text or '분배금' in tr.text:
                    em = tr.select_one('em')
                    if em: info['dividend_yield'] = em.text.strip() + '%'
        except:
            pass

        return info
    except:
        return info

@st.cache_data(ttl=3600)
def get_etf_holdings(ticker):
    """ETF 구성 종목(Top 10)을 가져옵니다."""
    holdings = []
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.content, 'html.parser')
        
        tables = soup.select('table')
        for t in tables:
            if '구성종목' in t.text or '구성자산' in t.text:
                for tr in t.select('tr')[1:]:
                    tds = tr.select('td')
                    if len(tds) >= 3:
                        name = tds[0].text.strip()
                        if name:
                            holdings.append({
                                'name': name,
                                'ratio': tds[2].text.strip()
                            })
                break
        return holdings[:10]
    except:
        return holdings
