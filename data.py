import pandas as pd
import streamlit as st
import yfinance as yf
import urllib3

# 방화벽 우회를 위한 SSL 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@st.cache_data(ttl=60) # 1분 단위 캐싱
def get_us_stock_data(tickers):
    """
    Yahoo Finance API를 사용하여 미국 주식 티커의 실시간 가격 및 등락률 데이터를 일괄적으로(Batch) 가져옵니다.
    """
    if not tickers:
        return pd.DataFrame()

    # 중복 제거 및 리스트화
    tickers_list = list(set([str(t).strip().upper() for t in tickers if str(t).strip()]))
    if not tickers_list:
        return pd.DataFrame()

    data = []
    try:
        # 단 한 번의 yf.download 호출로 병렬 다운로드 (극단적 네트워크 지연 방지를 위해 timeout=1.5초 제한)
        raw = yf.download(tickers_list, period="2d", interval="1d", progress=False, auto_adjust=True, timeout=1.5)
        if not raw.empty:
            close_df = raw["Close"]
            
            # 단일 티커면 Series → DataFrame 변환
            if len(tickers_list) == 1:
                t = tickers_list[0]
                closes = close_df.dropna()
                if len(closes) >= 2:
                    current_price = float(closes.iloc[-1])
                    prev_close = float(closes.iloc[-2])
                    change_pct = ((current_price - prev_close) / prev_close) * 100
                    status_icon = "상승 🟢" if change_pct > 0 else ("하락 🔴" if change_pct < 0 else "보합 ⚪")
                    data.append({
                        "심볼": t,
                        "현재가($)": round(current_price, 2),
                        "등락률(%)": round(change_pct, 2),
                        "상태": status_icon
                    })
            else:
                for t in tickers_list:
                    try:
                        closes = close_df[t].dropna()
                        if len(closes) >= 2:
                            current_price = float(closes.iloc[-1])
                            prev_close = float(closes.iloc[-2])
                            change_pct = ((current_price - prev_close) / prev_close) * 100
                            status_icon = "상승 🟢" if change_pct > 0 else ("하락 🔴" if change_pct < 0 else "보합 ⚪")
                            data.append({
                                "심볼": t,
                                "현재가($)": round(current_price, 2),
                                "등락률(%)": round(change_pct, 2),
                                "상태": status_icon
                            })
                        elif len(closes) == 1:
                            current_price = float(closes.iloc[-1])
                            data.append({
                                "심볼": t,
                                "현재가($)": round(current_price, 2),
                                "등락률(%)": 0.0,
                                "상태": "보합 ⚪"
                            })
                    except Exception:
                        pass
    except Exception as e:
        print(f"[get_us_stock_data] yfinance batch download failed: {e}")

    # 3. yfinance 일괄 조회가 실패했을 때의 KIS API 개별 조회 폴백 (방화벽/SSL 차단 우회 보장)
    if not data:
        for ticker in tickers_list:
            try:
                from data_kr import get_us_stock_price_kis
                kis_res = None
                for exch in ["NASDAQ", "NYSE", "AMEX"]:
                    try:
                        kis_res = get_us_stock_price_kis(ticker, exch)
                        if kis_res and kis_res.get("price", 0) > 0:
                            break
                    except Exception:
                        pass
                
                if kis_res and kis_res.get("price", 0) > 0:
                    price = float(kis_res["price"])
                    change_pct = float(kis_res.get("change_pct", 0) or 0)
                    status_icon = "상승 🟢" if change_pct > 0 else ("하락 🔴" if change_pct < 0 else "보합 ⚪")
                    data.append({
                        "심볼": ticker,
                        "현재가($)": round(price, 2),
                        "등락률(%)": round(change_pct, 2),
                        "상태": status_icon
                    })
            except Exception:
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
            reg_price  = round(fi.get('regularMarketPrice', 0) or price, 2)
            prev       = fi.get('regularMarketPreviousClose', 0) or fi.get('previousClose', 0) or 0
            change     = round(reg_price - prev, 2) if prev > 0 else 0.0
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
        # 연장 시간 거래(Pre/Post Market) 데이터 추출 보강
        pre_price  = round(info.get('preMarketPrice', 0) or 0, 2)
        pre_change = round(info.get('preMarketChange', 0) or 0, 2)
        pre_pct    = round((info.get('preMarketChangePercent', 0) or 0) * 100, 2)
        
        post_price  = round(info.get('postMarketPrice', 0) or 0, 2)
        post_change = round(info.get('postMarketChange', 0) or 0, 2)
        post_pct    = round((info.get('postMarketChangePercent', 0) or 0) * 100, 2)

        # fast_info는 소형주(페니주)에서 전일종가·52주가가 누락되거나 액면병합 잔재로
        # 왜곡되는 경우가 많다. 등락률이 0이거나 52주 범위가 비정상(현재가가 범위 밖)이면
        # 실제 일봉(분할조정 history)으로 보정한다.
        need_chg = (not change_pct) and bool(price and price > 0)
        need_w52 = (
            (not w52_high) or (not w52_low)
            or bool(price and (price > w52_high or price < w52_low))
            # 52주 고가/저가 비율이 비정상적으로 크면(예: 액면병합 잔재) 분할조정 일봉으로 재계산
            or bool(w52_high and w52_low and w52_high > w52_low * 50)
        )
        if need_chg or need_w52:
            try:
                hist = stock.history(period="1y", interval="1d", auto_adjust=True)
                if hist is not None and not hist.empty:
                    closes = hist["Close"].dropna()
                    if need_chg and len(closes) >= 2:
                        prev_c = float(closes.iloc[-2])
                        if prev_c > 0:
                            change = round(price - prev_c, 2)
                            change_pct = round((price - prev_c) / prev_c * 100, 2)
                    if need_w52:
                        hi = float(hist["High"].dropna().max()) if "High" in hist.columns else 0.0
                        lo = float(hist["Low"].dropna().min()) if "Low" in hist.columns else 0.0
                        if hi > 0:
                            w52_high = round(hi, 2)
                        if lo > 0:
                            w52_low = round(lo, 2)
            except Exception:
                pass

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
            "pre_price":        pre_price,
            "pre_change":       pre_change,
            "pre_pct":          pre_pct,
            "post_price":       post_price,
            "post_change":      post_change,
            "post_pct":         post_pct,
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


def get_usdkrw_rate(date_str: str) -> float:
    """로컬 SQLite 'exchange_rates'에서 환율을 우선 룩업하고, 캐시 미스 시에만 yfinance로 딱 1회 다운로드하여 로컬 DB에 영구 보존합니다."""
    target_date = date_str[:10]
    
    # 1. 로컬 SQLite DB에서 먼저 룩업
    try:
        from db import get_db_conn
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT rate FROM exchange_rates WHERE date_str = ?", (target_date,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return float(row["rate"])
    except Exception as e:
        print(f"Error reading exchange rate from local SQLite: {e}")
        
    # 2. 캐시 미스 시, yfinance를 이용해 특정 날짜 환율 단 1건만 조회
    rate = 1300.0
    try:
        import yfinance as yf
        from datetime import datetime, timedelta
        d = datetime.strptime(target_date, "%Y-%m-%d")
        end = (d + timedelta(days=5)).strftime("%Y-%m-%d")
        hist = yf.Ticker("USDKRW=X").history(start=target_date, end=end, interval="1d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[0])
        else:
            # 딕셔너리에 정확히 날짜가 없다면, 가장 가까운 이전 날짜 검색 시도 (최근 10일 탐색)
            hist_fallback = yf.Ticker("USDKRW=X").history(period="10d", interval="1d")
            if not hist_fallback.empty:
                rate = float(hist_fallback["Close"].iloc[-1])
    except Exception as e:
        print(f"Failed to fetch USD/KRW rate from yfinance: {e}")
        
    # 3. 조회한 환율을 로컬 SQLite DB에 기록하여 영구 보존 (다음번 조회 시 0.00001초 소요)
    try:
        from db import get_db_conn
        conn = get_db_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT OR REPLACE INTO exchange_rates (date_str, rate, updated_time) VALUES (?, ?, ?)",
            (target_date, float(rate), now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving exchange rate to local SQLite: {e}")
        
    return rate


@st.cache_data(ttl=60)
def get_us_prices_bulk(tickers_tuple: tuple) -> dict:
    """섹터 패널용 미국 종목 일괄 시세 조회 (ticker → {price, change_pct})"""
    tickers_list = list(set([str(t).strip().upper() for t in tickers_tuple if str(t).strip()]))
    if not tickers_list:
        return {}
        
    results = {}
    try:
        raw = yf.download(tickers_list, period="2d", interval="1d", progress=False, auto_adjust=True, timeout=1.5)
        if not raw.empty:
            close_df = raw["Close"]
            for t in tickers_list:
                try:
                    if len(tickers_list) == 1:
                        closes = close_df.dropna()
                    else:
                        closes = close_df[t].dropna()
                    if len(closes) >= 2:
                        current_price = float(closes.iloc[-1])
                        prev_close = float(closes.iloc[-2])
                        change_pct = ((current_price - prev_close) / prev_close) * 100
                        results[t] = {
                            "price": round(current_price, 2),
                            "change": round(current_price - prev_close, 2),
                            "change_pct": round(change_pct, 2)
                        }
                    elif len(closes) == 1:
                        current_price = float(closes.iloc[-1])
                        results[t] = {
                            "price": round(current_price, 2),
                            "change": 0.0,
                            "change_pct": 0.0
                        }
                except Exception:
                    results[t] = {"price": 0.0, "change": 0.0, "change_pct": 0.0}
    except Exception as e:
        print(f"[get_us_prices_bulk] Batch download failed: {e}")
        # 폴백: 배치 다운로드 실패 시 KIS API 미국 시세 고속 조회 폴백 (방화벽/SSL 차단 우회)
        from data_kr import get_us_stock_price_kis
        for ticker in tickers_list:
            try:
                kis_res = None
                for exch in ["NASDAQ", "NYSE", "AMEX"]:
                    try:
                        kis_res = get_us_stock_price_kis(ticker, exch)
                        if kis_res and kis_res.get("price", 0) > 0:
                            break
                    except Exception:
                        pass
                if kis_res and kis_res.get("price", 0) > 0:
                    price = float(kis_res["price"])
                    change_pct = float(kis_res.get("change_pct", 0) or 0)
                    results[ticker] = {
                        "price": round(price, 2),
                        "change": round(kis_res.get("change", 0.0), 2),
                        "change_pct": round(change_pct, 2)
                    }
                else:
                    results[ticker] = {"price": 0.0, "change": 0.0, "change_pct": 0.0}
            except Exception:
                results[ticker] = {"price": 0.0, "change": 0.0, "change_pct": 0.0}
                
    return results
