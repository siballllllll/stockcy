"""국내(KR) 시장 데이터 라우터 — KIS Open API 기반."""
from fastapi import APIRouter, Query

router = APIRouter()


def _kr():
    from data_kr import (
        get_kr_market_index, get_kr_stock_price,
        get_kr_volume_ranking, get_kr_change_ranking,
        get_kr_investor_trend, get_kr_minute_chart,
        get_kr_daily_chart, get_kr_prices_bulk,
        get_kr_index_history, get_kr_stock_name_kis,
        get_us_prices_bulk_kis,
    )
    return {
        "index":          get_kr_market_index,
        "price":          get_kr_stock_price,
        "volume_rank":    get_kr_volume_ranking,
        "change_rank":    get_kr_change_ranking,
        "investor":       get_kr_investor_trend,
        "minute_chart":   get_kr_minute_chart,
        "daily_chart":    get_kr_daily_chart,
        "prices_bulk":    get_kr_prices_bulk,
        "index_history":  get_kr_index_history,
        "stock_name":     get_kr_stock_name_kis,
        "us_bulk_kis":    get_us_prices_bulk_kis,
    }


@router.get("/indices")
def kr_indices():
    """KOSPI / KOSDAQ 현재 지수."""
    fns = _kr()
    try:
        kospi  = fns["index"]("KOSPI")
        kosdaq = fns["index"]("KOSDAQ")
        return {"KOSPI": kospi, "KOSDAQ": kosdaq}
    except Exception as e:
        return {"error": str(e)}


@router.get("/indices/{market}/history")
def kr_index_history(market: str, period: int = Query(20, description="최근 N 거래일")):
    """KOSPI 또는 KOSDAQ 지수 히스토리."""
    fns = _kr()
    try:
        data = fns["index_history"](market.upper(), period)
        if hasattr(data, "to_dict"):
            return data.to_dict(orient="records")
        return data or []
    except Exception as e:
        return {"error": str(e)}


@router.get("/stocks/{code}")
def kr_stock_price(code: str):
    """국내 종목 현재가 + 재무 지표 (KIS API)."""
    fns = _kr()
    result = fns["price"](code)
    return result or {"error": "데이터 없음"}


@router.get("/stocks/{code}/name")
def kr_stock_name(code: str):
    """KIS API로 종목코드 → 종목명 조회."""
    fns = _kr()
    name = fns["stock_name"](code)
    return {"code": code, "name": name or ""}


@router.get("/volume-ranking")
def kr_volume_ranking(market: str = Query("ALL", description="KOSPI | KOSDAQ | ALL")):
    """거래량 상위 종목 랭킹."""
    fns = _kr()
    try:
        data = fns["volume_rank"](market)
        return data or []
    except Exception as e:
        return {"error": str(e)}


@router.get("/change-ranking")
def kr_change_ranking(
    market: str  = Query("ALL"),
    direction: str = Query("up", description="up | down"),
):
    """등락률 상위/하위 종목 랭킹."""
    fns = _kr()
    try:
        data = fns["change_rank"](market, direction)
        return data or []
    except Exception as e:
        return {"error": str(e)}


@router.get("/investor-trend")
def kr_investor_trend(market: str = Query("KOSPI")):
    """외국인·기관 순매수 동향."""
    fns = _kr()
    try:
        data = fns["investor"](market)
        return data or []
    except Exception as e:
        return {"error": str(e)}


@router.get("/chart/{code}/minute")
def kr_minute_chart(code: str, interval: int = Query(5, description="분봉 단위 (1/5/15/30/60)")):
    """국내 종목 분봉 차트 데이터."""
    fns = _kr()
    try:
        df = fns["minute_chart"](code, interval)
        if hasattr(df, "to_dict"):
            return df.to_dict(orient="records")
        return df or []
    except Exception as e:
        return {"error": str(e)}


@router.get("/chart/{code}/daily")
def kr_daily_chart(code: str, period: int = Query(60, description="최근 N 거래일")):
    """국내 종목 일봉 차트 데이터."""
    fns = _kr()
    try:
        df = fns["daily_chart"](code, period)
        if hasattr(df, "to_dict"):
            return df.to_dict(orient="records")
        return df or []
    except Exception as e:
        return {"error": str(e)}


@router.get("/stocks-bulk")
def kr_stocks_bulk(codes: str = Query(..., description="콤마로 구분된 종목코드 목록")):
    """국내 종목 복수 시세 일괄 조회."""
    fns = _kr()
    code_list = tuple(c.strip() for c in codes.split(",") if c.strip())
    try:
        result = fns["prices_bulk"](code_list)
        return result or {}
    except Exception as e:
        return {"error": str(e)}


@router.get("/sector-map")
def kr_sector_map():
    """국내 섹터 맵 (섹터 → 세부섹터 → 종목)."""
    from db import load_sector_map
    try:
        return load_sector_map()
    except Exception as e:
        return {"error": str(e)}


@router.get("/hot-sectors")
async def kr_hot_sectors():
    """오늘의 핫 섹터 탐지 (AI 섹터 로테이션 분석)."""
    import asyncio
    from ai_engine import analyze_kr_hot_sectors
    try:
        result = await asyncio.to_thread(analyze_kr_hot_sectors)
        return result or []
    except Exception as e:
        return {"error": str(e)}
