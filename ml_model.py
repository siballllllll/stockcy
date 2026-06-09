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

_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ml_win_model.joblib")
_FEATURES = ["rsi", "ma_aligned", "pos_52w", "vol_ratio", "confidence"]
MIN_SAMPLES = 80   # 이 미만이면 학습 보류 (신뢰 가능한 최소 표본)


def build_training_set():
    """라벨 달린 학습 데이터 수집 → (X: list[dict], y: list[int]). y=1(상승)/0(하락)."""
    from db import get_db_conn
    conn = get_db_conn(); cur = conn.cursor()
    try:
        cur.execute(
            """SELECT rsi, ma_aligned, pos_52w, vol_ratio, confidence, outcome_return
               FROM agent_decisions
               WHERE action='BUY' AND outcome_return IS NOT NULL AND rsi IS NOT NULL"""
        )
        rows = [dict(r) for r in cur.fetchall()]
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
                "confidence": float(d["confidence"] or 0),
            })
            y.append(1 if float(d["outcome_return"] or 0) > 0 else 0)
        except Exception:
            continue
    return X, y


def _to_matrix(X):
    import numpy as np
    return np.array([[row[c] for c in _FEATURES] for row in X], dtype=float)


def train_model(force: bool = False) -> dict:
    """학습 + 교차검증 후 모델 저장. 데이터 부족이면 보류(force=True면 데모로 강제)."""
    X, y = build_training_set()
    n = len(y)
    if n < MIN_SAMPLES and not force:
        return {"trained": False, "samples": n, "min_required": MIN_SAMPLES,
                "reason": f"학습 데이터 부족 ({n}/{MIN_SAMPLES}건). 추천·매매 결과가 쌓이면 자동 학습 가능."}
    if len(set(y)) < 2:
        return {"trained": False, "samples": n, "reason": "승/패 한쪽 결과만 있어 학습 불가."}

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
        joblib.dump({"model": clf, "features": _FEATURES,
                     "trained_at": datetime.now().isoformat(), "samples": n}, _MODEL_PATH)
    return {"trained": True, "saved": not force, "demo": force, "samples": n,
            "cv_auc": round(auc, 3) if auc is not None else None,
            "base_win_rate": round(float(ym.mean()) * 100, 1)}


def predict_win_proba(features: dict):
    """저장된 모델로 상승(승) 확률(%) 예측. 모델 미존재 시 None."""
    if not os.path.exists(_MODEL_PATH):
        return None
    try:
        import joblib, numpy as np
        bundle = joblib.load(_MODEL_PATH)
        clf, cols = bundle["model"], bundle["features"]
        x = np.array([[float(features.get(c, 0) or 0) for c in cols]], dtype=float)
        return round(float(clf.predict_proba(x)[0][1]) * 100, 1)
    except Exception:
        return None


def ml_status() -> dict:
    X, y = build_training_set()
    return {
        "samples": len(y),
        "min_required": MIN_SAMPLES,
        "model_exists": os.path.exists(_MODEL_PATH),
        "ready_to_train": len(y) >= MIN_SAMPLES,
        "features": _FEATURES,
    }
