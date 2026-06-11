import streamlit as st
import pandas as pd
from utils.data_engine import scan_hybrid_flow, load_ohlcv
from utils.indicators import analyze_technical, compute_recommendation_score
from utils.ui_components import render_detail_analysis

st.set_page_config(page_title="프리미엄 스캐너", page_icon="🎯", layout="wide")

st.title("🎯 프리미엄 수급 및 모멘텀 스캐너")
st.markdown("수급 회전율, 거래대금, RSI 및 이평선 추세를 복합 분석하여 급등 확률이 높은 종목을 포착합니다.")

c1, c2 = st.columns(2)
with c1: min_cap = st.number_input('최소 시가총액 (억 단위)', value=1000, step=100)
with c2: min_trade = st.number_input('최소 거래대금 (억 단위)', value=20, step=10)

if 'scan_result' not in st.session_state:
    st.session_state.scan_result = None
    st.session_state.scan_base_date = ""

@st.dialog("🔍 종목 상세 분석 리포트", width="large")
def show_detail_popup(ticker, ticker_name, base_date, engine):
    st.markdown(f"### {ticker_name} ({ticker}) 심층 분석")
    render_detail_analysis(ticker, ticker_name, base_date, engine)

if st.button('🚀 스캐너 가동', type="primary"):
    with st.spinner('시장 전체 종목 스캔 중... (수 분 소요될 수 있습니다)'):
        engine = st.session_state.get('data_engine', '자동')
        result, base_date = scan_hybrid_flow(min_mktcap=min_cap, min_trading=min_trade)
        
        if result.empty:
            st.warning("조건을 만족하는 종목이 없습니다.")
            st.session_state.scan_result = None
        else:
            st.success(f"✅ {base_date} 기준 데이터 스캔 완료!")
            top_stocks = result.head(30).copy().reset_index(drop=True)
            
            trends, rsis = [], []
            my_bar = st.progress(0)
            
            for i, ticker in enumerate(top_stocks['티커']):
                df = load_ohlcv(ticker, base_date, 100, engine)
                tech = analyze_technical(df)
                if tech:
                    trends.append(tech['추세'])
                    rsis.append(tech['RSI'])
                else:
                    trends.append("데이터 부족")
                    rsis.append(50.0)
                my_bar.progress((i + 1) / len(top_stocks))
                
            my_bar.empty()
            
            top_stocks['추세'] = trends
            top_stocks['RSI'] = rsis
            top_stocks['거래대금_rank'] = top_stocks['거래대금(억)'].rank(pct=True)
            top_stocks['추천점수'] = top_stocks.apply(compute_recommendation_score, axis=1)
            top_stocks.sort_values('추천점수', ascending=False, inplace=True)
            top_stocks.reset_index(drop=True, inplace=True)
            top_stocks.index += 1
            
            def rank_label(i): return {1: '🥇', 2: '🥈', 3: '🥉'}.get(i, f'{i}위')
            if '순위' in top_stocks.columns:
                top_stocks.drop(columns=['순위'], inplace=True)
            top_stocks.insert(0, '순위', [rank_label(i) for i in top_stocks.index])
            
            st.session_state.scan_result = top_stocks
            st.session_state.scan_base_date = base_date

if st.session_state.scan_result is not None:
    top_stocks = st.session_state.scan_result
    base_date = st.session_state.scan_base_date
    
    display_cols = ['순위', '종목명', '현재가', '등락률(%)', '시가총액(억)', '거래대금(억)', '수급점수', '추세', 'RSI', '추천점수']
    event = st.dataframe(top_stocks[display_cols].set_index('순위'), use_container_width=True, height=500, on_select="rerun", selection_mode="single-row")
    
    st.markdown("---")
    st.subheader("🔍 선택 종목 팝업 상세 분석")
    st.info("👆 위 스캐너 결과 표에서 원하는 종목의 행을 클릭하시면 전문가의 팝업 상세 분석 리포트가 열립니다!")
    
    if len(event.selection.rows) > 0:
        row_idx = event.selection.rows[0]
        ticker = top_stocks.iloc[row_idx]['티커']
        selected_stock = top_stocks.iloc[row_idx]['종목명']
        engine = st.session_state.get('data_engine', '자동')
        show_detail_popup(ticker, selected_stock, base_date, engine)
