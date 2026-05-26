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
        get_us_prices_bulk_kis, get_kr_frgn_inst_rank,
        get_kr_code_to_name_map,
    )
    return {
        "index":          get_kr_market_index,
        "price":          get_kr_stock_price,
        "volume_rank":    get_kr_volume_ranking,
        "change_rank":    get_kr_change_ranking,
        "investor":       get_kr_investor_trend,
        "frgn_inst_rank": get_kr_frgn_inst_rank,
        "minute_chart":   get_kr_minute_chart,
        "daily_chart":    get_kr_daily_chart,
        "prices_bulk":    get_kr_prices_bulk,
        "index_history":  get_kr_index_history,
        "stock_name":     get_kr_stock_name_kis,
        "code_to_name":   get_kr_code_to_name_map,
        "us_bulk_kis":    get_us_prices_bulk_kis,
    }


def _parse_price(v) -> int:
    """'₩299,500' → 299500, 또는 이미 int/float 이면 그대로."""
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).replace("₩", "").replace(",", "").replace("주", "").strip()
    try:
        return int(float(s))
    except Exception:
        return 0


def _normalize_ranking(records: list) -> list:
    """거래량 상위 결과의 현재가·거래량 포맷 문자열을 숫자로 변환."""
    out = []
    for r in records:
        out.append({
            "종목코드":  str(r.get("종목코드", "")),
            "종목명":    str(r.get("종목명", "")),
            "현재가":    _parse_price(r.get("현재가", 0)),
            "등락률(%)": float(r.get("등락률(%)", 0)),
            "거래량":    _parse_price(r.get("거래량", 0)),
            "시장":      str(r.get("시장", "")),
        })
    return out


def _rename_chart_cols(df) -> list:
    """DataFrame(datetime/open/high/low/close/volume) → ChartCandle JSON 형태."""
    col_map = {
        "datetime": "일자", "open": "시가", "high": "고가",
        "low": "저가", "close": "종가", "volume": "거래량",
    }
    df = df.rename(columns=col_map)
    if "일자" in df.columns:
        df["일자"] = df["일자"].astype(str)
    return df.to_dict(orient="records")


def _period_int_to_str(n: int) -> str:
    """정수 거래일수를 get_kr_daily_chart 기간 문자열로 변환."""
    if n <= 5:   return "1w"
    if n <= 22:  return "15d"
    if n <= 35:  return "1mo"
    if n <= 95:  return "3mo"
    if n <= 185: return "6mo"
    if n <= 370: return "1y"
    return "2y"


@router.get("/indices")
def kr_indices():
    """KOSPI / KOSDAQ 현재 지수."""
    fns = _kr()
    try:
        result = fns["index"]()   # returns {"KOSPI": {...}, "KOSDAQ": {...}}
        return result or {}
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


@router.get("/stocks/all")
def kr_stocks_all():
    """전체 종목 코드 및 이름 맵 반환 (검색 자동완성용)."""
    fns = _kr()
    try:
        name_map = fns["code_to_name"]()
        # { "005930": "삼성전자", ... } 형태로 바로 반환
        return name_map or {}
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
    """KIS API로 종목코드 → 종목명 조회. (실패 시 로컬 맵 폴백)"""
    fns = _kr()
    name, err = fns["stock_name"](code)
    if not name:
        try:
            name_map = fns["code_to_name"]()
            name = name_map.get(code, "")
        except Exception:
            name = ""
    return {"code": code, "name": name or ""}


@router.get("/volume-ranking")
def kr_volume_ranking(market: str = Query("ALL", description="KOSPI | KOSDAQ | ALL (현재 구현은 KOSPI 고정)")):
    """거래량 상위 종목 랭킹 — get_kr_volume_ranking()은 인자 없음."""
    fns = _kr()
    try:
        data = fns["volume_rank"]()   # 인자 없음
        return _normalize_ranking(data or [])
    except Exception as e:
        return {"error": str(e)}


@router.get("/change-ranking")
def kr_change_ranking(
    market: str = Query("ALL", description="KOSPI | KOSDAQ | ALL"),
):
    """등락률 상위 종목 랭킹."""
    fns = _kr()
    # get_kr_change_ranking(market: str = "J") — J=KOSPI, Q=KOSDAQ
    mkt_code = "Q" if market.upper() == "KOSDAQ" else "J"
    try:
        data = fns["change_rank"](mkt_code)
        return _normalize_ranking(data or [])
    except Exception as e:
        return {"error": str(e)}


@router.get("/investor-trend")
def kr_investor_trend(market: str = Query("KOSPI")):
    """외국인·기관 순매수 상위 종목 (시장 전체 기준)."""
    fns = _kr()
    mkt_code = "Q" if market.upper() == "KOSDAQ" else "J"
    try:
        data = fns["frgn_inst_rank"](mkt_code)
        return data or []
    except Exception as e:
        return {"error": str(e)}


@router.get("/stocks/{code}/investor-trend")
def kr_investor_trend_by_code(code: str):
    """개별 종목의 외국인/기관 수급 데이터 조회."""
    import data_kr
    try:
        df = data_kr.get_kr_investor_trend(code)
        if hasattr(df, "to_dict"):
            return df.to_dict(orient="records")
        return df or []
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
def kr_daily_chart(
    code: str, 
    period: int = Query(60, description="최근 N 거래일"),
    unit: str = Query("D", description="D: 일봉, W: 주봉, M: 월봉")
):
    """국내 종목 일봉/주봉/월봉 차트 데이터 (ChartCandle 형태)."""
    fns = _kr()
    period_str = _period_int_to_str(period)
    try:
        # data_kr.get_kr_daily_chart(stock_code, period, unit) 형태로 호출하도록 처리
        df = fns["daily_chart"](code, period_str, unit)
        if hasattr(df, "to_dict") and not df.empty:
            return _rename_chart_cols(df)
        return []
    except Exception as e:
        return {"error": str(e)}


@router.get("/stocks-bulk")
def kr_stocks_bulk(codes: str = Query(..., description="콤마로 구분된 종목코드 목록")):
    """국내 종목 복수 시세 일괄 조회."""
    fns = _kr()
    # get_kr_prices_bulk expects tuples of (code, yf_ticker)
    # Since suffix isn't provided here, fallback to .KS (KIS API works regardless)
    code_list = tuple((c.strip(), c.strip() + ".KS") for c in codes.split(",") if c.strip())
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


@router.get("/today-market")
async def kr_today_market():
    """오늘의 시장 요약 + 급등 종목 분석 (analyze_today_market)."""
    import asyncio
    from ai_engine import analyze_today_market
    try:
        result = await asyncio.to_thread(analyze_today_market)
        return result or {}
    except Exception as e:
        return {"error": str(e)}
