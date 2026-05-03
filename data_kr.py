import requests
import streamlit as st
import pandas as pd

KIS_BASE = "https://openapi.koreainvestment.com:9443"


@st.cache_data(ttl=43200)  # 12시간 캐싱 (KIS 토큰 유효기간 24시간)
def get_kis_token():
    """KIS Open API 액세스 토큰 발급"""
    try:
        resp = requests.post(
            f"{KIS_BASE}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": st.secrets["kis"]["app_key"],
                "appsecret": st.secrets["kis"]["app_secret"],
            },
            timeout=10,
        )
        data = resp.json()
        return data.get("access_token")
    except Exception:
        return None


def _headers(tr_id: str) -> dict:
    token = get_kis_token()
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": st.secrets["kis"]["app_key"],
        "appsecret": st.secrets["kis"]["app_secret"],
        "tr_id": tr_id,
        "custtype": "P",
    }


def _get(path: str, tr_id: str, params: dict):
    """KIS API GET 요청 공통 함수. 실패 시 None 반환."""
    try:
        resp = requests.get(
            f"{KIS_BASE}{path}",
            headers=_headers(tr_id),
            params=params,
            timeout=10,
        )
        data = resp.json()
        return data if data.get("rt_cd") == "0" else None
    except Exception:
        return None


@st.cache_data(ttl=60)
def get_kr_stock_price(stock_code: str):
    """국내 주식 현재가 및 기본 정보 조회 (KIS API → yfinance 폴백, 1분 캐싱)"""
    data = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        "FHKST01010100",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": stock_code},
    )
    if data:
        o = data["output"]
        return {
            "code": stock_code,
            "name": o.get("hts_kor_isnm", stock_code),
            "price": int(o.get("stck_prpr", 0) or 0),
            "change": int(o.get("prdy_vrss", 0) or 0),
            "change_pct": float(o.get("prdy_ctrt", 0) or 0),
            "sign": o.get("prdy_vrss_sign", "3"),
            "volume": int(o.get("acml_vol", 0) or 0),
            "amount": int(o.get("acml_tr_pbmn", 0) or 0),
            "open": int(o.get("stck_oprc", 0) or 0),
            "high": int(o.get("stck_hgpr", 0) or 0),
            "low": int(o.get("stck_lwpr", 0) or 0),
            "w52_high": int(o.get("w52hgpr", 0) or 0),
            "w52_low": int(o.get("w52lwpr", 0) or 0),
            "per": o.get("per", "-"),
            "pbr": o.get("pbr", "-"),
            "market_cap": o.get("hts_avls", "-"),
        }

    # KIS API 실패 → yfinance 폴백 (.KS 우선, .KQ 차선)
    import yfinance as yf
    for suffix in [".KS", ".KQ"]:
        try:
            tk = yf.Ticker(f"{stock_code}{suffix}")
            fi = tk.fast_info
            info = tk.info
            price = round(fi.get("lastPrice", 0) or 0)
            prev  = fi.get("previousClose", 0) or 0
            if price <= 0:
                continue
            change     = round(price - prev)
            change_pct = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
            sign = "2" if change > 0 else "4" if change < 0 else "3"
            name = (info.get("shortName") or info.get("longName") or stock_code)
            return {
                "code": stock_code,
                "name": name,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "sign": sign,
                "volume": int(fi.get("lastVolume", 0) or 0),
                "amount": 0,
                "open":     round(fi.get("open", 0) or 0),
                "high":     round(fi.get("dayHigh", 0) or 0),
                "low":      round(fi.get("dayLow", 0) or 0),
                "w52_high": round(fi.get("fiftyTwoWeekHigh", 0) or 0),
                "w52_low":  round(fi.get("fiftyTwoWeekLow", 0) or 0),
                "per": round(info.get("trailingPE", 0) or 0, 1) or "-",
                "pbr": round(info.get("priceToBook", 0) or 0, 2) or "-",
                "market_cap": "-",
                "_source": "yfinance",
            }
        except Exception:
            continue
    return None


@st.cache_data(ttl=60)
def get_kr_investor_trend(stock_code: str):
    """종목별 외국인/기관/개인 순매수 동향 (최근 5영업일)"""
    data = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-investor",
        "FHKST01010900",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": stock_code},
    )
    if not data:
        return []
    results = []
    for item in data.get("output", [])[:5]:
        d = item.get("stck_bsop_date", "")
        if len(d) == 8:
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        results.append({
            "날짜": d,
            "개인": int(item.get("prsn_ntby_qty", 0) or 0),
            "외국인": int(item.get("frgn_ntby_qty", 0) or 0),
            "기관": int(item.get("orgn_ntby_qty", 0) or 0),
        })
    return results


@st.cache_data(ttl=60)
def get_kr_market_index():
    """KOSPI / KOSDAQ 지수 실시간 조회"""
    result = {}
    for name, code in [("KOSPI", "0001"), ("KOSDAQ", "1001")]:
        data = _get(
            "/uapi/domestic-stock/v1/quotations/inquire-index-price",
            "FHPUP02100000",
            {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": code},
        )
        if data:
            o = data["output"]
            result[name] = {
                "index": float(o.get("bstp_nmix_prpr", 0) or 0),
                "change": float(o.get("bstp_nmix_prdy_vrss", 0) or 0),
                "change_pct": float(o.get("prdy_ctrt", 0) or 0),
            }
    return result


@st.cache_data(ttl=60)
def get_kr_minute_chart(stock_code: str, interval: int = 5):
    """국내 주식 분봉 OHLCV (yfinance .KS/.KQ 자동 감지, KIS는 수급 전용)"""
    import yfinance as yf

    # yfinance가 지원하는 최소 인터벌로 fetch 후 리샘플
    if interval <= 5:
        yf_interval = "1m"
    elif interval <= 15:
        yf_interval = "5m"
    else:
        yf_interval = "15m"

    df = pd.DataFrame()
    for suffix in [".KS", ".KQ"]:
        try:
            raw = yf.Ticker(f"{stock_code}{suffix}").history(
                period="1d", interval=yf_interval, auto_adjust=True
            )
            if not raw.empty:
                raw.index = raw.index.tz_convert("Asia/Seoul")
                raw.index = raw.index.tz_localize(None)
                df = raw.reset_index()[["Datetime", "Open", "High", "Low", "Close", "Volume"]]
                df.columns = ["datetime", "open", "high", "low", "close", "volume"]
                break
        except Exception:
            continue

    if df.empty:
        return pd.DataFrame()

    # 요청 인터벌로 리샘플 (yf_interval과 다를 때만)
    if yf_interval != f"{interval}m":
        df = df.set_index("datetime")
        df = df.resample(f"{interval}min").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna().reset_index()

    return df


@st.cache_data(ttl=60)
def get_kr_prices_bulk(tickers_tuple: tuple) -> dict:
    """섹터 패널용 종목 일괄 시세 조회 (code → {price, change_pct})"""
    import yfinance as yf
    results = {}
    for code, yf_ticker in tickers_tuple:
        try:
            fi = yf.Ticker(yf_ticker).fast_info
            price = round(fi.get("lastPrice", 0) or 0)
            prev = fi.get("previousClose", 0) or 0
            change_pct = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
            results[code] = {"price": price, "change_pct": change_pct}
        except Exception:
            results[code] = {"price": 0, "change_pct": 0.0}
    return results


# ── 미국 주식 KIS API ────────────────────────────────────────────────────────
# 거래소 코드: sectors_us.py exchange → KIS EXCD
_KIS_EXCD = {"NASDAQ": "NAS", "NYSE": "NYS", "AMEX": "AMS"}


@st.cache_data(ttl=60)
def get_us_stock_price_kis(ticker: str, exchange: str = "NASDAQ"):
    """KIS API 해외주식 현재가 → yfinance 폴백"""
    excd = _KIS_EXCD.get(exchange.upper(), "NAS")
    data = _get(
        "/uapi/overseas-price/v1/quotations/price",
        "HHDFS76200200",
        {"AUTH": "", "EXCD": excd, "SYMB": ticker},
    )
    if data:
        o = data.get("output", {})
        price = float(o.get("last", 0) or 0)
        if price > 0:
            return {
                "name":       (o.get("name") or ticker).strip(),
                "price":      price,
                "change":     float(o.get("diff", 0) or 0),
                "change_pct": float(o.get("rate", 0) or 0),
                "sign":       o.get("sign", "3"),
                "volume":     int(o.get("tvol", 0) or 0),
                "open":       float(o.get("open", 0) or 0),
                "high":       float(o.get("high", 0) or 0),
                "low":        float(o.get("low", 0) or 0),
                "w52_high":   float(o.get("h52p", 0) or 0),
                "w52_low":    float(o.get("l52p", 0) or 0),
                "per":        o.get("perx", "-") or "-",
                "pbr":        o.get("pbry", "-") or "-",
                "market_cap": "-",
                "exchange":   exchange,
                "_source":    "kis",
            }
    # KIS 실패 → yfinance 폴백
    import yfinance as yf
    try:
        tk   = yf.Ticker(ticker)
        fi   = tk.fast_info
        info = tk.info
        p    = round(fi.get("lastPrice", 0) or 0, 2)
        prev = fi.get("previousClose", 0) or 0
        if p > 0:
            ch  = round(p - prev, 2)
            chp = round((ch / prev * 100) if prev > 0 else 0, 2)
            mktcap = info.get("marketCap", 0) or 0
            return {
                "name":       info.get("longName", ticker),
                "price":      p,
                "change":     ch,
                "change_pct": chp,
                "sign":       "2" if ch > 0 else "4" if ch < 0 else "3",
                "volume":     int(fi.get("lastVolume", 0) or 0),
                "open":       round(fi.get("open", 0) or 0, 2),
                "high":       round(fi.get("dayHigh", 0) or 0, 2),
                "low":        round(fi.get("dayLow", 0) or 0, 2),
                "w52_high":   round(fi.get("fiftyTwoWeekHigh", 0) or 0, 2),
                "w52_low":    round(fi.get("fiftyTwoWeekLow", 0) or 0, 2),
                "per":        round(info.get("trailingPE", 0) or 0, 1) or "-",
                "pbr":        round(info.get("priceToBook", 0) or 0, 2) or "-",
                "market_cap": f"${mktcap/1e9:.1f}B" if mktcap >= 1e9 else "-",
                "exchange":   exchange,
                "_source":    "yfinance",
            }
    except Exception:
        pass
    return None


@st.cache_data(ttl=60)
def get_us_prices_bulk_kis(tickers_exchange_tuple: tuple) -> dict:
    """섹터 패널용 미국 종목 일괄 시세 조회 (KIS → yfinance 폴백)"""
    import yfinance as yf
    results = {}
    for ticker, exchange in tickers_exchange_tuple:
        excd = _KIS_EXCD.get(exchange.upper(), "NAS")
        data = _get(
            "/uapi/overseas-price/v1/quotations/price",
            "HHDFS76200200",
            {"AUTH": "", "EXCD": excd, "SYMB": ticker},
        )
        if data:
            o = data.get("output", {})
            price = float(o.get("last", 0) or 0)
            if price > 0:
                results[ticker] = {
                    "price":      price,
                    "change_pct": float(o.get("rate", 0) or 0),
                }
                continue
        # yfinance 폴백
        try:
            fi   = yf.Ticker(ticker).fast_info
            p    = round(fi.get("lastPrice", 0) or 0, 2)
            prev = fi.get("previousClose", 0) or 0
            chp  = round(((p - prev) / prev * 100) if prev > 0 else 0, 2)
            results[ticker] = {"price": p, "change_pct": chp}
        except Exception:
            results[ticker] = {"price": 0.0, "change_pct": 0.0}
    return results


@st.cache_data(ttl=300)  # 5분 캐싱
def get_kr_volume_ranking():
    """거래량 상위 10개 종목 (KOSPI)"""
    data = _get(
        "/uapi/domestic-stock/v1/ranking/volume",
        "FHPST01710000",
        {
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20171",
            "fid_input_iscd": "0000",
            "fid_div_cls_code": "0",
            "fid_blng_cls_code": "0",
            "fid_trgt_cls_code": "111111111",
            "fid_trgt_exls_cls_code": "000000",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_input_date_1": "",
        },
    )
    if not data:
        return []
    results = []
    for item in data.get("output", [])[:10]:
        change_pct = float(item.get("prdy_ctrt", 0) or 0)
        results.append({
            "종목코드": item.get("mksc_shrn_iscd", ""),
            "종목명": item.get("hts_kor_isnm", ""),
            "현재가": f"₩{int(item.get('stck_prpr', 0) or 0):,}",
            "등락률(%)": change_pct,
            "거래량": f"{int(item.get('acml_vol', 0) or 0):,}주",
            "상태": "상승 🔴" if change_pct > 0 else ("하락 🔵" if change_pct < 0 else "보합 ⚪"),
        })
    return results


@st.cache_data(ttl=60)
def get_kr_index_history(symbol: str, period: str = "1d") -> pd.DataFrame:
    """KOSPI(^KS11) / KOSDAQ(^KQ11) 지수 히스토리 (yfinance)"""
    import yfinance as yf
    _interval_map = {
        "1d":  "5m",
        "5d":  "30m",
        "1mo": "1d",
        "3mo": "1d",
        "1y":  "1d",
    }
    interval = _interval_map.get(period, "1d")
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        if df.index.tz is not None:
            df.index = df.index.tz_convert("Asia/Seoul").tz_localize(None)
        df = df.reset_index()
        dt_col = "Datetime" if "Datetime" in df.columns else "Date"
        df = df[[dt_col, "Close"]].rename(columns={dt_col: "datetime", "Close": "close"})
        return df
    except Exception:
        return pd.DataFrame()
