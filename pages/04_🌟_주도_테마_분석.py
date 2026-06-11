import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime
from utils.data_engine import get_market_themes, get_theme_stocks

st.set_page_config(page_title="주도 테마 분석", page_icon="🌟", layout="wide")

st.markdown("""
<style>
.theme-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 0.75rem;
    padding: 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}
.theme-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #334155;
    padding-bottom: 0.5rem;
    margin-bottom: 0.5rem;
}
.theme-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #e2e8f0;
}
.theme-avg {
    font-size: 0.9rem;
    font-weight: 600;
}
.stock-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.stock-row:last-child {
    border-bottom: none;
}
.stock-name {
    font-weight: 600;
    color: #cbd5e1;
    font-size: 0.95rem;
}
.stock-ticker {
    font-size: 0.75rem;
    color: #64748b;
}
.stock-price {
    font-size: 0.9rem;
    color: #e2e8f0;
}
.text-red { color: #ef4444 !important; }
.text-blue { color: #3b82f6 !important; }
.text-gray { color: #94a3b8 !important; }
</style>
""", unsafe_allow_html=True)

st.title("🌟 장 주도 테마 & 대장주 요약")
st.caption("네이버 금융 테마 데이터를 기반으로 현재 시장을 주도하는 테마와 소속 대장주를 한눈에 파악합니다. (5분 주기 업데이트)")

@st.cache_data(ttl=300)
def load_theme_data():
    themes = get_market_themes()
    if themes.empty:
        return pd.DataFrame()
    
    # 등락률 순으로 정렬 후 상위 16개만 사용
    themes = themes.sort_values('Change', ascending=False).head(16).reset_index(drop=True)
    return themes

themes_df = load_theme_data()

if themes_df.empty:
    st.error("테마 데이터를 불러오는 데 실패했습니다.")
    st.stop()

# ── 1. 테마 트리맵 시각화 ──
st.subheader("📊 주도 테마 트리맵 (Treemap)")

# Treemap용 데이터 구성
labels = themes_df['Theme'].tolist()
parents = [""] * len(labels)
# 값은 절대값으로 크기를 정하되, 모두 양수로 만듦
values = themes_df['Change'].abs().tolist()

# 색상은 등락률 부호에 따라 결정
colors = []
customdata = []
for change in themes_df['Change']:
    if change > 0:
        colors.append('#dc2626') # Red
        customdata.append(f"+{change:.2f}%")
    elif change < 0:
        colors.append('#2563eb') # Blue
        customdata.append(f"{change:.2f}%")
    else:
        colors.append('#475569') # Gray
        customdata.append("0.00%")

fig = go.Figure(go.Treemap(
    labels=labels,
    parents=parents,
    values=values,
    customdata=customdata,
    texttemplate="<b>%{label}</b><br>%{customdata}",
    marker_colors=colors,
    textposition="middle center",
    textfont=dict(size=14, color='white')
))

fig.update_layout(
    margin=dict(t=10, l=10, r=10, b=10),
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    height=400
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader("🏆 테마별 대장주 Top 5")

# ── 2. 테마별 카드 UI (4열 그리드) ──
cols = st.columns(4)

# 테마를 4개씩 순회하며 열에 배치
for idx, row in themes_df.iterrows():
    col = cols[idx % 4]
    with col:
        theme_name = row['Theme']
        theme_change = row['Change']
        theme_url = row['Link']
        
        color_class = "text-red" if theme_change > 0 else "text-blue" if theme_change < 0 else "text-gray"
        sign = "+" if theme_change > 0 else ""
        
        # 카드 헤더 HTML
        header_html = f"""
<div class="theme-header">
    <span class="theme-title">#{idx+1} {theme_name}</span>
    <span class="theme-avg {color_class}">{sign}{theme_change:.2f}%</span>
</div>
"""
        
        # 주식 목록 HTML 생성
        with st.spinner(f"'{theme_name}' 로딩..."):
            stocks_df = get_theme_stocks(theme_url, top_n=5)
            
        stocks_html = ""
        if not stocks_df.empty:
            for _, s_row in stocks_df.iterrows():
                s_name = s_row['Name']
                s_ticker = s_row['Ticker']
                s_price = s_row['Price']
                s_change = s_row['Change_Pct']
                
                s_color = "text-red" if s_change > 0 else "text-blue" if s_change < 0 else "text-gray"
                s_sign = "+" if s_change > 0 else ""
                
                stocks_html += f"""
<div class="stock-row">
    <div>
        <div class="stock-name">{s_name}</div>
        <div class="stock-ticker">{s_ticker}</div>
    </div>
    <div style="text-align: right;">
        <div class="stock-price">{s_price:,}원</div>
        <div class="{s_color}" style="font-size: 0.85rem; font-weight: 600;">{s_sign}{s_change:.2f}%</div>
    </div>
</div>
"""
        else:
            stocks_html = "<div style='color:#94a3b8; font-size:0.85rem; text-align:center; padding:1rem;'>종목 데이터를 불러올 수 없습니다.</div>"
            
        card_html = f"""
<div class="theme-card">
    {header_html}
    <div style="margin-top: 0.5rem;">
        {stocks_html}
    </div>
</div>
"""
        
        st.markdown(card_html, unsafe_allow_html=True)
