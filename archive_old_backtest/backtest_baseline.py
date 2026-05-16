"""
backtest_baseline.py
─────────────────────────────────────────────────────────────────────────────
순수 시그널 알파 검증 백테스트. LLM 호출 없음. 기존 코드 무수정.

시그널: data_kr.get_kr_prebreakout_signal 로직을 순수 함수로 분리
데이터: pykrx(종목리스트) + yfinance 5분봉
        ※ pykrx/KIS API 모두 과거 5분봉 히스토리 미지원 → 한계 참조

실행:  python backtest_baseline.py
출력:  콘솔 리포트 + backtest_results/ (histogram.png, trades.csv)
─────────────────────────────────────────────────────────────────────────────
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
TOP_N_STOCKS        = 300     # 시총 상위 N 종목
SIGNAL_SCORE_MIN    = 3       # 시그널 발동 최소 점수 (0~5)
COST_ROUNDTRIP      = 0.007   # 왕복 비용 (수수료 0.5% + 슬리피지 0.2% = 0.7%)
CACHE_DIR           = "backtest_cache"
OUT_DIR             = "backtest_results"
MAX_WORKERS         = 8       # 병렬 다운로드 스레드 수
FIRST_SIGNAL_PER_DAY = True   # True: 종목×일 기준 첫 시그널만 (중복 포지션 방지)
PREV_DAYS_FOR_VOL_RATIO = 5   # vol_ratio 계산에 쓸 직전 영업일 수

# ═══════════════════════════════════════════════════════════════════════════════
import sys, warnings, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

warnings.filterwarnings("ignore")
Path(CACHE_DIR).mkdir(exist_ok=True)
Path(OUT_DIR).mkdir(exist_ok=True)

# ── 한글 폰트 ─────────────────────────────────────────────────────────────────
def _setup_korean_font():
    available = {f.name for f in fm.fontManager.ttflist}
    for candidate in ["Malgun Gothic", "NanumGothic", "AppleGothic", "Noto Sans KR"]:
        if candidate in available:
            plt.rcParams["font.family"] = candidate
            return
    plt.rcParams["font.family"] = "DejaVu Sans"

_setup_korean_font()
plt.rcParams["axes.unicode_minus"] = False

_DATA_LIMITATIONS: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 종목 리스트 — pykrx 시총 기준
# ═══════════════════════════════════════════════════════════════════════════════
def get_top_n_tickers(n: int) -> list[dict]:
    """
    pykrx로 KOSPI+KOSDAQ 시총 상위 N 종목 반환.
    Returns: [{"code": "005930", "name": "삼성전자", "market": "KOSPI"}, ...]
    """
    from pykrx import stock as krx

    today = datetime.date.today()
    ref_date = ""
    for delta in range(10):
        d = today - datetime.timedelta(days=delta)
        if d.weekday() < 5:
            ref_date = d.strftime("%Y%m%d")
            break

    results = []
    for market in ["KOSPI", "KOSDAQ"]:
        try:
            df = krx.get_market_cap(ref_date, market=market)
            if df.empty:
                continue
            df = df.reset_index()
            ticker_col = df.columns[0]
            cap_col = "시가총액" if "시가총액" in df.columns else df.select_dtypes("number").columns[0]
            df = df.sort_values(cap_col, ascending=False)

            for _, row in df.iterrows():
                code = str(row[ticker_col]).zfill(6)
                if not code.isdigit() or len(code) != 6:
                    continue
                try:
                    name = krx.get_market_ticker_name(code)
                except Exception:
                    name = code
                results.append({
                    "code":   code,
                    "name":   name or code,
                    "market": market,
                    "cap":    float(row[cap_col]),
                })
        except Exception as e:
            print(f"  [WARN] pykrx {market} 시총 조회 실패: {e}")

    if not results:
        raise RuntimeError("pykrx 종목 리스트 취득 실패")

    results.sort(key=lambda x: x["cap"], reverse=True)
    return results[:n]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 5분봉 데이터 취득 (yfinance, parquet 캐싱)
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_5min_bars(code: str, market: str) -> pd.DataFrame:
    """
    yfinance 5분봉 취득 (최대 ~60일). parquet 캐싱.
    """
    import yfinance as yf

    cache_path = Path(CACHE_DIR) / f"{code}.parquet"

    if cache_path.exists():
        mtime = datetime.datetime.fromtimestamp(cache_path.stat().st_mtime).date()
        if mtime == datetime.date.today():
            try:
                df = pd.read_parquet(cache_path)
                if not df.empty:
                    return df
            except Exception:
                pass

    suffix_order = [".KS", ".KQ"] if market == "KOSPI" else [".KQ", ".KS"]
    for suffix in suffix_order:
        try:
            raw = yf.Ticker(f"{code}{suffix}").history(
                period="60d", interval="5m", auto_adjust=True
            )
            if raw.empty:
                continue
            df = raw.reset_index()
            dt_col = next((c for c in df.columns if str(c).lower() in ("datetime", "date")), None)
            if dt_col is None:
                continue
            df = df.rename(columns={dt_col: "datetime"})
            df.columns = [str(c).lower().strip() for c in df.columns]
            needed = ["datetime", "open", "high", "low", "close", "volume"]
            if not all(c in df.columns for c in needed):
                continue
            df["datetime"] = pd.to_datetime(df["datetime"])
            if df["datetime"].dt.tz is not None:
                df["datetime"] = df["datetime"].dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
            t = df["datetime"].dt.time
            df = df[(t >= datetime.time(9, 0)) & (t <= datetime.time(15, 30))].copy()
            df = df[needed].dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
            if not df.empty:
                df.to_parquet(cache_path, index=False)
                return df
        except Exception:
            continue

    return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 시그널 감지 — data_kr.get_kr_prebreakout_signal 순수 함수 버전
# ═══════════════════════════════════════════════════════════════════════════════
def detect_signal(
    day_df: pd.DataFrame,
    bar_idx: int,
    vol_ratio: float,
) -> tuple[bool, int, dict]:
    """
    data_kr.get_kr_prebreakout_signal 로직의 순수 함수 버전.
    룩어헤드 바이어스 없음: bar_idx 봉까지의 데이터만 사용.

    Parameters
    ----------
    day_df    : 당일 5분봉 (시간순 정렬, 0-based 인덱스)
    bar_idx   : 현재 봉 인덱스
    vol_ratio : 사전 계산된 전일 동시간대 대비 거래량 비율

    Returns
    -------
    (fired, score, details)
    """
    n = bar_idx + 1
    if n < 12:
        return False, 0, {}

    # 1. 거래량 가속도: 최근 6봉 vs 직전 6봉 (data_kr.py 동일)
    recent_vol = day_df["volume"].iloc[max(n - 6, 0):n].sum()
    prev_vol   = day_df["volume"].iloc[max(n - 12, 0):max(n - 6, 0)].sum()
    vol_accel  = recent_vol / prev_vol if prev_vol > 0 else 0.0

    # 2. 박스권 돌파: 직전 6봉 고점 대비 현재 종가 (data_kr.py 동일)
    box_high     = day_df["high"].iloc[max(n - 7, 0):n - 1].max() if n > 2 else 0
    cur_close    = day_df["close"].iloc[bar_idx]
    consol_break = bool(cur_close > box_high) if box_high > 0 else False

    # 3. 최근 3봉 연속 양봉 (data_kr.py 동일)
    if n >= 3:
        last3      = day_df.iloc[n - 3:n]
        candle_seq = bool(all(last3["close"].values > last3["open"].values))
    else:
        candle_seq = False

    # 4. 점수 계산 (data_kr.py 스코어링 그대로)
    score = 0
    if vol_accel >= 2.5:
        score += 2
    elif vol_accel >= 1.5:
        score += 1
    if vol_ratio >= 3.0:
        score += 1
    if consol_break:
        score += 1
    if candle_seq:
        score += 1

    details = {
        "vol_accel":    round(vol_accel, 3),
        "vol_ratio":    round(vol_ratio, 3),
        "consol_break": consol_break,
        "candle_seq":   candle_seq,
    }
    return score >= SIGNAL_SCORE_MIN, score, details


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 단일 종목 백테스트
# ═══════════════════════════════════════════════════════════════════════════════
def backtest_ticker(df: pd.DataFrame, code: str, name: str) -> list[dict]:
    """
    단일 종목 전체 기간 백테스트.

    룩어헤드 바이어스 방지:
      진입가  — 시그널 봉 다음 봉 시가
      +30min  — entry_bar + 5봉 종가
      +60min  — entry_bar + 11봉 종가
      당일    — 15:20 이하 마지막 봉 종가
    비용     — COST_ROUNDTRIP(0.7%) 왕복 차감
    """
    if df.empty or len(df) < 20:
        return []

    df = df.copy().sort_values("datetime").reset_index(drop=True)
    df["_date"] = df["datetime"].dt.date
    dates = sorted(df["_date"].unique())

    # vol_ratio 효율 계산용: 날짜별 bar_idx → 누적 거래량 배열 사전 구축
    cumvol_by_date: dict[datetime.date, np.ndarray] = {}
    for date, grp in df.groupby("_date"):
        cumvol_by_date[date] = grp.sort_values("datetime")["volume"].cumsum().values

    CUTOFF_EXIT = datetime.time(15, 20)
    trades = []

    for date_i, date in enumerate(dates):
        day_mask = df["_date"] == date
        day_df   = df[day_mask].sort_values("datetime").reset_index(drop=True)

        prev_dates = dates[max(0, date_i - PREV_DAYS_FOR_VOL_RATIO):date_i]
        signaled   = False

        for bar_idx in range(11, len(day_df) - 1):
            if FIRST_SIGNAL_PER_DAY and signaled:
                break

            # vol_ratio: 오늘 bar_idx까지 누적량 / 직전 N일 같은 bar_idx 누적량 평균
            today_cumvol = int(cumvol_by_date[date][bar_idx])
            prev_cumvols = [
                cumvol_by_date[pd][bar_idx]
                for pd in prev_dates
                if pd in cumvol_by_date and bar_idx < len(cumvol_by_date[pd])
            ]
            avg_prev  = float(np.mean(prev_cumvols)) if prev_cumvols else 0.0
            vol_ratio = today_cumvol / avg_prev if avg_prev > 0 else 0.0

            fired, score, details = detect_signal(day_df, bar_idx, vol_ratio)
            if not fired:
                continue

            signaled = True

            entry_idx   = bar_idx + 1
            entry_price = float(day_df["open"].iloc[entry_idx])
            entry_time  = day_df["datetime"].iloc[entry_idx]

            if entry_price <= 0:
                continue

            def _ep(offset: int):
                idx = entry_idx + offset
                return float(day_df["close"].iloc[idx]) if idx < len(day_df) else None

            ep30  = _ep(5)   # entry open + 30min = entry bar close + 5봉
            ep60  = _ep(11)  # entry open + 60min = entry bar close + 11봉

            day_exits = day_df[day_df["datetime"].dt.time <= CUTOFF_EXIT]
            ep_day = float(day_exits["close"].iloc[-1]) if not day_exits.empty else None
            et_day = day_exits["datetime"].iloc[-1]    if not day_exits.empty else None

            def _ret(ep):
                if ep is None or ep <= 0:
                    return None
                return (ep - entry_price) / entry_price - COST_ROUNDTRIP

            trades.append({
                "code":          code,
                "name":          name,
                "date":          str(date),
                "month":         entry_time.strftime("%Y-%m"),
                "entry_time":    entry_time.strftime("%H:%M"),
                "hour_bucket":   entry_time.hour,
                "entry_price":   entry_price,
                "score":         score,
                "vol_accel":     details["vol_accel"],
                "vol_ratio":     details["vol_ratio"],
                "consol_break":  details["consol_break"],
                "candle_seq":    details["candle_seq"],
                "ret_30":        _ret(ep30),
                "ret_60":        _ret(ep60),
                "ret_day":       _ret(ep_day),
                "exit_time_day": et_day.strftime("%H:%M") if et_day is not None else None,
            })

    return trades


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 통계
# ═══════════════════════════════════════════════════════════════════════════════
def _stats(series: pd.Series, label: str) -> dict:
    s = series.dropna()
    if len(s) == 0:
        return {"label": label, "n": 0}

    win_rate = (s > 0).mean()
    mean_r   = s.mean()
    med_r    = s.median()
    std_r    = s.std()
    sharpe   = (mean_r / std_r * np.sqrt(252)) if std_r > 0 else 0.0

    cumret      = (1 + s).cumprod()
    rolling_max = cumret.cummax()
    max_dd      = ((cumret - rolling_max) / rolling_max).min()

    losses, max_consec, cur = (s <= 0).astype(int), 0, 0
    for v in losses:
        cur = cur + 1 if v else 0
        max_consec = max(max_consec, cur)

    return {
        "label": label, "n": len(s),
        "mean": mean_r, "median": med_r, "std": std_r,
        "win_rate": win_rate, "sharpe": sharpe,
        "max_dd": max_dd, "max_consec_loss": max_consec,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 리포트
# ═══════════════════════════════════════════════════════════════════════════════
def print_report(df: pd.DataFrame, data_period: str) -> None:
    SEP = "─" * 70
    print(f"\n{'═'*70}")
    print("  백테스트 기준선 리포트")
    print(f"{'═'*70}")
    print(f"  데이터 기간     : {data_period}")
    print(f"  분석 종목 수    : {df['code'].nunique():,}개")
    print(f"  시그널 최소점수 : {SIGNAL_SCORE_MIN}  (최대 5)")
    print(f"  왕복 비용       : {COST_ROUNDTRIP*100:.1f}%")
    print(f"  종목당 일별 첫번째 시그널만 : {FIRST_SIGNAL_PER_DAY}")
    print(f"  총 시그널 수    : {len(df):,}건")
    print()

    # ── 청산별 요약 ────────────────────────────────────────────────────────────
    for col, label in [("ret_30", "+30분 청산"), ("ret_60", "+60분 청산"), ("ret_day", "당일 청산")]:
        s = _stats(df[col], label)
        if s["n"] == 0:
            print(f"[{label}] 데이터 없음\n")
            continue
        print(f"[{label}]  유효 거래 수: {s['n']:,}")
        print(f"  평균 수익률   : {s['mean']*100:+.3f}%")
        print(f"  중앙값        : {s['median']*100:+.3f}%")
        print(f"  표준편차      : {s['std']*100:.3f}%")
        print(f"  승률          : {s['win_rate']*100:.1f}%")
        print(f"  샤프 (연환산) : {s['sharpe']:.3f}")
        print(f"  최대 낙폭     : {s['max_dd']*100:.2f}%")
        print(f"  최대 연속손실 : {s['max_consec_loss']}건")
        print()

    # ── 월별 시그널 수 ──────────────────────────────────────────────────────────
    print(SEP)
    print("월별 시그널 수:")
    for m, cnt in df.groupby("month").size().items():
        print(f"  {m}: {cnt:,}건")
    print()

    # ── 종목별 상위 10 ──────────────────────────────────────────────────────────
    print(SEP)
    print("종목별 시그널 상위 10:")
    for (code, name), cnt in df.groupby(["code", "name"]).size().sort_values(ascending=False).head(10).items():
        print(f"  {code}  {name}: {cnt:,}건")
    print()

    # ── 시간대별 성과 ───────────────────────────────────────────────────────────
    print(SEP)
    print("시간대별 성과 (+30분 청산 기준):")
    for hour in range(9, 15):
        sub = df[df["hour_bucket"] == hour]["ret_30"].dropna()
        if sub.empty:
            continue
        print(f"  {hour:02d}시대: n={len(sub):,}  "
              f"평균={sub.mean()*100:+.3f}%  "
              f"승률={(sub>0).mean()*100:.1f}%")
    print()

    # ── 최대 수익/손실 사례 ─────────────────────────────────────────────────────
    for col, label in [("ret_30", "+30분"), ("ret_60", "+60분"), ("ret_day", "당일")]:
        valid = df[df[col].notna()].copy()
        if valid.empty:
            continue
        print(SEP)
        print(f"최대 수익 TOP5 [{label}]:")
        for _, r in valid.nlargest(5, col).iterrows():
            print(f"  {r['code']} {r['name']:<12s}  {r['date']} {r['entry_time']}  "
                  f"수익={r[col]*100:+.2f}%  점수={r['score']}")
        print(f"\n최대 손실 TOP5 [{label}]:")
        for _, r in valid.nsmallest(5, col).iterrows():
            print(f"  {r['code']} {r['name']:<12s}  {r['date']} {r['entry_time']}  "
                  f"수익={r[col]*100:+.2f}%  점수={r['score']}")
        print()

    # ── 데이터 한계 ─────────────────────────────────────────────────────────────
    print(SEP)
    print("【데이터 한계 / 주의사항】")
    for lim in _DATA_LIMITATIONS:
        print(f"  * {lim}")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# 7. 히스토그램
# ═══════════════════════════════════════════════════════════════════════════════
def plot_histograms(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("수익률 분포 (비용 0.7% 왕복 차감 후)", fontsize=13)

    for ax, (col, title, color) in zip(axes, [
        ("ret_30",  "+30분 청산", "steelblue"),
        ("ret_60",  "+60분 청산", "darkorange"),
        ("ret_day", "당일 청산",  "seagreen"),
    ]):
        series = df[col].dropna() * 100
        if series.empty:
            ax.set_title(f"{title}\n(데이터 없음)")
            continue
        ax.hist(series, bins=60, color=color, alpha=0.75, edgecolor="none")
        ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
        ax.axvline(series.mean(), color="red", linewidth=1.2,
                   label=f"평균 {series.mean():.2f}%")
        win_r = (series > 0).mean() * 100
        ax.set_title(f"{title}\nn={len(series):,}  승률={win_r:.1f}%")
        ax.set_xlabel("수익률 (%)")
        ax.set_ylabel("빈도")
        ax.legend(fontsize=8)

    plt.tight_layout()
    out = Path(OUT_DIR) / "histogram.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  히스토그램 저장: {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. main
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print(f"  백테스트 시작  TOP_N={TOP_N_STOCKS}  MIN_SCORE={SIGNAL_SCORE_MIN}")
    print("=" * 70)

    _DATA_LIMITATIONS.extend([
        "5분봉 소스: yfinance (period=60d). 최대 ~60일 데이터만 제공됨.",
        "pykrx/KIS API 모두 과거 분봉 히스토리 미지원 → yfinance 단독 사용.",
        "yfinance 5분봉은 봉 누락이 발생할 수 있음 (데이터 완결성 미보장).",
        "요청된 2년 대신 최대 ~60일 사용. 표본 수가 적어 통계적 한계가 있음.",
        f"시그널 점수 체계: vol_accel≥2.5→+2, ≥1.5→+1 / vol_ratio≥3→+1 / "
        f"박스권돌파→+1 / 3연속양봉→+1. MIN_SCORE={SIGNAL_SCORE_MIN} 이상 시 발동.",
        "진입가=시그널 봉 다음 봉 시가. +30min/+60min 청산 봉이 당일 범위 초과 시 해당 거래 제외.",
    ])

    # ── 1. 종목 리스트 ────────────────────────────────────────────────────────
    print(f"\n[1/4] pykrx 시총 상위 {TOP_N_STOCKS}개 조회...")
    try:
        tickers = get_top_n_tickers(TOP_N_STOCKS)
        print(f"  → {len(tickers)}개 확보")
    except Exception as e:
        print(f"  [ERROR] {e}")
        sys.exit(1)

    # ── 2. 5분봉 다운로드 ─────────────────────────────────────────────────────
    print(f"\n[2/4] yfinance 5분봉 다운로드 (최대 {MAX_WORKERS} 병렬)...")
    stock_data: dict[str, tuple[str, pd.DataFrame]] = {}
    failed = 0

    def _fetch(t: dict):
        df = fetch_5min_bars(t["code"], t["market"])
        return t["code"], t["name"], df

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_fetch, t): t for t in tickers}
        for i, fut in enumerate(as_completed(futs), 1):
            code, name, df = fut.result()
            if df.empty:
                failed += 1
            else:
                stock_data[code] = (name, df)
            if i % 50 == 0 or i == len(tickers):
                print(f"  {i}/{len(tickers)} 완료  (실패: {failed}개)", end="\r")
    print()

    print(f"  → 데이터 확보: {len(stock_data)}개  실패/누락: {failed}개")
    if failed > 0:
        _DATA_LIMITATIONS.append(
            f"{failed}개 종목 5분봉 취득 실패 (상장폐지·yfinance 미지원 등)."
        )

    all_dates = []
    for _, df in stock_data.values():
        all_dates.extend(df["datetime"].dt.date.unique().tolist())
    data_period = (f"{min(all_dates)} ~ {max(all_dates)}" if all_dates else "없음")
    print(f"  실제 데이터 기간: {data_period}")

    # ── 3. 백테스트 ───────────────────────────────────────────────────────────
    print(f"\n[3/4] 백테스트 실행...")
    all_trades: list[dict] = []

    for i, (code, (name, df)) in enumerate(stock_data.items(), 1):
        trades = backtest_ticker(df, code, name)
        all_trades.extend(trades)
        if i % 50 == 0 or i == len(stock_data):
            print(f"  {i}/{len(stock_data)} 종목  누적 시그널: {len(all_trades):,}건", end="\r")
    print()

    if not all_trades:
        print(f"\n[WARN] 시그널 0건. SIGNAL_SCORE_MIN={SIGNAL_SCORE_MIN}를 낮추거나 데이터를 확인하세요.")
        print("\n【데이터 한계】")
        for lim in _DATA_LIMITATIONS:
            print(f"  * {lim}")
        return

    df_trades = pd.DataFrame(all_trades)
    csv_path = Path(OUT_DIR) / "trades.csv"
    df_trades.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  trades 저장: {csv_path}")

    # ── 4. 리포트 + 히스토그램 ───────────────────────────────────────────────
    print(f"\n[4/4] 결과 분석...")
    print_report(df_trades, data_period)
    plot_histograms(df_trades)
    print(f"완료. 결과: {OUT_DIR}/")


if __name__ == "__main__":
    main()
