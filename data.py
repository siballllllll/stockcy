import pandas as pd
import streamlit as st
import yfinance as yf
import urllib3

# 방화벽 우회를 위한 SSL 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@st.cache_data(ttl=60) # 1분 단위 캐싱
def get_us_stock_data(tickers):
    """
    Yahoo Finance API를 사용하여 미국 주식 티커의 실시간 가격 및 등락률 데이터를 가져옵니다.
    """
    if not tickers:
        return pd.DataFrame()

    data = []
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.fast_info
            
            current_price = info['lastPrice'] if 'lastPrice' in info else 0
            prev_close = info['previousClose'] if 'previousClose' in info else 0
            
            if current_price > 0 and prev_close > 0:
                change_pct = ((current_price - prev_close) / prev_close) * 100
                
                data.append({
                    "심볼": ticker,
                    "현재가($)": round(current_price, 2),
                    "등락률(%)": round(change_pct, 2),
                    "상태": "상승 🟢" if change_pct > 0 else ("하락 🔴" if change_pct < 0 else "보합 ⚪")
                })
        except Exception as e:
            continue
            
    if not data:
        st.warning("데이터를 불러오지 못했습니다. 종목 코드를 확인하거나 네트워크 상태를 점검해주세요.")
        return pd.DataFrame()

    df = pd.DataFrame(data)
    return df
