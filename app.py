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

from utils.data_engine import scan_hybrid_flow

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

from utils.ui_components import render_detail_analysis
########################################
# 4. 종합 점수 계산 및 추천 순위
########################################

def compute_recommendation_score(row):
    """
    장세 맞춤형 추천 점수
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

def compute_trend_score(row):
    """
    추세추종 추천 점수
    - 추세 (정배열): 40%
    - RSI 타점 (50~70 강세구간): 30%
    - 수급점수 (돌파 모멘텀): 30%
    """
    score = 0.0
    
    # 1) 추세 (정배열 만점)
    score += (1.0 if '정배열' in str(row.get('추세', '')) else 0.0) * 40
    
    # 2) RSI 강세 구간 (50~70)
    rsi = row.get('RSI', 50)
    if 50 <= rsi <= 70:
        rsi_score = 1.0
    elif 70 < rsi <= 80:
        rsi_score = 0.7  # 약간 과매수지만 추세 이어질 가능성
    elif 40 <= rsi < 50:
        rsi_score = 0.5  # 막 상승 시작
    else:
        rsi_score = 0.1
    score += rsi_score * 30
    
    # 3) 수급 점수 (거래량 동반 상승)
    score += min(row.get('수급점수', 0) / 10.0, 1.0) * 30
    
    return round(score, 1)

########################################
# 6. Streamlit UI
########################################

st.title('🚀 스마트 수급 & 머니플로우 스캐너')
st.caption("FinanceDataReader × pykrx 하이브리드 엔진 | 거래량·모멘텀 기반 Smart Money 포착")

with st.expander("ℹ️ 사용 안내 (클릭하여 펼치기)"):
    st.markdown("""
    - **수급점수**: 거래량 회전율 × 등락률 절대값. 단기 자금 유입 강도를 나타냅니다.
    - **장세 맞춤형 추천**: 수급(40%) + 거래대금(20%) + RSI 타점(25%) + 이평선 추세(15%)
    - **추세 추종 추천**: 정배열(40%) + 강세RSI(30%) + 수급모멘텀(30%)
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

        def rank_label(i):
            labels = {1: '🥇', 2: '🥈', 3: '🥉'}
            return labels.get(i, f'{i}위')

        display_cols = ['순위', '종목명', '현재가', '등락률(%)', '시가총액(억)',
                        '거래대금(억)', '수급점수', '추세', 'RSI', '추천점수']

        # 장세 맞춤형
        top_stocks_market = top_stocks.copy()
        top_stocks_market['추천점수'] = top_stocks_market.apply(compute_recommendation_score, axis=1)
        top_stocks_market.sort_values('추천점수', ascending=False, inplace=True)
        top_stocks_market.reset_index(drop=True, inplace=True)
        top_stocks_market.index += 1
        top_stocks_market.insert(0, '순위', [rank_label(i) for i in top_stocks_market.index])

        # 추세 추종형
        top_stocks_trend = top_stocks.copy()
        top_stocks_trend['추천점수'] = top_stocks_trend.apply(compute_trend_score, axis=1)
        top_stocks_trend.sort_values('추천점수', ascending=False, inplace=True)
        top_stocks_trend.reset_index(drop=True, inplace=True)
        top_stocks_trend.index += 1
        top_stocks_trend.insert(0, '순위', [rank_label(i) for i in top_stocks_trend.index])

        tab1, tab2 = st.tabs(["🌟 장세 맞춤형 추천", "📈 추세 추종 추천"])
        import io

        with tab1:
            col_title, col_btn = st.columns([7, 3])
            with col_title:
                st.subheader("📋 장세 맞춤형 추천 순위")
            with col_btn:
                excel_buffer1 = io.BytesIO()
                try:
                    with pd.ExcelWriter(excel_buffer1, engine='openpyxl') as writer:
                        top_stocks_market[display_cols].to_excel(writer, index=False, sheet_name='장세맞춤형')
                    st.download_button(
                        label="📥 엑셀(Excel) 다운로드",
                        data=excel_buffer1.getvalue(),
                        file_name=f"스마트_수급_장세맞춤형_{base_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="btn_market"
                    )
                except Exception as e:
                    csv_data1 = top_stocks_market[display_cols].to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 엑셀(CSV) 다운로드",
                        data=csv_data1,
                        file_name=f"스마트_수급_장세맞춤형_{base_date}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="btn_market_csv"
                    )

            event_market = st.dataframe(
                top_stocks_market[display_cols].set_index('순위'),
                use_container_width=True,
                height=400,
                on_select="rerun",
                selection_mode="single-row",
                key="df_market"
            )

        with tab2:
            col_title, col_btn = st.columns([7, 3])
            with col_title:
                st.subheader("📋 추세 추종 추천 순위")
            with col_btn:
                excel_buffer2 = io.BytesIO()
                try:
                    with pd.ExcelWriter(excel_buffer2, engine='openpyxl') as writer:
                        top_stocks_trend[display_cols].to_excel(writer, index=False, sheet_name='추세추종')
                    st.download_button(
                        label="📥 엑셀(Excel) 다운로드",
                        data=excel_buffer2.getvalue(),
                        file_name=f"스마트_수급_추세추종_{base_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="btn_trend"
                    )
                except Exception as e:
                    csv_data2 = top_stocks_trend[display_cols].to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 엑셀(CSV) 다운로드",
                        data=csv_data2,
                        file_name=f"스마트_수급_추세추종_{base_date}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="btn_trend_csv"
                    )

            event_trend = st.dataframe(
                top_stocks_trend[display_cols].set_index('순위'),
                use_container_width=True,
                height=400,
                on_select="rerun",
                selection_mode="single-row",
                key="df_trend"
            )

        # ── 차트 섹션 (session_state으로 선택 유지) ──
        st.markdown("---")
        st.subheader("📊 종목 정밀 차트")

        selected_ticker = None
        selected_name = None

        if event_market.selection and event_market.selection.rows:
            row_idx = event_market.selection.rows[0]
            selected_row = top_stocks_market.iloc[row_idx]
            selected_ticker = selected_row['티커']
            selected_name = selected_row['종목명']
        elif event_trend.selection and event_trend.selection.rows:
            row_idx = event_trend.selection.rows[0]
            selected_row = top_stocks_trend.iloc[row_idx]
            selected_ticker = selected_row['티커']
            selected_name = selected_row['종목명']

        if selected_ticker and selected_name:
            render_detail_analysis(selected_ticker, selected_name, base_date, '자동')
        else:
            st.info("👆 위 추천 순위 표에서 확인하고 싶은 종목의 행(체크박스)을 클릭하시면 상세 분석이 표시됩니다.")
