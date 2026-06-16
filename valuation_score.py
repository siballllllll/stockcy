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
_CACHE_TTL = 1800  # 30분


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


def _score_ev_ebitda_band(current: Optional[float], band: Optional[tuple]) -> dict:
    """EV/EBITDA 5년 밴드 위치: 하단→10 / 중간→6 / 상단→2.
    band=(min5, max5)가 없으면 현재 멀티플만 보여주고 점수는 N/A."""
    if current is None or current <= 0:
        return {"value": current, "score": None, "max": 10, "available": False,
                "note": "EV/EBITDA 산출 불가(적자 EBITDA·데이터 없음)"}
    if not band or band[1] <= band[0]:
        return {"value": round(current, 2), "score": None, "max": 10, "available": False,
                "note": f"현재 EV/EBITDA {current:.1f} (5년 밴드 미보유 → 밴드점수 N/A)"}
    lo, hi = band
    pos = (current - lo) / (hi - lo)
    if pos <= 0.33:   s, lab = 10, "하단 소외"
    elif pos <= 0.66: s, lab = 6, "중간 밴드"
    else:             s, lab = 2, "상단 과열"
    return {"value": round(current, 2), "score": s, "max": 10, "available": True,
            "note": f"EV/EBITDA {current:.1f} · 밴드 {lab}(위치 {pos*100:.0f}%)"}


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
    return {"peg": None, "fcf_yield": None, "ev_ebitda": None,
            "name": name or code, "_kr_per": per, "_kr_pbr": pbr}


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

    items = {
        "peg":            _score_peg(data.get("peg")),
        "fcf_yield":      _score_fcf_yield(data.get("fcf_yield")),
        "ev_ebitda_band": _score_ev_ebitda_band(data.get("ev_ebitda"), band=None),  # 밴드 시계열 미보유
    }

    avail = [it for it in items.values() if it["available"]]
    score_raw = sum(it["score"] for it in avail)
    available_max = sum(it["max"] for it in avail)
    score_30 = round(score_raw / available_max * 30, 1) if available_max else None
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
        result["kr_note"] = (
            f"KR 결정론 밸류는 포워드성장·FCF·EV/EBITDA 무료 소스 부재로 산정 불가. "
            f"(참고 PER={data.get('_kr_per')}, PBR={data.get('_kr_pbr')})"
        )
    elif available_max == 0:
        # US인데 0/3 = 영구적 부재가 아니라 yfinance 일시 장애(레이트리밋/타임아웃)일 가능성↑
        result["transient_note"] = "데이터 일시 조회 실패(yfinance 지연·레이트리밋 가능) — 잠시 후 다시 시도하세요."

    # 성공 결과만 캐시 — US 일시 실패(0/3)는 캐시하지 않아 다음 호출에 즉시 재시도되게 한다.
    if is_kr or available_max > 0:
        _cache_put(key, result)
    return result


if __name__ == "__main__":
    import json, sys
    syms = sys.argv[1:] or ["NVDA", "AAPL", "005930"]
    for s in syms:
        r = compute_valuation_score(s)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print("-" * 60)
