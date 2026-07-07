"""일일 승자 해부 (v3.127.0) — '오늘 실제로 오른 종목은 오르기 전날 어떤 모습이었나'.

사용자 방침(2026-07-07): 우리 추천의 사후 성적만 보지 말고, 매일 시장에서 실제로
오른 종목들의 흐름·테마·이슈·차트·수급·세력·심리를 디테일하게 해부해 누적 학습.
하락장에도 오르는 종목은 있으므로 이 루프는 장세와 무관하게 매일 배운다.

수집(결정론·Gemini 0원, 평일 장 마감 후 1회):
- 오늘 상승률 상위(KR, +5%↑) 종목의 '전일 기준' 상태를 복원:
  차트(볼린저%b·5/20일 모멘텀·RSI·거래량비율·MA20 이격·52주 위치)
  + 수급(전일 외인·기관 순매수 상위 여부, frgn_inst_snapshots)
  + 이슈(시나리오 등장 여부) + 심리 프록시(전일 거래량 폭증 여부)
- winner_autopsy 테이블에 날짜별 적재 → autopsy_profile()이 '상승 전조 프로파일'을
  집계(오른 종목의 몇 %가 전일 볼린저 하단이었나 등) → 리그 큐레이터 팩트에 공급.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("winner_autopsy")

MIN_GAIN_PCT = 5.0    # '오늘의 승자' 기준 상승률
MAX_WINNERS = 25      # 하루 해부 대상 상한 (OHLCV 조회 비용 통제)


def _conn():
    from db import get_db_conn
    return get_db_conn()


def _table(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS winner_autopsy (
        autopsy_date TEXT, ticker TEXT, name TEXT, gain_pct REAL,
        bb_pctb REAL, mom_5 REAL, mom_20 REAL, rsi REAL, vol_ratio REAL,
        ma20_dist REAL, pos_52w REAL,
        was_supply INTEGER, was_issue INTEGER, was_vol_surge INTEGER,
        created_at TEXT, PRIMARY KEY (autopsy_date, ticker))""")


def _prev_state(ticker: str):
    """전일(상승 전날) 기준 차트 상태 복원 — 오늘 캔들을 제외하고 지표 계산."""
    import FinanceDataReader as fdr
    start = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    df = fdr.DataReader(ticker, start)
    if df is None or len(df) < 22:
        return None
    # 오늘 봉 제외 (마지막 행이 오늘이면 잘라냄)
    if df.index[-1].date() >= datetime.now().date():
        df = df.iloc[:-1]
    if len(df) < 21:
        return None
    c = [float(x) for x in df["Close"].values]
    h = [float(x) for x in df["High"].values]
    l = [float(x) for x in df["Low"].values]
    v = [float(x) for x in df["Volume"].values]
    from ml_model import _extra_feats
    f = _extra_feats(c, h, l)
    # RSI(14)·거래량비율·MA20 이격·52주 위치 (판단시점 = 전일 종가)
    deltas = [c[i] - c[i - 1] for i in range(1, len(c))]
    gains = [d if d > 0 else 0.0 for d in deltas]; losses = [-d if d < 0 else 0.0 for d in deltas]
    ag = sum(gains[-14:]) / 14; al = sum(losses[-14:]) / 14
    f["rsi"] = round(100 - (100 / (1 + ag / al)), 1) if al > 0 else 100.0
    v20 = sum(v[-20:]) / 20
    f["vol_ratio"] = round(v[-1] / v20, 2) if v20 > 0 else 1.0
    ma20 = sum(c[-20:]) / 20
    f["ma20_dist"] = round((c[-1] / ma20 - 1) * 100, 2) if ma20 else None
    n52 = min(len(c), 252); hi = max(h[-n52:]); lo = min(l[-n52:])
    f["pos_52w"] = round((c[-1] - lo) / (hi - lo) * 100, 1) if hi > lo else 50.0
    return f


def run_daily_autopsy() -> dict:
    """오늘의 승자(상승률 상위) 해부 — 평일 장 마감 후 스케줄러가 호출."""
    today = datetime.now().strftime("%Y-%m-%d")
    # 1. 오늘 상승률 상위 수집 (KOSPI+KOSDAQ)
    winners = []
    try:
        from data_kr import get_kr_change_ranking
        for mkt in ("J", "Q"):
            for it in (get_kr_change_ranking(market=mkt) or []):
                code = str(it.get("종목코드", "")).strip().zfill(6)
                try:
                    raw_chg = it.get("등락률(%)", it.get("등락률", it.get("change_pct", 0)))
                    chg = float(str(raw_chg).replace("%", "").replace(",", ""))
                except Exception:
                    continue
                if code and code != "000000" and chg >= MIN_GAIN_PCT:
                    winners.append({"ticker": code, "name": str(it.get("종목명", code)), "gain": chg})
    except Exception as e:
        logger.error(f"[autopsy] 상승 랭킹 수집 실패: {e}")
        return {"saved": 0, "error": str(e)}
    # 중복 제거·상한
    seen = set(); uniq = []
    for w in sorted(winners, key=lambda x: -x["gain"]):
        if w["ticker"] not in seen:
            seen.add(w["ticker"]); uniq.append(w)
    winners = uniq[:MAX_WINNERS]
    if not winners:
        return {"saved": 0, "note": "오늘 +5% 이상 상승 종목 없음"}

    # 2. 컨텍스트 소스 로드 (전일 수급 상위·시나리오 등장)
    supply_prev = set()
    conn = _conn(); cur = conn.cursor()
    try:
        cur.execute("""SELECT DISTINCT ticker FROM frgn_inst_snapshots
                       WHERE snapshot_date >= date('now','-3 day') AND snapshot_date < date('now')""")
        supply_prev = {str(r["ticker"]).zfill(6) for r in cur.fetchall()}
    except Exception as e:
        logger.error(f"[autopsy] 수급 스냅샷 로드 실패: {e}")
    scenario_map = {}
    try:
        from db import load_scenario_stocks_set
        scenario_map = load_scenario_stocks_set() or {}
    except Exception:
        pass

    # 3. 종목별 전일 상태 복원 + 적재
    _table(cur)
    saved = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for w in winners:
        try:
            f = _prev_state(w["ticker"])
            if not f:
                continue
            cur.execute(
                """INSERT OR REPLACE INTO winner_autopsy
                   (autopsy_date, ticker, name, gain_pct, bb_pctb, mom_5, mom_20, rsi,
                    vol_ratio, ma20_dist, pos_52w, was_supply, was_issue, was_vol_surge, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (today, w["ticker"], w["name"], w["gain"],
                 f.get("bb_pctb"), f.get("mom_5"), f.get("mom_20"), f.get("rsi"),
                 f.get("vol_ratio"), f.get("ma20_dist"), f.get("pos_52w"),
                 1 if w["ticker"] in supply_prev else 0,
                 1 if int(scenario_map.get(w["ticker"], 0)) > 0 else 0,
                 1 if (f.get("vol_ratio") or 0) >= 2.0 else 0,
                 now))
            saved += 1
        except Exception as e:
            logger.error(f"[autopsy] {w['ticker']} 해부 실패: {e}")
    conn.commit(); conn.close()
    logger.info(f"[autopsy] {today} 승자 {saved}건 해부 완료")
    return {"saved": saved, "date": today}


def autopsy_profile(days: int = 14) -> dict:
    """최근 N일 '상승 전조 프로파일' — 오른 종목들이 전날 어떤 상태였는지 비율 집계.
    큐레이터 팩트·스크리너 검증에 공급. (전조 비율이 높은 조건 = 상승 예고 신호 후보)"""
    conn = _conn(); cur = conn.cursor()
    try:
        _table(cur)
        cur.execute(f"""SELECT COUNT(*) n,
            AVG(gain_pct) avg_gain,
            AVG(CASE WHEN bb_pctb <= 0.35 THEN 100.0 ELSE 0 END) p_bb_low,
            AVG(CASE WHEN bb_pctb >= 0.7 THEN 100.0 ELSE 0 END) p_bb_high,
            AVG(CASE WHEN mom_5 < 0 THEN 100.0 ELSE 0 END) p_m5_neg,
            AVG(CASE WHEN mom_5 >= 10 THEN 100.0 ELSE 0 END) p_m5_surge,
            AVG(CASE WHEN was_supply = 1 THEN 100.0 ELSE 0 END) p_supply,
            AVG(CASE WHEN was_issue = 1 THEN 100.0 ELSE 0 END) p_issue,
            AVG(CASE WHEN was_vol_surge = 1 THEN 100.0 ELSE 0 END) p_vol_surge,
            AVG(CASE WHEN rsi < 40 THEN 100.0 ELSE 0 END) p_rsi_low,
            AVG(CASE WHEN pos_52w >= 70 THEN 100.0 ELSE 0 END) p_52w_high
            FROM winner_autopsy WHERE autopsy_date >= date('now', ?)""", (f"-{int(days)} day",))
        r = dict(cur.fetchone() or {})
    finally:
        conn.close()
    n = int(r.get("n") or 0)
    if n == 0:
        return {"n": 0, "note": "해부 표본 없음 (첫 장 마감 후 쌓임)"}
    out = {"n": n, "days": days, "avg_gain": round(r["avg_gain"], 1)}
    labels = {
        "p_bb_low": "전일 볼린저 하단권(%b≤0.35)", "p_bb_high": "전일 볼린저 상단권(%b≥0.7)",
        "p_m5_neg": "전일 5일 모멘텀 마이너스(눌림)", "p_m5_surge": "전일 이미 5일 +10%↑(연속 급등)",
        "p_supply": "전일 외인·기관 순매수 상위", "p_issue": "시나리오·이슈 연관",
        "p_vol_surge": "전일 거래량 2배+ (심리 프록시)", "p_rsi_low": "전일 RSI 40 미만",
        "p_52w_high": "전일 52주 고점권(70%+)",
    }
    out["profile"] = {labels[k]: round(r[k], 1) for k in labels if r.get(k) is not None}
    return out


def autopsy_facts_lines(days: int = 14) -> list:
    """큐레이터 팩트 블록용 — 상승 전조 프로파일을 문장 리스트로."""
    p = autopsy_profile(days)
    if not p.get("n"):
        return []
    lines = [f"[승자 해부] 최근 {p['days']}일 상승률 +{MIN_GAIN_PCT}%↑ 종목 {p['n']}건 (평균 +{p['avg_gain']}%)의 '전일' 상태:"]
    for label, pct in sorted(p["profile"].items(), key=lambda kv: -kv[1]):
        if pct >= 25:   # 유의미한 전조만
            lines.append(f"  · {label}: {pct}%")
    return lines
