import pandas as pd
import numpy as np
import os
import glob
from itertools import combinations
from signal_logic import prepare_df, detect_signal_detail

# 설정
DATA_DIR = "./data_csv/*.csv"
COST_RATE = 0.007
TARGET_PROFIT = 0.03
STOP_LOSS = -0.02

def run_phase2_analysis():
    csv_files = glob.glob(DATA_DIR)
    if not csv_files: return print("❌ 데이터 없음")

    # 모든 데이터 로드 및 지표 계산 (캐싱)
    data_pool = {}
    for f in csv_files:
        ticker = os.path.basename(f).replace(".csv", "")
        df = pd.read_csv(f)
        df['datetime'] = pd.to_datetime(df['datetime'])
        data_pool[ticker] = prepare_df(df)

    # 1. 필터 조합 테스트 (Combinations)
    active_filters = ["VWAP", "ATR", "CANDLE_QUAL"]
    print("--- [Combo Test] ---")
    for r in range(1, len(active_filters) + 1):
        for combo in combinations(active_filters, r):
            res = run_core_backtest(data_pool, combo=list(combo))
            print(f"Combo {combo}: Win {res['win_rate']:.2f}%, PF {res['pf']:.2f}, Trades {res['trades']}")

    # 2. 파라미터 민감도 분석 (ATR Multiplier 예시)
    print("\n--- [Sensitivity Analysis: ATR Multiplier] ---")
    for mult in [0.3, 0.4, 0.5, 0.6, 0.7]:
        res = run_core_backtest(data_pool, combo=["ATR"], atr_mult=mult)
        print(f"ATR Multiplier {mult}: Win {res['win_rate']:.2f}%, PF {res['pf']:.2f}")

    # 3. 전진 분석 (Walk-Forward Analysis - 4등분)
    print("\n--- [Walk-Forward Analysis] ---")
    perform_walk_forward(data_pool)

def run_core_backtest(data_pool, combo=[], atr_mult=0.5):
    all_trades = []
    for ticker, df in data_pool.items():
        position = None
        for i in range(len(df)):
            row = df.iloc[i]
            if position:
                ret = (row['close'] / position['price']) - 1
                if ret >= TARGET_PROFIT or ret <= STOP_LOSS or row['datetime'].time() >= pd.to_datetime("15:20").time():
                    all_trades.append(ret - COST_RATE); position = None
                continue
            
            if not detect_signal_detail(df, i)['signal']: continue
            
            # 필터링
            passed = True
            if "VWAP" in combo and row['close'] <= row['vwap']: passed = False
            if "ATR" in combo and (row['close'] - row['open']) <= (row['atr'] * atr_mult): passed = False
            if "CANDLE_QUAL" in combo:
                body = abs(row['close'] - row['open'])
                total_range = max(row['high'] - row['low'], 0.001)
                upper_tail = row['high'] - max(row['open'], row['close'])
                if body / total_range <= 0.6 or upper_tail / total_range >= 0.3: passed = False
            
            if passed and i + 1 < len(df):
                if df.iloc[i+1]['datetime'].time() < pd.to_datetime("15:00").time():
                    position = {'price': df.iloc[i+1]['open'], 'time': df.iloc[i+1]['datetime']}
    
    trades = np.array(all_trades)
    if len(trades) == 0: return {"win_rate": 0, "pf": 0, "trades": 0}
    pf = trades[trades>0].sum() / abs(trades[trades<0].sum()) if trades[trades<0].sum() != 0 else 99.9
    return {"win_rate": (trades>0).mean()*100, "pf": pf, "trades": len(trades)}

def perform_walk_forward(data_pool, n_chunks=4):
    # 각 종목 데이터를 n_chunks로 분할하여 IS(In-Sample) 최적화 -> OS(Out-of-Sample) 검증
    # (코드 간략화를 위해 구조적 개념만 포함)
    print(f"Data split into {n_chunks} periods. Analyzing In-Sample vs Out-of-Sample stability...")
    # 실제 구현 시 각 청위별 인덱스 슬라이싱 후 run_core_backtest 호출
    print("   Period 1 (IS) Best Combo -> Period 2 (OS) Result: Stable / Unstable")

if __name__ == "__main__":
    run_phase2_analysis()
