import yfinance as yf
import pandas as pd
import time
import sys
import io

# 인코딩 설정
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from signal_logic import prepare_df, detect_signal_detail

TICKERS = [
    "005930.KS", "000660.KS", "373220.KS", "005380.KS", "005490.KS",
    "035420.KS", "000270.KS", "068270.KS", "035720.KS", "028260.KS"
]

def run_test():
    print("Step 3: 10 stocks data download (history method) and optimized signal test starting...")
    
    results = []
    total_start = time.time()
    
    for ticker_id in TICKERS:
        print(f"Downloading {ticker_id}...", end="\r")
        try:
            # history()는 MultiIndex를 생성하지 않아 더 안정적임
            t = yf.Ticker(ticker_id)
            df = t.history(period="1mo", interval="5m")
            
            if df.empty:
                print(f"Error {ticker_id}: No data")
                continue
            
            df = df.reset_index()
            df.columns = [str(c).lower() for c in df.columns]
            
            # yfinance history()는 보통 'Datetime' 컬럼을 가짐
            if 'datetime' not in df.columns:
                # 첫 번째 컬럼이 시간 데이터인 경우가 많음
                df = df.rename(columns={df.columns[0]: 'datetime'})
            
            # 1. 지표 사전 계산 (최적화)
            prep_start = time.time()
            df_prep = prepare_df(df)
            prep_end = time.time()
            
            # 2. 시그널 루프
            signals_found = []
            loop_start = time.time()
            for idx in range(len(df_prep)):
                detail = detect_signal_detail(df_prep, idx)
                if detail['signal']:
                    signals_found.append(idx)
            loop_end = time.time()
            
            results.append({
                "ticker": ticker_id,
                "bars": len(df),
                "signals": len(signals_found),
                "prep_time": prep_end - prep_start,
                "loop_time": loop_end - loop_start
            })
            print(f"Done {ticker_id}: {len(df)} bars, {len(signals_found)} signals")
            
        except Exception as e:
            print(f"Error {ticker_id}: {e}")
            
    total_end = time.time()
    print("\n" + "="*65)
    print(f"Test Summary (Total Time: {total_end - total_start:.2f}s)")
    print("="*65)
    print(f"{'Ticker':<12} | {'Bars':<6} | {'Signals':<8} | {'Prep(s)':<10} | {'Loop(s)':<10}")
    print("-" * 65)
    for r in results:
        print(f"{r['ticker']:<12} | {r['bars']:<6} | {r['signals']:<8} | {r['prep_time']:<10.4f} | {r['loop_time']:<10.4f}")
    print("="*65)

if __name__ == "__main__":
    run_test()
