import streamlit as st
import pandas as pd
from streamlit_lightweight_charts import renderLightweightCharts

st.set_page_config(layout="wide")
st.title("Lightweight Charts Test")

df = pd.DataFrame({
    'datetime': pd.date_range(start='2024-01-01', periods=100, freq='D'),
    'open': 100,
    'high': 105,
    'low': 95,
    'close': 102
})

df['time'] = df['datetime'].dt.strftime('%Y-%m-%d')
candles = df[['time', 'open', 'high', 'low', 'close']].to_dict('records')

chartOptions = {
    "layout": {"textColor": "black", "background": {"type": "solid", "color": "white"}},
    "width": 800,
    "height": 400
}

series = [{
    "type": "Candlestick",
    "data": candles,
    "options": {
        "upColor": "#ff4b4b",
        "downColor": "#2b7cff",
        "borderVisible": False,
        "wickUpColor": "#ff4b4b",
        "wickDownColor": "#2b7cff"
    }
}]

renderLightweightCharts([{"chart": chartOptions, "series": series}])
