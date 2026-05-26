from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
import numpy as np

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
    from sectors_us import US_SECTOR_MAP
    result = {}
    if sector_name == "전체":
        for sec, subs in US_SECTOR_MAP.items():
            for sub, items in subs.items():
                for item in items:
                    result[item['ticker']] = item['name']
    else:
        if sector_name in US_SECTOR_MAP:
            for sub, items in US_SECTOR_MAP[sector_name].items():
                for item in items:
                    result[item['ticker']] = item['name']
    return result

@router.post("/run")
def run_screener(req: ScreenerRequest):
    """
    초고속 yfinance 일괄 다운로드 엔진 기반 복합 스크리너
    """
    results = []
    import yfinance as yf
    
    if req.market == "KR":
        tickers_map = _get_kr_sector_stocks(req.sector)
        if not tickers_map:
            return {"results": []}
            
        suffix_map = _get_krx_suffix_map()
        yf_tickers = [suffix_map.get(code, code + ".KS") for code in tickers_map.keys()]
        yf_to_code = {suffix_map.get(code, code + ".KS"): code for code in tickers_map.keys()}
        
        try:
            raw = yf.download(yf_tickers, period="1y", auto_adjust=True, progress=False, threads=True)
            if raw is not None and not raw.empty:
                is_multi = isinstance(raw.columns, pd.MultiIndex)
                for yf_tk in yf_tickers:
                    code = yf_to_code[yf_tk]
                    if is_multi:
                        if yf_tk not in raw.columns.levels[1]:
                            continue
                        df_t = raw.xs(yf_tk, axis=1, level=1).dropna()
                    else:
                        df_t = raw.dropna()
                        
                    if not df_t.empty:
                        df_t = df_t.rename(columns=str.lower)
                        res = _check_conditions(code, tickers_map[code], df_t, req.conditions)
                        if res:
                            results.append(res)
        except Exception as e:
            print("KR Screener Error:", e)
                    
    elif req.market == "US":
        tickers_map = _get_us_sector_stocks(req.sector)
        if not tickers_map:
            return {"results": []}
            
        tickers_list = list(tickers_map.keys())
        try:
            raw = yf.download(tickers_list, period="1y", auto_adjust=True, progress=False, threads=True)
            if raw is not None and not raw.empty:
                is_multi = isinstance(raw.columns, pd.MultiIndex)
                for ticker in tickers_list:
                    if is_multi:
                        if ticker not in raw.columns.levels[1]:
                            continue
                        df_t = raw.xs(ticker, axis=1, level=1).dropna()
                    else:
                        df_t = raw.dropna()
                    
                    if not df_t.empty:
                        df_t = df_t.rename(columns=str.lower)
                        res = _check_conditions(ticker, tickers_map[ticker], df_t, req.conditions)
                        if res:
                            results.append(res)
        except Exception as e:
            print("US Screener Error:", e)

    # 1순위: 매칭된 개수 내림차순, 2순위: 등락률 내림차순 정렬
    results.sort(key=lambda x: (-x['match_count'], -x['change_pct']))
    return {"results": results}
