# -*- coding: utf-8 -*-
"""테마별 시나리오 실측표 + 학습 축 전향 검정 (v3.194.0)

    venv/Scripts/python scratch/theme_report.py            # 표 + 검정
    venv/Scripts/python scratch/theme_report.py --min 50   # 표본 하한 조정

왜 스크립트로 남기나: 화면(성과 탭 → AI 상태 → 시나리오 적중률)에도 같은 표가 나오지만,
전향 검정은 화면에 없다. 그리고 사전(theme_taxonomy.py)을 고칠 때마다 숫자가 바뀌므로
한 줄로 다시 뽑을 수 있어야 한다.

⚠️ 관측창 겹침을 허용하면 상관이 부풀어 결론이 뒤집힌다 — 이 스크립트는 창이 닫힌
   과거만 쓴다. 자세한 배경은 VERIFY.md의 V18.
"""
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("DB_PATH") or os.path.join(BASE, "db.sqlite3")
MIN_N = 30
if "--min" in sys.argv:
    MIN_N = int(sys.argv[sys.argv.index("--min") + 1])


def main():
    from ai_engine import load_scenario_tracking_stats

    st = load_scenario_tracking_stats()
    o = st.get("overall") or {}
    print(f"전체: n={o.get('count')} · 승률 {o.get('win_rate_d7')}% · "
          f"시장 대비 {o.get('excess_d7_return'):+}%p (기준: {o.get('basis')})")

    rows = [t for t in (st.get("by_theme") or []) if (t.get("count") or 0) >= MIN_N]
    rows.sort(key=lambda x: -(x.get("excess_d7") or 0))
    print(f"\n── 테마별 실측 (표본 {MIN_N}건 이상 {len(rows)}개, d7 초과수익 순) ──")
    print(f"{'테마':36} {'n':>5} {'d7초과':>8} {'승률':>6} {'n20':>5} {'d20초과':>8} {'승률':>6}")
    for t in rows:
        e20 = f"{t['excess_d20']:+.2f}" if t.get("excess_d20") is not None else "-"
        w20 = f"{t['win_rate_d20']:.1f}" if t.get("win_rate_d20") is not None else "-"
        print(f"{(t['group'] + ' ' + t['label'])[:34]:36} {t['count']:5} "
              f"{t['excess_d7']:+8.2f} {t['win_rate_d7']:6.1f} {t['count_d20']:5} {e20:>8} {w20:>6}")

    # ── 전향 검정 ────────────────────────────────────────────────────────────
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    def prospective(key, col, bcol, gap_days, min_prior=10):
        rs = cur.execute(
            f"""SELECT {key} AS k, substr(captured_at, 1, 10) AS d,
                       {col} - COALESCE({bcol}, 0) AS ex
                FROM scenario_stocks
                WHERE {col} IS NOT NULL AND {key} IS NOT NULL
                ORDER BY captured_at"""
        ).fetchall()
        hist, byday = defaultdict(list), defaultdict(list)
        for x in rs:
            t = datetime.strptime(x["d"], "%Y-%m-%d")
            past = [e for (pt, e) in hist[x["k"]] if (t - pt).days >= gap_days]
            if len(past) >= min_prior:
                byday[x["d"]].append((sum(past) / len(past), x["ex"]))
            hist[x["k"]].append((t, x["ex"]))
        xs, ys = [], []
        for _d, items in byday.items():
            if len(items) < 4:
                continue
            ms = sum(i[0] for i in items) / len(items)
            mv = sum(i[1] for i in items) / len(items)
            for s, v in items:
                xs.append(s - ms)
                ys.append(v - mv)
        if len(xs) < 200:
            return None, len(xs)
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
        return (num / den if den else 0.0), len(xs)

    print("\n── 전향 검정: '과거 성적이 좋은 축'을 고르면 이기나 ──")
    print("   같은 날 포착분끼리만 비교(장세 제거) · 관측창이 닫힌 과거만 점수에 사용")
    for key, label in (("theme_id", "테마"), ("sector", "섹터"), ("ticker", "종목")):
        parts = []
        for col, bcol, gap, w in (("d7_return", "bench_d7_return", 10, "d7"),
                                  ("d20_return", "bench_d20_return", 28, "d20")):
            rho, n = prospective(key, col, bcol, gap)
            parts.append(f"{w} {('%+.3f' % rho) if rho is not None else '표본부족':>7} (쌍 {n})")
        print(f"     {label:4} " + " · ".join(parts))
    print("   양수면 추종(잘 된 테마를 따라감), 음수면 역방향(눌림)이 답이다.")

    # 겹침을 허용했을 때의 값 — 왜 이 필터가 필요한지 같은 화면에서 보여준다.
    rho_bad, n_bad = prospective("ticker", "d20_return", "bench_d20_return", 0)
    print(f"\n   ⚠️ 참고 — 겹침 허용 시 종목 d20 r = "
          f"{('%+.3f' % rho_bad) if rho_bad is not None else '표본부족'} (쌍 {n_bad}).")
    print("      어제 픽과 오늘 픽의 수익률 구간이 19일 겹쳐 같은 기간을 두 번 센 값이다.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
