import threading
import time
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import FinanceDataReader as fdr

# ──────────────────────────────────────────
# Streamlit 페이지 설정
# ──────────────────────────────────────────
st.set_page_config(page_title="마켓 타이밍 & 추천", page_icon="📈", layout="wide")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>", unsafe_allow_html=True)

########################################
# 0. 유틸리티
########################################

@st.cache_data(ttl=600)
def get_latest_valid_date():
    """삼성전자 OHLCV 기준으로 가장 최근 유효 거래일을 반환합니다."""
    try:
        now = datetime.now()
        df = fdr.DataReader("005930",
                            (now - timedelta(days=10)).strftime('%Y-%m-%d'),
                            now.strftime('%Y-%m-%d'))
        if not df.empty:
            return df.index[-1].strftime('%Y%m%d')
    except:
        pass
    return (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

########################################
# 1. 데이터 수집 (FDR 기반)
########################################

@st.cache_data(ttl=3600)
def scan_hybrid_flow(min_mktcap=2000, min_trading=5):
    """FDR에서 전 종목 리스트를 받아 시가총액/거래대금으로 1차 필터링합니다."""
    try:
        df_krx = fdr.StockListing('KRX')
        df_krx['시가총액(억)'] = df_krx['Marcap'] / 1e8
        df_krx['거래대금(억)'] = df_krx['Amount'] / 1e8

        target_df = df_krx[
            (df_krx['시가총액(억)'] >= min_mktcap) &
            (df_krx['거래대금(억)'] >= min_trading)
        ].copy()

        # 거래대금 상위 200개로 압축 (성능)
        target_df = target_df.sort_values('거래대금(억)', ascending=False).head(200)

        rows = []
        progress_text = st.empty()
        bar = st.progress(0)
        total = len(target_df)

        for i, (_, row) in enumerate(target_df.iterrows()):
            try:
                if i % 5 == 0:
                    progress_text.text(f"스마트 스캔 중... ({i}/{total})")
                    bar.progress(i / total)

                volume_ratio = row['Volume'] / (row['Stocks'] * 0.001) if row['Stocks'] > 0 else 0
                rows.append({
                    '티커':         row['Code'],
                    '종목명':       row['Name'],
                    '현재가':       int(row['Close']),
                    '등락률(%)':    round(row['ChagesRatio'], 2),
                    '시가총액(억)': round(row['시가총액(억)']),
                    '거래대금(억)': round(row['거래대금(억)'], 1),
                    '수급점수':     round(volume_ratio * abs(row['ChagesRatio']), 2),
                })
            except:
                continue

        progress_text.empty()
        bar.empty()

        df_result = pd.DataFrame(rows)
        if not df_result.empty:
            df_result.sort_values('수급점수', ascending=False, inplace=True)
        return df_result, get_latest_valid_date()
    except Exception as e:
        st.error(f"데이터 스캔 중 오류: {e}")
        return pd.DataFrame(), ""

########################################
# 2. 기술적 지표 – RSI, 이평선 (pykrx)
########################################

@st.cache_data
def analyze_technical(ticker, base_date):
    """종목별 RSI(14) 및 이평선 배열을 반환합니다."""
    try:
        end   = datetime.strptime(base_date, '%Y%m%d')
        start = end - timedelta(days=400)   # 120일 이평선까지 필요
        df = fdr.DataReader(ticker, start, end)
        if not df.empty:
            df.rename(columns={'Open':'시가', 'High':'고가', 'Low':'저가', 'Close':'종가', 'Volume':'거래량'}, inplace=True)

        if df.empty or len(df) < 60:
            return '데이터부족', 0

        close = df['종가']
        df['MA5']  = close.rolling(5).mean()
        df['MA20'] = close.rolling(20).mean()
        df['MA60'] = close.rolling(60).mean()
        df['MA120']= close.rolling(120).mean()

        # RSI-14
        delta = close.diff()
        up   = delta.clip(lower=0)
        down = (-delta).clip(lower=0)
        rs   = up.ewm(com=13, adjust=False).mean() / down.ewm(com=13, adjust=False).mean()
        rsi  = 100 - (100 / (1 + rs))

        trend = '🔥정배열' if df['MA20'].iloc[-1] > df['MA60'].iloc[-1] else '❄️역배열'
        return trend, round(float(rsi.iloc[-1]), 1)
    except:
        return '오류', 0

from utils.data_engine import get_detailed_investor_flow
from utils.ui_components import render_detail_analysis
########################################
# 4. 종합 점수 계산 및 추천 순위
########################################

def compute_recommendation_score(row):
    """
    각 지표를 0~100점으로 정규화하여 가중 합산합니다.
    - 수급점수  : 40%  (거래량 회전율 × 등락률)
    - 거래대금  : 20%  (상위일수록 높은 점수)
    - RSI 타점  : 25%  (40~60 구간에서 최고 점수, 70이상/30이하 감점)
    - 추세(정배열): 15%
    """
    score = 0.0

    # 1) 수급 점수 – 이미 정규화된 값이므로 그대로 사용 (최대 클램프)
    score += min(row.get('수급점수', 0) / 10.0, 1.0) * 40

    # 2) 거래대금 – 비교군에서 상대 순위로 처리 (호출 시 이미 rank 열 존재)
    score += row.get('거래대금_rank', 0) * 20

    # 3) RSI 타점 (40~60 구간 = 만점)
    rsi = row.get('RSI', 50)
    if 40 <= rsi <= 60:
        rsi_score = 1.0
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        rsi_score = 0.6
    elif rsi < 30:
        rsi_score = 0.4   # 과매도 – 반등 기대 가능
    else:  # > 70
        rsi_score = 0.1   # 과매수 – 고점 위험
    score += rsi_score * 25

    # 4) 추세 (정배열이면 만점)
    score += (1.0 if '정배열' in str(row.get('추세', '')) else 0.0) * 15

    return round(score, 1)


########################################
# 6. Streamlit UI
########################################

st.title('🚀 스마트 수급 & 머니플로우 스캐너')
st.caption("FinanceDataReader × pykrx 하이브리드 엔진 | 거래량·모멘텀 기반 Smart Money 포착")

with st.expander("ℹ️ 사용 안내 (클릭하여 펼치기)"):
    st.markdown("""
    - **수급점수**: 거래량 회전율 × 등락률 절대값. 단기 자금 유입 강도를 나타냅니다.
    - **추천점수**: 수급(40%) + 거래대금(20%) + RSI 타점(25%) + 이평선 추세(15%) 종합 평가
    - **RSI 해석**: 30 이하 = 과매도(저점 반등 기대), 70 이상 = 과매수(추격 주의)
    - **KRX 서버 제한**: 장 시작 전은 전일 기준 데이터로 자동 분석합니다.
    """)

col1, col2 = st.columns(2)
with col1:
    min_cap   = st.number_input('최소 시가총액 (억 단위)', value=500, step=100, min_value=1)
with col2:
    min_trade = st.number_input('최소 거래대금 (억 단위)', value=10, step=10, min_value=1)

# ── 세션 스테이트: 차트 선택이 바뀌어도 결과 테이블 유지 ──
if 'scan_result' not in st.session_state:
    st.session_state.scan_result   = None
    st.session_state.scan_base_date = ''

if st.button('🎯 유망 종목 포착하기'):
    with st.spinner('FDR 하이브리드 엔진 가동 중...'):
        result, base_date = scan_hybrid_flow(min_mktcap=min_cap, min_trading=min_trade)
        # 결과를 세션 스테이트에 저장 → 종목 선택 변경 시 재스캔 없음
        st.session_state.scan_result    = result
        st.session_state.scan_base_date = base_date

# ── 결과 표시 ──
if st.session_state.scan_result is not None:
    result    = st.session_state.scan_result
    base_date = st.session_state.scan_base_date

    if result.empty:
        st.warning("조건을 만족하는 종목이 없습니다. 기준을 낮춰보세요.")
    else:
        today_str = datetime.now().strftime('%Y%m%d')
        if base_date != today_str:
            st.info(f"💡 장 시작 전 또는 공휴일 — **{base_date[:4]}-{base_date[4:6]}-{base_date[6:]}** 기준 데이터입니다.")
        else:
            st.success(f"✅ {base_date[:4]}-{base_date[4:6]}-{base_date[6:]} 실시간 데이터 스캔 완료!")

        # ── 기술적 지표 계산 ──
        top_stocks = result.head(30).copy().reset_index(drop=True)
        trends, rsis = [], []
        with st.spinner("기술적 지표 계산 중..."):
            for t in top_stocks['티커']:
                tr, rs = analyze_technical(t, base_date)
                trends.append(tr)
                rsis.append(rs)

        top_stocks['추세'] = trends
        top_stocks['RSI']  = rsis

        # 거래대금 상대 순위(0~1)
        top_stocks['거래대금_rank'] = top_stocks['거래대금(억)'].rank(pct=True)

        # 종합 추천 점수
        top_stocks['추천점수'] = top_stocks.apply(compute_recommendation_score, axis=1)
        top_stocks.sort_values('추천점수', ascending=False, inplace=True)
        top_stocks.reset_index(drop=True, inplace=True)
        top_stocks.index += 1  # 1위부터 시작

        # 순위 꾸미기
        def rank_label(i):
            labels = {1: '🥇', 2: '🥈', 3: '🥉'}
            return labels.get(i, f'{i}위')

        if '순위' in top_stocks.columns:
            top_stocks.drop(columns=['순위'], inplace=True)
        top_stocks.insert(0, '순위', [rank_label(i) for i in top_stocks.index])

        display_cols = ['순위', '종목명', '현재가', '등락률(%)', '시가총액(억)',
                        '거래대금(억)', '수급점수', '추세', 'RSI', '추천점수']

        st.subheader("📋 종합 추천 순위")
        event = st.dataframe(
            top_stocks[display_cols].set_index('순위'),
            use_container_width=True,
            height=400,
            on_select="rerun",
            selection_mode="single-row"
        )
        total = len(target_df)

        for i, (_, row) in enumerate(target_df.iterrows()):
            try:
                if i % 5 == 0:
                    progress_text.text(f"스마트 스캔 중... ({i}/{total})")
                    bar.progress(i / total)

                volume_ratio = row['Volume'] / (row['Stocks'] * 0.001) if row['Stocks'] > 0 else 0
                rows.append({
                    '티커':         row['Code'],
                    '종목명':       row['Name'],
                    '현재가':       int(row['Close']),
                    '등락률(%)':    round(row['ChagesRatio'], 2),
                    '시가총액(억)': round(row['시가총액(억)']),
                    '거래대금(억)': round(row['거래대금(억)'], 1),
                    '수급점수':     round(volume_ratio * abs(row['ChagesRatio']), 2),
                })
            except:
                continue

        progress_text.empty()
        bar.empty()

        df_result = pd.DataFrame(rows)
        if not df_result.empty:
            df_result.sort_values('수급점수', ascending=False, inplace=True)
        return df_result, get_latest_valid_date()
    except Exception as e:
        st.error(f"데이터 스캔 중 오류: {e}")
        return pd.DataFrame(), ""

########################################
# 2. 기술적 지표 – RSI, 이평선 (pykrx)
########################################

@st.cache_data
def analyze_technical(ticker, base_date):
    """종목별 RSI(14) 및 이평선 배열을 반환합니다."""
    try:
        end   = datetime.strptime(base_date, '%Y%m%d')
        start = end - timedelta(days=400)   # 120일 이평선까지 필요
        df = fdr.DataReader(ticker, start, end)
        if not df.empty:
            df.rename(columns={'Open':'시가', 'High':'고가', 'Low':'저가', 'Close':'종가', 'Volume':'거래량'}, inplace=True)

        if df.empty or len(df) < 60:
            return '데이터부족', 0

        close = df['종가']
        df['MA5']  = close.rolling(5).mean()
        df['MA20'] = close.rolling(20).mean()
        df['MA60'] = close.rolling(60).mean()
        df['MA120']= close.rolling(120).mean()

        # RSI-14
        delta = close.diff()
        up   = delta.clip(lower=0)
        down = (-delta).clip(lower=0)
        rs   = up.ewm(com=13, adjust=False).mean() / down.ewm(com=13, adjust=False).mean()
        rsi  = 100 - (100 / (1 + rs))

        trend = '🔥정배열' if df['MA20'].iloc[-1] > df['MA60'].iloc[-1] else '❄️역배열'
        return trend, round(float(rsi.iloc[-1]), 1)
    except:
        return '오류', 0

from utils.data_engine import get_detailed_investor_flow
from utils.ui_components import render_detail_analysis
########################################
# 4. 종합 점수 계산 및 추천 순위
########################################

def compute_recommendation_score(row):
    """
    각 지표를 0~100점으로 정규화하여 가중 합산합니다.
    - 수급점수  : 40%  (거래량 회전율 × 등락률)
    - 거래대금  : 20%  (상위일수록 높은 점수)
    - RSI 타점  : 25%  (40~60 구간에서 최고 점수, 70이상/30이하 감점)
    - 추세(정배열): 15%
    """
    score = 0.0

    # 1) 수급 점수 – 이미 정규화된 값이므로 그대로 사용 (최대 클램프)
    score += min(row.get('수급점수', 0) / 10.0, 1.0) * 40

    # 2) 거래대금 – 비교군에서 상대 순위로 처리 (호출 시 이미 rank 열 존재)
    score += row.get('거래대금_rank', 0) * 20

    # 3) RSI 타점 (40~60 구간 = 만점)
    rsi = row.get('RSI', 50)
    if 40 <= rsi <= 60:
        rsi_score = 1.0
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        rsi_score = 0.6
    elif rsi < 30:
        rsi_score = 0.4   # 과매도 – 반등 기대 가능
    else:  # > 70
        rsi_score = 0.1   # 과매수 – 고점 위험
    score += rsi_score * 25

    # 4) 추세 (정배열이면 만점)
    score += (1.0 if '정배열' in str(row.get('추세', '')) else 0.0) * 15

    return round(score, 1)


########################################
# 6. Streamlit UI
########################################

st.title('🚀 스마트 수급 & 머니플로우 스캐너')
st.caption("FinanceDataReader × pykrx 하이브리드 엔진 | 거래량·모멘텀 기반 Smart Money 포착")

with st.expander("ℹ️ 사용 안내 (클릭하여 펼치기)"):
    st.markdown("""
    - **수급점수**: 거래량 회전율 × 등락률 절대값. 단기 자금 유입 강도를 나타냅니다.
    - **추천점수**: 수급(40%) + 거래대금(20%) + RSI 타점(25%) + 이평선 추세(15%) 종합 평가
    - **RSI 해석**: 30 이하 = 과매도(저점 반등 기대), 70 이상 = 과매수(추격 주의)
    - **KRX 서버 제한**: 장 시작 전은 전일 기준 데이터로 자동 분석합니다.
    """)

col1, col2 = st.columns(2)
with col1:
    min_cap   = st.number_input('최소 시가총액 (억 단위)', value=500, step=100, min_value=1)
with col2:
    min_trade = st.number_input('최소 거래대금 (억 단위)', value=10, step=10, min_value=1)

# ── 세션 스테이트: 차트 선택이 바뀌어도 결과 테이블 유지 ──
if 'scan_result' not in st.session_state:
    st.session_state.scan_result   = None
    st.session_state.scan_base_date = ''

if st.button('🎯 유망 종목 포착하기'):
    with st.spinner('FDR 하이브리드 엔진 가동 중...'):
        result, base_date = scan_hybrid_flow(min_mktcap=min_cap, min_trading=min_trade)
        # 결과를 세션 스테이트에 저장 → 종목 선택 변경 시 재스캔 없음
        st.session_state.scan_result    = result
        st.session_state.scan_base_date = base_date

# ── 결과 표시 ──
if st.session_state.scan_result is not None:
    result    = st.session_state.scan_result
    base_date = st.session_state.scan_base_date

    if result.empty:
        st.warning("조건을 만족하는 종목이 없습니다. 기준을 낮춰보세요.")
    else:
        today_str = datetime.now().strftime('%Y%m%d')
        if base_date != today_str:
            st.info(f"💡 장 시작 전 또는 공휴일 — **{base_date[:4]}-{base_date[4:6]}-{base_date[6:]}** 기준 데이터입니다.")
        else:
            st.success(f"✅ {base_date[:4]}-{base_date[4:6]}-{base_date[6:]} 실시간 데이터 스캔 완료!")

        # ── 기술적 지표 계산 ──
        top_stocks = result.head(30).copy().reset_index(drop=True)
        trends, rsis = [], []
        with st.spinner("기술적 지표 계산 중..."):
            for t in top_stocks['티커']:
                tr, rs = analyze_technical(t, base_date)
                trends.append(tr)
                rsis.append(rs)

        top_stocks['추세'] = trends
        top_stocks['RSI']  = rsis

        # 거래대금 상대 순위(0~1)
        top_stocks['거래대금_rank'] = top_stocks['거래대금(억)'].rank(pct=True)

        # 종합 추천 점수
        top_stocks['추천점수'] = top_stocks.apply(compute_recommendation_score, axis=1)
        top_stocks.sort_values('추천점수', ascending=False, inplace=True)
        top_stocks.reset_index(drop=True, inplace=True)
        top_stocks.index += 1  # 1위부터 시작

        # 순위 꾸미기
        def rank_label(i):
            labels = {1: '🥇', 2: '🥈', 3: '🥉'}
            return labels.get(i, f'{i}위')

        if '순위' in top_stocks.columns:
            top_stocks.drop(columns=['순위'], inplace=True)
        top_stocks.insert(0, '순위', [rank_label(i) for i in top_stocks.index])

        display_cols = ['순위', '종목명', '현재가', '등락률(%)', '시가총액(억)',
                        '거래대금(억)', '수급점수', '추세', 'RSI', '추천점수']

        st.subheader("📋 종합 추천 순위")
        event = st.dataframe(
            top_stocks[display_cols].set_index('순위'),
            use_container_width=True,
            height=400,
            on_select="rerun",
            selection_mode="single-row"
        )

        # ── 차트 섹션 (session_state으로 선택 유지) ──
        st.markdown("---")
        st.subheader("📊 종목 정밀 차트")

        if event.selection and event.selection.rows:
            row_idx = event.selection.rows[0]
            selected_row = top_stocks.iloc[row_idx]
            selected_name = selected_row['종목명']
            selected_ticker = selected_row['티커']
            render_detail_analysis(selected_ticker, selected_name, base_date, '자동')
        else:
            st.info("👆 위 종합 추천 순위 표에서 확인하고 싶은 종목의 행(체크박스)을 클릭하시면 상세 분석이 표시됩니다.")
