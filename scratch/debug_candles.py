import sys
import os
import pandas as pd
from datetime import datetime

# 스톡시 경로 추가
sys.path.append(os.getcwd())

from data_kr import get_kr_minute_chart

def debug_chart_data(stock_code):
    print(f"--- Debugging Stock: {stock_code} ---")
    for iv in [1, 5, 15, 60]:
        df = get_kr_minute_chart(stock_code, interval=iv)
        if df.empty:
            print(f"Interval {iv}: EMPTY")
        else:
            print(f"Interval {iv}: {len(df)} rows")
            print(f"  First: {df['datetime'].iloc[0]}")
            print(f"  Last:  {df['datetime'].iloc[-1]}")
            # 중복 체크
            dupes = df[df['datetime'].duplicated()]
            if not dupes.empty:
                print(f"  WARNING: Found {len(dupes)} duplicate datetimes!")
            
            # 오늘 데이터 개수 체크
            today_str = datetime.now().strftime("%Y-%m-%d")
            today_df = df[df['datetime'].dt.strftime("%Y-%m-%d") == today_str]
            print(f"  Today's rows: {len(today_df)}")

if __name__ == "__main__":
    # 삼성전자(005930)로 테스트
    debug_chart_data("005930")
