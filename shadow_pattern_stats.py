"""섀도우 실측 패턴표 — 매수 순간 차트 상태별 시장 대비 승률 (v3.225.0).

[왜] 패턴 스크리너의 근거(개인 매매 프로필)는 사용자가 2026-06-29 이후 매매를 안 해 굳었다.
섀도우는 매일 기계적으로 사고팔고, 매수 순간 지표(bb·RSI·거래량비·20일선 이격·52주 위치·5일
모멘텀·이슈·수급)를 buy_reason JSON에 남긴다. 그 확정 거래를 조건별로 나눠 채점한 표가
'지금 시장에서 어떤 자리가 이기나'의 살아 있는 근거다.

채점 = 승률 기준 고정 규칙(v3.214.0)과 같다:
  초과수익 = profit_pct − 같은 보유 기간 지수 수익률(국내 코스피·미국 S&P500, 매수일 시가→매도일 종가)
  승리 = 초과수익 > 왕복 비용(국내 0.21%·미국 0.15%)  ← load_agent_trade_performance와 같은 식
같은 날 같은 종목을 여러 섀도우가 산 건 1건으로 합친다(평균). 섀도우 E(랜덤 대조군)는 뺀다.

⚠️ 이 표는 '보기와 판정용'이다. 스크리너 필터 문턱을 이 표로 자동으로 바꾸지 않는다 —
   매주 숫자가 흔들릴 때마다 규칙이 바뀌면 무엇이 효과였는지 가릴 수 없다(VERIFY.md V33).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_csv", "shadow_pattern_stats.json")
MIN_N = 25

# 스크리너 과열 필터(ai_engine.screen_by_my_pattern, v3.225.0)와 같은 문턱 — 어긋나면 판정이 틀린다.
HOT_RULES = (
    ("m5",   "5일 +5~10% 상승 추격", lambda x: _has(x, "m5") and 5 <= x["m5"] < 10),
    ("rsi",  "RSI 65 이상",           lambda x: _has(x, "rsi") and x["rsi"] >= 65),
    ("ma20", "20일선 +10% 이상",      lambda x: _has(x, "ma20d") and x["ma20d"] >= 10),
    ("vr",   "거래량 2배 이상",        lambda x: _has(x, "vr") and x["vr"] >= 2),
    ("p52",  "52주 고점권 80%+",       lambda x: _has(x, "p52") and x["p52"] >= 80),
)


def _has(x: dict, k: str) -> bool:
    return x.get(k) is not None


def is_hot(x: dict) -> bool:
    return any(f(x) for _, _, f in HOT_RULES)


def is_calm(x: dict) -> bool:
    """조용한 눌림 — 20일선 ±3%·RSI 35~55·거래량 평소 1.2배 미만 (V33 가점 후보)."""
    return (_has(x, "ma20d") and -3 <= x["ma20d"] < 3 and _has(x, "rsi") and 35 <= x["rsi"] < 55
            and _has(x, "vr") and x["vr"] < 1.2)


def _bench_series():
    import FinanceDataReader as fdr
    import yfinance as yf
    out = {}
    for kr in (True, False):
        ser = None
        for src in (("fdr", "KS11"), ("yf", "^KS11")) if kr else (("yf", "^GSPC"),):
            try:
                df = (fdr.DataReader(src[1], "2026-06-01") if src[0] == "fdr"
                      else yf.download(src[1], start="2026-06-01", progress=False, timeout=15))
                if df is None or df.empty:
                    continue
                o, c = df["Open"], df["Close"]
                if hasattr(o, "columns"):
                    o, c = o.iloc[:, 0], c.iloc[:, 0]
                ser = [(d.strftime("%Y-%m-%d"), float(o.loc[d]), float(v)) for d, v in c.dropna().items()]
                break
            except Exception as e:
                print(f"[shadow pattern] 지수 {src[1]} 실패: {e}")
        out[kr] = ser
    return out


def _idx(ser, day):
    bi = None
    for j, (d, _, _) in enumerate(ser):
        if d <= day:
            bi = j
        else:
            break
    return bi


def _bench(series, tk, bd, sd):
    """backfill_perf_benchmarks(에이전트 확정 거래)와 같은 방식 — 매수일 시가→매도일 종가, 미국은 KST-14h."""
    kr = tk.isdigit()
    ser = series.get(kr)
    if not ser:
        return None
    shift = timedelta(0) if kr else timedelta(hours=14)
    try:
        d0 = (datetime.strptime(str(bd)[:19], "%Y-%m-%d %H:%M:%S") - shift).strftime("%Y-%m-%d")
        d1 = (datetime.strptime(str(sd)[:19], "%Y-%m-%d %H:%M:%S") - shift).strftime("%Y-%m-%d")
    except Exception:
        return None
    i0, i1 = _idx(ser, d0), _idx(ser, d1)
    if i0 is None or i1 is None:
        return None
    b0 = ser[i0][1] if ser[i0][0] == d0 and ser[i0][1] > 0 else ser[i0][2]
    return (ser[i1][2] / b0 - 1) * 100 if b0 > 0 else None


def load_trades(since: str | None = None, series=None) -> list:
    """채점된 섀도우 확정 거래(중복 제거). since(YYYY-MM-DD)면 그날 이후 매수분만."""
    from db import get_db_conn
    series = series or _bench_series()
    conn = get_db_conn(); cur = conn.cursor()
    try:
        sql = ("SELECT owner, ticker, buy_date, sell_date, profit_pct, buy_reason FROM trade_history "
               "WHERE owner LIKE 'SHADOW_%' AND owner != 'SHADOW_E'")
        args = ()
        if since:
            sql += " AND buy_date >= ?"
            args = (since,)
        rows = cur.execute(sql, args).fetchall()
    finally:
        conn.close()
    graded = []
    for r in rows:
        br = str(r["buy_reason"] or "")
        if " | {" in br:                       # 추매 행: "추매 n회차 (...) | {json}"
            br = br.split(" | ", 1)[1]
        if not br.startswith("{"):
            continue
        try:
            x = json.loads(br)
        except Exception:
            continue
        tk = str(r["ticker"])
        b = _bench(series, tk, r["buy_date"], r["sell_date"])
        if b is None:
            continue
        p = float(r["profit_pct"] or 0)
        x.update(tk=tk, d=str(r["buy_date"])[:10], p=p, e=p - b, fee=0.21 if tk.isdigit() else 0.15)
        graded.append(x)
    groups: dict = {}
    for x in graded:
        groups.setdefault((x["tk"], x["d"]), []).append(x)
    uniq = []
    for v in groups.values():
        b = dict(v[0])
        b["p"] = sum(y["p"] for y in v) / len(v)
        b["e"] = sum(y["e"] for y in v) / len(v)
        uniq.append(b)
    return uniq


def summarize(rows: list, min_n: int = MIN_N) -> dict | None:
    if len(rows) < min_n:
        return None
    win = lambda L: round(sum(1 for x in L if x["e"] > x["fee"]) / max(1, len(L)) * 100, 1)
    s = sorted(rows, key=lambda x: x["d"])
    h = len(s) // 2
    return {"n": len(rows), "win_rate": win(rows), "excess": round(sum(x["e"] for x in rows) / len(rows), 2),
            "raw_win_rate": round(sum(1 for x in rows if x["p"] > 0) / len(rows) * 100, 1),
            "first_half": win(s[:h]), "second_half": win(s[h:]), "split_date": s[h]["d"]}


def _conditions():
    kr = lambda x: x["tk"].isdigit()
    C = [("all", "전체", lambda x: True), ("kr", "국내", kr), ("us", "미국", lambda x: not kr(x)),
         ("issue1", "이슈 있음", lambda x: x.get("issue")), ("issue0", "이슈 없음", lambda x: not x.get("issue")),
         ("supply1", "외국인·기관 순매수 상위", lambda x: x.get("supply"))]
    for lo, hi, lab in ((-9, 0.2, "하단 이탈~0.2"), (0.2, 0.4, "0.2~0.4"), (0.4, 0.6, "0.4~0.6"),
                        (0.6, 0.8, "0.6~0.8"), (0.8, 9, "0.8 이상")):
        C.append((f"bb_{lo}_{hi}", f"볼린저 위치 {lab}", lambda x, lo=lo, hi=hi: _has(x, "bb") and lo <= x["bb"] < hi))
    for lo, hi, lab in ((-99, -5, "-5% 미만"), (-5, 0, "-5~0%"), (0, 5, "0~+5%"), (5, 10, "+5~10%"), (10, 999, "+10% 이상")):
        C.append((f"m5_{lo}_{hi}", f"5일 등락 {lab}", lambda x, lo=lo, hi=hi: _has(x, "m5") and lo <= x["m5"] < hi))
    for lo, hi in ((0, 35), (35, 45), (45, 55), (55, 65), (65, 101)):
        C.append((f"rsi_{lo}_{hi}", f"RSI {lo}~{hi}" if hi < 101 else f"RSI {lo} 이상",
                  lambda x, lo=lo, hi=hi: _has(x, "rsi") and lo <= x["rsi"] < hi))
    for lo, hi in ((0, 20), (20, 50), (50, 80), (80, 101)):
        C.append((f"p52_{lo}_{hi}", f"52주 위치 {lo}~{min(hi, 100)}%", lambda x, lo=lo, hi=hi: _has(x, "p52") and lo <= x["p52"] < hi))
    for lo, hi, lab in ((0, 0.7, "0.7배 미만"), (0.7, 1.2, "0.7~1.2배"), (1.2, 2, "1.2~2배"), (2, 999, "2배 이상")):
        C.append((f"vr_{lo}_{hi}", f"거래량 {lab}", lambda x, lo=lo, hi=hi: _has(x, "vr") and lo <= x["vr"] < hi))
    for lo, hi, lab in ((-99, -10, "-10% 아래"), (-10, -3, "-10~-3%"), (-3, 3, "±3%"), (3, 10, "+3~10%"), (10, 999, "+10% 위")):
        C.append((f"ma20_{lo}_{hi}", f"20일선 {lab}", lambda x, lo=lo, hi=hi: _has(x, "ma20d") and lo <= x["ma20d"] < hi))
    C += [("calm", "조용한 눌림 (20일선±3%·RSI 35~55·거래량<1.2배)", is_calm),
          ("hot", "과열 (스크리너 필터 조건 하나라도)", is_hot),
          ("not_hot", "과열 아님", lambda x: not is_hot(x)),
          ("kr_bb_issue", "국내·볼린저<0.3·이슈 있음",
           lambda x: kr(x) and _has(x, "bb") and x["bb"] < 0.3 and x.get("issue"))]
    return C


def build(save: bool = True) -> dict:
    rows = load_trades()
    table = []
    for key, label, f in _conditions():
        s = summarize([x for x in rows if f(x)])
        if s:
            table.append({"key": key, "label": label, **s})
    base = next((t for t in table if t["key"] == "all"), None)
    for t in table:
        t["vs_all"] = round(t["win_rate"] - base["win_rate"], 1) if base else None
        # 앞·뒤 절반 둘 다 전체보다 같은 쪽이면 '꾸준함' — 한 시기 장세가 만든 숫자를 거른다
        if base:
            up = t["first_half"] > base["first_half"] and t["second_half"] > base["second_half"]
            dn = t["first_half"] < base["first_half"] and t["second_half"] < base["second_half"]
            t["steady"] = "good" if up else "bad" if dn else ""
    out = {"built_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "period": [min(x["d"] for x in rows), max(x["d"] for x in rows)] if rows else None,
           "n_trades": len(rows), "min_n": MIN_N, "table": table,
           "basis": "시장 대비·비용 차감 · 같은 날 같은 종목 1건 · 섀도우 E 제외"}
    if save:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def load() -> dict:
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


if __name__ == "__main__":
    r = build()
    print(r["built_at"], r["period"], r["n_trades"])
    for t in sorted(r["table"], key=lambda t: -t["win_rate"]):
        print(f"{t['key']:14s} n={t['n']:4d} {t['win_rate']:5.1f}% ({t['first_half']:5.1f}/{t['second_half']:5.1f}) {t['steady']}")
