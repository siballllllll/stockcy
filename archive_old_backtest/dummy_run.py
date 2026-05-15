import yfinance as yf
import os
import pandas as pd
import sys
import io

# 인코딩 설정
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backtest_phase1_filters import run_ablation_test

def dummy_run():
    print("Work 1: Pipeline integrity check starting...")
    
    if not os.path.exists("./data_csv"):
        os.makedirs("./data_csv")
        
    test_tickers = ["005930.KS", "000660.KS"]
    for t in test_tickers:
        print(f"   - Creating dummy data for {t}...")
        df = yf.Ticker(t).history(period="1mo", interval="5m")
        df = df.reset_index()
        df.columns = [str(c).lower() for c in df.columns]
        if 'datetime' not in df.columns:
            df = df.rename(columns={df.columns[0]: 'datetime'})
        
        df.to_csv(f"./data_csv/{t.split('.')[0]}.csv", index=False)
        
    print("\nPhase 1 Ablation Test Running (Dummy)...")
    try:
        run_ablation_test()
        print("\nPipeline Test Success: Table printed without errors.")
    except Exception as e:
        print(f"\nPipeline Test Failed: Error - {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    dummy_run()
