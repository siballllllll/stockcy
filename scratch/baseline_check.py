# -*- coding: utf-8 -*-
"""기준선 측정 — 시나리오 명단이 '같은 조건의 아무 종목'보다 나은가.

    venv/Scripts/python scratch/baseline_check.py

VERIFY.md의 「기준선 실측」 항목이 이 스크립트를 참조한다. 시세 캐시
(data_csv/baseline_bars.pkl)가 있으면 1분 안에 끝난다 — 없으면 종목 1,000개를 받느라
10분쯤 걸리고 그 구간에서 KRX 소스 문제로 실패할 수 있다(아래 ⚠️).

시가총액·날짜를 맞춘 대조군과 시나리오 픽을 비교한다.

[1차와 다른 점] 1차는 시나리오 픽(대형주 위주)을 전 종목 무작위와 비교했다. 그래서 차이가
'시나리오가 나쁘다'인지 '그 기간 대형주가 나빴다'인지 구분되지 않았다. 이번엔 **같은 시총
분위·같은 날짜**의 종목과 맞댄다. 월별로도 쪼개 국면별 일관성을 본다.

⚠️ 시가총액을 상장 목록에서 못 가져온다. KRX 리스팅의 Marcap·Close·Amount가 전부 무효값
   (`'-'`)으로 오고 **Stocks(발행주식수)만 유효**하다(실측 2026-09-30). 그래서 시총을
   `발행주식수 × 그 시점 주가`로 직접 계산한다 — 주가는 종목별 시세 조회로 확보한다.
⚠️ 분위 경계는 **대조군 표본의 시총 분포**로 정한다(시장 전체 시총을 못 구하므로).
"""
import json
import os
import pickle
import random
import sqlite3
import statistics as st
import sys
import warnings
from collections import defaultdict
from datetime import datetime as dt

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 저장소 루트
HERE = os.path.join(BASE, "data_csv")
# 시세 캐시 — 있으면 재실행이 1분 안에 끝나고 조회 실패 구간을 아예 지나가지 않는다.
CACHE = os.path.join(HERE, "baseline_bars.pkl")
sys.path.insert(0, BASE)
import pandas as pd  # noqa: E402
import FinanceDataReader as fdr  # noqa: E402

FEE = 0.21
START, END = "2026-05-20", "2026-10-05"
HORIZONS = [("d7", 7), ("d20", 20)]
N_SAMPLE = 1000
random.seed(20260930)

# ── 1) 발행주식수 (유효한 유일한 컬럼) ──────────────────────────────────────
lst = fdr.StockListing("KRX")
lst["_stocks"] = pd.to_numeric(lst["Stocks"], errors="coerce")
lst = lst.dropna(subset=["Code", "_stocks"])
# ⚠️ itertuples()는 밑줄로 시작하는 컬럼명을 위치 이름(_1·_2)으로 바꿔버린다 — zip을 쓴다.
shares = {str(c).zfill(6): float(v) for c, v in zip(lst["Code"], lst["_stocks"])}
print(f"상장 {len(shares)}종목 (발행주식수 확보)")

# ── 2) 대조군 표본 ──────────────────────────────────────────────────────────
all_codes = list(shares)
bars = pickle.load(open(CACHE, "rb")) if os.path.exists(CACHE) else {}
sample = list(bars)[:]                              # 이미 받아둔 것 재사용
pool = [c for c in all_codes if c not in bars]
sample += random.sample(pool, min(N_SAMPLE - len(sample), len(pool)))
print(f"대조군 표본 {len(sample)}종목 (캐시 {len(bars)} 재사용)")

need = [c for c in sample if c not in bars]
for i, code in enumerate(need, 1):
    try:
        df = fdr.DataReader(code, START, END)
        if df is not None and not df.empty:
            bars[code] = [(d.date(), float(v)) for d, v in df["Close"].dropna().items()]
    except Exception:
        pass
    if i % 100 == 0:
        print(f"  조회 {i}/{len(need)}", flush=True)
        pickle.dump(bars, open(CACHE, "wb"))
pickle.dump(bars, open(CACHE, "wb"))
ks = fdr.DataReader("KS11", START, END)
ks_ser = [(d.date(), float(v)) for d, v in ks["Close"].dropna().items()]
print(f"시세 확보 {len(bars)}종목\n")

# ── 3) 시총 = 발행주식수 × 기간 첫 종가, 분위 경계는 대조군 분포로 ──────────
ctrl_cap = {c: shares[c] * bars[c][0][1] for c in bars if c in shares and bars[c]}
caps_sorted = sorted(ctrl_cap.values())
cuts = [caps_sorted[int(len(caps_sorted) * k / 10)] for k in range(1, 10)]


def decile(cap):
    """0 = 소형 … 9 = 대형 (경계는 대조군 표본 분포)."""
    for i, c in enumerate(cuts):
        if cap < c:
            return i
    return 9


ctrl_dec = {c: decile(v) for c, v in ctrl_cap.items()}
from collections import Counter  # noqa: E402
print("대조군 분위 분포:", dict(sorted(Counter(ctrl_dec.values()).items())))


def ret_at(ser, cap_date, off):
    bi = None
    for j, (d, _) in enumerate(ser):
        if d <= cap_date:
            bi = j
        else:
            break
    if bi is None or bi + off >= len(ser):
        return None
    b0 = ser[bi][1]
    return None if b0 <= 0 else (ser[bi + off][1] - b0) / b0 * 100


# ── 4) 비교 ─────────────────────────────────────────────────────────────────
conn = sqlite3.connect(os.path.join(BASE, "db.sqlite3"))
conn.row_factory = sqlite3.Row
cur = conn.cursor()
result = {}
for key, off in HORIZONS:
    col, bcol = f"{key}_return", f"bench_{key}_return"
    cur.execute(f"""SELECT ticker, role, captured_price, substr(captured_at,1,10) d,
                           {col} - COALESCE({bcol},0) AS ex
                    FROM scenario_stocks
                    WHERE {col} IS NOT NULL AND COALESCE(market,'')='kr'
                      AND captured_price IS NOT NULL""")
    picks = [dict(r) for r in cur.fetchall()]
    dates = sorted({p["d"] for p in picks})

    ctrl = defaultdict(list)
    for code, ser in bars.items():
        dec = ctrl_dec.get(code)
        if dec is None:
            continue
        for ds in dates:
            cd = dt.strptime(ds, "%Y-%m-%d").date()
            b = ret_at(ks_ser, cd, off)
            r = ret_at(ser, cd, off)
            if b is None or r is None:
                continue
            ctrl[(ds, dec)].append(r - b)

    p_win = p_tot = 0
    c_win = 0.0
    p_ex, c_ex = [], []
    monthly = defaultdict(lambda: [0, 0, 0.0, 0.0, 0.0])
    dec_stat = defaultdict(lambda: [0, 0, 0.0, 0.0])
    unmatched = 0
    for p in picks:
        tk = str(p["ticker"]).zfill(6)
        sh = shares.get(tk)
        if not sh or not p["captured_price"]:
            unmatched += 1
            continue
        dec = decile(sh * float(p["captured_price"]))
        lst_c = ctrl.get((p["d"], dec))
        if not lst_c:
            unmatched += 1
            continue
        harm = (p["role"] == "피해")
        pex = p["ex"]
        pwin = (pex < -FEE) if harm else (pex > FEE)
        cwr = st.mean([1.0 if ((x < -FEE) if harm else (x > FEE)) else 0.0 for x in lst_c])
        cexm = st.mean(lst_c)
        p_tot += 1
        p_win += 1 if pwin else 0
        c_win += cwr
        p_ex.append(pex)
        c_ex.append(cexm)
        m = p["d"][:7]
        a = monthly[m]
        a[0] += 1 if pwin else 0
        a[1] += 1
        a[2] += pex
        a[3] += cwr
        a[4] += cexm
        b_ = dec_stat[dec]
        b_[0] += 1 if pwin else 0
        b_[1] += 1
        b_[2] += pex
        b_[3] += cexm

    if not p_tot:
        print(f"════ {key} ════ 매칭 0건 (실패 {unmatched}) — 중단")
        continue
    pw, cw = p_win / p_tot * 100, c_win / p_tot * 100
    print(f"════ {key} ════  매칭된 픽 {p_tot:,}건 (실패 {unmatched})")
    print(f"  시나리오     승률 {pw:5.1f}%   초과 {st.mean(p_ex):+6.2f}%p")
    print(f"  시총·날짜 매칭 대조군 승률 {cw:5.1f}%   초과 {st.mean(c_ex):+6.2f}%p")
    print(f"  차이         {pw - cw:+5.1f}%p        {st.mean(p_ex) - st.mean(c_ex):+6.2f}%p")
    print("  ── 월별 ──")
    for m in sorted(monthly):
        a = monthly[m]
        if a[1] < 30:
            continue
        print(f"    {m}  {a[1]:5}건  시나리오 {a[0]/a[1]*100:5.1f}% / 대조군 {a[3]/a[1]*100:5.1f}%"
              f"  → {a[0]/a[1]*100 - a[3]/a[1]*100:+6.1f}%p"
              f"   (초과 {a[2]/a[1]:+5.2f} vs {a[4]/a[1]:+5.2f}%p)")
    print("  ── 시총 분위별 (9=대형) ──")
    for d in sorted(dec_stat):
        a = dec_stat[d]
        if a[1] < 30:
            continue
        print(f"    분위 {d}  {a[1]:5}건  시나리오 {a[2]/a[1]:+6.2f}%p / 대조군 {a[3]/a[1]:+6.2f}%p"
              f"  → {a[2]/a[1] - a[3]/a[1]:+6.2f}%p")
    result[key] = {"n": p_tot, "pick_win": round(pw, 1), "ctrl_win": round(cw, 1),
                   "pick_excess": round(st.mean(p_ex), 2), "ctrl_excess": round(st.mean(c_ex), 2)}
    print()
conn.close()
json.dump(result, open(os.path.join(HERE, "baseline_result.json"), "w"), ensure_ascii=False, indent=1)
print("차이가 음수면 같은 크기·같은 날 종목보다 시나리오 픽이 나빴다는 뜻이다.")
