from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
import numpy as np
import st_compat as st

router = APIRouter()

class ScreenerRequest(BaseModel):
    market: str
    sector: str
    conditions: List[str]

def _calculate_macd(df, fast=12, slow=26, signal=9):
    """MACD 선 및 시그널 선 계산 (종가 기준)"""
    if df.empty or len(df) < slow + signal:
        return None, None
    close = df['close'] if 'close' in df.columns else df['종가']
    exp1 = close.ewm(span=fast, adjust=False).mean()
    exp2 = close.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd, sig

def _check_conditions(ticker: str, name: str, df: pd.DataFrame, conditions: List[str]) -> dict:
    if df is None or df.empty or len(df) < 20:
        return None
    
    # 최근 행 데이터
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    close = float(latest['close'] if 'close' in df.columns else latest['종가'])
    volume = float(latest['volume'] if 'volume' in df.columns else latest.get('거래량', 0))
    prev_close = float(prev['close'] if 'close' in df.columns else prev['종가'])
    change_pct = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0.0
    
    matched_conditions = []
    
    # 1. 52w_high: 과거 250거래일 기준 최고가의 95% 이상
    if "52w_high" in conditions:
        high_col = 'high' if 'high' in df.columns else '고가'
        recent_250 = df.tail(250)
        if len(recent_250) > 40: # 최소 데이터 신뢰 기준
            w52_high = recent_250[high_col].max()
            if close >= w52_high * 0.95:
                matched_conditions.append("52주 신고가 근접")
    
    # 2. volume_spike: 당일 거래량이 최근 5일 평균 거래량의 300% 이상
    if "volume_spike" in conditions:
        vol_col = 'volume' if 'volume' in df.columns else '거래량'
        recent_5 = df.tail(6).iloc[:-1] # 오늘 제외 최근 5일
        avg_vol = recent_5[vol_col].mean()
        if avg_vol > 0 and volume >= avg_vol * 3.0:
            matched_conditions.append("거래량 급증(300% 이상)")
            
    # 3. macd_golden_cross: MACD 선이 시그널 선을 상향 돌파 (오늘 MACD > Signal 이고, 어제 MACD <= Signal)
    if "macd_golden_cross" in conditions:
        macd, sig = _calculate_macd(df)
        if macd is not None and sig is not None and len(macd) >= 2:
            if macd.iloc[-1] > sig.iloc[-1] and macd.iloc[-2] <= sig.iloc[-2]:
                matched_conditions.append("MACD 골든크로스")
                
    if not matched_conditions:
        return None
        
    # 다차원 매칭 랭킹 시스템 적용 (선택한 조건 중 많이 맞은 종목이 상단에 배치되도록 가중치 랭킹화)
    return {
        "ticker": ticker,
        "name": name,
        "price": close,
        "change_pct": change_pct,
        "volume": volume,
        "matched": matched_conditions,
        "match_count": len(matched_conditions)
    }

def _get_krx_suffix_map() -> dict:
    """국내 종목코드 대 KOSPI/KOSDAQ yfinance 접미사 맵 생성 (fdr 기반)"""
    try:
        import FinanceDataReader as fdr
        df = fdr.StockListing("KRX")
        suffix_map = {}
        for _, row in df.iterrows():
            code = str(row['Code']).zfill(6)
            mkt = str(row.get('Market', 'KOSPI')).upper()
            if "KOSDAQ" in mkt:
                suffix_map[code] = code + ".KQ"
            else:
                suffix_map[code] = code + ".KS"
        return suffix_map
    except Exception:
        return {}

def _get_kr_sector_stocks(sector_name: str) -> dict:
    from db import load_sector_map
    smap = load_sector_map()
    result = {}
    if sector_name == "전체":
        for sec, subs in smap.items():
            for sub, items in subs.items():
                for item in items:
                    result[item['code']] = item['name']
    else:
        if sector_name in smap:
            for sub, items in smap[sector_name].items():
                for item in items:
                    result[item['code']] = item['name']
    return result

def _get_us_sector_stocks(sector_name: str) -> dict:
    from db import load_us_sector_map
    sector_map = load_us_sector_map()
    result = {}
    if sector_name == "전체":
        for sec, subs in sector_map.items():
            for sub, items in subs.items():
                for item in items:
                    result[item['ticker']] = item['name']
    else:
        if sector_name in sector_map:
            for sub, items in sector_map[sector_name].items():
                for item in items:
                    result[item['ticker']] = item['name']
    return result

@st.cache_data(ttl=7200)
def _load_sector_ohlc(market: str, sector: str) -> dict:
    """섹터 종목들의 1년치 OHLC(소문자 컬럼)를 {code/ticker: DataFrame}로 반환.
    가장 무거운 단계(yfinance 일괄 다운로드)를 2시간 TTL 캐시로 묶어 재호출을 즉시화한다.
    (일봉 기반 스크리너라 2시간 staleness 허용. 백그라운드 워밍이 만료 전 재충전)
    조건 매칭은 이 캐시 위에서 매번 가볍게 수행하므로 사용자가 조건을 바꿔도 빠르다."""
    import yfinance as yf
    out: dict = {}

    if market == "KR":
        tickers_map = _get_kr_sector_stocks(sector)
        if not tickers_map:
            return {}
        suffix_map = _get_krx_suffix_map()
        yf_tickers = [suffix_map.get(code, code + ".KS") for code in tickers_map.keys()]
        yf_to_code = {suffix_map.get(code, code + ".KS"): code for code in tickers_map.keys()}
        keys = yf_tickers
        keymap = yf_to_code
    elif market == "US":
        tickers_map = _get_us_sector_stocks(sector)
        if not tickers_map:
            return {}
        keys = list(tickers_map.keys())
        keymap = {k: k for k in keys}
    else:
        return {}

    # yfinance 네트워크 장애 가드: 서킷 열려있으면 즉시 빈 결과(스레드풀 점유 방지)
    from api.circuit import yf_breaker
    if yf_breaker.is_open():
        print(f"[screener] {market}/{sector} 스킵 (yfinance 서킷 열림)")
        return {}

    try:
        # timeout 필수 — 없으면 DNS resolving이 수십 분 매달려 동기 스레드풀을 점유한다
        raw = yf.download(keys, period="1y", auto_adjust=True, progress=False, threads=True, timeout=12)
        if raw is None or raw.empty:
            yf_breaker.record_failure()
            return {}
        is_multi = isinstance(raw.columns, pd.MultiIndex)
        for yf_tk in keys:
            code = keymap[yf_tk]
            if is_multi:
                if yf_tk not in raw.columns.levels[1]:
                    continue
                df_t = raw.xs(yf_tk, axis=1, level=1).dropna()
            else:
                df_t = raw.dropna()
            if not df_t.empty:
                out[code] = df_t.rename(columns=str.lower)
        yf_breaker.record_success()
    except Exception as e:
        yf_breaker.record_failure()
        print(f"[screener] {market}/{sector} OHLC 다운로드 실패:", e)
    return out


def warm_screener_cache(sectors=("전체",), markets=("KR", "US")) -> dict:
    """백그라운드에서 섹터 OHLC 캐시를 미리 채운다(첫 호출 120초 타임아웃 방지).
    서버 시작 직후 + 매일 1회 호출 권장."""
    warmed = {}
    for mkt in markets:
        for sec in sectors:
            try:
                n = len(_load_sector_ohlc(mkt, sec))
                warmed[f"{mkt}/{sec}"] = n
            except Exception as e:
                warmed[f"{mkt}/{sec}"] = f"err: {e}"
    return warmed


@router.post("/run")
def run_screener(req: ScreenerRequest):
    """
    초고속 yfinance 일괄 다운로드 엔진 기반 복합 스크리너 (OHLC 30분 TTL 캐시)
    """
    results = []

    ohlc = _load_sector_ohlc(req.market, req.sector)
    if not ohlc:
        return {"results": []}

    # 종목명 매핑 (가벼움 — 캐시 대상 아님)
    if req.market == "KR":
        names = _get_kr_sector_stocks(req.sector)
    else:
        names = _get_us_sector_stocks(req.sector)

    for code, df_t in ohlc.items():
        res = _check_conditions(code, names.get(code, code), df_t, req.conditions)
        if res:
            results.append(res)

    # 1순위: 매칭된 개수 내림차순, 2순위: 등락률 내림차순 정렬
    results.sort(key=lambda x: (-x['match_count'], -x['change_pct']))
    return {"results": results}
