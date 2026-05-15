import pandas as pd
import numpy as np
import os
import glob
from signal_logic import prepare_df, detect_signal_detail

# 테스트 설정
DATA_DIR = "./data_csv/*.csv"
COST_RATE = 0.007
TARGET_PROFIT = 0.03
STOP_LOSS = -0.02

def run_ablation_test():
    csv_files = glob.glob(DATA_DIR)
    if not csv_files:
        print("❌ 테스트 데이터(CSV)가 없습니다.")
        return

    # 시나리오 정의
    scenarios = {
        "A": "Baseline (No Filter)",
        "B": "VWAP Filter (Price > VWAP)",
        "C": "ATR Strength Filter (Body > ATR*0.5)",
        "D": "Vol Density Filter (Vol_Ratio > 5.0)",
        "E": "Market Filter (Placeholder)", # 지수 데이터 필요 시 추가
        "F": "Candle Quality Filter (Body > 60%, Upper < 30%)"
    }
    
    results = {k: [] for k in scenarios.keys()}

    for file_path in csv_files:
        ticker = os.path.basename(file_path).replace(".csv", "")
        df_raw = pd.read_csv(file_path)
        df_raw['datetime'] = pd.to_datetime(df_raw['datetime'])
        df = prepare_df(df_raw) # VWAP, ATR 등이 포함된 강화된 prepare_df 가정
        
        for key in scenarios.keys():
            trades = simulate_scenario(df, ticker, key)
            results[key].extend(trades)

    # 성과 지표 산출 및 표 출력
    print_comparison_table(results, scenarios)

def simulate_scenario(df, ticker, scenario_key):
    trades = []
    position = None
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        # 청산 로직
        if position:
            profit = (row['close'] / position['price']) - 1
            if profit >= TARGET_PROFIT or profit <= STOP_LOSS or row['datetime'].time() >= pd.to_datetime("15:20").time():
                trades.append(profit - COST_RATE)
                position = None
            continue

        # 진입 로직 + 필터 적용
        detail = detect_signal_detail(df, i)
        if not detail['signal']: continue
        
        # 필터링 조건 (Ablation)
        passed = True
        if scenario_key == "B": # VWAP
            passed = row['close'] > row['vwap']
        elif scenario_key == "C": # ATR
            passed = (row['close'] - row['open']) > (row['atr'] * 0.5)
        elif scenario_key == "D": # 고밀도 거래량
            passed = row['vol_ratio'] > 5.0
        elif scenario_key == "F": # 캔들 품질
            body = abs(row['close'] - row['open'])
            total_range = max(row['high'] - row['low'], 0.001)
            upper_tail = row['high'] - max(row['open'], row['close'])
            passed = (body / total_range > 0.6) and (upper_tail / total_range < 0.3)
        
        if passed and i + 1 < len(df):
            if df.iloc[i+1]['datetime'].time() < pd.to_datetime("15:00").time():
                position = {'price': df.iloc[i+1]['open'], 'time': df.iloc[i+1]['datetime']}
                
    return trades

def print_comparison_table(results, scenarios):
    print("\n" + "="*85)
    print(f"{'ID':<3} | {'Scenario Name':<25} | {'Trades':<7} | {'Win%':<7} | {'Avg%':<7} | {'P.Factor':<8}")
    print("-" * 85)
    
    for k, trades in results.items():
        if not trades:
            print(f"{k:<3} | {scenarios[k]:<25} | 0       | 0.00%   | 0.00%   | 0.00")
            continue
            
        trades = np.array(trades)
        win_rate = (trades > 0).mean() * 100
        avg_ret = trades.mean() * 100
        
        pos_sum = trades[trades > 0].sum()
        neg_sum = abs(trades[trades < 0].sum())
        pf = pos_sum / neg_sum if neg_sum > 0 else 99.9
        
        print(f"{k:<3} | {scenarios[k]:<25} | {len(trades):<7} | {win_rate:<7.2f}% | {avg_ret:<7.2f}% | {pf:<8.2f}")
    print("="*85)

if __name__ == "__main__":
    run_ablation_test()
