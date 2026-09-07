"""기능(source)별 Gemini 토큰 사용량·추정비용 집계 리포트.

data_csv/gemini_usage.jsonl 을 읽어 "어느 기능이 얼마나 썼는지"를 표로 보여준다.
(ai_engine._log_gemini_usage 가 매 Gemini 호출마다 1줄씩 기록)

사용법:
    python scratch/gemini_cost_report.py            # 전체 누적
    python scratch/gemini_cost_report.py 2026-06-04 # 특정 날짜만
    python scratch/gemini_cost_report.py today      # 오늘만
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

# Windows 콘솔(cp949)에서 em대시·한글 등 출력 시 UnicodeEncodeError 방지
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data_csv", "gemini_usage.jsonl")

# gemini-2.5-flash 단가 (USD per 1M tokens). 출력 단가는 thinking 토큰에도 적용.
# (ai_engine._calc_estimated_cost의 단가와 일치시킬 것 — 어긋나면 JSONL의 cost_usd와
#  이 리포트의 집계가 서로 다른 값을 말하게 된다.)
IN_RATE = 0.30
OUT_RATE = 2.50
USD_KRW = 1380  # 표시용 대략 환율

def main():
    if not os.path.exists(PATH):
        print(f"아직 사용 로그가 없습니다: {PATH}")
        print("→ 서버가 Gemini를 한 번 이상 호출하면 자동 생성됩니다. 하루 정도 돌린 뒤 다시 실행하세요.")
        return

    day = None
    if len(sys.argv) > 1:
        day = datetime.now().strftime("%Y-%m-%d") if sys.argv[1] == "today" else sys.argv[1]

    agg = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0, "think": 0, "search": 0})
    lines = 0
    with open(PATH, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if day and not str(r.get("ts", "")).startswith(day):
                continue
            lines += 1
            a = agg[r.get("source", "unknown")]
            a["calls"] += 1
            _in = int(r.get("in", 0))
            _out = int(r.get("out", 0))
            # think 필드가 없는 줄(래퍼 리팩터로 유실됐던 구간)은 total에서 역산한다.
            # 역산값은 검색 그라운딩의 도구 토큰까지 포함해 thinking을 과대계상하므로
            # (실측 3,360 vs 역산 6,457) 어디까지나 그 구간의 근사치다 — 필드가 있으면 그것이 우선.
            _think = r.get("think")
            if _think is None:
                _think = max(0, int(r.get("total", 0)) - _in - _out)
            a["in"] += _in
            a["out"] += _out
            a["think"] += int(_think)
            if r.get("search"): a["search"] += 1

    if lines == 0:
        print(f"해당 조건({day or '전체'})에 기록이 없습니다.")
        return

    rows = []
    for src, a in agg.items():
        out_total = a["out"] + a["think"]
        cost = a["in"] * IN_RATE / 1e6 + out_total * OUT_RATE / 1e6
        rows.append((cost, src, a, out_total))
    rows.sort(reverse=True)

    scope = day or "전체 누적"
    print(f"\n=== Gemini 기능별 사용량 ({scope}) ===")
    print(f"{'기능(source)':38} {'호출':>6} {'입력토큰':>12} {'출력+think':>12} {'추정원':>9} {'회당원':>8} {'검색':>5}")
    print("-" * 92)
    grand = 0.0
    gcalls = 0
    for cost, src, a, out_total in rows:
        grand += cost
        gcalls += a["calls"]
        krw = int(cost * USD_KRW)
        per = int(cost * USD_KRW / max(1, a["calls"]))
        print(f"{src[:38]:38} {a['calls']:>6} {a['in']:>12,} {out_total:>12,} {krw:>9,} {per:>8,} {a.get('search', 0):>5}")
    print("-" * 92)
    print(f"{'합계':38} {gcalls:>6} {'':>12} {'':>12} {int(grand*USD_KRW):>9,}")
    print(f"\n* 단가 가정: 입력 ${IN_RATE}/1M, 출력+thinking ${OUT_RATE}/1M (gemini-2.5-flash 기준)")
    print(f"* 그라운딩(검색) 호출은 무료 한도(1,500/일) 내라고 가정 — 초과 시 별도 과금.")

if __name__ == "__main__":
    main()
