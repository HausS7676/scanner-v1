import pandas as pd
import numpy as np

def generate_trading_strategy(df, current_price, rsi, trend, is_bull_market=True):
    """
    전문가 수준의 트레이딩 전략을 산출합니다.
    분할 매수/매도 타점, 손절가, 목표가를 수학적으로 계산하여 제시합니다.
    """
    if df is None or df.empty or len(df) < 20:
        return {"error": "데이터가 부족하여 전략을 산출할 수 없습니다."}
        
    close = df['종가']
    high = df['고가']
    low = df['저가']
    
    # 주요 지지/저항 라인 계산
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1])
    
    recent_high = float(high.tail(20).max())
    recent_low = float(low.tail(20).min())
    
    ATR = float((high - low).rolling(14).mean().iloc[-1])
    
    strategy = {
        "status": "관망",
        "action_text": "",
        "buy_plan": [],
        "sell_plan": [],
        "stop_loss": 0,
        "risk_reward_ratio": 0.0
    }
    
    # 1. 포지션 및 기본 스탠스 판별
    if "정배열" in trend:
        if rsi > 70:
            strategy["status"] = "보유자 영역 (과매수)"
            strategy["action_text"] = "단기 과열 구간입니다. 신규 진입을 자제하고 보유자는 분할 매도로 수익을 실현하세요."
        elif rsi < 40:
            strategy["status"] = "적극 매수 (눌림목)"
            strategy["action_text"] = "정배열 상승 추세 속의 건전한 눌림목입니다. 적극적인 분할 매수를 권장합니다."
        else:
            strategy["status"] = "매수 가능 (추세추종)"
            strategy["action_text"] = "상승 추세가 이어지고 있습니다. 추세에 동참하는 스윙 매매가 유효합니다."
    elif "역배열" in trend:
        if rsi < 30:
            strategy["status"] = "기술적 반등 노림"
            strategy["action_text"] = "과매도 구간으로 단기적인 기술적 반등이 나올 수 있으나, 짧은 목표가를 잡고 접근해야 합니다."
        else:
            strategy["status"] = "절대 관망 (하락 추세)"
            strategy["action_text"] = "하락 추세가 진행 중입니다. 바닥이 확인될 때까지 신규 매수를 자제하세요."
    else: # 혼조세
        strategy["status"] = "박스권 매매"
        strategy["action_text"] = "박스권 횡보 장세입니다. 박스권 하단에서 매수하고 상단에서 매도하는 전략이 유효합니다."
        
    # 2. 분할 매수 전략 (1차, 2차)
    buy1 = current_price
    buy2 = ma20 if current_price > ma20 else recent_low
    
    if strategy["status"] in ["적극 매수 (눌림목)", "매수 가능 (추세추종)", "기술적 반등 노림", "박스권 매매"]:
        strategy["buy_plan"] = [
            {"step": "1차 매수", "price": int(buy1), "weight": "40%", "reason": "현재가 부근 1차 진입"},
            {"step": "2차 매수", "price": int(buy2), "weight": "60%", "reason": "의미 있는 지지선(20일선 또는 전저점) 부근"}
        ]
        
    # 3. 목표가 산출 (1차, 2차)
    target1 = current_price + (ATR * 2)
    if "정배열" in trend:
        target2 = recent_high if recent_high > target1 else current_price + (ATR * 4)
    else:
        target2 = target1 + ATR
        
    strategy["sell_plan"] = [
        {"step": "1차 매도 (50%)", "price": int(target1), "reason": "단기 저항선 (수익 실현)"},
        {"step": "2차 매도 (50%)", "price": int(target2), "reason": "추세 돌파 후 2차 목표가"}
    ]
    
    # 4. 손절가 산출 (엄격한 리스크 관리)
    stop_loss = recent_low - (ATR * 0.5)
    if current_price - stop_loss > current_price * 0.15: # 15% 이상 손실 위험이면
        stop_loss = current_price * 0.90 # 최대 10% 손절로 타이트하게
        
    strategy["stop_loss"] = int(stop_loss)
    
    # 손익비 산출 (평균 매수단가 대비 1차 목표가 vs 손절가)
    avg_buy = (buy1 * 0.4) + (buy2 * 0.6) if strategy["buy_plan"] else current_price
    reward = target1 - avg_buy
    risk = avg_buy - strategy["stop_loss"]
    if risk > 0:
        strategy["risk_reward_ratio"] = round(reward / risk, 2)
    else:
        strategy["risk_reward_ratio"] = 0.0
        
    return strategy
