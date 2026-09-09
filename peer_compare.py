# 동종 비교 (peer comparison) — v3.151.0
#
# [왜 만들었나] 종목검색은 종목 하나를 깊게 보여주지만, 실제 판단은 "현금은 한 자리인데
# 후보가 셋"인 순간에 일어난다. 그때 필요한 건 PER 나열이 아니라 "이 후보들 중 어느 것이
# 내가 실제로 이겼던 자리에 있는가"다. 그래서 이 모듈은 두 가지만 한다:
#   ① 같은 섹터의 동종 종목을 국내·미국 양쪽에서 모은다
#   ② 각 종목이 섀도우 리그에서 실측된 어느 구간에 있는지 라벨을 붙인다
#
# [비용] LLM 호출 0. 가격·지표는 이미 쓰고 있는 함수를 그대로 재사용한다.
#
# ⚠️ 구간 라벨의 승률은 섀도우 리그 실현 거래의 실측값이고, 시장별로 검증 수준이 다르다.
#    특히 '이슈×지지구간'은 국내에서만 유의했다(미국 47.1%, p=0.774 = 신호 없음).
#    미국 종목에 국내 승률을 붙이면 안 된다 — _zone_of가 시장을 보고 갈라내는 이유다.

import concurrent.futures as _fut
import logging

logger = logging.getLogger("peer_compare")

MAX_SAME_MARKET = 7      # 같은 시장 동종 (현재 종목 제외)
MAX_CROSS_MARKET = 5     # 교차 시장 카운터파트
_FETCH_TIMEOUT = 25      # 전체 지표 수집 상한(초) — 종목검색 화면을 붙잡아두지 않는다


# ── 구간 정의 ────────────────────────────────────────────────────────────────
# 조건은 shadow_league._wants_buy와 **동일하게 유지할 것**. 어긋나면 아래 승률을
# 인용할 근거가 사라진다(리그가 실제로 그 조건으로 매매해서 나온 숫자이기 때문).
#   SHADOW_C 이슈×지지구간 : 61.0% (n=41) — 국내 70.8%(n=24) / 미국 47.1%(n=17, 신호없음)
#   SHADOW_A 눌림목        : 52.5% (n=40)
#   SHADOW_F 모멘텀추격    : 33.3% (n=33) — 랜덤과 구분 불가
#   SHADOW_E 랜덤 기준선   : 32.5% (n=40)
ZONE_BASELINE = 32.5

_ZONE_META = {
    "issue_zone": {"label": "이슈×지지구간", "win_rate": 61.0, "n": 41,
                   "kr_only": True, "note": "국내 70.8%(n=24) · 미국은 신호 없음(47.1%, p=0.774)"},
    "pullback":   {"label": "눌림목", "win_rate": 52.5, "n": 40,
                   "kr_only": False, "note": "볼린저 하단 + 조용한 거래량"},
    "chase":      {"label": "모멘텀 추격", "win_rate": 33.3, "n": 33,
                   "kr_only": False, "note": "랜덤 대조군(32.5%)과 구분되지 않음"},
    "neutral":    {"label": "해당 구간 없음", "win_rate": None, "n": None,
                   "kr_only": False, "note": "실측된 우위 구간에 해당하지 않음"},
}


def _zone_of(ind: dict, is_kr: bool, linked: bool) -> dict:
    """지표 → 실측 구간 판정. shadow_league._wants_buy의 A/C/F 조건과 동일하게 유지할 것."""
    bb = ind.get("bb_pctb")
    m5 = ind.get("mom_5")
    vr = ind.get("vol_ratio")
    rsi = ind.get("rsi")
    ma20d = ind.get("ma20_dist")

    key = "neutral"
    # C: 재료 있는 종목이 지지 구간에 왔고 아직 급등 전
    zone_ok = ((bb is not None and bb <= 0.35)
               or (ma20d is not None and -3.0 <= ma20d <= 1.0))
    if linked and zone_ok and (m5 is None or m5 < 5.0):
        key = "issue_zone"
    # A: 순수 눌림목
    elif (bb is not None and bb < 0.25 and m5 is not None and m5 <= -3
          and (vr is None or vr < 2.0) and (rsi is None or rsi < 55)):
        key = "pullback"
    # F: 모멘텀 추격 (실측상 랜덤과 구분 불가 — 경고 목적으로 라벨링)
    elif m5 is not None and m5 >= 10.0:
        key = "chase"

    meta = dict(_ZONE_META[key])
    meta["key"] = key
    # 국내에서만 유의했던 구간은 미국 종목에 승률을 붙이지 않는다.
    if meta.get("kr_only") and not is_kr:
        meta["win_rate"] = None
        meta["note"] = "미국에서는 통계적 우위가 확인되지 않은 구간 — 라벨만 표시"
    return meta


# ── 피어 탐색 ────────────────────────────────────────────────────────────────
def _norm(tk) -> str:
    return str(tk or "").strip().upper()


def _kr_code(tk) -> str:
    s = str(tk or "").strip()
    return s.zfill(6) if s.isdigit() else s


def find_peers(ticker: str, market: str) -> dict:
    """현재 종목의 섹터를 찾고, 같은 시장 동종 + 교차 시장 카운터파트를 반환.

    교차 시장은 sector_knowledge.SECTOR_KNOWLEDGE를 쓴다 — 이 테이블만이 한 테마 아래에
    kr/us 종목을 함께 들고 있어서 국내↔미국을 같은 축에 놓을 수 있다(31개 테마 중 26개).
    KR_SECTOR_MAP과 US_SECTOR_MAP은 상위 섹터명이 서로 달라(반도체 vs AI·반도체) 직접
    조인되지 않으므로 교차 축으로 쓰지 않는다.
    """
    is_kr = str(market) == "국내" or _kr_code(ticker).isdigit()
    tk = _kr_code(ticker) if is_kr else _norm(ticker)

    out = {"ticker": tk, "name": tk, "market": "국내" if is_kr else "미국",
           "sector": None, "sub_sector": None, "theme": None,
           "same_market": [], "cross_market": []}

    # 1) 같은 시장 — 섹터맵에서 현재 종목이 속한 세부섹터를 찾는다
    try:
        from db import load_sector_map, load_us_sector_map
        smap = load_sector_map() if is_kr else load_us_sector_map()
    except Exception as e:
        logger.error(f"[peer] 섹터맵 로드 실패: {e}")
        smap = {}

    for sector, subs in (smap or {}).items():
        if not isinstance(subs, dict):
            continue
        for sub, items in subs.items():
            if not isinstance(items, list):
                continue
            hit = any(
                (_kr_code(it.get("code")) == tk) if is_kr else (_norm(it.get("ticker")) == tk)
                for it in items if isinstance(it, dict))
            if not hit:
                continue
            out["sector"], out["sub_sector"] = sector, sub
            for it in items:                      # 기준 종목 이름도 여기서 확보
                if isinstance(it, dict):
                    _pt = _kr_code(it.get("code")) if is_kr else _norm(it.get("ticker"))
                    if _pt == tk and it.get("name"):
                        out["name"] = it.get("name")
                        break
            for it in items:
                if not isinstance(it, dict):
                    continue
                pt = _kr_code(it.get("code")) if is_kr else _norm(it.get("ticker"))
                if not pt or pt == tk:
                    continue
                out["same_market"].append({"ticker": pt, "name": it.get("name") or pt,
                                           "market": "국내" if is_kr else "미국"})
            break
        if out["sector"]:
            break

    # 2) 교차 시장 — 같은 테마 안의 반대편 시장 종목
    try:
        from sector_knowledge import SECTOR_KNOWLEDGE
    except Exception as e:
        logger.error(f"[peer] 섹터 지식 로드 실패: {e}")
        SECTOR_KNOWLEDGE = {}

    for theme, v in (SECTOR_KNOWLEDGE or {}).items():
        mine = v.get("kr" if is_kr else "us") or []
        found = any(
            (_kr_code(x.get("code")) == tk) if is_kr else (_norm(x.get("ticker")) == tk)
            for x in mine if isinstance(x, dict))
        if not found:
            continue
        out["theme"] = theme
        for x in (v.get("us" if is_kr else "kr") or []):
            if not isinstance(x, dict):
                continue
            xt = _norm(x.get("ticker")) if is_kr else _kr_code(x.get("code"))
            if xt:
                out["cross_market"].append({"ticker": xt, "name": x.get("name") or xt,
                                            "market": "미국" if is_kr else "국내"})
        break

    out["same_market"] = out["same_market"][:MAX_SAME_MARKET]
    out["cross_market"] = out["cross_market"][:MAX_CROSS_MARKET]
    return out


# ── 임의 종목 비교 (v3.164.0) ────────────────────────────────────────────────
# 동종 비교(compare_peers)는 섹터맵으로 상대를 자동 선정한다. 이쪽은 사용자가 직접 고른
# 종목만 나란히 놓는다 — 섹터가 달라도, 국내·미국이 섞여도 상관없다.
# 지표는 _one_row를 그대로 쓰고, 여기에 DB에서 오는 수급·이슈를 덧붙인다
# (둘 다 조회 비용이 사실상 0이라 기본 포함). PER/PBR은 네이버 스크래핑이라 느려서
# 별도 요청(with_valuation=True)일 때만 붙인다.
MAX_COMPARE = 5


def _supply_of(cur, ticker: str) -> dict:
    """최근 수급 스냅샷 — 외국인/기관 순매수 (국내만 적재됨)."""
    try:
        cur.execute(
            """SELECT snapshot_date, frgn_ntby, orgn_ntby, combined
               FROM frgn_inst_snapshots WHERE ticker = ?
               ORDER BY snapshot_date DESC LIMIT 5""", (ticker,))
        rows = [dict(r) for r in cur.fetchall()]
    except Exception:
        return {}
    if not rows:
        return {}
    latest = rows[0]
    return {
        "date": latest.get("snapshot_date"),
        "frgn": latest.get("frgn_ntby"),
        "orgn": latest.get("orgn_ntby"),
        "combined": latest.get("combined"),
        # 최근 5일 합 — 하루치만 보면 노이즈라 추세를 같이 준다
        "sum5": sum(int(r.get("combined") or 0) for r in rows),
        "days": len(rows),
    }


def _issues_of(cur, ticker: str) -> dict:
    """이 종목이 등장한 시나리오 — 몇 번, 최근 무엇."""
    try:
        cur.execute(
            """SELECT scenario_title, role, captured_at
               FROM scenario_stocks WHERE ticker = ?
               ORDER BY captured_at DESC LIMIT 3""", (ticker,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) AS n FROM scenario_stocks WHERE ticker = ?", (ticker,))
        n = int((cur.fetchone() or {"n": 0})["n"])
    except Exception:
        return {}
    return {
        "count": n,
        "recent": [{"title": str(r.get("scenario_title") or "")[:60],
                    "role": r.get("role"),
                    "at": str(r.get("captured_at") or "")[:10]} for r in rows],
    }


def _ai_analysis_of(cur, ticker: str) -> str:
    """저장된 AI 판단 요약 — 비교 근거로 넣는다. 두 곳을 모두 본다 (v3.166.0).

    · analysis_history : 사용자가 종목검색에서 직접 돌린 AI 종목분석.
      목표가·손절가까지 있어 가장 진하지만 **양이 적다** — 5종목뿐이다.
      결과가 브라우저에 14일 캐시되어 같은 종목을 다시 열어도 재분석이 일어나지 않고,
      기록은 새 분석이 끝난 순간에만 하기 때문이다(중복 적재 방지).
    · agent_decisions : AI 에이전트가 스캔하며 남긴 판단. 65종목·135건으로 훨씬 넓고
      매일 자동으로 쌓이며 추가 비용이 0이다. 목표가는 없지만 액션·신뢰도·판단 근거가 있다.

    임의의 두 종목을 1:1로 비교할 때 종목분석이 있는 경우가 드물어, 넓은 쪽을 함께 쓴다.
    """
    out = []
    try:
        cur.execute(
            """SELECT analysis_time, rating, long_term_rating, short_term_view_pct,
                      buy_target, sell_target
               FROM analysis_history WHERE ticker = ?
               ORDER BY analysis_time DESC LIMIT 1""", (ticker,))
        r = cur.fetchone()
        if r:
            d = dict(r)
            out.append(
                f"[종목분석 {str(d.get('analysis_time') or '')[:10]}] 단기 {d.get('rating')}, "
                f"장기 {d.get('long_term_rating')}, 단기전망 {d.get('short_term_view_pct')}, "
                f"매수타점 {d.get('buy_target')}, 목표 {d.get('sell_target')}")
    except Exception:
        pass

    try:
        cur.execute(
            """SELECT decided_at, action, confidence, entry_price, reason
               FROM agent_decisions WHERE ticker = ?
               ORDER BY decided_at DESC LIMIT 2""", (ticker,))
        for r in cur.fetchall():
            d = dict(r)
            out.append(
                f"[에이전트 판단 {str(d.get('decided_at') or '')[:10]}] "
                f"{d.get('action')} (신뢰도 {d.get('confidence')}, 당시가 {d.get('entry_price')}) — "
                f"{str(d.get('reason') or '')[:180]}")
    except Exception:
        pass

    return " / ".join(out)


def compare_tickers(tickers: list, with_valuation: bool = False) -> dict:
    """사용자가 지정한 종목들을 나란히 비교. LLM 호출 없음."""
    seen, targets = set(), []
    for t in (tickers or []):
        raw = str(t or "").strip()
        if not raw:
            continue
        is_kr = raw.isdigit()
        tk = _kr_code(raw) if is_kr else _norm(raw)
        if tk in seen:
            continue
        seen.add(tk)
        targets.append({"ticker": tk, "name": tk, "market": "국내" if is_kr else "미국"})
        if len(targets) >= MAX_COMPARE:
            break
    if not targets:
        return {"rows": [], "baseline_win_rate": ZONE_BASELINE}

    linked_map = {}
    try:
        from db import load_scenario_stocks_set
        linked_map = load_scenario_stocks_set() or {}
    except Exception as e:
        logger.error(f"[compare] 시나리오 맵 로드 실패: {e}")

    rows = []
    try:
        with _fut.ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
            futs = {ex.submit(_one_row, t, linked_map): t["ticker"] for t in targets}
            for f in _fut.as_completed(futs, timeout=_FETCH_TIMEOUT):
                try:
                    rows.append(f.result())
                except Exception as e:
                    logger.error(f"[compare] row 실패: {e}")
    except Exception as e:
        logger.error(f"[compare] 병렬 수집 중단: {e}")

    # DB에서 오는 항목(수급·이슈)은 한 커넥션으로 몰아서 — 비용 거의 0
    try:
        from db import get_db_conn
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            for r in rows:
                tk = r["ticker"]
                r["supply"] = _supply_of(cur, tk) if r.get("market") == "국내" else {}
                r["issues"] = _issues_of(cur, tk)
                r["ai_analysis"] = _ai_analysis_of(cur, tk)
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[compare] 수급·이슈 조회 실패: {e}")

    if with_valuation:
        _attach_valuation(rows)

    order = {t["ticker"]: i for i, t in enumerate(targets)}
    rows.sort(key=lambda r: order.get(r["ticker"], 99))
    return {"rows": rows, "baseline_win_rate": ZONE_BASELINE,
            "zone_legend": {k: {"label": v["label"], "win_rate": v["win_rate"],
                                "n": v["n"], "note": v["note"]}
                            for k, v in _ZONE_META.items() if k != "neutral"}}


def _attach_valuation(rows: list):
    """PER/PBR/시총 보강 — 네이버 스크래핑(국내)이라 느려서 요청 시에만 부른다."""
    def _one(r):
        tk = r["ticker"]
        try:
            if r.get("market") == "국내":
                from data_kr import get_kr_stock_price
                d = get_kr_stock_price(tk, with_fundamental=True) or {}
                r["per"] = d.get("per")
                r["pbr"] = d.get("pbr")
                r["market_cap"] = d.get("market_cap")
            else:
                from data import get_us_stock_detail
                d = get_us_stock_detail(tk) or {}
                r["per"] = d.get("per")
                r["pbr"] = d.get("pbr")
                r["market_cap"] = d.get("market_cap")
        except Exception as e:
            logger.error(f"[compare] 밸류 조회 실패 {tk}: {e}")

    try:
        with _fut.ThreadPoolExecutor(max_workers=min(5, max(1, len(rows)))) as ex:
            list(ex.map(_one, rows))
    except Exception as e:
        logger.error(f"[compare] 밸류 병렬 실패: {e}")


# ── 지표 수집 ────────────────────────────────────────────────────────────────
def _one_row(entry: dict, linked_map: dict) -> dict:
    tk = entry["ticker"]
    is_kr = str(entry.get("market")) == "국내"
    row = {"ticker": tk, "name": entry.get("name") or tk, "market": entry.get("market"),
           "price": None, "change_pct": None, "rsi": None, "mom_5": None,
           "bb_pctb": None, "ma20_dist": None, "pos_52w": None, "vol_ratio": None,
           "zone": None, "error": None}
    try:
        from ai_engine import _get_trade_indicators
        ind = _get_trade_indicators(tk, "")
        d = ind.get("daily") or {}
        mlx = d.get("ml_extra") or {}
        row.update({
            "price": d.get("current_price"),
            "change_pct": d.get("today_change_pct"),
            "rsi": d.get("rsi"),
            "mom_5": mlx.get("mom_5"),
            "bb_pctb": mlx.get("bb_pctb"),
            "pos_52w": d.get("pos_52w_pct"),
            "vol_ratio": d.get("volume_ratio"),
            "ma20_dist": (round((float(d["current_price"]) / float(d["ma20"]) - 1) * 100, 2)
                          if d.get("ma20") and d.get("current_price") else None),
        })
        # shadow_league SHADOW_C와 동일하게 "시나리오 등장 1회 이상"을 재료 있음으로 본다
        row["zone"] = _zone_of(row, is_kr, int(linked_map.get(tk, 0) or 0) > 0)
    except Exception as e:
        row["error"] = str(e)[:120]
        logger.error(f"[peer] 지표 수집 실패 {tk}: {e}")
    return row


_CACHE: dict = {}          # (ticker, market) -> (만료 epoch, 결과)
CACHE_TTL_SEC = 180        # 장중 3분 — 지표는 일봉 기준이라 이 정도는 안전하고,
                           # 같은 종목을 다시 열 때 12~13종목 재수집을 통째로 아낀다.


def compare_peers(ticker: str, market: str, use_cache: bool = True) -> dict:
    """동종 비교 결과 — 현재 종목 + 같은 시장 동종 + 교차 시장 카운터파트를 한 표로.

    LLM 호출 없음. 지표는 스레드로 병렬 수집하고 전체 상한을 둬서 화면을 붙잡지 않는다.
    12~13종목의 시세를 받아오므로 첫 호출은 수 초 걸린다 — 그래서 결과를 짧게 캐시한다.
    """
    import time as _t
    ck = (_kr_code(ticker) if str(market) == "국내" else _norm(ticker), str(market))
    if use_cache:
        hit = _CACHE.get(ck)
        if hit and hit[0] > _t.time():
            out = dict(hit[1])
            out["cached"] = True
            return out

    peers = find_peers(ticker, market)
    targets = ([{"ticker": peers["ticker"], "name": peers.get("name") or peers["ticker"],
                 "market": peers["market"]}]
               + peers["same_market"] + peers["cross_market"])

    # 시나리오 등장 이력(재료 유무) — 이슈×지지구간 판정에 필요. 한 번만 조회한다.
    # 반환은 set이 아니라 {ticker: 시나리오 등장 수} 맵이다.
    linked_map = {}
    try:
        from db import load_scenario_stocks_set
        linked_map = load_scenario_stocks_set() or {}
    except Exception as e:
        logger.error(f"[peer] 시나리오 종목 맵 로드 실패: {e}")

    rows = []
    try:
        with _fut.ThreadPoolExecutor(max_workers=min(8, max(1, len(targets)))) as ex:
            futs = {ex.submit(_one_row, t, linked_map): t for t in targets}
            for f in _fut.as_completed(futs, timeout=_FETCH_TIMEOUT):
                try:
                    rows.append(f.result())
                except Exception as e:
                    logger.error(f"[peer] row 실패: {e}")
    except Exception as e:
        # 타임아웃이어도 그때까지 모인 행은 그대로 쓴다 (부분 결과 > 빈 화면)
        logger.error(f"[peer] 병렬 수집 중단: {e}")

    by_tk = {r["ticker"]: r for r in rows}
    base = by_tk.get(peers["ticker"])

    def _ordered(entries):
        return [by_tk[e["ticker"]] for e in entries if e["ticker"] in by_tk]

    result = {
        "base": base,
        "cached": False,
        "sector": peers["sector"],
        "sub_sector": peers["sub_sector"],
        "theme": peers["theme"],
        "same_market": _ordered(peers["same_market"]),
        "cross_market": _ordered(peers["cross_market"]),
        "baseline_win_rate": ZONE_BASELINE,
        "zone_legend": {k: {"label": v["label"], "win_rate": v["win_rate"],
                            "n": v["n"], "note": v["note"]}
                        for k, v in _ZONE_META.items() if k != "neutral"},
    }
    # 부분 결과(수집 타임아웃)는 캐시하지 않는다 — 빈 표가 3분간 고정되면 곤란하다.
    if base and (result["same_market"] or result["cross_market"]):
        _CACHE[ck] = (_t.time() + CACHE_TTL_SEC, result)
        if len(_CACHE) > 200:
            for k in sorted(_CACHE, key=lambda x: _CACHE[x][0])[:100]:
                _CACHE.pop(k, None)
    return result
