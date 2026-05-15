"""
signal_logic.py (Optimized V2 - Phase 1 ready)
"""
import pandas as pd
import numpy as np

SIGNAL_SCORE_THRESHOLD = 3

def prepare_df(df_5min: pd.DataFrame) -> pd.DataFrame:
    df = df_5min.copy()
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['date'] = df['datetime'].dt.date
    df['time'] = df['datetime'].dt.time
    
    # 1. 거래량 가속도 및 비율 미리 계산
    df['vol_sum_6'] = df.groupby('date')['volume'].transform(lambda x: x.rolling(6).sum())
    df['vol_sum_prev_6'] = df.groupby('date')['vol_sum_6'].shift(6)
    df['vol_accel'] = (df['vol_sum_6'] / df['vol_sum_prev_6']).fillna(0)
    
    df['cum_vol'] = df.groupby('date')['volume'].cumsum()
    pivot = df.pivot_table(index='time', columns='date', values='cum_vol')
    hist_avg = pivot.expanding(axis=1).mean().shift(1, axis=1)
    hist_avg_long = hist_avg.stack().reset_index()
    hist_avg_long.columns = ['time', 'date', 'hist_avg_cum_vol']
    df = pd.merge(df, hist_avg_long, on=['time', 'date'], how='left')
    df['vol_ratio'] = (df['cum_vol'] / df['hist_avg_cum_vol']).fillna(0)
    
    # 2. 박스권 및 이평선
    df['box_high'] = df.groupby('date')['high'].transform(lambda x: x.rolling(6).max().shift(1))
    df['ma5'] = df.groupby('date')['close'].transform(lambda x: x.rolling(5).mean())
    df['ma20'] = df.groupby('date')['close'].transform(lambda x: x.rolling(20).mean())
    
    # 3. VWAP 및 ATR
    df['cum_val'] = (df['close'] * df['volume']).groupby(df['date']).cumsum()
    df['vwap'] = (df['cum_val'] / df['cum_vol']).fillna(0)
    
    df['prev_close'] = df.groupby('date')['close'].shift(1)
    df['tr'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['prev_close']), 
                                     abs(df['low'] - df['prev_close'])))
    df['atr'] = df.groupby('date')['tr'].transform(lambda x: x.rolling(14).mean()).fillna(0)
    
    # 4. 캔들 품질
    df['is_up'] = df['close'] > df['open']
    df['candle_seq_check'] = df.groupby('date')['is_up'].transform(
        lambda x: x.rolling(3).apply(lambda s: 1.0 if s.all() else 0.0, raw=True)
    ).fillna(0)
    
    return df

def detect_signal_detail(df: pd.DataFrame, idx: int) -> dict:
    row = df.iloc[idx]
    
    # 이미 계산된 컬럼 참조
    vol_accel = row['vol_accel']
    vol_ratio = row['vol_ratio']
    box_high = row['box_high']
    cur_close = row['close']
    consol_break = bool(cur_close > box_high) if box_high > 0 else False
    candle_seq = bool(row['candle_seq_check'] == 1.0)
    
    score = 0
    if vol_accel >= 2.5: score += 2
    elif vol_accel >= 1.5: score += 1
    if vol_ratio >= 3.0: score += 1
    if consol_break: score += 1
    if candle_seq: score += 1
    
    return {
        "signal": score >= SIGNAL_SCORE_THRESHOLD,
        "score": score,
        "vol_accel": vol_accel,
        "vol_ratio": vol_ratio,
        "consol_break": consol_break,
        "candle_seq": candle_seq
    }
