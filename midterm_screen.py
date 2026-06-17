"""[중장기 가치 발굴 스크리너 — 결정론] 3개월+ 보유 후보 랭킹

이번에 구축한 밸류에이션 점수 + 재무 국면을 종합해, 섹터 단위로 '중장기 보유 매력'
순으로 줄세운다. AI 미사용·무료. (전 종목 동시는 레이트리밋상 불가 → 섹터 단위 스캔)

중장기 매력 점수 = 재무 국면(가장 중요) + 자산가치(PBR) + 품질(ROE) + 현금창출(FCF Yield) − 생존력 페널티
"""

import time


# 보유 기간별 프로파일 — 같은 데이터에 가중치만 다르게 (기준의 다양성)
#  swing(1개월~): 반등 변곡·일시부진 회복 중시, 깊은 저평가 비중 낮음
#  value(3개월~1년): 싼 가치(PBR)+순환 바닥 회복 중시 (기본)
#  quality(수년+): 꾸준한 ROE·구조적 성장(매출 CAGR) 중시, 비싸도 우량이면 OK
HORIZONS = {"swing": "1개월~", "value": "3개월~1년", "quality": "수년+"}

_PHASE_TABLE = {
    "swing":   [("회복 신호", 30), ("일시 부진", 18), ("정상", 15), ("회복 대기", 10), ("구조적", -15), ("취약", -25)],
    "value":   [("회복 신호", 28), ("정상", 25), ("회복 대기", 20), ("일시 부진", 8), ("구조적", -15), ("취약", -30)],
    "quality": [("정상", 30), ("회복 신호", 15), ("회복 대기", 8), ("일시 부진", 3), ("구조적", -25), ("취약", -30)],
}
_PBR_W = {"swing": 0.6, "value": 1.0, "quality": 0.3}
_ROE_W = {"swing": 0.7, "value": 1.0, "quality": 1.6}


def _phase_pts(p: str, horizon: str) -> int:
    for k, v in _PHASE_TABLE.get(horizon, _PHASE_TABLE["value"]):
        if k in p:
            return v
    return 0


def _compute_from_val(v: dict, name: str = "", horizon: str = "value") -> dict:
    """compute_valuation_score 결과(v) → 보유기간별 매력 점수 dict. (순수 함수 — API 미호출)"""
    ph = v.get("phase") or {}
    sig = ph.get("signals") or {}
    items = v.get("items") or {}
    p = ph.get("phase", "") or ""

    score = float(_phase_pts(p, horizon))
    pbr = sig.get("pbr")
    if pbr is not None:
        base = 12 if pbr < 1 else 7 if pbr < 1.5 else 3 if pbr < 2.5 else 0      # 자산가치
        score += base * _PBR_W[horizon]
    roe = sig.get("roe")
    if roe is not None:
        base = 12 if roe >= 15 else 7 if roe >= 8 else 2 if roe >= 0 else -5     # 품질
        score += base * _ROE_W[horizon]
    cagr = sig.get("rev_cagr_pct")
    if cagr is not None and horizon == "quality":                               # 장기 성장
        score += 14 if cagr >= 10 else 8 if cagr >= 3 else 0 if cagr >= 0 else -10
    fy = (items.get("fcf_yield") or {}).get("value")
    if fy is not None:
        score += 10 if fy >= 5 else 5 if fy >= 2 else (-5 if fy < 0 else 0)      # 현금창출
    if horizon == "swing" and sig.get("rebounding"):
        score += 10                                                             # 단기 변곡 가점
    if sig.get("survivable") is False:
        score -= 15                                                             # 생존력 페널티

    return {
        "code": v.get("ticker"), "name": v.get("name") or name,
        "midterm_score": round(score, 1), "horizon": horizon,
        "phase": p, "reason": ph.get("reason", ""),
        "pbr": pbr, "roe": roe, "rev_cagr": cagr,
        "fcf_yield": round(fy, 2) if fy is not None else None,
        "ev_ebitda": (items.get("ev_ebitda_band") or {}).get("value"),
    }


def score_one(code: str, name: str = "", market: str = "KR", horizon: str = "value") -> dict:
    from valuation_score import compute_valuation_score
    v = compute_valuation_score(code, market)
    r = _compute_from_val(v, name, horizon)
    r["code"] = code
    return r


def screen_sector_midterm(codes_names: list, market: str = "KR", horizon: str = "value",
                          limit: int = 30, delay: float = 0.3) -> dict:
    """섹터 종목들[(code, name)]을 보유기간(horizon)별 매력 순으로 랭킹. delay로 레이트리밋 보호."""
    if horizon not in HORIZONS:
        horizon = "value"
    out, scanned = [], 0
    for code, name in (codes_names or [])[:limit]:
        try:
            r = score_one(code, name, market, horizon)
            scanned += 1
            if r.get("phase") or r.get("pbr") is not None or r.get("fcf_yield") is not None:
                out.append(r)
        except Exception:
            pass
        time.sleep(delay)
    out.sort(key=lambda x: x["midterm_score"], reverse=True)
    return {"scanned": scanned, "horizon": horizon, "horizon_label": HORIZONS[horizon], "ranked": out}
