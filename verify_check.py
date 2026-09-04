"""verify_check.py — 밀린 검증 항목 현황판.

VERIFY.md에 적어둔 "나중에 확인하기로 한 것들"을 실제 DB/설정에 대고 점검한다.
사람이 날짜를 기억할 필요가 없도록, 이 스크립트 하나가 "지금 뭘 볼 때인지"를 알려준다.

    venv/Scripts/python verify_check.py

각 항목은 (상태, 근거 수치, 다음 행동)을 출력한다. 상태 기호:
    [DUE]     기한이 됐고 판정 가능 — 지금 확인할 것
    [READY]   기한 전이지만 조건을 이미 충족 — 앞당겨 판정 가능
    [WAIT]    기한 전이고 표본도 부족 — 그대로 두면 됨
    [BLOCKED] 기한이 와도 판정 불가 — 선행 수정이 필요
    [DONE]    해결 확인됨 — VERIFY.md에서 지워도 됨
"""
import os
import sqlite3
import sys
from datetime import date, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("DB_PATH") or os.path.join(BASE, "db.sqlite3")
TODAY = date.today()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def _one(cur, sql, params=()):
    try:
        r = cur.execute(sql, params).fetchone()
        return tuple(r) if r else ()
    except Exception as e:
        return ("ERR", str(e)[:60])


def _days_to(due: str) -> int:
    return (datetime.strptime(due, "%Y-%m-%d").date() - TODAY).days


def _hdr(item_id, title, due=None):
    when = "" if not due else (
        f"  (기한 {due}, {'D-' + str(_days_to(due)) if _days_to(due) >= 0 else 'D+' + str(-_days_to(due))})")
    return f"\n{'─' * 74}\n{item_id}. {title}{when}"


def main():
    if not os.path.exists(DB):
        print(f"DB를 찾을 수 없습니다: {DB}")
        return 1
    c = _conn()
    cur = c.cursor()
    out = []

    print(f"검증 현황판 — {TODAY}   (원장: VERIFY.md)")

    # ── V1. AI 종목분석 신뢰도 (v3.138.0/1) ─────────────────────────────────
    print(_hdr("V1", "AI 종목분석 신뢰도 — 근거 팩·변동폭 앵커 도입 효과", "2026-09-25"))
    n_hist = _one(cur, "SELECT COUNT(*) FROM analysis_history")
    n_new = _one(cur, "SELECT COUNT(*) FROM analysis_history WHERE analysis_time >= '2026-09-04'")
    cols = [r[1] for r in cur.execute("PRAGMA table_info(analysis_history)")]
    has_outcome = "d7_return" in cols
    print(f"   analysis_history 총 {n_hist[0]}건 (v3.138 이후 {n_new[0]}건)")
    if not has_outcome:
        print("   [BLOCKED] 사후 수익률 컬럼이 없다 — db.init_local_db()가 안 돌았을 수 있음.")
    else:
        try:
            from ai_engine import analysis_hit_rate
            hr = analysis_hit_rate()
        except Exception as e:
            hr = {"n": 0, "error": str(e)[:60]}
        print(f"   결과 측정 완료 {hr.get('n', 0)}건 / 방향 판정 가능 {hr.get('judged', 0)}건")
        if hr.get("judged"):
            print(f"   방향 적중률 {hr['hit_rate_pct']}%  (적중 {hr['hit']} / 빗나감 {hr['miss']})")
            print(f"   예측폭 평균오차 {hr['mean_abs_error_pct']}%p · 변동폭 절단 발생 {hr['clamped_rate_pct']}%")
        if (hr.get("judged") or 0) < 20:
            print(f"   [WAIT] 방향 판정 표본 {hr.get('judged', 0)}건 — 20건 이상 쌓이면 판정.")
            print("          표본은 종목분석을 실행할수록 늘어난다(분석 1회 = 이력 1건).")
        elif (hr.get("hit_rate_pct") or 0) >= 55:
            print("   [DUE] 표본 충족, 기준 통과 — 개선이 실제로 먹혔다고 판단할 근거가 됨.")
        else:
            print("   [DUE] 표본 충족, 기준 미달 — 프롬프트/주입 데이터를 다시 손볼 것.")
    print("   통과 기준: 방향 판정 20건+ AND 단기 전망 방향 적중률 55%+")

    # ── V2. 자체 ML 복귀 게이트 ─────────────────────────────────────────────
    print(_hdr("V2", "자체 ML 판단 반영 복귀 여부 — 실전 AUC 재측정", "2026-09-24"))
    pairs = _one(cur, "SELECT COUNT(*) FROM ml_training_samples WHERE pred_d7 IS NOT NULL AND label IS NOT NULL")
    fresh = _one(cur, "SELECT COUNT(*) FROM ml_training_samples "
                      "WHERE pred_d7 IS NOT NULL AND label IS NOT NULL AND decided_at >= '2026-09-03'")
    print(f"   예측-실측 쌍 {pairs[0]}건 (09-03 재학습 이후 신규 {fresh[0]}건)")
    print("   09-03 측정치: 실전 AUC d7 0.524 / d3 0.447 → 복귀 기준 미달로 ML_DECISIONS=0 유지 중")
    if fresh[0] < 40:
        print(f"   [WAIT] 재학습 이후 신규 표본 {fresh[0]}건 — AUC 재측정에는 40건 이상 권장.")
    else:
        print("   [DUE] 신규 표본 충족 — 재학습 이후 구간만으로 AUC를 다시 계산할 것.")
    print("   통과 기준: 신규 구간 실전 AUC 0.60+ → 판단 반영 4곳 복귀.")
    print("   ⚠️ CV(교차검증) 점수로 판정 금지 — 0.705는 학습셋 점수이지 실전 성능이 아님.")

    # ── V3. 섀도우 리그 승자 이식 ───────────────────────────────────────────
    print(_hdr("V3", "섀도우 리그 — 이기는 매매형태를 메인에 이식할지"))
    rows = list(cur.execute(
        """SELECT owner, COUNT(*) n, ROUND(AVG(profit_pct), 2) avg_pct,
                  ROUND(100.0 * SUM(CASE WHEN profit_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) win
           FROM trade_history WHERE trade_source = '섀도우'
           GROUP BY owner ORDER BY avg_pct DESC"""))
    total = sum(r["n"] for r in rows)
    print(f"   섀도우 실현 {total}건")
    for r in rows:
        print(f"     {r['owner']:<10} {r['n']:>3}건  평균 {r['avg_pct']:+6.2f}%  승률 {r['win']:>5.1f}%")
    # 1차 판정(09-04)에서 C만 유의 → v3.141.0에 국내 OR 경로로 이식. 이제 국내 C 표본만 본다.
    kr_c = _one(cur, """SELECT COUNT(*), ROUND(100.0 * SUM(CASE WHEN profit_pct > 0 THEN 1 ELSE 0 END)
                               / COUNT(*), 1)
                        FROM trade_history
                        WHERE trade_source = '섀도우' AND owner = 'SHADOW_C'
                          AND ticker GLOB '[0-9]*'""")
    n_c, w_c = (kr_c + (0, 0))[:2]
    print(f"   → 이식된 C(국내): {n_c}건 승률 {w_c}%  [1차 판정 시 24건 70.8%, 대조군 28.6%, p=0.0024]")
    if (n_c or 0) < 50:
        print(f"   [WAIT] 재판정 기준선 n=50까지 {50 - (n_c or 0)}건 남음. 그대로 두면 됨.")
    elif (w_c or 0) >= 60:
        print("   [DUE] n=50 도달, 승률 60%+ 유지 — 하드 게이트 승격 검토.")
    elif (w_c or 0) < 45:
        print("   [DUE] n=50 도달, 승률 45% 미만 — OR 경로(AGENT_ISSUE_ZONE_GATE=0) 회수 검토.")
    else:
        print("   [DUE] n=50 도달, 승률 45~60% — 현행 유지하며 계속 관찰.")
    print("   이식 위치: ai_engine.issue_zone_signal() / api/agent.py 매수 게이트 OR 경로")
    print("   ⚠️ 조건식은 shadow_league._wants_buy의 SHADOW_C와 동일하게 유지할 것.")

    # ── V4. 수급 스냅샷 스케줄러 ────────────────────────────────────────────
    print(_hdr("V4", "수급 스냅샷 캐치업 수정(v3.107.1) 실적재 확인"))
    snap = _one(cur, "SELECT COUNT(*), MAX(snapshot_date) FROM frgn_inst_snapshots")
    print(f"   frgn_inst_snapshots {snap[0]}행, 최신 {snap[1]}")
    if snap[0] and snap[1] and (TODAY - datetime.strptime(snap[1], "%Y-%m-%d").date()).days <= 5:
        print("   [DONE] 정상 적재 중 — 세력 이상급증 감지(v3.107.0)의 전제 충족. 원장에서 지워도 됨.")
    else:
        print("   [DUE] 최신 적재가 5일 이상 밀렸다 — 스케줄러 재확인 필요.")

    # ── V5. 토스 Open API IP 허용목록 ───────────────────────────────────────
    print(_hdr("V5", "토스 Open API — 공인 IP 허용목록 등록 (사용자 액션)"))
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BASE, ".env"))
        import toss_api
        ok = bool(toss_api.get_token())
        print(f"   토큰 발급: {'성공' if ok else '실패'}")
        print("   [DONE] 호가창·최근체결·장운영 표시 정상화됨." if ok else
              "   [BLOCKED] 403 access_denied(IP not allowed) 지속 — 토스증권 개발자센터에서\n"
              "             현재 공인 IP를 등록해야 함. 등록 전까지 '오늘 휴장'은 거짓 표시.")
    except Exception as e:
        print(f"   [BLOCKED] 확인 실패: {str(e)[:80]}")

    # ── V6. AI 추천 적중률 파이프라인 ───────────────────────────────────────
    print(_hdr("V6", "AI 추천 적중률 파이프라인 — 수집 자체가 되는지"))
    rec = _one(cur, "SELECT COUNT(*), SUM(d7_return IS NOT NULL) FROM ai_recommendations")
    print(f"   ai_recommendations {rec[0]}행 (d7 채워진 것 {rec[1] or 0}건)")
    if rec[0] == 0:
        print("   [DONE] 0행이지만 문제 없음 — v3.140.0에서 적중률 추적을 analysis_history로 옮겼다.")
        print("          (데이터가 실제로 들어오는 쪽이 그쪽이다. V1이 그 결과를 판정한다.)")
        print("          이 테이블과 track_ai_recommendation_outcomes는 유휴 상태로 남겨둔 것뿐.")
    else:
        print("   [DUE] 데이터가 쌓이는 중 — 적중률 산출 가능.")
    print("   ⚠️ 남은 간극: 구형 log_ai_recommendation은 ML 학습샘플도 함께 적재했다.")
    print("      analysis_history 경로에는 그게 없어, 종목분석은 ML 학습에 기여하지 않는다(V2와 별개 사안).")

    # ── V7. ML 학습에 종목분석 소스 편입 여부 ───────────────────────────────
    print(_hdr("V7", "ML 학습에 종목분석 소스(stock_analysis)를 편입할지"))
    sa = _one(cur, "SELECT COUNT(*), SUM(d7_return IS NOT NULL) FROM ml_training_samples "
                   "WHERE source = 'stock_analysis'")
    n_sa, lab = (sa + (0, 0))[:2]
    print(f"   적재 {n_sa or 0}건 (결과 라벨 채워진 것 {lab or 0}건)")
    try:
        from ml_model import EXCLUDED_SOURCES
        print(f"   학습 제외 목록: {EXCLUDED_SOURCES}")
    except Exception:
        pass
    if (lab or 0) < 40:
        print(f"   [WAIT] 라벨 {lab or 0}건 — 40건 이상 쌓이면 이 소스 단독 AUC를 측정할 것.")
        print("          그때까지는 제외 상태 유지(학습 오염 없음). 적재는 계속된다.")
    else:
        print("   [DUE] 표본 충족 — stock_analysis만으로 d7 AUC를 계산할 것.")
    print("   통과 기준: 이 소스 단독 AUC 0.55+ → EXCLUDED_SOURCES에서 제거해 학습 편입.")
    print("   ⚠️ scenario 전례(예측력 0인 채 학습셋 67% 점유 → 실전 AUC 0.524) 반복 금지.")

    c.close()
    print(f"\n{'─' * 74}")
    print("자세한 배경과 판정 기준은 VERIFY.md 참조.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
