import pandas as pd
import numpy as np
import streamlit as st

@st.cache_data
def analyze_technical(df):
    """
    주어진 OHLCV DataFrame을 기반으로 기술적 지표를 계산합니다.
    """
    if df is None or df.empty or len(df) < 60: 
        return None
        
    result = {}
    close = df['종가']
    volume = df.get('거래량', pd.Series())
    
    # 이동평균선
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    ma120 = close.rolling(120).mean() if len(df) >= 120 else close.rolling(len(df)).mean()
    
    cur = close.iloc[-1]
    cur_ma5 = ma5.iloc[-1]
    cur_ma20 = ma20.iloc[-1]
    cur_ma60 = ma60.iloc[-1]
    
    # RSI
    delta = close.diff()
    up, down = delta.clip(lower=0), (-delta).clip(lower=0)
    rs = up.ewm(com=13, adjust=False).mean() / down.ewm(com=13, adjust=False).mean()
    rsi = 100 - (100 / (1 + rs))
    
    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal
    
    # 트렌드 판별
    trend = "혼조세"
    if cur > cur_ma20 and cur_ma20 > cur_ma60: trend = "🔥 정배열"
    elif cur < cur_ma20 and cur_ma20 < cur_ma60: trend = "❄️ 역배열"
    
    result['현재가'] = cur
    result['추세'] = trend
    result['RSI'] = float(rsi.iloc[-1])
    result['MACD_Hist'] = float(macd_hist.iloc[-1])
    result['MA20이격도'] = (cur / cur_ma20) * 100
    
    return result

def compute_recommendation_score(row):
    """스캐너 데이터프레임의 행별 추천 점수 계산"""
    score = 0.0
    score += min(row.get('수급점수', 0) / 10.0, 1.0) * 40
    score += row.get('거래대금_rank', 0) * 20
    rsi = row.get('RSI', 50)
    if 40 <= rsi <= 60: rsi_score = 1.0
    elif 30 <= rsi < 40 or 60 < rsi <= 70: rsi_score = 0.6
    elif rsi < 30: rsi_score = 0.4
    else: rsi_score = 0.1
    score += rsi_score * 25
    score += (1.0 if '정배열' in str(row.get('추세', '')) else 0.0) * 15
    return round(score, 1)
