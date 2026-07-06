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
# 기본 3개 + 확장 5개(모멘텀·MACD·볼린저%b·ATR) + 시장 구분(is_us).
# _extra_feats와 EXTRA_FEATURES 동기화 유지.
# ma_aligned는 v3.110.0에서 제거 — 전 기간 중요도 0.0(죽은 피처), 제거 시 d3 AUC 0.625→0.64.
# 호출부 피처 dict에 ma_aligned가 남아 있어도 무해(행렬은 _FEATURES 기준으로만 구성).
_BASE_FEATURES = ["rsi", "pos_52w", "vol_ratio"]
EXTRA_FEATURES = ["mom_5", "mom_20", "macd_hist", "bb_pctb", "atr_pct"]
_FEATURES = _BASE_FEATURES + EXTRA_FEATURES + ["is_us"]
_FEATURE_DEFAULTS = {"bb_pctb": 0.5}   # 미제공 시 중립값이 0이 아닌 피처
MIN_SAMPLES = 80   # 이 미만이면 학습 보류 (신뢰 가능한 최소 표본)
RECENCY_HALF_LIFE_DAYS = 60   # 최근성 가중치 반감기 — 5월 같은 옛 레짐의 영향 자연 감쇠
# 예측 기간(horizon): 단타 d3 / 스윙 d7 / 중장기 d20. 각각 별도 모델.
HORIZONS = {"d3": "d3_return", "d7": "d7_return", "d20": "d20_return"}


def _extra_feats(c: list, h: list, l: list) -> dict:
    """판단시점까지의 종가/고가/저가(c,h,l)로 확장 피처 계산.
    mom_5/mom_20=5·20거래일 모멘텀(%), macd_hist=MACD 히스토그램(가격대비%),
    bb_pctb=볼린저 %b(0~1), atr_pct=ATR(14) 가격대비%. 데이터 부족 시 중립값."""
    import statistics
    n = len(c)
    out = {"mom_5": 0.0, "mom_20": 0.0, "macd_hist": 0.0, "bb_pctb": 0.5, "atr_pct": 0.0}
    last = c[-1] if n else 0
    if n >= 6 and c[-6]:
        out["mom_5"] = round((last / c[-6] - 1) * 100, 2)
    if n >= 21 and c[-21]:
        out["mom_20"] = round((last / c[-21] - 1) * 100, 2)
    # MACD(12,26,9) 히스토그램 — 가격 대비 정규화
    if n >= 26:
        k12, k26 = 2 / 13, 2 / 27
        e12 = e26 = c[0]; macd_series = []
        for x in c:
            e12 = x * k12 + e12 * (1 - k12)
            e26 = x * k26 + e26 * (1 - k26)
            macd_series.append(e12 - e26)
        ks = 2 / 10; sig = macd_series[0]
        for m in macd_series[1:]:
            sig = m * ks + sig * (1 - ks)
        if last:
            out["macd_hist"] = round((macd_series[-1] - sig) / last * 100, 3)
    # 볼린저 %b (20일, 2σ)
    if n >= 20:
        w = c[-20:]; ma = sum(w) / 20; sd = statistics.pstdev(w)
        up, lo = ma + 2 * sd, ma - 2 * sd
        if up > lo:
            out["bb_pctb"] = round((last - lo) / (up - lo), 3)
    # ATR(14) 가격 대비 %
    if n >= 15:
        trs = []
        for i in range(n - 14, n):
            trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
        if last:
            out["atr_pct"] = round((sum(trs) / len(trs)) / last * 100, 3)
    return out


def _model_path(horizon: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), f"ml_win_model_{horizon}.joblib")


def build_training_set(horizon: str = "d7"):
    """기간별 라벨 학습 데이터 → (X: list[dict], y: list[int], dates: list[str]).
    y=1(상승)/0(하락). decided_at 오름차순 정렬 — 시계열 CV·최근성 가중치의 전제.
    소스: ml_training_samples(패턴·시나리오·AI추천)의 해당 dN_return."""
    col = HORIZONS.get(horizon, "d7_return")
    from db import get_db_conn
    conn = get_db_conn(); cur = conn.cursor()
    rows = []
    try:
        # 확장 피처(mom_5 등)는 ml_training_samples에만 존재 → 그 컬럼이 채워진 행만 사용.
        # agent_decisions는 확장 피처가 없어 통합 피처셋 학습에서 제외(28건 손실 < 9피처 이득).
        cur.execute(
            f"""SELECT ticker, decided_at, rsi, ma_aligned, pos_52w, vol_ratio,
                       mom_5, mom_20, macd_hist, bb_pctb, atr_pct, {col} AS ret
                FROM ml_training_samples
                WHERE {col} IS NOT NULL AND rsi IS NOT NULL AND mom_5 IS NOT NULL
                ORDER BY decided_at ASC"""
        )
        rows += [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    X, y, dates = [], [], []
    for d in rows:
        try:
            tk = str(d.get("ticker") or "")
            X.append({
                "rsi":        float(d["rsi"] or 0),
                "ma_aligned": 1.0 if d["ma_aligned"] else 0.0,
                "pos_52w":    float(d["pos_52w"] or 0),
                "vol_ratio":  float(d["vol_ratio"] or 0),
                "mom_5":      float(d["mom_5"] or 0),
                "mom_20":     float(d["mom_20"] or 0),
                "macd_hist":  float(d["macd_hist"] or 0),
                "bb_pctb":    float(d["bb_pctb"] if d["bb_pctb"] is not None else 0.5),
                "atr_pct":    float(d["atr_pct"] or 0),
                "is_us":      1.0 if any(ch.isalpha() for ch in tk) else 0.0,
            })
            y.append(1 if float(d["ret"] or 0) > 0 else 0)
            dates.append(str(d.get("decided_at") or "")[:10])
        except Exception:
            continue
    return X, y, dates


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
    # fill_attempts >= 5 인 행은 영구 실패(상폐·데이터없음 종목)로 보고 스캔 제외 →
    #   매번 헛조회로 LIMIT을 잡아먹는 starvation 재발 방지.
    cur.execute(
        """SELECT id, ticker, decided_at FROM ml_training_samples
           WHERE decided_at >= ?
             AND COALESCE(fill_attempts, 0) < 5
             AND ( d1_return IS NULL OR d3_return IS NULL OR d7_return IS NULL
                   OR mom_5 IS NULL
                   OR (d20_return IS NULL AND decided_at <= date('now','-30 day')) )
           ORDER BY decided_at ASC LIMIT ?""",
        (cutoff, int(limit)))
    rows = [dict(r) for r in cur.fetchall()]
    today = datetime.now().date()
    pending = []
    failed_ids = []   # 이번 실행에서 '해당 종목 데이터 조회 실패'한 행 id

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
        feat = {"rsi": round(rsi, 1), "vol_ratio": round(vr, 2), "pos_52w": round(pos, 1),
                "ma_aligned": ma_al, "entry": cur_p}
        feat.update(_extra_feats(c, h, l))
        return feat

    for row in rows:
        try:
            decided = datetime.strptime(str(row["decided_at"])[:10], "%Y-%m-%d").date()
        except Exception:
            failed_ids.append(row["id"])   # 날짜 자체가 깨진 행 — 영영 못 채움
            continue
        if (today - decided).days < 1:
            continue   # 아직 하루도 안 지남 — 실패가 아니라 대기
        raw = str(row["ticker"]).strip()
        is_us = any(ch.isalpha() for ch in raw)
        # BRK.B 등 점 표기는 yfinance에서 BRK-B — 점→하이픈 정규화(과거 영구실패 원인 중 하나)
        tk = raw.upper().replace(".", "-") if is_us else raw.zfill(6)
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
                failed_ids.append(row["id"])
                continue
            base_i = None
            for j, dt in enumerate(df.index):
                d = dt.date() if hasattr(dt, "date") else dt
                if d <= decided:
                    base_i = j
                else:
                    break
            if base_i is None or base_i < 20:
                failed_ids.append(row["id"])   # 판단일 이전 이력 부족(신규상장 등)
                continue
            f = _feat_at(df["Close"].values, df["Volume"].values, df["High"].values,
                         df["Low"].values, df["Open"].values, base_i)
            if not f:
                failed_ids.append(row["id"])
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
                            f["mom_5"], f["mom_20"], f["macd_hist"], f["bb_pctb"], f["atr_pct"],
                            round(entry, 2), r1, r3, r7, r20, label, now, row["id"]))
        except Exception as e:
            print(f"[ml sample track] {tk} 실패: {e}")
            failed_ids.append(row["id"])
            continue

    updated = 0
    if pending:
        try:
            cur.executemany(
                """UPDATE ml_training_samples
                   SET rsi=?, ma_aligned=?, pos_52w=?, vol_ratio=?,
                       mom_5=?, mom_20=?, macd_hist=?, bb_pctb=?, atr_pct=?, entry_price=?,
                       d1_return=?, d3_return=?, d7_return=?, d20_return=?, label=?, outcome_checked_at=?
                   WHERE id=?""", pending)
            conn.commit(); updated = len(pending)
        except Exception as e:
            print(f"[ml sample track] 저장 실패: {e}")

    # fill_attempts는 '네트워크가 살아있음이 증명된 실행'(성공 1건 이상)에서, 실제 실패한 행만 +1.
    # 예전엔 스캔 즉시 전원 +1이라 학교망 차단 같은 전체 실패 기간에 정상 종목이 5회를 채우고
    # 영구 제외되는 오판이 있었음(6/22 이후 표본 136건 라벨 중단의 원인).
    counted = False
    if failed_ids and updated > 0:
        try:
            cur.executemany(
                "UPDATE ml_training_samples SET fill_attempts = COALESCE(fill_attempts,0)+1 WHERE id=?",
                [(i,) for i in failed_ids])
            conn.commit(); counted = True
        except Exception as e:
            print(f"[ml sample track] fill_attempts 갱신 실패: {e}")
    conn.close()
    return {"updated_now": updated, "scanned": len(rows), "failed": len(failed_ids),
            "attempts_counted": counted}


def _to_matrix(X):
    import numpy as np
    return np.array([[row[c] for c in _FEATURES] for row in X], dtype=float)


def train_model(horizon: str = "d7", force: bool = False) -> dict:
    """기간별 학습 + 시계열 교차검증 후 모델 저장. 데이터 부족이면 보류(force=True면 데모로 강제).

    [v3.108 품질 업그레이드]
    - 시계열 CV(TimeSeriesSplit): 랜덤 K-fold는 '미래 데이터로 과거를 맞추는' 누출로
      AUC가 부풀려짐 → 항상 과거로 학습→미래로 검증하는 정직한 지표로 교체.
    - 확률 보정(CalibratedClassifierCV/sigmoid): GBM 원시 predict_proba는 과신 경향
      → 보정 후 '상승확률 62%'가 실제 62% 빈도에 근접하도록.
    - 최근성 가중치: 반감기 60일 지수감쇠 — 5월 급등주 레짐 같은 옛 데이터 영향 자연 감소."""
    X, y, dates = build_training_set(horizon)
    n = len(y)
    if n < MIN_SAMPLES and not force:
        return {"horizon": horizon, "trained": False, "samples": n, "min_required": MIN_SAMPLES,
                "reason": f"{horizon} 학습 데이터 부족 ({n}/{MIN_SAMPLES}건). 결과가 쌓이면 자동 학습 가능."}
    if len(set(y)) < 2:
        return {"horizon": horizon, "trained": False, "samples": n, "reason": "승/패 한쪽 결과만 있어 학습 불가."}

    import numpy as np
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score
    import joblib

    Xm, ym = _to_matrix(X), np.array(y)
    # 최근성 가중치 (build_training_set이 decided_at 오름차순 보장)
    today = datetime.now().date()
    ages = []
    for ds in dates:
        try:
            ages.append((today - datetime.strptime(ds, "%Y-%m-%d").date()).days)
        except Exception:
            ages.append(0)
    w = np.array([0.5 ** (max(0, a) / RECENCY_HALF_LIFE_DAYS) for a in ages])

    # 정직한 성능 측정: 시계열 분할 — 각 fold는 과거로만 학습해 미래를 예측
    auc = None
    try:
        aucs = []
        for tr_i, te_i in TimeSeriesSplit(n_splits=min(4, max(2, n // 60))).split(Xm):
            if len(set(ym[te_i])) < 2:
                continue   # 검증 구간에 승/패 한쪽만 있으면 AUC 정의 불가
            m = GradientBoostingClassifier(random_state=42)
            m.fit(Xm[tr_i], ym[tr_i], sample_weight=w[tr_i])
            aucs.append(roc_auc_score(ym[te_i], m.predict_proba(Xm[te_i])[:, 1]))
        if aucs:
            auc = float(np.mean(aucs))
    except Exception as e:
        print(f"[ml train] 시계열 CV 실패: {e}")

    # 최종 모델: 확률 보정 래핑 (표본 충분할 때). 실패 시 순정 GBM 폴백.
    base = GradientBoostingClassifier(random_state=42)
    clf = None; calibrated = False
    if n >= 150:
        try:
            from sklearn.calibration import CalibratedClassifierCV
            try:
                cal = CalibratedClassifierCV(estimator=base, method="sigmoid", cv=3)
            except TypeError:   # sklearn<1.2 파라미터명 호환
                cal = CalibratedClassifierCV(base_estimator=base, method="sigmoid", cv=3)
            cal.fit(Xm, ym, sample_weight=w)
            clf = cal; calibrated = True
        except Exception as e:
            print(f"[ml train] 확률 보정 실패, 순정 GBM 폴백: {e}")
    if clf is None:
        base.fit(Xm, ym, sample_weight=w)
        clf = base
    if not force:
        joblib.dump({"model": clf, "features": _FEATURES, "horizon": horizon,
                     "trained_at": datetime.now().isoformat(), "samples": n,
                     "cv_auc": round(auc, 3) if auc is not None else None,
                     "cv_method": "time_series", "calibrated": calibrated,
                     "recency_half_life": RECENCY_HALF_LIFE_DAYS}, _model_path(horizon))
    return {"horizon": horizon, "trained": True, "saved": not force, "demo": force, "samples": n,
            "cv_auc": round(auc, 3) if auc is not None else None,
            "cv_method": "time_series", "calibrated": calibrated,
            "base_win_rate": round(float(ym.mean()) * 100, 1)}


def train_all() -> dict:
    """세 기간 모두 학습 시도(가능한 것만)."""
    return {h: train_model(h) for h in HORIZONS}


_BUNDLE_CACHE: dict = {}   # {horizon: (mtime, bundle)} — 스크리너가 후보 60개×기간별 호출해도 로드 1회

def _load_bundle(horizon: str):
    path = _model_path(horizon)
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    hit = _BUNDLE_CACHE.get(horizon)
    if hit and hit[0] == mtime:
        return hit[1]
    import joblib
    bundle = joblib.load(path)
    _BUNDLE_CACHE[horizon] = (mtime, bundle)
    return bundle


def predict_win_proba(features: dict, horizon: str = "d7"):
    """저장된 기간별 모델로 상승 확률(%) 예측. 모델 미존재 시 None.
    미제공 피처는 중립값(_FEATURE_DEFAULTS, 그 외 0)으로 채움."""
    try:
        bundle = _load_bundle(horizon)
        if not bundle:
            return None
        import numpy as np
        clf, cols = bundle["model"], bundle["features"]
        x = np.array([[float(features.get(c, _FEATURE_DEFAULTS.get(c, 0)) if features.get(c) is not None
                             else _FEATURE_DEFAULTS.get(c, 0)) for c in cols]], dtype=float)
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
