import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from utils.data_engine import (
    load_ohlcv, get_investor_flow, get_recent_news, get_company_info,
    get_financial_trends, get_consensus_and_valuation, get_recent_disclosures, get_detailed_investor_flow,
    check_is_etf, get_etf_basic_info, get_etf_holdings
)
from utils.indicators import analyze_technical
from utils.strategy import generate_trading_strategy

import os



def safe_float(val):
    try:
        if isinstance(val, str):
            val = val.replace(',', '')
        return float(val)
    except:
        return np.nan

def generate_expert_summary(ticker_name, comp_info, fin_df, cons_data, tech, inv_detail_df):
    summary = f"### 💡 AI 트레이딩 전문가의 '{ticker_name}' 초보자 맞춤 브리핑\n\n"
    
    summary += f"**1. 돈은 잘 벌고 있나요? (펀더멘털/실적 분석)**\n"
    if not fin_df.empty and '영업이익' in fin_df.index:
        op_data = fin_df.loc['영업이익'].dropna()
        if len(op_data) >= 2:
            recent_op = safe_float(op_data.iloc[-1])
            prev_op = safe_float(op_data.iloc[-2])
            recent_year = op_data.index[-1]
            prev_year = op_data.index[-2]
            
            diff = recent_op - prev_op
            growth_rate = (diff / abs(prev_op)) * 100 if prev_op != 0 else 0
                
            if recent_op > 0:
                summary += f"> 최근 실적({recent_year} 기준)으로 **영업이익 {recent_op:,.0f}억 원(흑자)**을 기록 중입니다. "
            else:
                summary += f"> 최근 실적({recent_year} 기준)으로 **영업이익 {recent_op:,.0f}억 원(적자)**을 기록 중입니다. "
                
            if diff > 0:
                summary += f"이전 기간({prev_year}) 대비 **{diff:,.0f}억 원(+{growth_rate:.1f}%) 증가**하며 실적이 개선되고 있습니다.\n"
            elif diff < 0:
                summary += f"이전 기간({prev_year}) 대비 **{abs(diff):,.0f}억 원({growth_rate:.1f}%) 감소**하며 실적이 악화되고 있습니다.\n"
            else:
                summary += f"이전 기간과 비슷한 수준의 실적을 유지하고 있습니다.\n"
        else:
            recent_op = safe_float(op_data.iloc[-1]) if not op_data.empty else 0
            if recent_op > 0:
                summary += f"> 최근 실적 기준으로 **영업이익 {recent_op:,.0f}억 원(흑자)**을 기록 중입니다. 돈을 잘 벌고 있는 튼튼한 기업입니다.\n"
            else:
                summary += f"> 최근 실적 기준으로 **영업이익 {recent_op:,.0f}억 원(적자)**을 기록 중입니다. 실적 턴어라운드가 필요한 상황입니다.\n"
    else:
        summary += f"> 기업의 재무/실적 데이터를 현재 확인할 수 없습니다.\n"
    
    summary += f"\n**2. 최근 주가는 왜 이런 흐름을 보일까요? (모멘텀 및 지속가능성)**\n"
    if not inv_detail_df.empty:
        def get_consecutive_days(series):
            if len(series) == 0: return 0, 0, "관망"
            last_val = series.iloc[-1]
            days, total = 0, 0
            if last_val > 0:
                for val in reversed(series):
                    if val > 0: days += 1; total += val
                    else: break
                return days, total, "순매수"
            elif last_val < 0:
                for val in reversed(series):
                    if val < 0: days += 1; total += val
                    else: break
                return days, total, "순매도"
            return 0, 0, "관망"

        for_series = inv_detail_df.get('외국인합계', pd.Series(dtype=float))
        ins_series = inv_detail_df.get('기관합계', pd.Series(dtype=float))
        
        for_msg, ins_msg = "", ""
        if not for_series.empty:
            f_days, f_tot, f_type = get_consecutive_days(for_series)
            if f_days > 0:
                for_msg = f"외국인은 최근 **{f_days}거래일 연속 {f_tot/1e8:,.0f}억 원을 {f_type}**하고 있습니다. "
                
        if not ins_series.empty:
            i_days, i_tot, i_type = get_consecutive_days(ins_series)
            if i_days > 0:
                ins_msg = f"기관은 최근 **{i_days}거래일 연속 {i_tot/1e8:,.0f}억 원을 {i_type}**하고 있습니다."
                
        if for_msg or ins_msg:
            summary += f"> {for_msg}{ins_msg}\n"
            
            recent_for = inv_detail_df['외국인_누적'].iloc[-1] - inv_detail_df['외국인_누적'].iloc[-20] if len(inv_detail_df) >= 20 else 0
            recent_ins = inv_detail_df['기관_누적'].iloc[-1] - inv_detail_df['기관_누적'].iloc[-20] if len(inv_detail_df) >= 20 else 0
            
            if recent_for > 0 and recent_ins > 0:
                summary += "> 전반적인 한 달 흐름에서도 **외국인과 기관이 쌍끌이 매수** 중이므로 수급 모멘텀이 매우 강력합니다.\n"
            elif recent_for < 0 and recent_ins < 0:
                summary += "> 전반적인 한 달 흐름에서도 **외국인과 기관이 쌍끌이 매도** 중이므로 수급 부담이 큰 상황입니다.\n"
            else:
                summary += "> 한 달 기준으로는 두 주체의 방향성이 엇갈리고 있으니 단기 수급 변화에 주의하세요.\n"
        else:
            summary += "> 외국인과 기관의 뚜렷한 연속 매수/매도세가 보이지 않습니다.\n"
    else:
        summary += "> 최근 수급 동향을 파악할 수 없습니다.\n"
        
    if tech:
        if tech['추세'] == "정배열 상승추세":
            summary += "> 차트상으로도 **모든 이동평균선이 정배열(위로 향함)인 상승 추세**입니다. 상승 모멘텀이 매우 좋습니다.\n"
        elif tech['추세'] == "역배열 하락추세":
            summary += "> 차트상으로는 **이동평균선이 역배열인 하락 추세**입니다. 바닥이 확인되기 전까지는 섣부른 매수보다는 관망하는 것이 좋습니다.\n"
        else:
            summary += "> 차트상 뚜렷한 방향성이 없는 혼조세입니다.\n"
            
    summary += f"\n**3. 초보자를 위한 투자 전략 요약**\n"
    if tech:
        rsi = tech['RSI']
        if rsi > 70:
            summary += "> 현재 주가가 단기적으로 과열(RSI 70 이상)되어 있습니다. **지금 당장 추격 매수하는 것은 위험**합니다. 조정(주가가 조금 떨어지는 것)을 기다려보세요.\n"
        elif rsi < 30:
            summary += "> 현재 주가가 단기적으로 많이 빠진 과매도(RSI 30 이하) 상태입니다. **분할 매수로 접근해 볼 만한 좋은 기회**가 될 수 있습니다.\n"
        else:
            summary += "> 현재 주가는 과열이나 과매도 상태가 아닌 적정 수준에서 등락하고 있습니다.\n"
            
    return summary

def render_detail_analysis(ticker, ticker_name, base_date, engine):
    is_etf = check_is_etf(ticker)
    
    if is_etf:
        render_etf_analysis(ticker, ticker_name, base_date, engine)
        return

    with st.spinner(f"'{ticker_name}' 종합 금융 데이터를 수집 중입니다..."):
        df = load_ohlcv(ticker, base_date, 300, engine)
        comp_info = get_company_info(ticker)
        fin_df = get_financial_trends(ticker)
        cons_data = get_consensus_and_valuation(ticker)
        inv_detail_df = get_detailed_investor_flow(ticker, base_date)
        news = get_recent_news(ticker)
        disclosures = get_recent_disclosures(ticker)

    if df.empty:
        st.error("데이터를 불러올 수 없습니다. 종목 코드를 확인해주세요.")
        return

    current_price = df['종가'].iloc[-1]
    
    st.markdown(f"## 📊 {ticker_name} <span style='font-size:1rem; color:gray;'>({ticker})</span>", unsafe_allow_html=True)
    st.markdown(f"### {current_price:,}원", unsafe_allow_html=True)
    
    tech = analyze_technical(df)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(generate_expert_summary(ticker_name, comp_info, fin_df, cons_data, tech, inv_detail_df))
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # 1. 기업개요
    with st.container(border=True):
        st.markdown("#### 🏢 기업개요")
        st.caption("출처: 네이버 금융 / 에프앤가이드")
        st.write(comp_info.get("summary", "기업 개요 정보가 없습니다."))

    # 2. 재무 추이 (연간 4년)
    st.markdown("#### 📈 재무 추이 (연간 4년)")
    if not fin_df.empty:
        try:
            years = fin_df.columns.tolist()
            # 3개의 카드로 분할
            col1, col2, col3 = st.columns(3)
            
            with col1:
                with st.container(border=True):
                    st.markdown("**손익 추이**")
                    fig1 = go.Figure()
                    if '매출액' in fin_df.index:
                        fig1.add_trace(go.Bar(x=years, y=fin_df.loc['매출액'].apply(safe_float), name='매출액', marker_color='#93c5fd'))
                    if '영업이익' in fin_df.index:
                        fig1.add_trace(go.Bar(x=years, y=fin_df.loc['영업이익'].apply(safe_float), name='영업이익', marker_color='#fca5a5'))
                    fig1.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=0), showlegend=False, template='plotly_dark')
                    st.plotly_chart(fig1, use_container_width=True)

            with col2:
                with st.container(border=True):
                    st.markdown("**수익성 비율 (%)**")
                    fig2 = go.Figure()
                    if 'ROE(지배주주)' in fin_df.index:
                        fig2.add_trace(go.Scatter(x=years, y=fin_df.loc['ROE(지배주주)'].apply(safe_float), name='ROE', line=dict(color='#ef4444', width=2)))
                    if '영업이익률' in fin_df.index:
                        fig2.add_trace(go.Scatter(x=years, y=fin_df.loc['영업이익률'].apply(safe_float), name='영업이익률', line=dict(color='#10b981', width=2)))
                    fig2.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=0), showlegend=False, template='plotly_dark')
                    st.plotly_chart(fig2, use_container_width=True)

            with col3:
                with st.container(border=True):
                    st.markdown("**재무 건전성 (부채비율)**")
                    fig3 = go.Figure()
                    if '부채비율' in fin_df.index:
                        fig3.add_trace(go.Scatter(x=years, y=fin_df.loc['부채비율'].apply(safe_float), name='부채비율', fill='tozeroy', marker_color='#8b5cf6'))
                    fig3.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=0), showlegend=False, template='plotly_dark')
                    st.plotly_chart(fig3, use_container_width=True)
        except Exception as e:
            st.error("재무 차트 렌더링 중 오류가 발생했습니다.")
    else:
        st.info("재무 데이터를 불러올 수 없습니다.")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # 3. 컨센서스 및 가치평가
    col_l, col_r = st.columns([1, 1])
    with col_l:
        with st.container(border=True):
            st.markdown("#### 📊 가치평가")
            st.markdown(f"- **시가총액:** {cons_data.get('market_cap', 'N/A')}")
            st.markdown(f"- **PER (주가수익비율):** {comp_info.get('per', 'N/A')}")
            st.markdown(f"- **PBR (주가순자산비율):** {comp_info.get('pbr', 'N/A')}")
            st.markdown(f"- **동일업종 PER:** {cons_data.get('same_sector_per', 'N/A')}")
            
        with st.container(border=True):
            st.markdown("#### 📉 가격 통계")
            st.markdown(f"- **52주 최고:** {cons_data.get('high52', 'N/A')}")
            st.markdown(f"- **52주 최저:** {cons_data.get('low52', 'N/A')}")
            st.markdown(f"- **외국인 보유율:** {cons_data.get('foreign_ratio', 'N/A')}")

    with col_r:
        with st.container(border=True):
            st.markdown("#### 🎯 컨센서스 (증권사 예상치)")
            st.markdown(f"- **평균 목표주가:** {cons_data.get('target_price', 'N/A')}")
            st.markdown(f"- **투자의견:** {cons_data.get('opinion', 'N/A')}")
            st.markdown(f"- **배당수익률:** {comp_info.get('dividend', 'N/A')}")
            
    st.markdown("<br>", unsafe_allow_html=True)

    # 4. 투자자별 순매수 (최근 200일)
    st.markdown("#### 👥 투자자별 순매수 (최근 200일 누적)")
    if not inv_detail_df.empty:
        fig_inv = make_subplots(specs=[[{"secondary_y": True}]])
        fig_inv.add_trace(go.Bar(x=inv_detail_df.index, y=inv_detail_df['외국인합계'], name='외국인 (일별)', marker_color='#3b82f6', opacity=0.5), secondary_y=False)
        fig_inv.add_trace(go.Scatter(x=inv_detail_df.index, y=inv_detail_df['기관_누적'], name='기관 (누적)', line=dict(color='#ef4444', width=2)), secondary_y=True)
        fig_inv.update_layout(height=400, template='plotly_dark', margin=dict(l=0, r=0, t=30, b=0), hovermode='x unified')
        st.plotly_chart(fig_inv, use_container_width=True)
        
        # 합계 테이블
        st.markdown("**기간별 누적 순매수 대금 / 수량**")
        periods = [5, 20, 60, 120, 200]
        table_data = []
        for p in periods:
            if len(inv_detail_df) >= p:
                slice_df = inv_detail_df.tail(p)
                table_data.append({
                    "기간": f"{p}일",
                    "개인": slice_df['개인'].sum(),
                    "외국인": slice_df['외국인합계'].sum(),
                    "기관계": slice_df['기관합계'].sum()
                })
        
        if table_data:
            tdf = pd.DataFrame(table_data).set_index("기간")
            # Style negative as blue, positive as red
            def color_val(val):
                color = '#ef4444' if val > 0 else '#3b82f6' if val < 0 else 'white'
                return f'color: {color}'
            st.dataframe(tdf.style.format("{:,.0f}").map(color_val), use_container_width=True)
    else:
        st.info("상세 투자자별 매매동향 데이터를 가져올 수 없습니다. (pykrx 미설치 또는 일시적 에러)")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # 5. 차트 및 매매 전략
    st.markdown("#### 📊 주가 차트 및 트레이딩 전략")
    df['MA5'] = df['종가'].rolling(5).mean()
    df['MA20'] = df['종가'].rolling(20).mean()
    df['MA60'] = df['종가'].rolling(60).mean()
    
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], name='일봉',
        increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'
    ))
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#8b5cf6', width=2), name='20일선'))
    fig.update_layout(height=400, xaxis_rangeslider_visible=False, template='plotly_dark', margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

    if tech:
        strategy = generate_trading_strategy(df, current_price, tech['RSI'], tech['추세'])
        st.info(f"**전문가 코멘트:** {strategy['action_text']}")
        
        if strategy['buy_plan'] or strategy['sell_plan']:
            st.markdown("##### 🎯 매매 시나리오 (예시)")
            b_col, s_col, l_col = st.columns(3)
            with b_col:
                st.markdown("**📉 분할 매수 타점**")
                for plan in strategy['buy_plan']:
                    st.markdown(f"- **{plan['step']}**: {plan['price']:,}원 ({plan['weight']})\\n  <span style='color:gray;font-size:0.8em;'>{plan['reason']}</span>", unsafe_allow_html=True)
            with s_col:
                st.markdown("**📈 분할 매도 목표가**")
                for plan in strategy['sell_plan']:
                    st.markdown(f"- **{plan['step']}**: {plan['price']:,}원\\n  <span style='color:gray;font-size:0.8em;'>{plan['reason']}</span>", unsafe_allow_html=True)
            with l_col:
                st.markdown("**🛡️ 리스크 관리**")
                st.markdown(f"- **손절가**: {strategy['stop_loss']:,}원")
                st.markdown(f"- **예상 손익비**: {strategy['risk_reward_ratio']}")
                st.caption("손절가는 전저점을 이탈할 경우로 설정되었습니다.")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # 6. 뉴스 및 공시
    st.markdown("#### 📰 최신 뉴스 및 📄 주요 공시")
    n_col, d_col = st.columns(2)
    with n_col:
        with st.container(border=True):
            st.markdown("**네이버 금융 - 최신순 뉴스**")
            for n in news:
                if 'link' in n and n['link']:
                    st.markdown(f"- [{n['title']}]({n['link']})")
                else:
                    st.markdown(f"- {n['title']}")
            if not news: st.caption("최근 뉴스가 없습니다.")
            
    with d_col:
        with st.container(border=True):
            st.markdown("**DART/네이버 - 최신 공시**")
            for d in disclosures:
                if 'link' in d and d['link']:
                    st.markdown(f"- [{d['title']}]({d['link']}) <span style='color:gray;font-size:0.8em;'>({d['date']})</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"- {d['title']} <span style='color:gray;font-size:0.8em;'>({d['date']})</span>", unsafe_allow_html=True)
            if not disclosures: st.caption("최근 공시가 없습니다.")

def generate_etf_expert_summary(ticker_name, etf_info, tech, inv_detail_df):
    summary = f"### 💡 AI 트레이딩 전문가의 '{ticker_name}' 초보자 맞춤 브리핑\n\n"
    
    summary += f"**1. 이 펀드는 어떤 상품인가요? (ETF 개요)**\n"
    summary += f"> 이 ETF는 **{etf_info.get('index', '알 수 없는 지수')}**를 기초지수로 추종합니다. 운용사는 {etf_info.get('manager', 'N/A')}이며, 펀드 총보수는 연 {etf_info.get('fee', 'N/A')}입니다.\n"
    if etf_info.get('dividend_yield', 'N/A') != 'N/A':
         summary += f"> 배당(분배금) 수익률은 **{etf_info['dividend_yield']}** 수준입니다.\n\n"
    else:
         summary += f"> 최근 배당(분배금) 데이터가 조회되지 않습니다.\n\n"
    
    summary += f"**2. 최근 주가는 왜 이런 흐름을 보일까요? (수급 및 모멘텀)**\n"
    if not inv_detail_df.empty:
        recent_for = inv_detail_df['외국인_누적'].iloc[-1] - inv_detail_df['외국인_누적'].iloc[-20] if len(inv_detail_df) >= 20 else 0
        recent_ins = inv_detail_df['기관_누적'].iloc[-1] - inv_detail_df['기관_누적'].iloc[-20] if len(inv_detail_df) >= 20 else 0
        if recent_for > 0 and recent_ins > 0:
            summary += "> 최근 한 달간 **외국인과 기관이 동시에 매수**하고 있습니다! 큰 손들이 들어오고 있다는 것은 긍정적인 신호입니다.\n"
        elif recent_for > 0 or recent_ins > 0:
            summary += "> 외국인 또는 기관 중 한 주체가 매수세를 보이고 있습니다. 부분적으로 긍정적인 신호입니다.\n"
        else:
            summary += "> 외국인과 기관의 뚜렷한 매수세가 보이지 않습니다.\n"
    else:
        summary += "> 최근 수급 동향을 파악할 수 없습니다.\n"
        
    if tech:
        if tech['추세'] == "정배열 상승추세":
            summary += "> 차트상으로 **상승 추세(정배열)**를 그리고 있습니다.\n"
        elif tech['추세'] == "역배열 하락추세":
            summary += "> 차트상으로는 **하락 추세(역배열)**입니다. 바닥 확인이 필요합니다.\n"
        else:
            summary += "> 차트상 뚜렷한 방향성이 없는 혼조세입니다.\n"
            
    summary += f"\n**3. 초보자를 위한 투자 전략 요약**\n"
    if tech:
        rsi = tech['RSI']
        if rsi > 70:
            summary += "> 현재 단기적으로 과열(RSI 70 이상)되어 있습니다. **추격 매수는 위험**하며 조정 시 분할 매수를 고려하세요.\n"
        elif rsi < 30:
            summary += "> 현재 단기 과매도(RSI 30 이하) 상태입니다. **분할 매수로 접근해 볼 만한 기회**가 될 수 있습니다.\n"
        else:
            summary += "> 현재 주가는 적정 수준에서 등락 중이므로 시장 지표에 맞추어 보수적으로 접근하세요.\n"
            
    return summary

def render_etf_analysis(ticker, ticker_name, base_date, engine):
    with st.spinner(f"'{ticker_name}' ETF 데이터를 수집 중입니다..."):
        df = load_ohlcv(ticker, base_date, 300, engine)
        etf_info = get_etf_basic_info(ticker)
        holdings = get_etf_holdings(ticker)
        inv_detail_df = get_detailed_investor_flow(ticker, base_date)
        news = get_recent_news(ticker)

    if df.empty:
        st.error("데이터를 불러올 수 없습니다. 종목 코드를 확인해주세요.")
        return

    current_price = df['종가'].iloc[-1]
    
    st.markdown(f"## 📊 {ticker_name} <span style='font-size:1rem; color:gray;'>({ticker} - ETF)</span>", unsafe_allow_html=True)
    st.markdown(f"### {current_price:,}원", unsafe_allow_html=True)
    
    tech = analyze_technical(df)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(generate_etf_expert_summary(ticker_name, etf_info, tech, inv_detail_df))
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # 1. ETF 기본 정보
    with st.container(border=True):
        st.markdown("#### 🏢 ETF 기본 정보")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("NAV(순자산가치)", etf_info.get('nav', 'N/A'))
        c2.metric("최근 배당/분배금 수익률", etf_info.get('dividend_yield', 'N/A'))
        c3.metric("펀드보수", etf_info.get('fee', 'N/A'))
        c4.metric("자산운용사", etf_info.get('manager', 'N/A'))
        
        st.write(f"**기초지수:** {etf_info.get('index', 'N/A')}")
        st.write(f"**상장일:** {etf_info.get('listing_date', 'N/A')}")

    # 2. 보유 종목 (Top 10)
    st.markdown("#### 🥧 포트폴리오 구성 종목 (Top 10)")
    if holdings:
        h_df = pd.DataFrame(holdings)
        h_df.columns = ['구성종목', '비중']
        
        col1, col2 = st.columns([1, 1])
        with col1:
            st.dataframe(h_df, use_container_width=True, hide_index=True)
        with col2:
            fig_pie = go.Figure(data=[go.Pie(labels=h_df['구성종목'], values=h_df['비중'].str.replace('%','').astype(float), hole=.3, textinfo='label+percent')])
            fig_pie.update_layout(height=350, margin=dict(l=0, r=0, t=0, b=0), template='plotly_dark', showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("구성 종목 정보를 불러올 수 없습니다.")

    # 3. 기술적 분석 및 수급 추이 (기존 재활용)
    st.markdown("#### 📊 차트 및 수급 분석")
    t_col1, t_col2 = st.columns([2, 1])
    
    with t_col1:
        with st.container(border=True):
            st.markdown("**가격 추세 및 이동평균선**")
            fig = make_subplots(specs=[[{"secondary_y": False}]])
            fig.add_trace(go.Scatter(x=df.index, y=df['종가'], name='종가', line=dict(color='#60a5fa', width=2)))
            if 'MA20' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name='20일선', line=dict(color='#f472b6', width=1)))
            if 'MA60' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], name='60일선', line=dict(color='#a78bfa', width=1)))
            fig.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0), template='plotly_dark')
            st.plotly_chart(fig, use_container_width=True)
            
    with t_col2:
        with st.container(border=True):
            st.markdown("**기술적 지표 요약**")
            st.write(f"- **현재 추세:** {tech.get('추세', '알 수 없음')}")
            st.write(f"- **RSI (14):** {tech.get('RSI', 0):.1f}")
            st.write(f"- **MA20 이격도:** {tech.get('MA20이격도', 0):.1f}%")
            st.write(f"- **MACD 히스토그램:** {tech.get('MACD_Hist', 0):.1f}")
            
        with st.container(border=True):
            st.markdown("**누적 수급 (최근 20일)**")
            if not inv_detail_df.empty:
                recent = inv_detail_df.tail(20)
                fig_inv = go.Figure()
                fig_inv.add_trace(go.Scatter(x=recent.index, y=recent['외국인_누적'], name='외국인', line=dict(color='#f43f5e')))
                fig_inv.add_trace(go.Scatter(x=recent.index, y=recent['기관_누적'], name='기관', line=dict(color='#3b82f6')))
                fig_inv.add_trace(go.Scatter(x=recent.index, y=recent['개인_누적'], name='개인', line=dict(color='#10b981')))
                fig_inv.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), showlegend=False, template='plotly_dark')
                st.plotly_chart(fig_inv, use_container_width=True)
            else:
                st.info("수급 데이터 없음")

    # 4. 관련 뉴스
    st.markdown("#### 📰 최신 뉴스")
    with st.container(border=True):
        for n in news:
            if 'link' in n and n['link']:
                st.markdown(f"- [{n['title']}]({n['link']})")
            else:
                st.markdown(f"- {n['title']}")
        if not news: st.caption("최근 뉴스가 없습니다.")
