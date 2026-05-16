"""smoke test for signal_logic.py"""
import pandas as pd
import numpy as np
from signal_logic import detect_signal, detect_signal_detail, SIGNAL_SCORE_THRESHOLD

np.random.seed(42)
prev = pd.date_range("2024-01-12 09:00", periods=20, freq="5min")
base = pd.date_range("2024-01-15 09:00", periods=30, freq="5min")

rows = []
for dt in prev:
    rows.append({"datetime": dt, "open": 10000, "high": 10100, "low": 9900, "close": 10050, "volume": 1000})
for i, dt in enumerate(base):
    vol = 5000 if i >= 24 else 1000  # last 6 bars: vol 5x surge
    close = 10080 + i * 10           # consecutive rising closes
    rows.append({"datetime": dt, "open": close - 50, "high": close + 50, "low": close - 100, "close": close, "volume": vol})

df = pd.DataFrame(rows)

# idx=49 = last bar of the test day (index 20+29=49)
result = detect_signal_detail(df, idx=49)
print("=== signal_logic smoke test ===")
print("threshold  :", SIGNAL_SCORE_THRESHOLD)
print("signal     :", result["signal"])
print("score      :", result["score"])
print("vol_accel  :", result["vol_accel"])
print("vol_ratio  :", result["vol_ratio"])
print("consol_brk :", result["consol_break"])
print("candle_seq :", result["candle_seq"])
print("above_ma   :", result["above_ma"])

# basic sanity: vol_accel should be > 1 given 5x volume surge in last 6 bars
assert result["vol_accel"] > 1.0, f"expected vol_accel > 1, got {result['vol_accel']}"
# candle_seq: all 30 base bars have close > open (close - open = 50), so True
assert result["candle_seq"] is True, "expected candle_seq True"

print("=== PASS ===")
