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


@router.get("/stocks/{ticker}")
def us_stock_detail(ticker: str, exchange: str = Query("NASDAQ")):
    """미국 개별 종목 상세 (현재가, 지표, 재무 요약)."""
    _, _, get_detail, _ = _data()
    result = get_detail(ticker.upper(), exchange)
    return result or {}


@router.get("/sector-map")
def us_sector_map():
    """미국 섹터 맵 (섹터 → 세부섹터 → 종목 목록)."""
    from db import load_us_sector_map
    return load_us_sector_map()
