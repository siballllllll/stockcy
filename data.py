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


@st.cache_data(ttl=60)
def get_us_market_indices():
    """S&P 500, NASDAQ, DOW, VIX 실시간 지수 조회"""
    symbols = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI", "VIX": "^VIX"}
    results = {}
    for name, symbol in symbols.items():
        try:
            fi = yf.Ticker(symbol).fast_info
            price = fi.get('lastPrice', 0) or 0
            prev = fi.get('previousClose', 0) or 0
            change = price - prev
            results[name] = {
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct": round((change / prev * 100) if prev > 0 else 0, 2),
            }
        except Exception:
            pass
    return results


@st.cache_data(ttl=60)
def get_us_stock_detail(ticker: str):
    """미국 주식 상세 정보 조회 (시가/고저/52주/PER/PBR/기관보유율 등)"""
    try:
        stock = yf.Ticker(ticker)
        fi = stock.fast_info
        info = stock.info
        price = fi.get('lastPrice', 0) or 0
        prev = fi.get('previousClose', 0) or 0
        change = price - prev
        mktcap = info.get('marketCap', 0) or 0
        inst_pct = round((info.get('heldPercentInstitutions', 0) or 0) * 100, 1)
        insider_pct = round((info.get('heldPercentInsiders', 0) or 0) * 100, 1)
        return {
            "name": info.get('longName', ticker),
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round((change / prev * 100) if prev > 0 else 0, 2),
            "volume": int(fi.get('lastVolume', 0) or 0),
            "avg_volume": int(fi.get('threeMonthAverageVolume', 0) or 0),
            "open": round(fi.get('open', 0) or 0, 2),
            "high": round(fi.get('dayHigh', 0) or 0, 2),
            "low": round(fi.get('dayLow', 0) or 0, 2),
            "w52_high": round(fi.get('fiftyTwoWeekHigh', 0) or 0, 2),
            "w52_low": round(fi.get('fiftyTwoWeekLow', 0) or 0, 2),
            "market_cap": f"${mktcap/1e9:.1f}B" if mktcap >= 1e9 else f"${mktcap/1e6:.0f}M" if mktcap >= 1e6 else "-",
            "per": round(info.get('trailingPE', 0) or 0, 1) or "-",
            "pbr": round(info.get('priceToBook', 0) or 0, 2) or "-",
            "institutional_pct": inst_pct,
            "insider_pct": insider_pct,
            "sector": info.get('sector', ''),
            "beta": round(info.get('beta', 0) or 0, 2),
        }
    except Exception:
        return None
