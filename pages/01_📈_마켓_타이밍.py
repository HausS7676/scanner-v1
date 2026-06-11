import streamlit as st
import plotly.graph_objects as go
from utils.data_engine import get_exchange_rate, get_us_treasury, get_kospi_series, get_market_flow

st.set_page_config(page_title="마켓 타이밍", page_icon="📈", layout="wide")


st.markdown("""
<style>
.card {
    background: rgba(30, 41, 59, 0.7); 
    border: 1px solid rgba(56, 189, 248, 0.2);
    border-radius: 1rem; 
    padding: 1.5rem; 
    margin-bottom: 1rem;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
}
.card-title { font-size: 1.2rem; font-weight: 700; color: #38bdf8; margin-bottom: 0.5rem; }
.card-value { font-size: 2rem; font-weight: 900; color: #f8fafc; }
.text-bull { color: #10b981 !important; }
.text-bear { color: #ef4444 !important; }
.text-neutral { color: #f59e0b !important; }
</style>
""", unsafe_allow_html=True)

st.title("🧭 마켓 타이밍 및 시황 분석")

def render_market_timing():
    with st.spinner("시장 데이터 분석 중..."):
        usd = get_exchange_rate()
        ust = get_us_treasury()
        kdf = get_kospi_series()
        flow = get_market_flow()
        
        score = 0
        
        macro_score = 0
        if usd < 1320: macro_score += 15
        elif usd < 1370: macro_score += 10
        elif usd < 1400: macro_score += 5
        if ust < 4.0: macro_score += 15
        elif ust < 4.4: macro_score += 10
        elif ust < 4.6: macro_score += 5
        score += macro_score
        
        tech_score = 0
        k_status = "데이터 없음"
        k_curr = 0
        if not kdf.empty:
            curr = kdf["Close"].iloc[-1]
            ma20 = kdf["MA20"].iloc[-1]
            ma60 = kdf["MA60"].iloc[-1]
            k_curr = curr
            if curr > ma20: tech_score += 15
            if ma20 > ma60: tech_score += 15
            if curr > ma20 and ma20 > ma60: k_status = "정배열 상승추세"
            elif curr < ma20 and ma20 < ma60: k_status = "역배열 하락추세"
            else: k_status = "혼조세"
        score += tech_score
        
        score += flow.get("score", 0)
        
        # 동적 상세 분석 이유 생성
        reasons = []
        if usd < 1320: reasons.append("✅ **환율 안정적:** 환율이 1320원 미만으로 외국인 자금 유입에 매우 유리합니다.")
        elif usd < 1370: reasons.append("⚠️ **환율 주의:** 환율이 1320~1370원 사이로 다소 주의가 필요합니다.")
        elif usd < 1400: reasons.append("🚨 **환율 위험:** 환율이 1370원 이상으로 높아 자금 이탈 우려가 있습니다.")
        else: reasons.append("🚨 **환율 초위험:** 환율이 1400원을 넘어 시장에 매우 큰 부담을 줍니다.")
        
        if ust < 4.0: reasons.append("✅ **금리 안정적:** 미국채 10년물 금리가 4.0% 미만으로 증시에 긍정적입니다.")
        elif ust < 4.4: reasons.append("⚠️ **금리 주의:** 미국채 금리가 4.0~4.4% 사이로 평이한 수준입니다.")
        else: reasons.append("🚨 **금리 위험:** 미국채 금리가 4.4% 이상으로 주식 시장 자금 조달에 부담이 됩니다.")
        
        if k_status == "정배열 상승추세": reasons.append("✅ **추세 상승:** KOSPI가 20일선 및 60일선 위에 있어 강력한 상승 추세입니다.")
        elif k_status == "역배열 하락추세": reasons.append("🚨 **추세 하락:** KOSPI가 역배열 상태로 하락장이 지속되고 있습니다.")
        elif k_curr > ma20: reasons.append("✅ **추세 반등:** KOSPI가 단기 20일선을 회복하여 반등을 모색 중입니다.")
        else: reasons.append("⚠️ **추세 관망:** KOSPI가 단기 20일선 아래에 위치하여 관망이 필요합니다.")
        
        if flow.get("price_up") and flow.get("vol_ratio", 0) > 1.1:
            reasons.append("✅ **수급 양호:** 시장 대표 ETF에 거래량이 실린 강한 매수세가 확인되었습니다.")
        elif flow.get("price_up"):
            reasons.append("⚠️ **수급 보통:** 시장 대표 ETF가 우상향 중이나 추가적인 거래량 유입이 필요합니다.")
        else:
            reasons.append("🚨 **수급 악화:** 시장 전체적으로 매수세가 부족하며 매도 관망 심리가 우세합니다.")
        
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if score >= 70: color, status = "text-bull", "매수 적극 권장 (강세장)"
        elif score >= 40: color, status = "text-neutral", "비중 조절 / 관망 (중립)"
        else: color, status = "text-bear", "매수 보류 / 현금 확보 (약세장)"
        
        st.markdown(f"""
        <div class="card" style="text-align:center;">
            <div class="card-title">현재 시장 진입(매수) 점수</div>
            <div style="font-size: 4rem; font-weight: 900;" class="{color}">{score}점</div>
            <div style="font-size: 1.5rem; font-weight: 700;" class="{color}">{status}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with st.expander("💡 시장 진입(매수) 점수는 어떻게 계산되나요?"):
        st.markdown("""
        **시장 진입(매수) 점수**는 총 100점 만점으로, 현재 주식 시장에 신규 자금을 투입하기 얼마나 좋은 시기인지를 나타내는 종합 지표입니다.
        
        * **🌐 거시경제 지표 (최대 30점)** 
          * 달러/원 환율이 낮을수록 (1320원 미만 시 최고점)
          * 미국채 10년물 금리가 안정적일수록 (4.0% 미만 시 최고점)
          * 👉 **이유:** 환율과 금리가 낮아야 외국인 투자 자금이 국내 증시로 강하게 유입됩니다.
          
        * **📈 KOSPI 기술적 추세 (최대 30점)** 
          * 현재 KOSPI 지수가 20일 이동평균선 위에 위치 (15점)
          * 단기(20일) 이평선이 장기(60일) 이평선 위에 있는 정배열 상태 (15점)
          * 👉 **이유:** 추세가 하락장(역배열)일 때 바닥을 잡으려 하기보다는, 확실한 상승 추세에 올라타는 것이 안전합니다.
          
        * **💰 수급 및 거래량 모멘텀 (최대 40점)** 
          * 시장 전체(KODEX 200 기준)의 단기 가격 추세가 우상향 중일 때 (20점)
          * 이전 평균 대비 거래량이 유의미하게 급증했을 때 (20점)
          * 👉 **이유:** 거래량이 실린 상승은 스마트 머니(기관/외국인 등 큰손)의 본격적인 시장 개입을 의미합니다.
          
        > **[ 결과 해석 ]**
        > - **70점 이상 (강세장):** 주도주를 중심으로 적극적인 매수 및 주식 비중 확대를 권장합니다.
        > - **40 ~ 69점 (중립장):** 시장 방향성이 모호합니다. 기존 보유 종목은 유지하되, 신규 매수는 분할로 조심스럽게 접근하세요.
        > - **40점 미만 (약세장):** 현금 비중을 높이고 보수적인 방어 매매(또는 관망)가 필요한 시기입니다.
        """)
        
    st.markdown("### 🔍 현재 점수 산출 배경 (상세 분석)")
    with st.container():
        st.markdown("<div style='background: rgba(30, 41, 59, 0.5); padding: 1.5rem; border-radius: 10px; border: 1px solid rgba(56, 189, 248, 0.3); margin-bottom: 2rem;'>", unsafe_allow_html=True)
        for r in reasons:
            st.markdown(f"<p style='font-size: 1.1rem; margin-bottom: 0.5rem;'>{r}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    st.subheader("📊 부문별 시장 동향")
    cols = st.columns(3)
    with cols[0]:
        st.markdown(f"""<div class="card">
            <div class="card-title">🌐 거시경제 지표</div>
            <div class="card-value">USD: {usd:.1f}원</div>
            <div style="color:#cbd5e1; margin-top:10px;">미국채 10년물: {ust:.2f}%</div>
        </div>""", unsafe_allow_html=True)
        
    with cols[1]:
        st.markdown(f"""<div class="card">
            <div class="card-title">📈 KOSPI 기술적 추세</div>
            <div class="card-value">{int(k_curr)} pt</div>
            <div style="color:#cbd5e1; margin-top:10px;">추세: {k_status}</div>
        </div>""", unsafe_allow_html=True)
        
    with cols[2]:
        st.markdown(f"""<div class="card">
            <div class="card-title">💰 수급 및 거래량</div>
            <div class="card-value">{flow['status']}</div>
            <div style="color:#cbd5e1; margin-top:10px;">거래량 급증: {"발생" if flow.get('vol_ratio',0)>1.1 else "보통"}</div>
        </div>""", unsafe_allow_html=True)
        
    if not kdf.empty:
        st.markdown("### 📉 KOSPI 지수 추이")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=kdf.index, y=kdf["Close"], mode="lines", name="KOSPI", line=dict(color="#38bdf8", width=2)))
        fig.add_trace(go.Scatter(x=kdf.index, y=kdf["MA20"], mode="lines", name="20일선", line=dict(color="#f59e0b", width=1.2, dash="dot")))
        fig.add_trace(go.Scatter(x=kdf.index, y=kdf["MA60"], mode="lines", name="60일선", line=dict(color="#818cf8", width=1.2, dash="dot")))
        fig.update_layout(height=400, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#cbd5e1"), margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

render_market_timing()
