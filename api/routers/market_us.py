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


import threading

_US_ALL_STOCKS_CACHE = None
_US_ALL_STOCKS_LOCK = threading.Lock()

def _load_all_us_stocks():
    global _US_ALL_STOCKS_CACHE
    if _US_ALL_STOCKS_CACHE is not None:
        return _US_ALL_STOCKS_CACHE
        
    with _US_ALL_STOCKS_LOCK:
        if _US_ALL_STOCKS_CACHE is not None:
            return _US_ALL_STOCKS_CACHE

        from sectors_us import US_SECTOR_MAP
        result: dict[str, str] = {}
        for sectors in US_SECTOR_MAP.values():
            for stocks in sectors.values():
                for s in stocks:
                    result[s["ticker"]] = s["name"]
        
        # FDR 백그라운드 로드
        def _fetch_fdr():
            try:
                import FinanceDataReader as fdr
                from us_kr_names import get_kr_name, US_KR_NAME_MAP
                temp_map = result.copy()
                
                # 수동 매핑 사전의 한글 주식명을 최우선으로 적재
                for ticker, kr_name in US_KR_NAME_MAP.items():
                    temp_map[ticker] = kr_name
                
                for ex in ['NASDAQ', 'NYSE', 'AMEX']:
                    try:
                        df = fdr.StockListing(ex)
                        for _, row in df.iterrows():
                            t = str(row['Symbol'])
                            n = str(row['Name'])
                            if t not in temp_map:
                                temp_map[t] = get_kr_name(t, n)
                            else:
                                # 이미 존재하더라도 수동 매핑 사전에 최신화된 정보가 있다면 우선 적용
                                if t in US_KR_NAME_MAP:
                                    temp_map[t] = US_KR_NAME_MAP[t]
                    except Exception:
                        pass
                global _US_ALL_STOCKS_CACHE
                _US_ALL_STOCKS_CACHE = temp_map
            except Exception:
                pass
        
        threading.Thread(target=_fetch_fdr, daemon=True).start()
        _US_ALL_STOCKS_CACHE = result
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
    """USD/KRW 실시간 환율 (yfinance USDKRW=X)."""
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
                return {"rate": round(rate, 2), "symbol": "USDKRW", "fallback": False}
        except Exception:
            yf_breaker.record_failure()
    return {"rate": 1350.0, "symbol": "USDKRW", "fallback": True}


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
