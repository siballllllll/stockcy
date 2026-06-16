"""[월街 스코어링 — 밸류에이션 결정론 파트 프로토타입]

100점 매트릭스의 1번 축(밸류에이션 30점)을 LLM 없이 '실데이터'로만 계산한다.
설계 철학: 추정 금지. 데이터가 없으면 점수를 지어내지 않고 N/A로 두고, 점수는
'사용 가능한 항목'에 대해서만 환산하며 신뢰도(coverage)를 함께 반환한다.
→ 사용자가 "어디까지가 사실이고 어디부터가 미산정인지" 알 수 있게 한다.

배점(요청한 매트릭스 그대로):
  A. PEG 비율            10점  : ≤1.0→10 / ≤1.5→7 / ≤2.0→4 / >2.0→0
  B. FCF Yield           10점  : ≥7%→10 / ≥4%→7 / ≥1%→3 / <1%→0
  C. EV/EBITDA 밴드 위치  10점  : 하단 소외→10 / 중간→6 / 상단 과열→2

데이터 소스:
  - US(알파벳 티커): yfinance .info (PEG·FCF·시총·EV/EBITDA 실데이터 제공)
  - KR(6자리 코드) : 포워드 성장률·FCF·EV/EBITDA 무료 신뢰 소스가 없어 대부분 N/A.
                     (PER/PBR만 참고용. KR 결정론 밸류는 본질적으로 약함 — 정직하게 표기)

⚠️ EV/EBITDA '5년 밴드'는 yfinance가 시계열을 주지 않아 현재 멀티플만 수집하고 밴드 점수는
   N/A 처리한다. 업그레이드 경로: 우리 앱은 이미 일별 히스토리를 누적하므로, EV/EBITDA를
   매일 스냅샷하면 수개월 뒤 자체 밴드를 만들 수 있다(별도 작업).
"""

from __future__ import annotations
import time
from typing import Optional

# ── 가벼운 TTL 캐시 (yfinance 과호출 방지) — st.cache_data는 FastAPI에서 불안정해 미사용 ──
_CACHE: dict[str, tuple[float, dict]] = {}
# 펀더멘털은 분기마다 갱신되므로 24시간 캐시로 충분. 같은 종목을 하루 1번만 yfinance에 물어
# IP 레이트리밋(특히 공유망)을 사실상 회피한다. 실패(0/3) 결과는 캐시하지 않아 즉시 재시도됨.
_CACHE_TTL = 86400  # 24시간


def _cache_get(key: str):
    v = _CACHE.get(key)
    if v and (time.time() - v[0]) < _CACHE_TTL:
        return v[1]
    return None


def _cache_put(key: str, val: dict):
    _CACHE[key] = (time.time(), val)


# ── 항목별 스코어링 규칙 ──────────────────────────────────────────────────────
def _score_peg(peg: Optional[float]) -> dict:
    """PEG: ≤1.0→10 / ≤1.5→7 / ≤2.0→4 / >2.0→0. 음수/0(역성장·적자)은 의미없음 → N/A."""
    if peg is None or peg <= 0:
        return {"value": peg, "score": None, "max": 10, "available": False,
                "note": "PEG 산출 불가(적자·역성장·데이터 없음)"}
    if peg <= 1.0:   s = 10
    elif peg <= 1.5: s = 7
    elif peg <= 2.0: s = 4
    else:            s = 0
    return {"value": round(peg, 2), "score": s, "max": 10, "available": True,
            "note": f"PEG {peg:.2f}"}


def _score_fcf_yield(fcf_yield_pct: Optional[float]) -> dict:
    """FCF Yield(%): ≥7→10 / ≥4→7 / ≥1→3 / <1→0. 마이너스 현금흐름도 '실데이터 0점'."""
    if fcf_yield_pct is None:
        return {"value": None, "score": None, "max": 10, "available": False,
                "note": "FCF/시총 데이터 없음"}
    y = fcf_yield_pct
    if y >= 7:   s = 10
    elif y >= 4: s = 7
    elif y >= 1: s = 3
    else:        s = 0
    return {"value": round(y, 2), "score": s, "max": 10, "available": True,
            "note": f"FCF Yield {y:.2f}%"}


def _score_ev_ebitda_band(current: Optional[float], band: Optional[tuple],
                          band_info: Optional[dict] = None) -> dict:
    """EV/EBITDA 자체 밴드 위치: 하단→10 / 중간→6 / 상단→2.
    band=(min, max)는 누적 스냅이 충분(ready)할 때만 들어온다. 아니면 누적 진행상황을 표시."""
    if current is None or current <= 0:
        return {"value": current, "score": None, "max": 10, "available": False,
                "note": "EV/EBITDA 산출 불가(적자 EBITDA·데이터 없음)"}
    n = int((band_info or {}).get("n", 0) or 0)
    need = int((band_info or {}).get("min_points", 20) or 20)
    if not band or band[1] <= band[0]:
        prog = f"누적 {n}/{need}일" if n < need else f"{n}일(값 분산 부족)"
        return {"value": round(current, 2), "score": None, "max": 10, "available": False,
                "note": f"현재 EV/EBITDA {current:.1f} · 자체 밴드 {prog} (충분히 쌓이면 점수화)"}
    lo, hi = band
    pos = (current - lo) / (hi - lo)
    if pos <= 0.33:   s, lab = 10, "하단 소외"
    elif pos <= 0.66: s, lab = 6, "중간 밴드"
    else:             s, lab = 2, "상단 과열"
    return {"value": round(current, 2), "score": s, "max": 10, "available": True,
            "note": f"EV/EBITDA {current:.1f} · 자체 밴드({n}일) {lab}(위치 {pos*100:.0f}%)"}


# ── 데이터 수집 ───────────────────────────────────────────────────────────────
_YF_POOL = None


def _yf_pool():
    global _YF_POOL
    if _YF_POOL is None:
        from concurrent.futures import ThreadPoolExecutor
        _YF_POOL = ThreadPoolExecutor(max_workers=2)
    return _YF_POOL


def _fetch_us(ticker: str, timeout_sec: int = 12) -> dict:
    """yfinance .info에서 밸류에이션 원시값 수집. yfinance .info는 느리고 레이트리밋에
    잘 걸려서 타임아웃으로 감싼다(엔드포인트가 멈추지 않게). 실패 시 빈 info → 전부 N/A."""
    from concurrent.futures import TimeoutError as _FTimeout
    def _do():
        import yfinance as yf
        return yf.Ticker(ticker).info or {}
    try:
        info = _yf_pool().submit(_do).result(timeout=timeout_sec)
    except (_FTimeout, Exception):
        info = {}

    peg = info.get("trailingPegRatio") or info.get("pegRatio")
    try:
        peg = float(peg) if peg is not None else None
    except (TypeError, ValueError):
        peg = None

    fcf = info.get("freeCashflow")
    mcap = info.get("marketCap")
    fcf_yield = None
    if fcf is not None and mcap:
        try:
            fcf_yield = float(fcf) / float(mcap) * 100
        except (TypeError, ValueError, ZeroDivisionError):
            fcf_yield = None

    ev_ebitda = info.get("enterpriseToEbitda")
    try:
        ev_ebitda = float(ev_ebitda) if ev_ebitda is not None else None
    except (TypeError, ValueError):
        ev_ebitda = None

    return {"peg": peg, "fcf_yield": fcf_yield, "ev_ebitda": ev_ebitda,
            "name": info.get("shortName") or info.get("longName") or ticker}


def _fetch_kr(code: str) -> dict:
    """KR은 포워드 성장·FCF·EV/EBITDA 무료 소스가 없어 밸류 3항목 모두 산출 불가.
    PER/PBR만 참고로 가져오되 점수에는 쓰지 않는다(정직성)."""
    per = pbr = name = None
    fin = {}
    try:
        from data_kr import _get_kr_per_pbr_naver
        d = _get_kr_per_pbr_naver(code) or {}
        per, pbr = d.get("per"), d.get("pbr")
    except Exception:
        pass
    try:
        from data_kr import get_kr_code_to_name_map
        name = (get_kr_code_to_name_map() or {}).get(code)
    except Exception:
        pass
    try:
        from data_kr import get_kr_financials_kis
        fin = get_kr_financials_kis(code) or {}
    except Exception:
        fin = {}

    # PEG = PER / 과거 순이익성장률(%). 단, 회복연도·적자전환 등 성장률 왜곡 구간(범위 밖)은
    # 가짜 저평가를 만들므로 채점에서 제외(N/A). 정상 성장 구간(5~60%)에서만 산출.
    peg = None
    g = fin.get("ni_growth")
    growth_distorted = (g is not None and not (5 <= g <= 60))
    if per and per > 0 and g is not None and 5 <= g <= 60:
        peg = round(per / g, 2)

    return {"peg": peg, "fcf_yield": None, "ev_ebitda": None,
            "name": name or code, "_kr_per": per, "_kr_pbr": pbr,
            "_kr_fin": fin, "_kr_growth_distorted": growth_distorted}


# ── 메인 진입점 ───────────────────────────────────────────────────────────────
def compute_valuation_score(ticker: str, market: Optional[str] = None) -> dict:
    """밸류에이션 결정론 점수(30점). LLM 미사용.

    반환:
      {
        "ticker", "name", "market",
        "items": {"peg": {...}, "fcf_yield": {...}, "ev_ebitda_band": {...}},
        "score_raw": 사용가능 항목 점수 합,
        "available_max": 사용가능 항목 만점 합(0/10/20/30),
        "score_30": available 기준 30점 환산값(없으면 None),
        "coverage": "2/3 항목 실데이터",
        "confidence_pct": available_max/30*100,
        "kr_note": (KR일 때만) PER/PBR 참고값,
      }
    """
    raw_ticker = str(ticker).strip().upper()
    is_kr = (market == "KR") or (raw_ticker.isdigit() and len(raw_ticker) <= 6)
    mkt = "KR" if is_kr else "US"
    key = f"{mkt}:{raw_ticker}"

    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        data = _fetch_kr(raw_ticker.zfill(6)) if is_kr else _fetch_us(raw_ticker)
    except Exception as e:
        return {"ticker": raw_ticker, "market": mkt, "error": f"데이터 수집 실패: {e}",
                "items": {}, "score_raw": 0, "available_max": 0, "score_30": None,
                "coverage": "0/3 항목", "confidence_pct": 0.0}

    # EV/EBITDA: 오늘 값을 스냅 적재(추가 호출 0) → 누적된 자체 밴드로 점수화 시도.
    ev = data.get("ev_ebitda")
    band = None
    band_info = None
    try:
        from db import save_ev_ebitda_snapshot, load_ev_ebitda_band
        if not is_kr and ev and ev > 0:
            save_ev_ebitda_snapshot(raw_ticker, ev)          # 하루 1점(날짜 유니크)
        band_info = load_ev_ebitda_band(raw_ticker)
        if band_info.get("ready") and band_info.get("min") is not None:
            band = (band_info["min"], band_info["max"])
    except Exception:
        band_info = None

    items = {
        "peg":            _score_peg(data.get("peg")),
        "fcf_yield":      _score_fcf_yield(data.get("fcf_yield")),
        "ev_ebitda_band": _score_ev_ebitda_band(ev, band, band_info),
    }

    avail = [it for it in items.values() if it["available"]]
    score_raw = sum(it["score"] for it in avail)
    available_max = sum(it["max"] for it in avail)
    # 종합 30점 환산은 '항목 2개 이상(20점)'일 때만 — 1개 항목으로 30점 만점처럼
    # 과대표시되는 것을 방지(예: PEG만 만점인데 30/30으로 보이는 오해 차단).
    score_30 = round(score_raw / available_max * 30, 1) if available_max >= 20 else None
    n_avail = len(avail)

    result = {
        "ticker": raw_ticker,
        "name": data.get("name", raw_ticker),
        "market": mkt,
        "items": items,
        "score_raw": score_raw,
        "available_max": available_max,
        "score_30": score_30,
        "coverage": f"{n_avail}/3 항목 실데이터",
        "confidence_pct": round(available_max / 30 * 100, 0),
    }
    if is_kr:
        fin = data.get("_kr_fin") or {}
        ctx = []
        if fin.get("roe") is not None:        ctx.append(f"ROE {fin['roe']}%")
        if fin.get("debt_ratio") is not None: ctx.append(f"부채비율 {fin['debt_ratio']}%")
        if fin.get("rev_growth") is not None: ctx.append(f"매출성장 {fin['rev_growth']}%")
        ctx_str = " · ".join(ctx) if ctx else "KIS 재무 제한"
        peg_note = " (PEG: 성장률 왜곡 구간이라 채점 제외)" if data.get("_kr_growth_distorted") else ""
        result["kr_note"] = (
            f"KIS 재무 기반 — PER={data.get('_kr_per')}, PBR={data.get('_kr_pbr')}, {ctx_str}.{peg_note} "
            f"FCF·EV/EBITDA는 KIS 현금흐름표 부재로 보류(추후 DART)."
        )
    elif available_max == 0:
        # US인데 0/3 = 영구적 부재가 아니라 yfinance 일시 장애(레이트리밋/타임아웃)일 가능성↑
        result["transient_note"] = "데이터 일시 조회 실패(yfinance 지연·레이트리밋 가능) — 잠시 후 다시 시도하세요."

    # 성공 결과만 캐시 — 실패는 캐시하지 않아 다음 호출에 즉시 재시도되게 한다.
    #  · US: 항목 1개+ 산출되면 성공 / 0개면 yfinance 일시장애 → 미캐시
    #  · KR: KIS 재무를 실제 취득했으면 성공 / 못 받았으면(토큰 등) 미캐시
    kr_ok = is_kr and bool(data.get("_kr_fin"))
    if available_max > 0 or kr_ok:
        _cache_put(key, result)
    return result


def snapshot_ev_ebitda_for(tickers, delay_sec: float = 1.5, limit: int = 60) -> dict:
    """[일별 스냅 배치] 주어진 US 티커들의 '오늘' EV/EBITDA를 적재한다(스케줄러용).
    결과 캐시를 우회해 매일 1점을 보장한다. yfinance 보호: 종목당 딜레이 + 개수 제한.
    KR(6자리 숫자)·중복·빈값은 건너뛴다."""
    from db import save_ev_ebitda_snapshot
    seen: set[str] = set()
    saved = 0
    for tk in tickers or []:
        t = str(tk).strip().upper()
        if not t or t in seen or t.isdigit():   # 빈값/중복/KR 제외
            continue
        seen.add(t)
        if len(seen) > limit:
            break
        try:
            ev = _fetch_us(t).get("ev_ebitda")
            if ev and ev > 0:
                save_ev_ebitda_snapshot(t, ev)
                saved += 1
        except Exception:
            pass
        time.sleep(delay_sec)   # yfinance 레이트리밋 보호
    return {"requested": len(seen), "saved": saved}


if __name__ == "__main__":
    import json, sys
    syms = sys.argv[1:] or ["NVDA", "AAPL", "005930"]
    for s in syms:
        r = compute_valuation_score(s)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print("-" * 60)
