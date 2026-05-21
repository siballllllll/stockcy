"""미국 시장 데이터 라우터 — yfinance 기반."""
from fastapi import APIRouter, Query
from typing import List

router = APIRouter()

# 지연 import (streamlit_mock 패치 이후 로드 보장)
def _data():
    from data import (
        get_us_stock_data, get_us_market_indices,
        get_us_stock_detail, get_us_market_session,
    )
    return get_us_stock_data, get_us_market_indices, get_us_stock_detail, get_us_market_session


@router.get("/indices")
def us_indices():
    """S&P500, NASDAQ, DOW, VIX 실시간 지수."""
    _, get_indices, _, _ = _data()
    return get_indices()


@router.get("/session")
def us_session():
    """현재 미국 장 세션 상태 (정규장/프리/애프터/마감)."""
    _, _, _, get_session = _data()
    try:
        return get_session()
    except Exception:
        return {"session": "unknown"}


@router.get("/stocks")
def us_stocks(tickers: str = Query(..., description="콤마로 구분된 티커 목록 예: AAPL,NVDA")):
    """미국 주식 복수 시세 조회."""
    get_stock_data, _, _, _ = _data()
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    df = get_stock_data(ticker_list)
    if df is None or df.empty:
        return []
    return df.to_dict(orient="records")


@router.get("/stocks/all")
def us_stocks_all():
    """US 전체 종목 티커 → 한국어 이름 맵 반환 (검색 자동완성용)."""
    try:
        from sectors_us import US_SECTOR_MAP
        result: dict[str, str] = {}
        for sectors in US_SECTOR_MAP.values():
            for stocks in sectors.values():
                for s in stocks:
                    result[s["ticker"]] = s["name"]
        return result
    except Exception:
        return {}


@router.get("/stocks/{ticker}")
def us_stock_detail(ticker: str, exchange: str = Query("NASDAQ")):
    """미국 개별 종목 상세 (현재가, 지표, 재무 요약)."""
    _, _, get_detail, _ = _data()
    result = get_detail(ticker.upper(), exchange)
    return result or {}


@router.get("/chart/{ticker}")
def us_chart(
    ticker: str,
    period: str = Query("1y", description="yfinance period: 1d,5d,1mo,3mo,6mo,1y,2y,5y"),
    interval: str = Query("1d", description="yfinance interval: 1m,5m,15m,30m,60m,1d,1wk,1mo"),
):
    """미국 주식 OHLCV 차트 데이터 (yfinance 기반). 분봉 포함."""
    try:
        import yfinance as yf
        is_minute = interval.endswith("m") and interval != "1mo"
        df = yf.Ticker(ticker.upper()).history(period=period, interval=interval, auto_adjust=True)
        if df is None or df.empty:
            return []
        records = []
        for dt, row in df.iterrows():
            # 분봉은 전체 datetime, 일봉 이상은 날짜만
            if is_minute:
                import pandas as pd
                ts = pd.Timestamp(dt)
                time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                time_str = str(dt)[:10]
            records.append({
                "일자":  time_str,
                "시가":  round(float(row.Open),  2),
                "고가":  round(float(row.High),  2),
                "저가":  round(float(row.Low),   2),
                "종가":  round(float(row.Close), 2),
                "거래량": int(row.Volume),
            })
        return records
    except Exception:
        return []


@router.get("/exchange-rate")
def us_exchange_rate():
    """USD/KRW 실시간 환율 (yfinance USDKRW=X)."""
    try:
        import yfinance as yf
        fi = yf.Ticker("USDKRW=X").fast_info
        rate = float(fi.get("regularMarketPrice", 0) or fi.get("lastPrice", 0) or 0)
        if rate <= 0:
            hist = yf.Ticker("USDKRW=X").history(period="2d")
            if not hist.empty:
                rate = float(hist["Close"].iloc[-1])
        if rate > 0:
            return {"rate": round(rate, 2), "symbol": "USDKRW", "fallback": False}
    except Exception:
        pass
    return {"rate": 1350.0, "symbol": "USDKRW", "fallback": True}


@router.get("/sector-map")
def us_sector_map():
    """미국 섹터 맵 (섹터 → 세부섹터 → 종목 목록)."""
    from db import load_us_sector_map
    return load_us_sector_map()
