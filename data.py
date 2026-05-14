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
def get_us_stock_detail(ticker: str, exchange: str = "NASDAQ"):
    """미국 주식 상세 정보 조회 (KIS 현재가 + yfinance 보조지표)"""
    # KIS로 실시간 가격 먼저 조회
    kis_data = None
    try:
        from data_kr import get_us_stock_price_kis
        kis_data = get_us_stock_price_kis(ticker, exchange)
    except Exception:
        pass

    try:
        stock = yf.Ticker(ticker)
        fi = stock.fast_info
        info = stock.info

        if kis_data and kis_data.get("price", 0) > 0:
            price      = kis_data["price"]
            change     = kis_data["change"]
            change_pct = kis_data["change_pct"]
            volume     = kis_data["volume"]
            open_p     = kis_data["open"]
            high_p     = kis_data["high"]
            low_p      = kis_data["low"]
            w52_high   = kis_data["w52_high"]
            w52_low    = kis_data["w52_low"]
            per        = kis_data["per"]
            pbr        = kis_data["pbr"]
            name       = kis_data["name"]
        else:
            price      = round(fi.get('lastPrice', 0) or 0, 2)
            prev       = fi.get('previousClose', 0) or 0
            change     = round(price - prev, 2)
            change_pct = round((change / prev * 100) if prev > 0 else 0, 2)
            volume     = int(fi.get('lastVolume', 0) or 0)
            open_p     = round(fi.get('open', 0) or 0, 2)
            high_p     = round(fi.get('dayHigh', 0) or 0, 2)
            low_p      = round(fi.get('dayLow', 0) or 0, 2)
            w52_high   = round(fi.get('fiftyTwoWeekHigh', 0) or 0, 2)
            w52_low    = round(fi.get('fiftyTwoWeekLow', 0) or 0, 2)
            per        = round(info.get('trailingPE', 0) or 0, 1) or "-"
            pbr        = round(info.get('priceToBook', 0) or 0, 2) or "-"
            name       = info.get('longName', ticker)

        mktcap      = info.get('marketCap', 0) or 0
        inst_pct    = round((info.get('heldPercentInstitutions', 0) or 0) * 100, 1)
        insider_pct = round((info.get('heldPercentInsiders', 0) or 0) * 100, 1)
        return {
            "name":             name,
            "price":            price,
            "change":           change,
            "change_pct":       change_pct,
            "volume":           volume,
            "avg_volume":       int(fi.get('threeMonthAverageVolume', 0) or 0),
            "open":             open_p,
            "high":             high_p,
            "low":              low_p,
            "w52_high":         w52_high,
            "w52_low":          w52_low,
            "market_cap":       f"${mktcap/1e9:.1f}B" if mktcap >= 1e9 else f"${mktcap/1e6:.0f}M" if mktcap >= 1e6 else "-",
            "per":              per,
            "pbr":              pbr,
            "institutional_pct": inst_pct,
            "insider_pct":      insider_pct,
            "sector":           info.get('sector', ''),
            "beta":             round(info.get('beta', 0) or 0, 2),
            "exchange":         info.get('exchange', exchange),
            "pre_price":        round(info.get('preMarketPrice', 0) or 0, 2),
            "pre_change":       round(info.get('preMarketChange', 0) or 0, 2),
            "pre_pct":          round((info.get('preMarketChangePercent', 0) or 0) * 100, 2),
            "post_price":       round(info.get('postMarketPrice', 0) or 0, 2),
            "post_change":      round(info.get('postMarketChange', 0) or 0, 2),
            "post_pct":         round((info.get('postMarketChangePercent', 0) or 0) * 100, 2),
        }
    except Exception:
        return kis_data  # yfinance 실패 시 KIS 데이터라도 반환


def get_us_market_session() -> dict:
    """현재 미국 시장 세션 상태 반환 (ET 기준)"""
    from datetime import datetime
    try:
        import pytz
        et = datetime.now(pytz.timezone('America/New_York'))
    except Exception:
        from datetime import timezone, timedelta
        et = datetime.now(timezone(timedelta(hours=-4)))  # EDT 근사
    h, m, wd = et.hour, et.minute, et.weekday()
    t = h * 60 + m
    et_str = et.strftime("%I:%M %p ET")
    if wd >= 5:
        return {"session": "closed", "label": "⛔ 주말 휴장", "color": "#555", "et_time": et_str}
    if 4*60 <= t < 9*60+30:
        return {"session": "pre",     "label": "🌅 프리마켓",    "color": "#f5c518", "et_time": et_str}
    elif 9*60+30 <= t < 16*60:
        return {"session": "regular", "label": "🟢 정규 마켓",   "color": "#00c853", "et_time": et_str}
    elif 16*60 <= t < 20*60:
        return {"session": "after",   "label": "🌙 애프터마켓",  "color": "#7b61ff", "et_time": et_str}
    else:
        return {"session": "closed",  "label": "⛔ 장 마감",     "color": "#555",    "et_time": et_str}


@st.cache_data(ttl=60)
def get_us_prices_bulk(tickers_tuple: tuple) -> dict:
    """섹터 패널용 미국 종목 일괄 시세 조회 (ticker → {price, change_pct})"""
    results = {}
    for ticker in tickers_tuple:
        try:
            fi = yf.Ticker(ticker).fast_info
            price = round(fi.get("lastPrice", 0) or 0, 2)
            prev = fi.get("previousClose", 0) or 0
            change = round(price - prev, 2) if prev > 0 else 0.0
            change_pct = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
            results[ticker] = {"price": price, "change": change, "change_pct": change_pct}
        except Exception:
            results[ticker] = {"price": 0.0, "change": 0.0, "change_pct": 0.0}
    return results
