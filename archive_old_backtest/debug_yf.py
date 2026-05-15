import yfinance as yf
df = yf.download("005930.KS", period="1d", interval="5m", progress=False)
print("Columns:", df.columns)
print("Index Name:", df.index.name)
df_reset = df.reset_index()
print("Reset Columns:", df_reset.columns)
