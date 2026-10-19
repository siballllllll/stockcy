"""그날 시장 판단 (v3.208.0) — 지수가 빠진 이유가 '조정(매수 기회)'인지 '붕괴(관망)'인지.

[왜] 섀도우 951건을 매수 당시 지수 상태로 쪼개 보니(2026-10-19) 숫자만으로는 답이 안 나왔다.
     지수 20일 고점 대비 -3~-5% 구간이 승률 23%로 최악이었지만 -8% 이하는 46%로 오히려 좋았다 —
     같은 '빠진 날'이라도 원인에 따라 결론이 정반대다. 사용자 지적: 하락이 추가매수 기회인
     조정장일 수도 있으니 뉴스·시나리오로 원인을 보고 판단해야 한다.
[그런데] AI 해설은 사후에 붙이면 무엇이든 그럴듯하다. 그래서 세 가지를 지킨다.
  1) 장 열리기 전에 적는다 — 국내는 09:00 전에 만든 판단만 채점한다(pre_open).
  2) 재료를 같이 남긴다 — 판단 근거가 된 이슈 번호와 뉴스 헤드라인(시나리오의 news_snapshot).
     틀렸을 때 '재료가 틀렸나 vs 해석이 틀렸나'를 가르기 위함이다.
  3) 기록만 한다 — 실전 매매에는 쓰지 않는다. 섀도우 C4(C와 같고 '관망'인 날만 신규 매수를 쉰다)가
     C와 겨뤄 이기면 그때 메인으로 옮긴다.
"""
import json
from datetime import datetime, timedelta

STANCES = ("매수 기회", "중립", "관망")
CAUSES = ("구조적 악재", "일시적 충격", "수급·차익실현", "호재·모멘텀", "뚜렷한 원인 없음")
_MKT = {"kr": ("국내", "KS11", "KOSPI"), "us": ("미국", "US500", "S&P500")}


def _conn():
    from db import get_db_conn
    return get_db_conn()


def _ensure_table(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS market_judgments (
        judge_date TEXT, market TEXT,
        cause_type TEXT, stance TEXT, confidence TEXT,
        driver_issues TEXT, reason TEXT, key_risk TEXT,
        index_state TEXT, evidence TEXT,
        pre_open INTEGER, created_at TEXT,
        idx_d1 REAL, idx_d5 REAL, outcome_checked_at TEXT,
        UNIQUE(judge_date, market))""")


def _local_today(mk: str) -> str:
    from zoneinfo import ZoneInfo
    tz = "Asia/Seoul" if mk == "kr" else "America/New_York"
    return datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")


def _index_state(code: str, mk: str) -> dict:
    """판단 재료용 지수 상태 — 전 거래일 종가 기준(장 전에 알 수 있는 값만).
    오늘 봉은 버린다: 장중·장 마감 뒤에 다시 돌리면 오늘 결과가 재료로 새어 들어간다."""
    import FinanceDataReader as fdr
    start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    c = fdr.DataReader(code, start)["Close"].dropna()
    c = c[[str(i)[:10] < _local_today(mk) for i in c.index]]
    if len(c) < 21:
        return {}
    last = float(c.iloc[-1])
    return {"last_date": str(c.index[-1])[:10], "close": round(last, 2),
            "d1": round((last / float(c.iloc[-2]) - 1) * 100, 2),
            "d5": round((last / float(c.iloc[-6]) - 1) * 100, 2),
            "d20": round((last / float(c.iloc[-21]) - 1) * 100, 2),
            "from_20d_high": round((last / float(c.iloc[-20:].max()) - 1) * 100, 2)}


def _evidence(issues: list) -> list:
    out = []
    for it in issues:
        heads = [f"{h.get('published', '')[5:16]} {h.get('title', '')}"
                 for h in ((it.get("news_snapshot") or {}).get("items") or [])[:4]]
        out.append({"no": it.get("issue_no"), "title": it.get("title"),
                    "summary": str(it.get("summary") or "")[:300],
                    "status": it.get("scout_status"), "headlines": heads})
    return out


def _prompt(today: str, states: dict, ev: list) -> str:
    st = "\n".join(f"- {_MKT[k][2]}: {json.dumps(v, ensure_ascii=False)}" for k, v in states.items())
    iss = "\n".join(
        f"[{e['no']}] {e['title']} ({e['status']})\n    {e['summary']}\n"
        + "".join(f"    · {h}\n" for h in e["headlines"])
        for e in ev)
    return (
        "당신은 신중한 매크로 전략가입니다. 한국어로만 답하세요.\n"
        f"오늘({today}) 장이 열리기 전입니다. 아래 재료로 오늘 국내(KOSPI)·미국(S&P500) 시장에서 "
        "개별 종목 **신규 매수**를 해도 되는 날인지 판단하세요.\n\n"
        "【지수 상태 — 전 거래일 종가 기준, d1/d5/d20 = 등락률%, from_20d_high = 20일 고점 대비%】\n"
        f"{st}\n\n【오늘의 이슈와 생성 시점 뉴스 헤드라인】\n{iss}\n"
        "【판단 원칙】\n"
        "- 지수가 빠졌다는 사실만으로 '관망'을 고르지 마세요. 원인이 일시적 충격·수급·차익실현이고 "
        "기업 이익 전망이 훼손되지 않았다면 오히려 '매수 기회'일 수 있습니다.\n"
        "- '관망'은 원인이 진행 중이고 더 빠질 근거가 구체적일 때만(신용 위기·정책 충격 진행·실적 "
        "전망 하향 등). 그 근거를 key_risk가 아니라 reason에 적으세요.\n"
        "- 헤드라인이 이슈를 뒷받침하지 않으면(관련 보도 없음·오래된 기사) 그 이슈의 비중을 낮추고 "
        "confidence를 낮추세요.\n"
        "- 확신이 없으면 '중립'이 정답입니다. 이 판단은 나중에 실제 결과와 대조해 채점됩니다.\n\n"
        "아래 JSON만 출력하세요(설명·마크다운 금지):\n"
        '{"kr": {"cause_type": "' + "/".join(CAUSES) + '", '
        '"stance": "' + "/".join(STANCES) + '", "confidence": "높음/보통/낮음", '
        '"driver_issues": [이슈 번호 정수], "reason": "2문장 이내", '
        '"key_risk": "이 판단이 틀리게 될 조건 1문장"}, '
        '"us": {같은 형식}}'
    )


def judge_market_today(scenarios: dict | None = None, force: bool = False) -> dict:
    """오늘 판단을 만든다(이미 있으면 건너뜀). scenarios 없으면 오늘 시나리오 로그를 읽는다."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    conn = _conn(); cur = conn.cursor()
    try:
        _ensure_table(cur); conn.commit()
        cur.execute("SELECT COUNT(*) FROM market_judgments WHERE judge_date=?", (today,))
        if cur.fetchone()[0] >= 2 and not force:
            return {"skipped": "exists"}
    finally:
        conn.close()
    if scenarios is None:
        from db import load_daily_market_log
        scenarios = load_daily_market_log(today, "scenarios") or {}
    issues = (scenarios or {}).get("issues") or []
    if not issues:
        return {"skipped": "no_scenarios"}
    states = {}
    for k, (_, code, _) in _MKT.items():
        try:
            states[k] = _index_state(code, k)
        except Exception as e:
            print(f"[market judgment] {code} 지수 조회 실패: {e}")
            states[k] = {}
    ev = _evidence(issues)
    from ai_engine import _call_llm, _parse_json_response
    resp = _call_llm(_prompt(today, states, ev), use_search=False, temperature=0.3,
                     response_mime_type="application/json", timeout_sec=90,
                     max_output_tokens=1500, thinking=False)
    res = _parse_json_response(resp)
    if not isinstance(res, dict):
        return {"error": "판단 파싱 실패"}
    pre_open_kr = 1 if (now.hour, now.minute) < (9, 0) else 0
    saved = {}
    conn = _conn(); cur = conn.cursor()
    try:
        for k in ("kr", "us"):
            j = res.get(k) or {}
            stance = j.get("stance") if j.get("stance") in STANCES else "중립"
            cause = j.get("cause_type") if j.get("cause_type") in CAUSES else "뚜렷한 원인 없음"
            drivers = [int(x) for x in (j.get("driver_issues") or []) if str(x).isdigit()]
            cur.execute(
                """INSERT OR REPLACE INTO market_judgments
                   (judge_date, market, cause_type, stance, confidence, driver_issues, reason, key_risk,
                    index_state, evidence, pre_open, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (today, k, cause, stance, str(j.get("confidence") or ""), json.dumps(drivers),
                 str(j.get("reason") or "")[:500], str(j.get("key_risk") or "")[:300],
                 json.dumps(states.get(k) or {}, ensure_ascii=False),
                 json.dumps([e for e in ev if e["no"] in drivers] or ev, ensure_ascii=False),
                 # 미국 판단은 KST 아침에 만들어 그날 밤 개장 전이므로 항상 장 전이다.
                 pre_open_kr if k == "kr" else 1, now.strftime("%Y-%m-%d %H:%M:%S")))
            saved[k] = {"stance": stance, "cause": cause}
        conn.commit()
    finally:
        conn.close()
    print(f"[market judgment] {today} 국내 {saved.get('kr')} · 미국 {saved.get('us')}")
    return {"saved": saved}


def today_stances() -> dict:
    """섀도우용 — {'국내': stance, '미국': stance}. 각 시장의 현지 날짜 판단을 본다.
    미국 세션(현지 D일)은 KST D일 아침에 만든 판단이 맡는다 — KST 자정을 넘긴 새벽에도 같다."""
    from zoneinfo import ZoneInfo
    out = {}
    try:
        kr_d = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
        us_d = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        conn = _conn(); cur = conn.cursor()
        _ensure_table(cur)
        for mk, d, label in (("kr", kr_d, "국내"), ("us", us_d, "미국")):
            cur.execute("SELECT stance FROM market_judgments WHERE judge_date=? AND market=?", (d, mk))
            r = cur.fetchone()
            if r:
                out[label] = r[0]
        conn.close()
    except Exception as e:
        print(f"[market judgment] 오늘 판단 조회 실패: {e}")
    return out


def track_judgment_outcomes() -> dict:
    """판단일 지수 결과 채우기 — d1 = 그날 시가→종가, d5 = 그날 시가→5거래일째 종가."""
    import pandas as pd
    import FinanceDataReader as fdr
    conn = _conn(); cur = conn.cursor()
    updated = 0
    try:
        _ensure_table(cur)
        cur.execute("SELECT judge_date, market FROM market_judgments WHERE idx_d5 IS NULL")
        rows = cur.fetchall()
        if not rows:
            return {"updated": 0}
        # 시작일을 며칠 당긴다 — FDR US500은 시작일이 오늘이면 빈 응답에서 'timestamp' KeyError가 난다.
        start = (datetime.strptime(min(r[0] for r in rows), "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        bars = {}
        for k, (_, code, _) in _MKT.items():
            try:
                d = fdr.DataReader(code, start)[["Open", "Close"]].dropna()
                d.index = pd.to_datetime(d.index).normalize()
                # 현지 오늘 봉은 장중 미완성일 수 있다 — 끝난 거래일만 채점한다.
                bars[k] = d[d.index < pd.Timestamp(_local_today(k))]
            except Exception as e:
                print(f"[market judgment] {code} 결과 조회 실패: {e}")
        for jd, mk in rows:
            d = bars.get(mk)
            if d is None:
                continue
            sub = d[d.index >= pd.Timestamp(jd)]
            if sub.empty:
                continue
            o = float(sub["Open"].iloc[0]) or float(sub["Close"].iloc[0])
            d1 = (float(sub["Close"].iloc[0]) / o - 1) * 100
            d5 = (float(sub["Close"].iloc[4]) / o - 1) * 100 if len(sub) >= 5 else None
            cur.execute("""UPDATE market_judgments SET idx_d1=?, idx_d5=?, outcome_checked_at=?
                           WHERE judge_date=? AND market=?""",
                        (round(d1, 2), round(d5, 2) if d5 is not None else None,
                         datetime.now().strftime("%Y-%m-%d %H:%M:%S"), jd, mk))
            updated += 1
        conn.commit()
    finally:
        conn.close()
    return {"updated": updated}


def load_judgment_stats() -> dict:
    """판단별 채점 — 지수 결과와, 그날 섀도우가 산 종목의 실현 성적."""
    conn = _conn(); cur = conn.cursor()
    try:
        _ensure_table(cur)
        cur.execute("""SELECT judge_date, market, stance, cause_type, confidence, reason,
                              pre_open, idx_d1, idx_d5 FROM market_judgments
                       ORDER BY judge_date DESC""")
        rows = [dict(r) for r in cur.fetchall()]
        # 섀도우 실현 거래 — 매수일(시장 현지)과 시장으로 판단과 잇는다
        cur.execute("""SELECT ticker, buy_date, profit_pct FROM trade_history
                       WHERE trade_source='섀도우' AND buy_date >= ?""",
                    (min((r["judge_date"] for r in rows), default="9999"),))
        trades = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    from zoneinfo import ZoneInfo
    KST, NY = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")
    by_day = {}
    for t in trades:
        try:
            bt = datetime.strptime(str(t["buy_date"])[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
        except Exception:
            continue
        mk = "kr" if str(t["ticker"]).isdigit() else "us"
        d = (bt.astimezone(NY) if mk == "us" else bt).strftime("%Y-%m-%d")
        by_day.setdefault((d, mk), []).append(float(t["profit_pct"] or 0))
    groups = []
    for mk in ("kr", "us"):
        for stance in STANCES:
            rs = [r for r in rows if r["market"] == mk and r["stance"] == stance and r["pre_open"]]
            if not rs:
                continue
            d1 = [r["idx_d1"] for r in rs if r["idx_d1"] is not None]
            d5 = [r["idx_d5"] for r in rs if r["idx_d5"] is not None]
            pcts = [p for r in rs for p in by_day.get((r["judge_date"], mk), [])]
            groups.append({
                "market": _MKT[mk][0], "stance": stance, "days": len(rs),
                "idx_d1_avg": round(sum(d1) / len(d1), 2) if d1 else None,
                "idx_d5_avg": round(sum(d5) / len(d5), 2) if d5 else None,
                "shadow_trades": len(pcts),
                "shadow_win_rate": round(sum(1 for p in pcts if p > 0) / len(pcts) * 100, 1) if pcts else None,
                "shadow_avg": round(sum(pcts) / len(pcts), 2) if pcts else None,
            })
    return {"groups": groups, "recent": rows[:14],
            "note": "장 전에 만든 판단만 채점(국내 09:00 전). 섀도우 성적은 실현 거래만 — 보유 중인 건 아직 빠져 있다."}
