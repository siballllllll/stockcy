"""국내(KR) 시장 데이터 라우터 — KIS Open API 기반."""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List

router = APIRouter()


class BulkCodesBody(BaseModel):
    codes: List[str]


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
def kr_stock_price(code: str, fundamental: bool = Query(False, description="PER/PBR 등 펀더멘털 보강(네이버 스크래핑) — 검색 상세에서만 true")):
    """국내 종목 현재가 (KIS API). fundamental=true일 때만 PER/PBR 네이버 보강(느림).
    기본 false — 가격만 필요한 다수 호출부(보유·즐겨찾기·대시보드)의 불필요한 네트워크 지연 방지."""
    from data_kr import get_kr_stock_price
    result = get_kr_stock_price(code, with_fundamental=fundamental)
    # [교정] KIS가 보합(등락률 0%·이전가)을 주는 경우(장 초반·KOSDAQ) → bulk와 동일한 KRX 가격캐시(FDR)로
    # 가격·등락률을 교정. bulk는 정상인데 종목별 KIS만 0%로 나오던 문제를 모든 호출부에서 한 번에 해결.
    if result and abs(float(result.get("change_pct") or 0)) < 0.005:
        try:
            from api.main import KRX_PRICE_CACHE
            hit = KRX_PRICE_CACHE.get(str(code).strip().zfill(6))
            if hit and (hit.get("price") or 0) > 0 and abs(float(hit.get("change_pct") or 0)) >= 0.01:
                result["price"] = hit["price"]
                result["change_pct"] = hit["change_pct"]
                result["sign"] = "2" if hit["change_pct"] > 0 else "4"
        except Exception:
            pass
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


@router.get("/supply-power-flow")
def kr_supply_power_flow():
    """실시간 외국인·기관(세력) 자금 흐름 — 시장별 유입/이탈 + 동반매수 강도."""
    import data_kr
    try:
        return data_kr.get_supply_power_flow()
    except Exception as e:
        return {"error": str(e), "markets": {}}


@router.get("/supply-rotation")
def kr_supply_rotation():
    """세력 자금 이동 추적 — 직전 스냅샷 대비 자금이 더 들어온/빠진 종목 (히스토리 기반)."""
    import data_kr
    try:
        return data_kr.detect_supply_rotation()
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.get("/supply-cumulative")
def kr_supply_cumulative(days: int = 20, market: str = ""):
    """기간 누적 세력 매집 TOP — 최근 days일 합산 외국인·기관 순매수 + 매집 지속일.
    오늘 하루가 아니라 '일정 기간 꾸준히 사 모은' 종목."""
    from db import load_cumulative_supply
    return load_cumulative_supply(days=days, market=(market or None))


@router.post("/supply-snapshot")
def kr_supply_snapshot():
    """오늘의 외국인·기관 수급 스냅샷 즉시 저장 (종목 + 섹터). 스케줄러도 매일 호출."""
    import data_kr
    try:
        stock_res = data_kr.snapshot_frgn_inst_today()
        sector_res = data_kr.snapshot_sector_flow_today()
        return {**stock_res, "sector": sector_res}
    except Exception as e:
        return {"saved": 0, "error": str(e)}


@router.get("/sector-rotation")
def kr_sector_rotation():
    """섹터 자금 로테이션 — 어느 섹터로 세력 자금이 들어오고/빠지는지 (히스토리 기반)."""
    import data_kr
    try:
        return data_kr.detect_sector_rotation()
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.get("/sector-trend")
def kr_sector_trend(days: int = 10, top_n: int = 10):
    """최근 N거래일 섹터 자금 추세 — 누적·연속 유입일·일별 시계열 (추세 차트용)."""
    import data_kr
    try:
        return data_kr.compute_sector_trend(days, top_n)
    except Exception as e:
        return {"dates": [], "sectors": [], "error": str(e)}


@router.get("/sector-flow")
def kr_sector_flow(days: int = 14, sector: str | None = None):
    """섹터별 수급 흐름 시계열 (최근 N거래일)."""
    from db import load_sector_flow_series, load_sector_flow_dates
    try:
        return {"dates": load_sector_flow_dates(days), "series": load_sector_flow_series(sector, days)}
    except Exception as e:
        return {"dates": [], "series": [], "error": str(e)}


@router.post("/sector-flow/backfill")
def kr_sector_flow_backfill(days: int = 20):
    """pykrx로 과거 N거래일 섹터 수급을 동기 백필 (소량용; 대량은 backfill-bg)."""
    import data_kr
    try:
        return data_kr.backfill_sector_flow_pykrx(days)
    except Exception as e:
        return {"filled": 0, "error": str(e)}


@router.post("/sector-flow/backfill-bg")
def kr_sector_flow_backfill_bg(days: int = 500, throttle: float = 0.25):
    """대량 섹터 백필을 백그라운드에서 시작 (throttle로 KRX 차단 방지, 즉시 반환).
    이미 적재된 날짜는 건너뛰어 증분/재개됨. 진행률은 backfill-status로 확인."""
    import data_kr
    try:
        return data_kr.start_sector_backfill_bg(days, throttle)
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/sector-flow/backfill-status")
def kr_sector_flow_backfill_status():
    """백그라운드 섹터 백필 진행 상황."""
    import data_kr
    try:
        return data_kr.sector_backfill_status()
    except Exception as e:
        return {"running": False, "error": str(e)}


@router.get("/sector-analysis")
def kr_sector_analysis():
    """섹터 흐름 히스토리 분석 — 지속 매집/이탈 섹터, 유입 일관성, 최장 연속유입."""
    import data_kr
    try:
        return data_kr.analyze_sector_flow_history()
    except Exception as e:
        return {"available": False, "error": str(e)}


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
    """국내 종목 복수 시세 일괄 조회 — 인메모리 캐시 즉시 반환 (캐시 미스는 0원 반환)."""
    from api.main import KRX_PRICE_CACHE
    _default = {"status_code": "55", "mrkt_warn": "00", "short_over": "N",
                "managed": "N", "halt": "N", "vi_type": "N", "vi_ovtm": "N"}
    code_list = [c.strip().zfill(6) for c in codes.split(",") if c.strip()]
    # 종목명 보강 — 캐시엔 가격만 있어 name=code(티커)로 나오던 문제(즐겨찾기 등). 코드→이름 맵(ETF 포함) 사용.
    try:
        from data_kr import get_kr_code_to_name_map
        name_map = get_kr_code_to_name_map()
    except Exception:
        name_map = {}

    if KRX_PRICE_CACHE:
        result = {}
        for code in code_list:
            nm = name_map.get(code, code)
            hit = KRX_PRICE_CACHE.get(code)
            if hit:
                result[code] = {"name": nm, **hit, **_default}
            else:
                result[code] = {"name": nm, "price": 0, "change_pct": 0.0, **_default}
        return result

    # 캐시 미준비 시 기존 방식 폴백
    fns = _kr()
    code_tuple = tuple((c, c + ".KS") for c in code_list)
    try:
        return fns["prices_bulk"](code_tuple) or {}
    except Exception as e:
        return {"error": str(e)}


@router.get("/overtime-bulk")
def kr_overtime_bulk(codes: str = Query(..., description="콤마로 구분된 종목코드 — 시간외 단일가 일괄 조회")):
    """국내 종목 시간외 단일가(장 마감 후) 일괄 조회 (네이버). 데이터 없는 종목은 생략."""
    from data_kr import get_kr_overtime_price
    import concurrent.futures
    code_list = [c.strip().zfill(6) for c in codes.split(",") if c.strip()][:40]
    result: dict = {}
    if not code_list:
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(get_kr_overtime_price, c): c for c in code_list}
        for fut in concurrent.futures.as_completed(futs):
            try:
                d = fut.result()
                if d:
                    result[futs[fut]] = d
            except Exception:
                pass
    return result


@router.post("/stocks-bulk")
def kr_stocks_bulk_post(body: BulkCodesBody):
    """국내 종목 복수 시세 일괄 조회 (POST — 대량 코드 지원, 431 방지)."""
    fns = _kr()
    code_list = tuple((c.strip(), c.strip() + ".KS") for c in body.codes if c.strip())
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
