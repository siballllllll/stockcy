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

    # ── V5. 토스 Open API 접속 ──────────────────────────────────────────────
    print(_hdr("V5", "토스 Open API 접속 — 실패 시 VPN 여부부터 확인"))
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BASE, ".env"))
        import toss_api
        ok = bool(toss_api.get_token())
        print(f"   토큰 발급: {'성공' if ok else '실패'}")
        if ok:
            print("   [DONE] 호가창·최근체결·장운영 표시 정상.")
        else:
            # 2026-09-04 사용자 확인: 원인은 VPN. 등록으로 풀 문제가 아니므로 조치를 권하지 말 것.
            print("   [정보] 403 access_denied(IP not allowed) — 확인된 원인은 VPN이다.")
            print("          집에서 VPN 없이 쓰면 정상. 개발자센터에 IP를 새로 등록하지 말 것")
            print("          (VPN IP는 매번 바뀌어 등록해도 소용없다). VPN 여부부터 확인.")
            print("          이 상태에서는 개장일에도 '오늘 휴장'으로 잘못 표시된다(UI 미해결 과제).")
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

    # ── V8. ML 학습에 스캔 후보 전체 편입 여부 ──────────────────────────────
    print(_hdr("V8", "ML 학습에 스캔 후보 전체(scan)를 편입할지"))
    sc = _one(cur, "SELECT COUNT(*), SUM(d7_return IS NOT NULL) FROM ml_training_samples "
                   "WHERE source = 'scan'")
    n_sc, lab_sc = (sc + (0, 0))[:2]
    base = _one(cur, "SELECT SUM(d7_return IS NOT NULL) FROM ml_training_samples "
                     "WHERE source = 'pattern'")
    print(f"   적재 {n_sc or 0}건 (결과 라벨 {lab_sc or 0}건)  ↔  현행 학습셋 pattern 라벨 {base[0] or 0}건")
    if (lab_sc or 0) < 200:
        print(f"   [WAIT] 라벨 {lab_sc or 0}건 — 200건 이상에서 판정(하루 30~40건이면 약 2~3주).")
        print("          그때까지 제외 상태 유지. 적재만 계속되고 학습 오염은 없다.")
    else:
        print("   [DUE] 표본 충족 — pattern 단독 AUC vs (pattern+scan) 합본 AUC를 비교할 것.")
    print("   통과 기준: 합본 AUC가 pattern 단독 대비 +0.03 이상 개선 → 편입.")
    print("   ⚠️ 유니버스가 거래대금·등락률 상위라 '시장 전체'가 아님. 볼륨이 커서 편입 시")
    print("      pattern이 묻힐 수 있고, 매일 재스캔되는 종목은 자기상관이 있다.")

    # ── V9. 시나리오 확률 라운딩 ────────────────────────────────────────────
    print(_hdr("V9", "시나리오 확률 라운딩 — 프롬프트 수정(v3.143.0) 효과"))
    import re as _re
    fixed_from = "2026-09-05"   # 프롬프트 수정 다음날부터 집계
    vals = []
    try:
        for _d, js in cur.execute("SELECT scenario_date, scenario_json FROM agent_scenarios "
                                  "WHERE scenario_date >= ?", (fixed_from,)):
            vals += [int(x) for x in _re.findall(r'"probability_pct"\s*:\s*(\d+)', js or "")]
    except Exception as e:
        print(f"   조회 실패: {str(e)[:60]}")
    if len(vals) < 20:
        print(f"   수정 이후 표본 {len(vals)}개 — 20개 이상에서 판정.")
        print("   [WAIT] 시나리오가 더 생성되기를 기다리는 중.")
    else:
        m5 = sum(1 for v in vals if v % 5 == 0)
        rate = 100.0 * m5 / len(vals)
        print(f"   수정 이후 {len(vals)}개 중 5의 배수 {m5}개 ({rate:.1f}%)  [수정 전 09-04: 100%]")
        if rate <= 30:
            print("   [DONE] 무작위 기대치 수준으로 회복 — 프롬프트가 원인이었던 것으로 판단.")
        else:
            print("   [DUE] 여전히 높다 — 프롬프트 문제가 아니다. 모델·파라미터 쪽을 의심할 것")
            print("         (thinking_budget, temperature, gemini-2.5-flash 모델 드리프트).")
    print("   통과 기준: 5의 배수 비율 30% 이하 (무작위 기대치는 20% 근처).")

    # ── V10. 촉매 모멘텀(섀도우 G·H) ────────────────────────────────────────
    print(_hdr("V10", "촉매 모멘텀(섀도우 G·H) — 사용자 실제 패턴의 전향 검증"))
    gh = list(cur.execute(
        """SELECT owner, COUNT(*) n, ROUND(AVG(profit_pct), 2) avg_pct,
                  ROUND(100.0 * SUM(CASE WHEN profit_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) win
           FROM trade_history WHERE owner IN ('SHADOW_G','SHADOW_H')
           GROUP BY owner"""))
    e = _one(cur, """SELECT COUNT(*), ROUND(100.0 * SUM(CASE WHEN profit_pct > 0 THEN 1 ELSE 0 END)
                            / COUNT(*), 1)
                     FROM trade_history WHERE owner = 'SHADOW_E'""")
    # 보유(미실현)도 같이 보여준다 — 실현 0건이어도 진입이 나오고 있는지가 먼저 관측 대상이다.
    openpos = list(cur.execute(
        """SELECT owner,
                  SUM(CASE WHEN ticker GLOB '[0-9]*' THEN 1 ELSE 0 END) kr,
                  SUM(CASE WHEN ticker GLOB '[0-9]*' THEN 0 ELSE 1 END) us
           FROM portfolio WHERE owner IN ('SHADOW_G','SHADOW_H') GROUP BY owner"""))
    for r in openpos:
        print(f"     {r['owner']} 보유 중: 국내 {r['kr']}종목 / 미국 {r['us']}종목")
    if not gh:
        if openpos:
            print("   진입은 나오고 있다(위 보유). 실현은 청산일이 지나야 잡힌다"
                  " — G는 4일, H는 10일.")
            print("   [WAIT] 실현 0건 — 표본이 쌓이는 중.")
        else:
            print("   아직 매수도 실현도 0건 — 진입 조건이 엄격하다(촉매 강도 '강'만 통과).")
            print("   [WAIT] 며칠째 매수가 0이면 조건이 과한지 점검할 것(모멘텀 대역 또는 강도 기준).")
    else:
        for r in gh:
            print(f"     {r['owner']:<10} {r['n']:>3}건  평균 {r['avg_pct']:+6.2f}%  승률 {r['win']:>5.1f}%"
                  f"  (청산 {'3거래일' if r['owner'] == 'SHADOW_G' else '7거래일'})")
        print(f"     대조군 E   {e[0]:>3}건  승률 {e[1]}%")
        tot = sum(r["n"] for r in gh)
        if tot < 30:
            print(f"   [WAIT] 합계 {tot}건 — 30건에서 판정.")
        else:
            print("   [DUE] 표본 충족 — G vs E(전략 유효성), G vs H(청산 속도), H vs A·C(진입 우열)")
            print("         세 갈래로 분해해 판정할 것.")
    # 시장별 분해 — 이 가설의 출처가 국내 데이터라 합쳐서 판정하면 안 된다.
    mk = list(cur.execute(
        """SELECT CASE WHEN ticker GLOB '[0-9]*' THEN '국내' ELSE '미국' END m,
                  COUNT(*) n,
                  ROUND(100.0 * SUM(CASE WHEN profit_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) w
           FROM trade_history WHERE owner IN ('SHADOW_G','SHADOW_H') GROUP BY m"""))
    if mk:
        print("   시장별: " + " / ".join(f"{r['m']} {r['n']}건 승률 {r['w']}%" for r in mk))
    print("   통과 기준: 실현 30건+ 에서 랜덤 대조군(E) 대비 승률 유의(p<0.05).")
    print("   ⚠️ 시장을 갈라서 판정할 것. 이 가설의 출처는 국내 데이터다 —")
    print("      섀도우 C도 국내 70.8%(p=0.0024) / 미국 47.1%(p=0.774)로 갈렸고, 리딩방 25건은 전부 국내.")
    print("      미국 표본만 쌓이면 V10은 다른 질문에 답하게 된다(국내 30건이 본 판정).")
    print("   ⚠️ G/H는 진입이 동일하고 청산만 다른 쌍이다 — H를 지우면 청산 효과를 못 잰다.")

    c.close()
    print(f"\n{'─' * 74}")
    print("자세한 배경과 판정 기준은 VERIFY.md 참조.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
