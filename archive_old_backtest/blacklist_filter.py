import pandas as pd

def should_skip(df, current_idx):
    """
    현재 봉 인덱스를 기준으로 해당 종목이 매매 부적합(Blacklist) 종목인지 판별한다.
    
    Returns:
        True: 스킵해야 함 (부적합)
        False: 매매 가능
    """
    # ── 데이터 유효성 확인 ──
    if current_idx < 1560: # 20거래일(약 1560봉) 데이터가 확보되지 않은 경우 스킵
        return True
    
    row = df.iloc[current_idx]
    current_price = row['close']

    # ── 1. 가격대 필터 ──
    # 동전주(2,000원 미만) 및 고가주(500,000원 이상) 회피
    if current_price < 2000 or current_price > 500000:
        return True

    # ── 2. 시가총액/유동성 필터 ──
    # 과거 20거래일(1560봉) 평균 거래대금이 20억 원 미만인 경우 스킵
    # 거래대금 = 종가 * 거래량
    last_20d_bars = df.iloc[current_idx-1560 : current_idx]
    avg_trading_value_5min = (last_20d_bars['close'] * last_20d_bars['volume']).mean()
    # 1일 평균 거래대금 환산 (1일 약 78개 5분봉 기준)
    avg_daily_trading_value = avg_trading_value_5min * 78
    
    if avg_daily_trading_value < 2000000000: # 20억 원
        return True

    # ── 3. 비정상 변동성(상/하한가) 필터 ──
    # 최근 5거래일(390봉) 이내에 상한가(+30%) 또는 하한가(-30%)를 기록한 이력 확인
    last_5d_bars = df.iloc[current_idx-390 : current_idx]
    
    # KIS API/CSV 데이터 특성상 전일종가가 없으므로, 당일 시가 대비 변동성으로 근사치 계산
    # 혹은 데이터에 pct_change가 있다면 더 정확함. 여기서는 보수적으로 고점/저점 변동성 체크
    for _, bar in last_5d_bars.iterrows():
        # 당일 봉 내부에서의 등락률이 25% 이상인 경우 (상한가 근접) 스킵
        # (전일 종가 데이터가 없는 상황을 고려한 보수적 필터링)
        intra_day_volatility = (bar['high'] - bar['low']) / bar['open']
        if intra_day_volatility >= 0.25:
            return True
            
    return False
