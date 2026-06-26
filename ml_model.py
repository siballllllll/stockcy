"""자체 ML 예측 모델 (표 데이터, 로컬·무료, 외부 과금 없음).

역할: 우리가 쌓은 '매수 판단 시점 지표 → 사후 수익률(결과)' 데이터로 학습해
'이 조건이면 상승할 확률 N%'를 예측. Gemini(외부 LLM)와 달리 우리 데이터로 학습됨.

원칙:
- scikit-learn(GradientBoosting) — 노트북 CPU로 학습/예측, 호출당 과금 0.
- 학습 데이터가 MIN_SAMPLES 미만이면 '보류'를 반환(과적합 방지). 억지로 학습하지 않음.
- 주 소스: agent_decisions(rsi/ma_aligned/pos_52w/vol_ratio/confidence + outcome_return).
  데이터가 쌓이면 다른 엔진의 (피처→결과)도 union하도록 확장 예정.
"""
import os
from datetime import datetime

# 공통 피처(엔진 무관) — 에이전트·패턴·시나리오·AI추천을 모두 같은 피처로 통일
_FEATURES = ["rsi", "ma_aligned", "pos_52w", "vol_ratio"]
MIN_SAMPLES = 80   # 이 미만이면 학습 보류 (신뢰 가능한 최소 표본)
# 예측 기간(horizon): 단타 d3 / 스윙 d7 / 중장기 d20. 각각 별도 모델.
HORIZONS = {"d3": "d3_return", "d7": "d7_return", "d20": "d20_return"}


def _model_path(horizon: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), f"ml_win_model_{horizon}.joblib")


def build_training_set(horizon: str = "d7"):
    """기간별 라벨 학습 데이터 → (X: list[dict], y: list[int]). y=1(상승)/0(하락).
    소스: ml_training_samples(패턴·시나리오·AI추천)의 해당 dN_return + (d7 한정) agent_decisions."""
    col = HORIZONS.get(horizon, "d7_return")
    from db import get_db_conn
    conn = get_db_conn(); cur = conn.cursor()
    rows = []
    try:
        cur.execute(
            f"""SELECT rsi, ma_aligned, pos_52w, vol_ratio, {col} AS ret
                FROM ml_training_samples
                WHERE {col} IS NOT NULL AND rsi IS NOT NULL"""
        )
        rows += [dict(r) for r in cur.fetchall()]
        # 에이전트 결과(단일 horizon)는 스윙(d7)에만 합류
        if horizon == "d7":
            cur.execute(
                """SELECT rsi, ma_aligned, pos_52w, vol_ratio, outcome_return AS ret
                   FROM agent_decisions
                   WHERE action='BUY' AND outcome_return IS NOT NULL AND rsi IS NOT NULL"""
            )
            rows += [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    X, y = [], []
    for d in rows:
        try:
            X.append({
                "rsi":        float(d["rsi"] or 0),
                "ma_aligned": 1.0 if d["ma_aligned"] else 0.0,
                "pos_52w":    float(d["pos_52w"] or 0),
                "vol_ratio":  float(d["vol_ratio"] or 0),
            })
            y.append(1 if float(d["ret"] or 0) > 0 else 0)
        except Exception:
            continue
    return X, y


def track_ml_sample_outcomes(limit: int = 250, max_age_days: int = 60) -> dict:
    """통합 샘플(ml_training_samples)의 미완성 행에 대해, 과거 데이터로 판단시점 지표(피처) +
    d1/d3/d7 수익률 + 라벨을 한꺼번에 채운다. (추천 시점엔 종목만 기록 → 여기서 사후 보강)
    추가 다운로드는 이 일일 job에서만 — 사용자 요청 경로엔 부담 0.
    limit: 한 번에 처리할 최대 건수(대량 백필 시 분할 처리). 오래된(라벨 가능성 높은) 것부터."""
    from db import get_db_conn
    from datetime import datetime, timedelta
    import FinanceDataReader as fdr
    import yfinance as yf

    conn = get_db_conn(); cur = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    # '채울 수 있는데 아직 빈' 행만 스캔한다. d20만 비어있고 아직 +20거래일이 안 지난
    # 행을 매번 재처리하면 LIMIT 예산을 잡아먹어 신규 행이 굶는 버그가 있었음 →
    # d1/d3/d7이 비었거나, d20은 충분히(약 30일+) 지난 경우에만 대상에 포함.
    cur.execute(
        """SELECT id, ticker, decided_at FROM ml_training_samples
           WHERE decided_at >= ?
             AND ( d1_return IS NULL OR d3_return IS NULL OR d7_return IS NULL
                   OR (d20_return IS NULL AND decided_at <= date('now','-30 day')) )
           ORDER BY decided_at ASC LIMIT ?""",
        (cutoff, int(limit)))
    rows = [dict(r) for r in cur.fetchall()]
    today = datetime.now().date()
    pending = []

    def _feat_at(closes, vols, highs, lows, opens, bi):
        # bi = 판단일 인덱스. 그 시점까지의 데이터로 지표 계산.
        if bi < 20:
            return None
        c = [float(x) for x in closes[:bi + 1]]; v = [float(x) for x in vols[:bi + 1]]
        h = [float(x) for x in highs[:bi + 1]]; l = [float(x) for x in lows[:bi + 1]]
        deltas = [c[i] - c[i - 1] for i in range(1, len(c))]
        gains = [d if d > 0 else 0.0 for d in deltas]; losses = [-d if d < 0 else 0.0 for d in deltas]
        ag = sum(gains[-14:]) / 14; al = sum(losses[-14:]) / 14
        rsi = 100 - (100 / (1 + ag / al)) if al > 0 else 100.0
        v20 = sum(v[-20:]) / 20; vr = (v[-1] / v20) if v20 > 0 else 1.0
        n52 = min(len(c), 252); hi = max(h[-n52:]); lo = min(l[-n52:]); cur_p = c[-1]
        pos = (cur_p - lo) / (hi - lo) * 100 if hi > lo else 50.0
        ma5 = sum(c[-5:]) / 5; ma20 = sum(c[-20:]) / 20; ma60 = sum(c[-60:]) / 60 if len(c) >= 60 else ma20
        ma_al = 1 if (cur_p > ma5 > ma20 > ma60) else 0
        return {"rsi": round(rsi, 1), "vol_ratio": round(vr, 2), "pos_52w": round(pos, 1),
                "ma_aligned": ma_al, "entry": cur_p}

    for row in rows:
        try:
            decided = datetime.strptime(str(row["decided_at"])[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        if (today - decided).days < 1:
            continue
        raw = str(row["ticker"]).strip()
        is_us = any(ch.isalpha() for ch in raw)
        tk = raw.upper() if is_us else raw.zfill(6)
        start = (decided - timedelta(days=400)).strftime("%Y-%m-%d")
        end = (decided + timedelta(days=45)).strftime("%Y-%m-%d")   # d20(약 1개월)까지 포함
        try:
            if is_us:
                import pandas as pd
                df = yf.download(tk, start=start, end=end, progress=False, timeout=10, auto_adjust=True)
                if df is not None and isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)   # 단일 티커 MultiIndex 평탄화
            else:
                df = fdr.DataReader(tk, start, end)
            if df is None or df.empty:
                continue
            base_i = None
            for j, dt in enumerate(df.index):
                d = dt.date() if hasattr(dt, "date") else dt
                if d <= decided:
                    base_i = j
                else:
                    break
            if base_i is None or base_i < 20:
                continue
            f = _feat_at(df["Close"].values, df["Volume"].values, df["High"].values,
                         df["Low"].values, df["Open"].values, base_i)
            if not f:
                continue
            entry = f["entry"]
            def _p(off):
                k = base_i + off
                return float(df["Close"].iloc[k]) if len(df) > k else None
            def _r(p): return round((p - entry) / entry * 100, 2) if (p and entry) else None
            r1, r3, r7, r20 = _r(_p(1)), _r(_p(3)), _r(_p(7)), _r(_p(20))
            label = (1 if r7 > 0 else 0) if r7 is not None else None
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pending.append((f["rsi"], f["ma_aligned"], f["pos_52w"], f["vol_ratio"],
                            round(entry, 2), r1, r3, r7, r20, label, now, row["id"]))
        except Exception as e:
            print(f"[ml sample track] {tk} 실패: {e}")
            continue

    updated = 0
    if pending:
        try:
            cur.executemany(
                """UPDATE ml_training_samples
                   SET rsi=?, ma_aligned=?, pos_52w=?, vol_ratio=?, entry_price=?,
                       d1_return=?, d3_return=?, d7_return=?, d20_return=?, label=?, outcome_checked_at=?
                   WHERE id=?""", pending)
            conn.commit(); updated = len(pending)
        except Exception as e:
            print(f"[ml sample track] 저장 실패: {e}")
    conn.close()
    return {"updated_now": updated, "scanned": len(rows)}


def _to_matrix(X):
    import numpy as np
    return np.array([[row[c] for c in _FEATURES] for row in X], dtype=float)


def train_model(horizon: str = "d7", force: bool = False) -> dict:
    """기간별 학습 + 교차검증 후 모델 저장. 데이터 부족이면 보류(force=True면 데모로 강제)."""
    X, y = build_training_set(horizon)
    n = len(y)
    if n < MIN_SAMPLES and not force:
        return {"horizon": horizon, "trained": False, "samples": n, "min_required": MIN_SAMPLES,
                "reason": f"{horizon} 학습 데이터 부족 ({n}/{MIN_SAMPLES}건). 결과가 쌓이면 자동 학습 가능."}
    if len(set(y)) < 2:
        return {"horizon": horizon, "trained": False, "samples": n, "reason": "승/패 한쪽 결과만 있어 학습 불가."}

    import numpy as np
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score
    import joblib

    Xm, ym = _to_matrix(X), np.array(y)
    clf = GradientBoostingClassifier(random_state=42)
    auc = None
    try:
        cv = min(5, max(2, n // 2))
        auc = float(cross_val_score(clf, Xm, ym, cv=cv, scoring="roc_auc").mean())
    except Exception:
        pass
    clf.fit(Xm, ym)
    if not force:
        joblib.dump({"model": clf, "features": _FEATURES, "horizon": horizon,
                     "trained_at": datetime.now().isoformat(), "samples": n,
                     "cv_auc": round(auc, 3) if auc is not None else None}, _model_path(horizon))
    return {"horizon": horizon, "trained": True, "saved": not force, "demo": force, "samples": n,
            "cv_auc": round(auc, 3) if auc is not None else None,
            "base_win_rate": round(float(ym.mean()) * 100, 1)}


def train_all() -> dict:
    """세 기간 모두 학습 시도(가능한 것만)."""
    return {h: train_model(h) for h in HORIZONS}


def predict_win_proba(features: dict, horizon: str = "d7"):
    """저장된 기간별 모델로 상승 확률(%) 예측. 모델 미존재 시 None."""
    path = _model_path(horizon)
    if not os.path.exists(path):
        return None
    try:
        import joblib, numpy as np
        bundle = joblib.load(path)
        clf, cols = bundle["model"], bundle["features"]
        x = np.array([[float(features.get(c, 0) or 0) for c in cols]], dtype=float)
        return round(float(clf.predict_proba(x)[0][1]) * 100, 1)
    except Exception:
        return None


def ml_status() -> dict:
    out = {"min_required": MIN_SAMPLES, "features": _FEATURES, "horizons": {}}
    for h in HORIZONS:
        n = len(build_training_set(h)[1])
        info = {
            "samples": n,
            "ready_to_train": n >= MIN_SAMPLES,
            "model_exists": os.path.exists(_model_path(h)),
            "trained_at": None,
            "trained_samples": None,
            "cv_auc": None,
        }
        if info["model_exists"]:
            try:
                import joblib
                b = joblib.load(_model_path(h))
                info["trained_at"] = b.get("trained_at")
                info["trained_samples"] = b.get("samples")
                info["cv_auc"] = b.get("cv_auc")
            except Exception:
                pass
        out["horizons"][h] = info
    return out
