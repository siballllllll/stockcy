"""[중장기 가치 발굴 스크리너 — 결정론] 3개월+ 보유 후보 랭킹

이번에 구축한 밸류에이션 점수 + 재무 국면을 종합해, 섹터 단위로 '중장기 보유 매력'
순으로 줄세운다. AI 미사용·무료. (전 종목 동시는 레이트리밋상 불가 → 섹터 단위 스캔)

중장기 매력 점수 = 재무 국면(가장 중요) + 자산가치(PBR) + 품질(ROE) + 현금창출(FCF Yield) − 생존력 페널티
"""

import time


def _phase_pts(p: str) -> int:
    if "정상" in p:        return 30   # 정상·양호
    if "회복 신호" in p:    return 28   # 순환 바닥 → 회복 신호
    if "회복 대기" in p:    return 18   # 순환 바닥 (회복 대기)
    if "일시 부진" in p:    return 8
    if "구조적" in p:       return -15  # 구조적 쇠퇴 의심
    if "취약" in p:         return -30  # 재무 취약(가치 함정)
    return 0


def _compute_from_val(v: dict, name: str = "") -> dict:
    """compute_valuation_score 결과(v) → 중장기 매력 점수 dict. (순수 함수 — API 미호출)"""
    ph = v.get("phase") or {}
    sig = ph.get("signals") or {}
    items = v.get("items") or {}
    p = ph.get("phase", "") or ""

    score = _phase_pts(p)
    pbr = sig.get("pbr")
    if pbr is not None:
        score += 12 if pbr < 1 else 7 if pbr < 1.5 else 3 if pbr < 2.5 else 0   # 자산가치
    roe = sig.get("roe")
    if roe is not None:
        score += 12 if roe >= 15 else 7 if roe >= 8 else 2 if roe >= 0 else -5  # 품질
    fy = (items.get("fcf_yield") or {}).get("value")
    if fy is not None:
        score += 10 if fy >= 5 else 5 if fy >= 2 else (-5 if fy < 0 else 0)     # 현금창출
    if sig.get("survivable") is False:
        score -= 15                                                            # 생존력 페널티

    return {
        "code": v.get("ticker"), "name": v.get("name") or name,
        "midterm_score": round(score, 1),
        "phase": p, "reason": ph.get("reason", ""),
        "pbr": pbr, "roe": roe,
        "fcf_yield": round(fy, 2) if fy is not None else None,
        "ev_ebitda": (items.get("ev_ebitda_band") or {}).get("value"),
    }


def score_one(code: str, name: str = "", market: str = "KR") -> dict:
    from valuation_score import compute_valuation_score
    v = compute_valuation_score(code, market)
    r = _compute_from_val(v, name)
    r["code"] = code
    return r


def screen_sector_midterm(codes_names: list, market: str = "KR",
                          limit: int = 30, delay: float = 0.3) -> dict:
    """섹터 종목들[(code, name)]을 중장기 매력 순으로 랭킹. delay로 레이트리밋 보호."""
    out, scanned = [], 0
    for code, name in (codes_names or [])[:limit]:
        try:
            r = score_one(code, name, market)
            scanned += 1
            # 데이터가 사실상 없는 종목(국면 미산정 + PBR 없음)은 제외
            if r.get("phase") or r.get("pbr") is not None or r.get("fcf_yield") is not None:
                out.append(r)
        except Exception:
            pass
        time.sleep(delay)
    out.sort(key=lambda x: x["midterm_score"], reverse=True)
    return {"scanned": scanned, "ranked": out}
