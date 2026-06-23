"""미국 시장 데이터 라우터 — yfinance 기반."""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List

router = APIRouter()


class UsBulkBody(BaseModel):
    tickers: List[str]


@router.post("/prices-bulk")
def us_prices_bulk(body: UsBulkBody):
    """US 종목 일괄 시세 — KIS 해외시세 우선(+yfinance 보완), 60초 인메모리 캐시.
    거래소(EXCD)는 서버가 US 섹터맵에서 해석. 반환: {ticker: {price, change_pct}}."""
    from db import us_ticker_exchange_map
    from data_kr import get_us_prices_bulk_kis
    exmap = us_ticker_exchange_map()
    # 캐시 적중률을 위해 정렬된 튜플로 전달
    pairs = tuple(sorted(
        (t.strip().upper(), exmap.get(t.strip().upper(), "NASDAQ"))
        for t in body.tickers if t and t.strip()
    ))
    return get_us_prices_bulk_kis(pairs)

# 지연 import (data.py 의 무거운 의존성을 요청 시점에만 로드)
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


@router.get("/kr-names")
def us_kr_names_lookup(tickers: str = Query(..., description="콤마 구분 US 티커")):
    """US 티커 → 한글 종목명 맵 (us_kr_names.US_KR_NAME_MAP). 즐겨찾기 한글화용."""
    from us_kr_names import US_KR_NAME_MAP
    out = {}
    for t in tickers.split(","):
        t = t.strip().upper()
        if t and t in US_KR_NAME_MAP:
            out[t] = US_KR_NAME_MAP[t]
    return out


import threading

_US_ALL_STOCKS_CACHE = None     # 검색 자동완성용 {ticker: 한글/영문명}
_US_FULL_LOADED = False          # FDR 전체 상장목록 로드 성공 여부
_US_FETCH_INPROGRESS = False     # 백그라운드 FDR 로드 진행 중 여부
_US_ALL_STOCKS_LOCK = threading.Lock()


def _fetch_fdr_us():
    """FDR로 NASDAQ/NYSE/AMEX 전체 상장 종목을 받아 캐시에 병합.
    성공해야 _US_FULL_LOADED=True. 실패하면 플래그가 False로 남아 다음 호출에서 재시도된다."""
    global _US_ALL_STOCKS_CACHE, _US_FULL_LOADED, _US_FETCH_INPROGRESS
    try:
        import FinanceDataReader as fdr
        from us_kr_names import get_kr_name, US_KR_NAME_MAP
        temp_map = dict(_US_ALL_STOCKS_CACHE or {})
        # 수동 한글명 매핑 최우선 적재
        for ticker, kr_name in US_KR_NAME_MAP.items():
            temp_map[ticker] = kr_name
        got_any = False
        for ex in ['NASDAQ', 'NYSE', 'AMEX']:
            try:
                df = fdr.StockListing(ex)
                if df is None or df.empty:
                    continue
                for _, row in df.iterrows():
                    t = str(row['Symbol'])
                    n = str(row['Name'])
                    if t not in temp_map:
                        temp_map[t] = get_kr_name(t, n)
                    elif t in US_KR_NAME_MAP:
                        temp_map[t] = US_KR_NAME_MAP[t]
                got_any = True
            except Exception:
                pass
        if got_any:
            _US_ALL_STOCKS_CACHE = temp_map
            _US_FULL_LOADED = True
            print(f"[US stocks] 전체 상장목록 로드 완료: {len(temp_map)}종목")
        else:
            print("[US stocks] FDR 상장목록 로드 실패 — 다음 요청 때 재시도")
    except Exception as e:
        print(f"[US stocks] 로드 오류: {e}")
    finally:
        _US_FETCH_INPROGRESS = False


def _load_all_us_stocks():
    """미국 종목 {ticker: 이름} 맵 반환 (검색 자동완성용).
    기본 큐레이션 목록을 즉시 제공하고, FDR 전체 목록은 백그라운드로 로드한다.
    [자가복구] FDR 로드가 실패해도 작은 목록에 갇히지 않고 다음 호출에서 재시도한다."""
    global _US_ALL_STOCKS_CACHE, _US_FETCH_INPROGRESS

    # 1) 기본 큐레이션 목록(US_SECTOR_MAP) 즉시 확보
    if _US_ALL_STOCKS_CACHE is None:
        with _US_ALL_STOCKS_LOCK:
            if _US_ALL_STOCKS_CACHE is None:
                from sectors_us import US_SECTOR_MAP
                result: dict[str, str] = {}
                for sectors in US_SECTOR_MAP.values():
                    for stocks in sectors.values():
                        for s in stocks:
                            result[s["ticker"]] = s["name"]
                _US_ALL_STOCKS_CACHE = result

    # 2) 전체 목록이 아직 안 실렸고 진행 중도 아니면 백그라운드 로드(재)시도
    if not _US_FULL_LOADED and not _US_FETCH_INPROGRESS:
        with _US_ALL_STOCKS_LOCK:
            if not _US_FULL_LOADED and not _US_FETCH_INPROGRESS:
                _US_FETCH_INPROGRESS = True
                threading.Thread(target=_fetch_fdr_us, daemon=True).start()

    return _US_ALL_STOCKS_CACHE

@router.get("/stocks/all")
def us_stocks_all():
    """US 전체 종목 티커 → 한국어 이름 맵 반환 (검색 자동완성용)."""
    try:
        return _load_all_us_stocks()
    except Exception:
        return {}


@router.get("/stocks/{ticker}")
def us_stock_detail(ticker: str, exchange: str = Query("NASDAQ")):
    """미국 개별 종목 상세 (현재가, 지표, 재무 요약)."""
    from api.circuit import yf_breaker
    if yf_breaker.is_open():
        return {}  # 시세 소스 장애 중 — 즉시 반환
    _, _, get_detail, _ = _data()
    result = get_detail(ticker.upper(), exchange)
    if result:
        yf_breaker.record_success()
    return result or {}


@router.get("/chart/{ticker}")
def us_chart(
    ticker: str,
    period: str = Query("1y", description="yfinance period: 1d,5d,1mo,3mo,6mo,1y,2y,5y"),
    interval: str = Query("1d", description="yfinance interval: 1m,5m,15m,30m,60m,1d,1wk,1mo"),
):
    """미국 주식 OHLCV 차트 데이터 (yfinance 기반). 분봉 포함."""
    from api.circuit import yf_breaker
    if yf_breaker.is_open():
        return []  # 시세 소스 장애 중 — 스레드 점유 없이 즉시 반환
    try:
        import yfinance as yf
        is_minute = interval.endswith("m") and interval != "1mo"
        df = yf.Ticker(ticker.upper()).history(period=period, interval=interval, auto_adjust=True, prepost=is_minute, timeout=4)
        yf_breaker.record_success()
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
        yf_breaker.record_failure()
        return []


@router.get("/crypto/{symbol}")
def crypto_price(symbol: str = "BTC"):
    """암호화폐 현재가 (yfinance BTC-USD 등)."""
    from api.circuit import yf_breaker
    if not yf_breaker.is_open():
        try:
            import yfinance as yf
            ticker = f"{symbol.upper()}-USD"
            fi = yf.Ticker(ticker).fast_info
            price = float(fi.get("regularMarketPrice", 0) or fi.get("lastPrice", 0) or 0)
            prev  = float(fi.get("previousClose", 0) or 0)
            change_pct = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
            if price > 0:
                yf_breaker.record_success()
                return {"symbol": symbol.upper(), "price": round(price, 2), "change_pct": change_pct}
        except Exception:
            yf_breaker.record_failure()
    return {"symbol": symbol.upper(), "price": 0, "change_pct": 0, "error": True}


@router.get("/exchange-rate")
def us_exchange_rate():
    """USD/KRW 실시간 환율 — 토스 환율 우선, yfinance(USDKRW=X) 폴백, 최후 1350."""
    # 1순위: 토스 참고 환율 (1분 갱신, 안정적)
    try:
        import toss_api
        rate = toss_api.get_exchange_rate("USD", "KRW")
        if rate and rate > 0:
            return {"rate": round(rate, 2), "symbol": "USDKRW", "fallback": False, "source": "toss"}
    except Exception:
        pass

    # 2순위: yfinance
    from api.circuit import yf_breaker
    if not yf_breaker.is_open():
        try:
            import yfinance as yf
            fi = yf.Ticker("USDKRW=X").fast_info
            rate = float(fi.get("regularMarketPrice", 0) or fi.get("lastPrice", 0) or 0)
            if rate <= 0:
                hist = yf.Ticker("USDKRW=X").history(period="2d", timeout=4)
                if not hist.empty:
                    rate = float(hist["Close"].iloc[-1])
            if rate > 0:
                yf_breaker.record_success()
                return {"rate": round(rate, 2), "symbol": "USDKRW", "fallback": False, "source": "yfinance"}
        except Exception:
            yf_breaker.record_failure()
    return {"rate": 1350.0, "symbol": "USDKRW", "fallback": True, "source": "default"}


@router.get("/treasury-10y")
def us_treasury_10y():
    """미 10년물 국채금리 (yfinance ^TNX)."""
    from api.circuit import yf_breaker
    if not yf_breaker.is_open():
        try:
            import yfinance as yf
            hist = yf.Ticker("^TNX").history(period="5d", timeout=4)
            if not hist.empty:
                cur = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cur
                yf_breaker.record_success()
                return {"yield": round(cur, 3), "change": round(cur - prev, 3), "fallback": False}
        except Exception:
            yf_breaker.record_failure()
    return {"yield": 0.0, "change": 0.0, "fallback": True}


@router.get("/exchange-rates-historical")
def us_exchange_rates_historical(dates: str = Query(..., description="콤마로 구분된 YYYY-MM-DD 날짜")):
    """여러 날짜에 대한 USD/KRW 종가 환율 반환 (로컬 파일 캐싱 지원)"""
    import os
    import json
    import datetime
    
    date_list = [d.strip() for d in dates.split(",") if d.strip()]
    if not date_list:
        return {}

    cache_dir = "data_csv"
    cache_path = os.path.join(cache_dir, "fx_historical_cache.json")
    
    # 1. 캐시 디렉토리 생성 및 로드
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
        
    cache_data = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except Exception:
            cache_data = {}

    final_result = {}
    missing_dates = []

    # 2. 캐시에서 먼저 확인
    for d in date_list:
        if d in cache_data:
            final_result[d] = cache_data[d]
        else:
            missing_dates.append(d)

    # 3. 누락된 날짜만 yfinance로 조회 (소스 장애 시 브레이커가 건너뜀)
    from api.circuit import yf_breaker
    if missing_dates and not yf_breaker.is_open():
        try:
            import yfinance as yf
            start_date = min(missing_dates)
            start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d") - datetime.timedelta(days=7)
            end_dt = datetime.datetime.strptime(max(missing_dates), "%Y-%m-%d") + datetime.timedelta(days=2)

            hist = yf.Ticker("USDKRW=X").history(
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                timeout=5,
            )
            yf_breaker.record_success()
            
            rates_by_date = {}
            for dt, row in hist.iterrows():
                date_str = str(dt)[:10]
                rates_by_date[date_str] = round(float(row.Close), 2)

            # yfinance 성공 시 캐시에 병합 및 파일 쓰기
            if rates_by_date:
                sorted_avail = sorted(list(rates_by_date.keys()) + list(cache_data.keys()))
                all_rates = {**cache_data, **rates_by_date}
                
                new_cached_entries = {}
                for d in missing_dates:
                    closest_date = next((x for x in reversed(sorted_avail) if x <= d and x in all_rates), None)
                    if closest_date:
                        rate_val = all_rates[closest_date]
                    else:
                        closest_future = next((x for x in sorted_avail if x >= d and x in all_rates), None)
                        rate_val = all_rates[closest_future] if closest_future else 1350.0
                    
                    final_result[d] = rate_val
                    new_cached_entries[d] = rate_val
                
                # 파일에 업데이트 사항 저장
                cache_data.update(new_cached_entries)
                try:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            else:
                raise ValueError("yfinance returned empty data")
                
        except Exception as e:
            yf_breaker.record_failure()
            print("yfinance fetch error, fallback to cache/default:", e)
            sorted_avail = sorted(cache_data.keys())
            for d in missing_dates:
                closest_date = next((x for x in reversed(sorted_avail) if x <= d), None)
                if closest_date:
                    final_result[d] = cache_data[closest_date]
                else:
                    closest_future = next((x for x in sorted_avail if x >= d), None)
                    final_result[d] = cache_data[closest_future] if closest_future else 1350.0

    elif missing_dates:
        # 브레이커 개방 중 — yfinance 건너뛰고 캐시/기본값으로 채움 (응답 누락 방지)
        sorted_avail = sorted(cache_data.keys())
        for d in missing_dates:
            closest_date = next((x for x in reversed(sorted_avail) if x <= d), None)
            if closest_date:
                final_result[d] = cache_data[closest_date]
            else:
                closest_future = next((x for x in sorted_avail if x >= d), None)
                final_result[d] = cache_data[closest_future] if closest_future else 1350.0

    return final_result


@router.get("/sector-map")
def us_sector_map():
    """미국 섹터 맵 (섹터 → 세부섹터 → 종목 목록)."""
    from db import load_us_sector_map
    return load_us_sector_map()
