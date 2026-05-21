import traceback
try:
    from data import get_us_stock_data
    df = get_us_stock_data(["AAPL", "NVDA"])
    print("SUCCESS")
    print(df)
except Exception as e:
    print("ERROR:")
    traceback.print_exc()
