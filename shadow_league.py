"""섀도우 리그 (v3.118.0) — 사용자에게 안 보이는 대조군 AI 트레이더들.

목적: 메인 에이전트(Gemini 하이브리드)와 같은 시장·같은 시각에 서로 다른 전략으로
가상매매하는 섀도우 2개를 병행 운용 → "어떤 매매 형태의 승률이 실제로 높은가"를
대조군으로 실측. 성적이 검증되면(전략당 실현 30건+) 승자 규칙의 메인 이식을 제안.

원칙:
- Gemini 호출 0 (결정론 규칙 + 로컬 ML만) → 추가 과금 없음.
- 메인 스캔이 이미 수집한 지표(decision._indicators)를 재사용 — 신규 다운로드는
  섀도우 보유 종목 시세 조회(종목당 1회)뿐.
- 저장은 기존 테이블 재사용(portfolio/trade_history/virtual_balances, owner=SHADOW_*).
  UI는 AI_AGENT만 조회하므로 화면에 자동으로 안 보임.

전략 프로파일:
- SHADOW_A "순수 눌림목": 실측 승률 62~71% 구간(볼린저 하단+눌림+조용한 거래량)을
  기계적으로 매수. 감·해설 없이 데이터 규칙만.
- SHADOW_B "ML 순종": 자체 ML 7일 확률 55%+ 종목만, 확률로 사이징. ML을 그대로
  믿으면 얼마나 버는지 측정(사후검증의 실전판).
- SHADOW_C "이슈×구간" (v3.119.0): 재료(최근 시나리오 등장 종목)가 있으면서 차트상
  지지 구간(볼린저 하단권 또는 20일선 ±3% 재접근)에 온 종목만 매수 — 사용자 실제
  매매 스타일(재료 보고 눌림 대기 진입)의 결정론 재현.
- SHADOW_D "수급 추종" (v3.120.0): 외국인·기관 순매수 상위(KR)만 매수(과열 배제).
  스마트머니 단독 축의 첫 실측 — 지금까지 스크리너 가점으로만 쓰이던 데이터.
- SHADOW_E "랜덤 베이스라인" (v3.120.0): 후보 중 무작위 매수. 과학적 대조군 —
  모든 전략의 성적이 '운인지 실력인지'를 가리는 눈금자. 날짜+티커 시드로 결정론화.
- SHADOW_F "모멘텀 추격" (v3.120.0): 5일 +10%↑ 강세주 추격 — 실측 22% 구간의
  실시간 확인사살용 악마의 변호인. 다른 전략이 금지하는 바로 그 구간만 산다.
청산(공통, 결정론) — v3.124.0 개정: **7거래일(≈10일) 순수 타임스탑 + 재난용 -20%만.**
이전(-5%/+8% 중간청산)은 측정 기준과 모순이었음: 근거 데이터(눌림목 62~71%)는
'7거래일 무손절 보유' 결과인데 섀도우에 -5% 손절을 달아 급락일 노이즈에 잘려나감
(2026-07-07 첫날 전원 당일 손절 사태, 사용자 지적). 매수 근거는 기간 만료까지
지켜보는 게 이 리그의 측정 원칙 — 가상 자금이라 손실 방어보다 측정이 목적.
⚠️ 청산 규칙을 통일해야 리그가 '진입 방식'만의 우열을 측정한다 — 전략별 청산 변경 금지.
"""
import logging
from datetime import datetime

logger = logging.getLogger("shadow_league")

SHADOW_START_CASH = 10_000_000.0
SHADOW_DAILY_BUY_CAP = 5      # 메인(3회)보다 완화 — 가상이므로 표본 축적 우선
SHADOW_BUDGET_FRAC = 0.12     # 포지션당 현금 12% (메인과 동일 기준)
EXIT_DISASTER = -20.0         # 재난용 손절 % (상폐급 폭락만 차단 — 측정 왜곡 최소화)
EXIT_DAYS = 10                # 타임스탑 (달력일 ≈ 7거래일, d7 호라이즌 정합) — 주 청산 수단

SHADOWS = ("SHADOW_A", "SHADOW_B", "SHADOW_C", "SHADOW_D", "SHADOW_E", "SHADOW_F")


def _conn():
    from db import get_db_conn
    return get_db_conn()


def _fee(market: str) -> float:
    return 0.21 if market == "국내" else 0.15   # 왕복 수수료+거래세 %


def _cash(cur, owner: str) -> float:
    cur.execute("SELECT balance FROM virtual_balances WHERE owner=?", (owner,))
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT OR REPLACE INTO virtual_balances (owner, balance, updated_time) VALUES (?, ?, ?)",
                    (owner, SHADOW_START_CASH, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        return SHADOW_START_CASH
    return float(row["balance"])


def _set_cash(cur, owner: str, amount: float):
    cur.execute("INSERT OR REPLACE INTO virtual_balances (owner, balance, updated_time) VALUES (?, ?, ?)",
                (owner, float(amount), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


def _holdings(cur, owner: str) -> list:
    cur.execute("SELECT ticker, name, quantity, buy_price, updated_time, buy_reason FROM portfolio WHERE UPPER(owner)=?",
                (owner.upper(),))
    return [dict(r) for r in cur.fetchall()]


def _today_buys(cur, owner: str) -> int:
    cur.execute("SELECT COUNT(*) AS n FROM portfolio WHERE UPPER(owner)=? AND substr(updated_time,1,10)=?",
                (owner.upper(), datetime.now().strftime("%Y-%m-%d")))
    row = cur.fetchone()
    return int(row["n"] if row else 0)


def _buy(cur, owner: str, tk: str, name: str, market: str, price: float, qty: int, note: str, usdkrw: float):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cost = price * qty * (1 + (0.00015 if market == "국내" else 0.0007))
    if market == "미국":
        cost *= usdkrw
    cash = _cash(cur, owner)
    if cash < cost or qty < 1:
        return False
    _set_cash(cur, owner, cash - cost)
    cur.execute(
        """INSERT OR REPLACE INTO portfolio (owner, ticker, name, quantity, buy_price, rating,
               updated_time, trade_source, trade_type, buy_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, '섀도우', '가상', ?)""",
        (owner, tk, name, qty, float(price), f"섀도우 자동 매수 ({owner})", now, note))
    return True


def _sell(cur, owner: str, h: dict, market: str, price: float, reason: str, usdkrw: float):
    qty = float(h["quantity"]); bp = float(h["buy_price"]); sp = float(price)
    buy_fee = 0.00015 if market == "국내" else 0.0007
    sell_fee = 0.00195 if market == "국내" else 0.0008
    invested = bp * qty * (1 + buy_fee)
    returned = sp * qty * (1 - sell_fee)
    profit = returned - invested
    pct = (profit / invested * 100) if invested > 0 else 0.0
    revenue = returned * (usdkrw if market == "미국" else 1.0)
    _set_cash(cur, owner, _cash(cur, owner) + revenue)
    # buy_reason에 진입 시점 컨텍스트(JSON)가 실려 있음 — 전략×상황 합성 분석의 원료.
    cur.execute(
        """INSERT INTO trade_history (owner, sell_date, ticker, name, quantity, buy_price, sell_price,
               profit, profit_pct, result, learning_point, trade_source, trade_type, buy_date, buy_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '섀도우', '가상', ?, ?)""",
        (owner, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), h["ticker"], h["name"], qty, bp, sp,
         profit, pct, "수익" if profit >= 0 else "손실", reason, str(h.get("updated_time") or ""),
         str(h.get("buy_reason") or "")))
    cur.execute("DELETE FROM portfolio WHERE UPPER(owner)=? AND ticker=?", (owner.upper(), h["ticker"]))
    return pct


def _price_of(tk: str, market: str):
    try:
        if market == "국내":
            from data_kr import get_kr_stock_price
            return float((get_kr_stock_price(tk) or {}).get("price", 0))
        from data import get_us_stock_detail
        return float((get_us_stock_detail(tk) or {}).get("price", 0))
    except Exception:
        return 0.0


def _wants_buy(owner: str, ind: dict, tk: str = "", ctx: dict = None) -> tuple:
    """전략별 매수 판정 → (매수여부, 사이징 배수, 근거 한 줄). ctx: 사이클 공용 컨텍스트."""
    bb = ind.get("bb_pctb"); m5 = ind.get("mom_5"); vr = ind.get("vol_ratio")
    rsi = ind.get("rsi"); ml7 = ind.get("ml_d7"); ma20d = ind.get("ma20_dist")
    if owner == "SHADOW_A":
        # 순수 눌림목 — 실측 승률 62~71% 구간의 기계적 재현
        ok = (bb is not None and bb < 0.25 and m5 is not None and m5 <= -3
              and (vr is None or vr < 2.0) and (rsi is None or rsi < 55))
        return ok, 1.0, f"눌림목 규칙(bb {bb}·5일 {m5}%·거래량 {vr}배)"
    if owner == "SHADOW_B":
        # ML 순종 — 7일 확률 55%+만, 확률만큼 사이징
        ok = ml7 is not None and ml7 >= 55.0
        mult = 1.0 + min(0.5, max(0.0, ((ml7 or 55) - 55) / 20.0)) if ok else 1.0
        return ok, mult, f"ML d7 {ml7}%"
    if owner == "SHADOW_C":
        # 이슈×구간 — 재료(최근 시나리오 등장)가 있는 종목이 지지 구간에 왔을 때만
        linked = int((ctx or {}).get("scenario_map", {}).get(tk, 0)) > 0
        zone = ((bb is not None and bb <= 0.35)
                or (ma20d is not None and -3.0 <= ma20d <= 1.0))
        not_hot = m5 is None or m5 < 5.0   # 급등 중 재료주 추격 배제
        ok = linked and zone and not_hot
        return ok, 1.0, f"이슈연관×지지구간(bb {bb}·MA20 {ma20d}%·5일 {m5}%)"
    if owner == "SHADOW_D":
        # 수급 추종 — 외국인·기관 순매수 상위(KR)면 매수, 과열만 배제
        in_supply = tk in (ctx or {}).get("supply_set", set())
        not_hot = (m5 is None or m5 < 10.0) and (rsi is None or rsi < 70)
        ok = in_supply and not_hot
        return ok, 1.0, f"외인·기관 순매수 상위(5일 {m5}%·RSI {rsi})"
    if owner == "SHADOW_E":
        # 랜덤 베이스라인 — 날짜+티커 시드 결정론 난수 (같은 날 재스캔해도 판정 불변)
        import hashlib
        seed = int(hashlib.md5(f"{datetime.now():%Y-%m-%d}{tk}".encode()).hexdigest()[:8], 16)
        ok = (seed % 100) < 12   # 후보의 약 12% 무작위 매수
        return ok, 1.0, "랜덤 대조군"
    if owner == "SHADOW_F":
        # 모멘텀 추격 — 5일 +10%↑ 강세주만 (다른 전략이 금지하는 구간의 확인사살)
        ok = m5 is not None and m5 >= 10.0
        return ok, 1.0, f"모멘텀 추격(5일 {m5}%)"
    return False, 1.0, ""


def run_shadow_cycle(candidates: list, kr_open: bool, us_open: bool, force: bool = False,
                     usdkrw: float = 1450.0, regimes: dict = None) -> dict:
    """1주기 섀도우 운용 — 메인 스캔 직후 호출. candidates: 메인 루프가 수집한
    [{ticker, name, market, price, ind}] (ind = decision._indicators, ml_d7 포함).
    regimes: {'국내': '공격/중립/수비', '미국': ...} — 진입 컨텍스트 기록용."""
    out = {}
    conn = _conn(); cur = conn.cursor()
    # 사이클 공용 컨텍스트 — C(이슈 연관 맵)·D(수급 상위 집합) 판정용, 사이클당 1회 로드
    ctx = {"scenario_map": {}, "supply_set": set()}
    try:
        from db import load_scenario_stocks_set
        ctx["scenario_map"] = load_scenario_stocks_set() or {}
    except Exception as e:
        logger.error(f"[shadow] 시나리오 맵 로드 실패: {e}")
    if kr_open or force:
        try:
            from data_kr import get_kr_frgn_inst_rank
            _sup = (get_kr_frgn_inst_rank("J", 30, "buy") or []) + (get_kr_frgn_inst_rank("Q", 30, "buy") or [])
            ctx["supply_set"] = {str(s.get("종목코드", "")).strip().zfill(6) for s in _sup if s.get("종목코드")}
        except Exception as e:
            logger.error(f"[shadow] 수급 랭킹 로드 실패: {e}")
    try:
        today = datetime.now()
        for owner in SHADOWS:
            summary = {"sell": 0, "buy": 0}
            # 1) 보유 청산 판정 (결정론: 손절 -5 / 익절 +8 / 10일 타임스탑)
            for h in _holdings(cur, owner):
                tk = str(h["ticker"])
                market = "국내" if tk.isdigit() else "미국"
                if (market == "국내" and not kr_open and not force) or (market == "미국" and not us_open and not force):
                    continue
                px = _price_of(tk, market)
                if px <= 0 or not h.get("buy_price"):
                    continue
                net = (px - float(h["buy_price"])) / float(h["buy_price"]) * 100.0 - _fee(market)
                held_days = 0
                try:
                    held_days = (today - datetime.strptime(str(h["updated_time"])[:10], "%Y-%m-%d")).days
                except Exception:
                    pass
                reason = None
                if net <= EXIT_DISASTER:
                    reason = f"재난 손절 {net:+.2f}% (상폐급 폭락 차단)"
                elif held_days >= EXIT_DAYS:
                    reason = f"기간만료 청산 {held_days}일 ({net:+.2f}%) — 근거를 끝까지 지켜본 결과"
                if reason:
                    _sell(cur, owner, h, market, px, reason, usdkrw)
                    summary["sell"] += 1
            # 2) 신규 매수 판정 — 메인 스캔이 수집한 후보 재사용 (다운로드 0)
            held = {str(h["ticker"]) for h in _holdings(cur, owner)}
            buys_left = SHADOW_DAILY_BUY_CAP - _today_buys(cur, owner)
            for c in candidates:
                if buys_left <= 0:
                    break
                tk = str(c.get("ticker") or "")
                if not tk or tk in held:
                    continue
                _mkt = c.get("market") or ("국내" if tk.isdigit() else "미국")
                # 개장 게이트 — 후보는 메인 루프에서 이미 걸러지지만 방어적으로 재확인
                if not force and ((_mkt == "국내" and not kr_open) or (_mkt == "미국" and not us_open)):
                    continue
                ind = c.get("ind") or {}
                ok, mult, note = _wants_buy(owner, ind, tk=tk, ctx=ctx)
                if not ok:
                    continue
                price = float(c.get("price") or 0)
                if price <= 0:
                    continue
                market = c.get("market") or ("국내" if tk.isdigit() else "미국")
                cash = _cash(cur, owner)
                budget = min(cash * SHADOW_BUDGET_FRAC * mult, cash * 0.25)
                px_krw = price * (usdkrw if market == "미국" else 1.0)
                qty = int(budget // px_krw) if px_krw > 0 else 0
                if qty < 1 and px_krw <= budget * 1.5 and px_krw <= cash * 0.25:
                    qty = 1
                if qty < 1:
                    continue
                # 진입 컨텍스트 기록 (JSON) — "어떤 상황에서 이 기법이 통했나"를 나중에
                # 전략×상황 매트릭스로 분석해 하나의 통합 패턴으로 합성하기 위한 원료.
                import json as _json
                _ctx_rec = _json.dumps({
                    "note": note, "regime": (regimes or {}).get(market, "?"),
                    "bb": ind.get("bb_pctb"), "m5": ind.get("mom_5"), "rsi": ind.get("rsi"),
                    "vr": ind.get("vol_ratio"), "ml7": ind.get("ml_d7"), "ma20d": ind.get("ma20_dist"),
                    "p52": ind.get("pos_52w"),
                    "issue": 1 if int(ctx.get("scenario_map", {}).get(tk, 0)) > 0 else 0,
                    "supply": 1 if tk in ctx.get("supply_set", set()) else 0,
                }, ensure_ascii=False)
                if _buy(cur, owner, tk, c.get("name") or tk, market, price, qty, _ctx_rec, usdkrw):
                    held.add(tk)
                    buys_left -= 1
                    summary["buy"] += 1
            conn.commit()
            out[owner] = summary
    except Exception as e:
        logger.error(f"[shadow] cycle 오류: {e}")
    finally:
        conn.close()
    return out


# ── 리그 큐레이터 (v3.126.0) — 섀도우 총괄 어시스턴트 ────────────────────────
# 매일 장 마감 후: 결정론 분석(랜덤 대조군 대비·매트릭스 주목 셀·최근 추세 변화)
# → Gemini 1콜(무검색·저가)로 애널리스트 코멘트 생성(이전 회차를 이어받아 누적 학습)
# → shadow_insights 테이블에 보관 + /performance·텔레그램 브리핑 노출.

def _insights_table(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS shadow_insights (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, insight_date TEXT UNIQUE,
        facts TEXT, commentary TEXT)""")


def analyze_league(min_n: int = 5) -> dict:
    """결정론 리그 분석 — 큐레이터의 팩트 수집 단계 (Gemini 없이 매일 무료 실행 가능).
    반환: {"findings": [문장...], "trend": [...], "cells": 매트릭스 상위}"""
    status = shadow_league_status()
    players = {p["owner"]: p for p in status.get("players", [])}
    findings, trend = [], []
    # 1) 랜덤 대조군(E) 대비 — '운인지 실력인지' 판정
    base = players.get("SHADOW_E")
    if base and base.get("win_rate") is not None and (base.get("realized_trades") or 0) >= 8:
        for o, p in players.items():
            if o == "SHADOW_E" or (p.get("realized_trades") or 0) < 8 or p.get("win_rate") is None:
                continue
            diff = p["win_rate"] - base["win_rate"]
            if abs(diff) >= 10:
                findings.append(f"{p['label']}: 랜덤 대조군 대비 승률 {diff:+.1f}%p — {'실력 신호' if diff > 0 else '전략 열위 신호'}")
    # 2) 매트릭스 주목 셀 — 리그 전체 평균 승률과의 편차가 큰 상황
    syn = shadow_synthesis(min_n=min_n)
    cells = syn.get("cells") or []
    all_wr = [p.get("win_rate") for p in players.values()
              if str(p.get("owner", "")).startswith("SHADOW") and p.get("win_rate") is not None]
    league_avg = (sum(all_wr) / len(all_wr)) if all_wr else None
    if league_avg is not None:
        for c in cells:
            dev = c["win_rate"] - league_avg
            if abs(dev) >= 15 and c["n"] >= 8:
                findings.append(
                    f"주목 셀: {str(c['strategy']).replace('SHADOW_', '섀도우 ')} × {c['situation']} — "
                    f"승률 {c['win_rate']}% (리그 평균 대비 {dev:+.1f}%p, {c['n']}건)")
    # 3) 최근 7일 vs 이전 추세 — 전략별 승률 변화 감지
    conn = _conn(); cur = conn.cursor()
    try:
        for o in SHADOWS + ("AI_AGENT",):
            cur.execute("""SELECT
                SUM(CASE WHEN sell_date >= date('now','-7 day') THEN 1 ELSE 0 END) rn,
                AVG(CASE WHEN sell_date >= date('now','-7 day') THEN (CASE WHEN profit_pct>0 THEN 100.0 ELSE 0 END) END) rw,
                SUM(CASE WHEN sell_date <  date('now','-7 day') THEN 1 ELSE 0 END) pn,
                AVG(CASE WHEN sell_date <  date('now','-7 day') THEN (CASE WHEN profit_pct>0 THEN 100.0 ELSE 0 END) END) pw
                FROM trade_history WHERE owner=?""", (o,))
            r = cur.fetchone()
            if r and (r["rn"] or 0) >= 5 and (r["pn"] or 0) >= 5 and r["rw"] is not None and r["pw"] is not None:
                delta = r["rw"] - r["pw"]
                if abs(delta) >= 12:
                    lbl = players.get(o, {}).get("label", o)
                    trend.append(f"{lbl}: 최근 7일 승률 {r['rw']:.0f}% (이전 {r['pw']:.0f}%, {delta:+.0f}%p) — 레짐 변화 가능성")
    finally:
        conn.close()
    return {"findings": findings, "trend": trend, "cells": cells[:8],
            "league_avg": round(league_avg, 1) if league_avg is not None else None}


def curator_daily_report(use_gemini: bool = True) -> dict:
    """리그 큐레이터 일일 리포트 — 분석 팩트를 요약하고(무료), Gemini가 이전 회차를
    이어받아 코멘트를 씀(하루 1콜·무검색·저가). shadow_insights에 날짜별 1건 보관."""
    a = analyze_league()
    status = shadow_league_status()
    today = datetime.now().strftime("%Y-%m-%d")
    fact_lines = []
    for p in status.get("players", []):
        fact_lines.append(f"- {p['label']}: 실현 {p.get('realized_trades')}건 승률 {p.get('win_rate')}% 평균 {p.get('avg_pct')}% 보유 {p.get('open_positions')}")
    fact_lines += [f"- {f}" for f in a["findings"]] + [f"- {t}" for t in a["trend"]]
    for c in a["cells"][:6]:
        fact_lines.append(f"- 셀: {c['strategy']}×{c['situation']} 승률 {c['win_rate']}% ({c['n']}건)")
    # 승자 해부 — 시장에서 실제로 오른 종목들의 전일 프로파일 (리그 밖 학습 소스)
    try:
        from winner_autopsy import autopsy_facts_lines
        fact_lines += autopsy_facts_lines()
    except Exception:
        pass
    facts = "\n".join(fact_lines)

    conn = _conn(); cur = conn.cursor()
    _insights_table(cur)
    cur.execute("SELECT insight_date, commentary FROM shadow_insights ORDER BY insight_date DESC LIMIT 1")
    prev = cur.fetchone()
    prev_txt = f"[직전 회차({prev['insight_date']}) 코멘트]\n{prev['commentary']}\n\n" if prev else ""
    conn.close()

    commentary = ""
    if use_gemini:
        try:
            from ai_engine import _call_gemini
            prompt = (
                "당신은 'AI 트레이딩 전략 리그'를 총괄하는 수석 애널리스트입니다.\n"
                "반드시 한국어로만 작성하세요. 한자 금지.\n"
                "리그: 7개 전략(메인 Gemini하이브리드 + 섀도우 A눌림목/B ML순종/C이슈×구간/D수급/E랜덤대조군/F모멘텀추격)이 "
                "동일 시장에서 경쟁 중. 목적은 승자 선발이 아니라 '어떤 상황에서 어떤 진입이 통하는가'를 찾아 통합 패턴을 합성하는 것.\n\n"
                + prev_txt +
                f"[오늘({today}) 실측 팩트]\n{facts}\n\n"
                "위 팩트만 근거로(추측 금지, 표본 적으면 적다고 명시) 다음을 작성:\n"
                "1) 오늘의 핵심 관찰 2~3문장 (직전 회차와 달라진 점이 있으면 반드시 비교)\n"
                "2) 승률이 오르는 조건에 대한 가설 1개 (검증에 필요한 표본 수 명시)\n"
                "3) 다음 관찰 포인트 1문장\n"
                "총 6문장 이내, 담백하게."
            )
            resp = _call_gemini(prompt, use_search=False, temperature=0.4,
                                timeout_sec=40, max_output_tokens=800, thinking=False)
            commentary = (resp.text if hasattr(resp, "text") else str(resp)).strip()
        except Exception as e:
            commentary = f"(코멘트 생성 실패: {e})"
    conn = _conn(); cur = conn.cursor()
    _insights_table(cur)
    cur.execute("INSERT OR REPLACE INTO shadow_insights (created_at, insight_date, facts, commentary) VALUES (?, ?, ?, ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), today, facts, commentary))
    conn.commit(); conn.close()
    return {"date": today, "facts": facts, "commentary": commentary,
            "findings": a["findings"], "trend": a["trend"]}


def latest_curator_insight() -> dict:
    """가장 최근 큐레이터 인사이트 (성과 탭·브리핑 노출용)."""
    try:
        conn = _conn(); cur = conn.cursor()
        _insights_table(cur)
        cur.execute("SELECT insight_date, commentary FROM shadow_insights ORDER BY insight_date DESC LIMIT 1")
        r = cur.fetchone(); conn.close()
        return {"date": r["insight_date"], "commentary": r["commentary"]} if r else {}
    except Exception:
        return {}


def format_league_briefing() -> str:
    """리그 진행 브리핑 (텔레그램 자동 발송용) — 순위·1라운드 진행률·매트릭스 상위 셀.
    터미널/Claude 세션과 무관하게 백엔드 스케줄러(월·목 16:40)가 발송한다."""
    s = shadow_league_status()
    players = s.get("players", [])
    ranked = sorted(players, key=lambda p: (p.get("win_rate") if p.get("win_rate") is not None else -1), reverse=True)
    lines = [f"🥊 섀도우 리그 브리핑 ({s.get('as_of', '')})", ""]
    for i, p in enumerate(ranked, 1):
        wr = p.get("win_rate"); avg = p.get("avg_pct"); n = p.get("realized_trades") or 0
        lines.append(f"{i}. {p.get('label')}")
        lines.append(f"   실현 {n}건 · 승률 {wr if wr is not None else '—'}% · 평균 {('%+.2f%%' % avg) if avg is not None else '—'} · 보유 {p.get('open_positions')}종목")
    cells = (s.get("synthesis") or {}).get("cells") or []
    if cells:
        lines += ["", "🧩 전략×상황 매트릭스 상위:"]
        for c in cells[:5]:
            lines.append(f"· {str(c['strategy']).replace('SHADOW_', '섀도우 ')} × {c['situation']}: 승률 {c['win_rate']}% (평균 {c['avg_pct']:+.2f}%, {c['n']}건)")
    else:
        lines += ["", "🧩 매트릭스: 아직 표본 5건+ 셀 없음 (수집 중)"]
    shadow_done = sum(min(30, p.get("realized_trades") or 0) for p in players
                      if str(p.get("owner", "")).startswith("SHADOW"))
    lines += ["", f"📈 1라운드 진행률: {shadow_done}/180 (전략당 실현 30건 목표)",
              "→ 달성 시 상황별 통합 패턴 1차 합성 + 2라운드(보유기간 리그) 시작"]
    ins = latest_curator_insight()
    if ins.get("commentary"):
        lines += ["", f"🧠 큐레이터 코멘트 ({ins.get('date')}):", ins["commentary"]]
    return "\n".join(lines)


def shadow_synthesis(min_n: int = 5) -> dict:
    """전략×상황 매트릭스 — 리그의 최종 목적. '누가 이기냐'가 아니라 각 기법이
    어떤 상황(레짐·이슈·수급·변동 구간)에서 유리한지를 실측해, 상황별 최적 기법을
    합친 '우리만의 통합 패턴'을 도출하기 위한 분석. (진입 컨텍스트 JSON 파싱)"""
    import json as _json
    conn = _conn(); cur = conn.cursor()
    cells = {}   # (owner, 상황키) -> [win수, 전체, 수익률합]
    try:
        cur.execute(
            """SELECT owner, profit_pct, buy_reason FROM trade_history
               WHERE owner LIKE 'SHADOW_%' AND buy_reason LIKE '{%'""")
        for r in cur.fetchall():
            try:
                c = _json.loads(r["buy_reason"])
            except Exception:
                continue
            pct = float(r["profit_pct"] or 0)
            situations = [f"레짐:{c.get('regime', '?')}"]
            if c.get("issue"): situations.append("이슈연관")
            if c.get("supply"): situations.append("수급상위")
            bb = c.get("bb")
            if bb is not None:
                situations.append("볼린저하단" if bb <= 0.35 else ("볼린저상단" if bb >= 0.7 else "볼린저중단"))
            for s in situations:
                k = (r["owner"], s)
                if k not in cells:
                    cells[k] = [0, 0, 0.0]
                cells[k][1] += 1
                cells[k][2] += pct
                if pct > 0:
                    cells[k][0] += 1
    except Exception as e:
        return {"error": str(e), "cells": []}
    finally:
        conn.close()
    out = []
    for (owner, situation), (w, n, s) in sorted(cells.items()):
        if n < min_n:
            continue   # 표본 부족 셀은 노이즈 — 숨김
        out.append({"strategy": owner, "situation": situation, "n": n,
                    "win_rate": round(w / n * 100, 1), "avg_pct": round(s / n, 2)})
    out.sort(key=lambda x: (x["win_rate"], x["n"]), reverse=True)
    return {"cells": out, "min_n": min_n,
            "note": "전략×상황별 실측 승률 — 상황별 최적 기법을 합성해 통합 패턴을 만들기 위한 매트릭스"}


def shadow_detail(owner: str, limit: int = 30) -> dict:
    """개별 섀도우 상세 — 보유 종목 + 최근 거래 (/performance 리그 우측 패널용).
    buy_reason의 진입 컨텍스트 JSON은 서버에서 파싱해 ctx로 내려준다."""
    import json as _json
    if owner not in SHADOWS:
        return {"error": "unknown owner", "holdings": [], "trades": []}
    conn = _conn(); cur = conn.cursor()
    try:
        cur.execute(
            """SELECT ticker, name, quantity, buy_price, updated_time AS buy_date, buy_reason
               FROM portfolio WHERE UPPER(owner)=? ORDER BY updated_time DESC""", (owner.upper(),))
        holdings = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """SELECT sell_date, buy_date, ticker, name, quantity, buy_price, sell_price,
                      profit, profit_pct, result, learning_point, buy_reason
               FROM trade_history WHERE owner=? ORDER BY sell_date DESC LIMIT ?""",
            (owner, int(limit)))
        trades = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    for row in holdings + trades:
        br = str(row.pop("buy_reason", "") or "")
        if br.startswith("{"):
            try:
                row["ctx"] = _json.loads(br)
            except Exception:
                pass
    # 보유 종목 현재가·실질 평가손익 — '산 금액 vs 지금 금액'이 한눈에 보이게 (v3.124.0)
    for h in holdings:
        tk = str(h["ticker"])
        market = "국내" if tk.isdigit() else "미국"
        try:
            px = _price_of(tk, market)
            if px > 0 and h.get("buy_price"):
                h["current_price"] = px
                h["eval_pct"] = round((px - float(h["buy_price"])) / float(h["buy_price"]) * 100 - _fee(market), 2)
        except Exception:
            pass
    return {"owner": owner, "holdings": holdings, "trades": trades}


def shadow_league_status() -> dict:
    """리그 성적표 — 메인(AI_AGENT) vs 섀도우들의 실현 성적 비교 (/performance용)."""
    conn = _conn(); cur = conn.cursor()
    out = {"as_of": datetime.now().strftime("%Y-%m-%d %H:%M"), "players": []}
    label = {"AI_AGENT": "메인 (Gemini 하이브리드)", "SHADOW_A": "섀도우 A (순수 눌림목)",
             "SHADOW_B": "섀도우 B (ML 순종)", "SHADOW_C": "섀도우 C (이슈×구간)",
             "SHADOW_D": "섀도우 D (수급 추종)", "SHADOW_E": "섀도우 E (랜덤 대조군)",
             "SHADOW_F": "섀도우 F (모멘텀 추격)"}
    try:
        for owner in ("AI_AGENT",) + SHADOWS:
            cur.execute(
                """SELECT COUNT(*) n,
                          ROUND(AVG(CASE WHEN profit_pct > 0 THEN 100.0 ELSE 0 END), 1) win,
                          ROUND(AVG(profit_pct), 2) avg_pct, ROUND(SUM(profit), 0) total_profit
                   FROM trade_history WHERE owner=?""", (owner,))
            r = dict(cur.fetchone() or {})
            cur.execute("SELECT COUNT(*) n FROM portfolio WHERE UPPER(owner)=?", (owner.upper(),))
            open_n = int((cur.fetchone() or {"n": 0})["n"])
            cur.execute("SELECT balance FROM virtual_balances WHERE owner=?",
                        ("AI" if owner == "AI_AGENT" else owner,))
            b = cur.fetchone()
            out["players"].append({
                "owner": owner, "label": label.get(owner, owner),
                "realized_trades": int(r.get("n") or 0),
                "win_rate": r.get("win"), "avg_pct": r.get("avg_pct"),
                "total_profit": r.get("total_profit"),
                "open_positions": open_n,
                "cash": round(float(b["balance"]), 0) if b else None,
            })
    except Exception as e:
        out["error"] = str(e)
    finally:
        conn.close()
    try:
        out["synthesis"] = shadow_synthesis()   # 전략×상황 매트릭스 (표본 5건+ 셀만)
    except Exception:
        pass
    try:
        out["curator"] = latest_curator_insight()   # 큐레이터 최신 코멘트
    except Exception:
        pass
    return out
