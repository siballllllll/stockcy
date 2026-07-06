"""
Stockcy FastAPI 서버 엔트리포인트

실행 방법:
  uvicorn api.main:app --reload --port 8000

⚠️  반드시 프로젝트 루트에서 실행해야 합니다 (data.py, db.py 등을 임포트하기 위해).
"""
import sys
import os

# ── 0. stdout/stderr를 로그 파일로도 복제 (hidden 실행이라 콘솔이 안 보임 → 진단용) ──
class _Tee:
    def __init__(self, *streams):
        self._streams = [s for s in streams if s is not None]
    def write(self, data):
        for s in self._streams:
            try:
                s.write(data); s.flush()
            except Exception:
                pass
    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass

try:
    _log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend.log")
    _log_fp = open(_log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.stdout, _log_fp)
    sys.stderr = _Tee(sys.stderr, _log_fp)
except Exception:
    pass

# ── 1. .env 로드 (환경변수를 st.secrets 대신 사용) ──────────────────────────
from dotenv import load_dotenv
load_dotenv()

# ── 2. 네이티브 런타임 호환 모듈 (구 Streamlit 대체) ──────────────────────────
#     data.py / db.py / ai_engine.py 등이 `import st_compat as st` 로 직접 사용한다.
#     (.env 로드 후 import 되어야 secrets 가 환경변수로 채워진다.)
import st_compat  # noqa: F401

# ── 3. FastAPI 및 라우터 임포트 ──────────────────────────────────────────────
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from version import APP_VERSION

from api.routers import (
    market_kr as kr,
    market_us as us,
    ai,
    portfolio,
    admin,
    trading,
    screener,
    auth,
)

# ── 4. FastAPI 앱 생성 ───────────────────────────────────────────────────────
app = FastAPI(
    title="Stockcy Backend API",
    description="국내/미국 주식 데이터 및 AI 분석 API",
    version=APP_VERSION,
)

# ── 5. 미들웨어 설정 ─────────────────────────────────────────────────────────
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "https://drop-down-prankish-breath.ngrok-free.dev",
    "https://stockcy.trade",
]
# 클라우드 배포 시 프론트 도메인 허용: FRONTEND_URL 환경변수가 있으면 추가
_frontend_env = os.environ.get("FRONTEND_URL", "").strip()
if _frontend_env and _frontend_env not in origins:
    origins.append(_frontend_env)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # ngrok / cloudtype 배포 도메인 동적 허용 (SSE 직접연결 CORS 차단 방지)
    allow_origin_regex=r"https://.*\.(ngrok-free\.dev|cloudtype\.app|stockcy\.trade)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 6. 라우터 등록 ────────────────────────────────────────────────────────────
app.include_router(trading.router,    prefix="/api",          tags=["Trading"])
app.include_router(us.router,         prefix="/api/us",       tags=["미국 시장"])
app.include_router(kr.router,         prefix="/api/kr",       tags=["국내 시장"])
app.include_router(ai.router,         prefix="/api/ai",       tags=["AI 분석"])
app.include_router(screener.router,   prefix="/api/screener", tags=["스크리너"])
app.include_router(portfolio.router,  prefix="/api",          tags=["포트폴리오·즐겨찾기"])
app.include_router(admin.router,      prefix="/api/admin",    tags=["관리자"])
app.include_router(auth.router,       prefix="/api/auth",     tags=["인증"])

# ── 7. 헬스체크 ───────────────────────────────────────────────────────────────
# async def로 정의 → 동기 스레드풀을 쓰지 않으므로, 외부 시세 소스 장애로 풀이
# 고갈돼도 생존신호/버전은 항상 즉시 응답한다.
@app.get("/api/health", tags=["시스템"])
async def health():
    return {"status": "ok", "app": f"Stockcy API v{APP_VERSION}"}

@app.get("/api/version", tags=["시스템"])
async def get_version():
    return {"version": APP_VERSION}

@app.get("/api/circuit", tags=["시스템"])
async def circuit_status():
    """외부 시세 소스 서킷 브레이커 상태 (open=현재 fail-fast 중)."""
    from api.circuit import yf_breaker
    return yf_breaker.status()

@app.on_event("startup")
async def _boost_threadpool():
    """동기(def) 엔드포인트용 AnyIO 스레드풀 한도 상향 (기본 40 → 200).
    외부 시세 호출이 일부 매달려도 단순 엔드포인트가 막히지 않도록 헤드룸 확보."""
    try:
        import anyio
        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = 200
        print(f"[startup] 동기 스레드풀 토큰 = {limiter.total_tokens}")
    except Exception as e:
        print(f"[startup] 스레드풀 토큰 상향 실패: {e}")


# ── 8. 백그라운드 전종목 가격 캐시 스케줄러 ──────────────────────────────────
import threading as _threading
import time as _time

# 전종목 가격 인메모리 캐시: {"code": {"price": ..., "change_pct": ...}}
KRX_PRICE_CACHE: dict = {}
_KRX_CACHE_UPDATED: float = 0.0
_KRX_REFRESH_SEC = 90   # 90초마다 갱신
_KRX_FAIL_STREAK = 0    # 연속 실패 횟수 (로그 스팸 방지용)


def _refresh_krx_prices():
    """FDR StockListing으로 전종목 가격을 갱신해 KRX_PRICE_CACHE에 저장.

    [방어] FDR krx/listing.py는 내부 requests.get가 네트워크로 실패하면 except에서
    할당 전 변수 r을 참조해 UnboundLocalError('r')를 던지는 버그가 있다. 즉 'r' 오류는
    사실상 일시적 네트워크 실패다. 따라서 짧은 백오프로 재시도하고, 끝내 실패하면
    기존 캐시를 그대로 유지(덮어쓰지 않음)한 채 간결한 로그만 남긴다.
    (이 함수는 백그라운드 데몬 스레드에서 돌아 재시도 sleep이 요청 처리를 막지 않는다.)"""
    global _KRX_CACHE_UPDATED, _KRX_FAIL_STREAK
    import FinanceDataReader as fdr

    df = None
    last_err = "알 수 없음"
    for attempt in range(3):
        try:
            df = fdr.StockListing("KRX")
            if df is not None and not df.empty:
                break
            last_err = "빈 응답"
        except Exception as e:
            # FDR의 UnboundLocalError('r')는 내부 네트워크 실패를 의미 — 재시도 가치 있음
            last_err = "네트워크 실패(FDR)" if "'r'" in str(e) else str(e)[:100]
        _time.sleep(1.5 * (attempt + 1))  # 1.5초 → 3초 백오프

    if df is None or df.empty:
        _KRX_FAIL_STREAK += 1
        # 캐시는 덮어쓰지 않고 유지. 로그는 처음과 5회마다만 — 스팸 방지
        if _KRX_FAIL_STREAK == 1 or _KRX_FAIL_STREAK % 5 == 0:
            print(f"[KRX cache] 갱신 실패({_KRX_FAIL_STREAK}회 연속): {last_err} "
                  f"— 기존 캐시 {len(KRX_PRICE_CACHE)}종목 유지")
        return

    tmp = {}
    for _, row in df.iterrows():
        code = str(row.get("Code", "")).strip().zfill(6)
        try:
            price    = int(row.get("Close", 0) or 0)
            chg_pct  = round(float(row.get("ChagesRatio", 0) or 0), 2)
            if price > 0:
                tmp[code] = {"price": price, "change_pct": chg_pct}
        except Exception:
            pass

    # ETF/ETN은 StockListing("KRX")에 없음 → ETF 리스팅으로 가격 보강(ETF가 0원/0%로 뜨던 문제).
    etf_n = 0
    try:
        etf_df = fdr.StockListing("ETF/KR")
        if etf_df is not None and not etf_df.empty:
            for _, row in etf_df.iterrows():
                code = str(row.get("Symbol", "")).strip().zfill(6)
                try:
                    price = int(row.get("Price", 0) or 0)
                    chg = round(float(row.get("ChangeRate", 0) or 0), 2)
                    if price > 0:
                        tmp[code] = {"price": price, "change_pct": chg}
                        etf_n += 1
                except Exception:
                    pass
    except Exception as _e:
        print(f"[KRX cache] ETF 리스팅 보강 실패(주식만 유지): {_e}")

    if not tmp:
        return  # 파싱 결과가 비면 캐시 유지

    KRX_PRICE_CACHE.update(tmp)
    _KRX_CACHE_UPDATED = _time.time()
    if _KRX_FAIL_STREAK > 0:
        print(f"[KRX cache] 갱신 복구 — {len(tmp)}종목(ETF {etf_n}) (직전 {_KRX_FAIL_STREAK}회 실패 후)")
        _KRX_FAIL_STREAK = 0
    else:
        print(f"[KRX cache] {len(tmp)}종목 갱신 완료 (ETF {etf_n} 포함)")


def _price_refresh_loop():
    """서버 시작 후 즉시 1회 갱신, 이후 90초마다 반복."""
    _refresh_krx_prices()
    while True:
        _time.sleep(_KRX_REFRESH_SEC)
        _refresh_krx_prices()


@app.on_event("startup")
def start_price_cache():
    t = _threading.Thread(target=_price_refresh_loop, daemon=True)
    t.start()
    print("[KRX cache] 백그라운드 가격 캐시 스케줄러 시작")


# ── 9. 에이전트 일일 이슈 자동 분석 스케줄러 ─────────────────────────────────
_LAST_ISSUE_DATE = ""

def _daily_issue_loop():
    """매일 07:50 KST에 오늘의 핫이슈/심리 자동 분석 (서버 시작 시 1회 즉시 실행)."""
    global _LAST_ISSUE_DATE
    import datetime as _dt
    # 서버 시작 직후 1회 즉시 분석 — 단, 오늘 이미 분석한 기록이 있으면 스킵 (재시작 중복 방지)
    try:
        from db import has_today_agent_issues
        today_str = _dt.datetime.now().strftime("%Y-%m-%d")
        if has_today_agent_issues():
            _LAST_ISSUE_DATE = today_str   # 오늘 이미 있음 → 오늘 정기분석도 스킵
            print(f"[daily issue] 오늘({today_str}) 이미 분석됨 → 이슈 분석 스킵 (비용 절약)")
            # 단, 메인 시나리오 캐시가 비어있으면 그것만 보강 생성
            try:
                from db import load_ai_cache, save_ai_cache
                existing = load_ai_cache("market_scenarios_latest")
                if not (existing and "error" not in existing):
                    from ai_engine import generate_market_scenarios
                    main_res = generate_market_scenarios()
                    if main_res and "error" not in main_res:
                        save_ai_cache("market_scenarios_latest", main_res, 12)
                        print("[daily issue] 메인 시나리오 캐시 보강 생성 완료")
            except Exception as me:
                print(f"[daily issue] 메인 시나리오 보강 실패: {me}")
        else:
            from ai_engine import analyze_agent_daily_issues
            r = analyze_agent_daily_issues()
            _LAST_ISSUE_DATE = today_str
            print(f"[daily issue] 서버 시작 시 분석 완료: {r.get('count',0)}개 이슈")
            # [노이즈 절감] 시나리오/일일이슈 텔레그램 알림 비활성 — 앱 내 시나리오 화면으로 충분.
            #   분석(analyze_agent_daily_issues)은 유지 = AI 학습/앱 데이터는 계속 갱신됨.
            #   다시 켜려면 아래 send_scenario_alert 호출 복원.
    except Exception as e:
        print(f"[daily issue] 시작 시 분석 오류: {e}")

    # 하루 2회 자동 분석 — 슬롯별로 마지막 실행일을 따로 추적
    _slot_done = {"us": "", "kr": ""}
    while True:
        try:
            now = _dt.datetime.now()
            today = now.strftime("%Y-%m-%d")
            wd = now.weekday()  # 월=0 ... 일=6

            # 🇺🇸 미국장 마감 직후 (한국 새벽 06:10). 미국 월~금장 = 한국 화~토 → wd 1~5
            us_slot = (1 <= wd <= 5 and now.hour == 6 and now.minute >= 10)
            # 🇰🇷 한국장 마감 직후 (15:40). 한국 월~금 → wd 0~4
            kr_slot = (0 <= wd <= 4 and now.hour == 15 and now.minute >= 40)

            slot = "us" if us_slot else ("kr" if kr_slot else None)
            if slot and _slot_done[slot] != today:
                try:
                    from ai_engine import analyze_agent_daily_issues
                    r = analyze_agent_daily_issues()
                    _slot_done[slot] = today
                    print(f"[daily issue] {slot} 슬롯 분석 완료: {r.get('count',0)}개 이슈 ({today})")
                    # [노이즈 절감] 시나리오/일일이슈 텔레그램 알림 비활성 — 앱 내 시나리오 화면으로 충분.
                    #   분석은 유지 = AI 학습/앱 데이터는 계속 갱신됨.
                except Exception as e:
                    print(f"[daily issue] {slot} 슬롯 오류: {e}")
        except Exception:
            pass
        _time.sleep(300)   # 5분마다 체크


@app.on_event("startup")
def start_daily_issue_scheduler():
    t = _threading.Thread(target=_daily_issue_loop, daemon=True)
    t.start()
    print("[daily issue] 에이전트 일일 이슈 분석 스케줄러 시작 (평일 07:50 + 시작 시 1회)")


# ── 10. 일일 알림 자동 발송 스케줄러 ──────────────────────────────────────────
_LAST_ALERT_DATE = ""

def _daily_alert_loop():
    """매일 08:30 KST에 일일 알림 자동 발송 (하루 1회 보장)."""
    global _LAST_ALERT_DATE
    import datetime as _dt
    while True:
        try:
            now = _dt.datetime.now()
            today = now.strftime("%Y-%m-%d")
            # 평일(월~금)이고 8시 30분~9시 사이이고 오늘 아직 안 보냈으면 발송
            if (now.weekday() < 5
                and now.hour == 8 and now.minute >= 30
                and _LAST_ALERT_DATE != today):
                try:
                    from ai_engine import send_daily_alert
                    result = send_daily_alert()
                    if result.get("sent"):
                        _LAST_ALERT_DATE = today
                        print(f"[daily alert] 발송 완료: {today}")
                    else:
                        print(f"[daily alert] 스킵: {result.get('reason') or result.get('error')}")
                except Exception as e:
                    print(f"[daily alert] 오류: {e}")
        except Exception:
            pass
        _time.sleep(120)   # 2분마다 체크


@app.on_event("startup")
def start_daily_alert_scheduler():
    t = _threading.Thread(target=_daily_alert_loop, daemon=True)
    t.start()
    print("[daily alert] 일일 알림 스케줄러 시작 (평일 08:30)")


# ── 10-b. 시나리오 적중률 자동 추적 스케줄러 ──────────────────────────────────
_LAST_SCENARIO_TRACK_DATE = ""

def _scenario_tracking_loop():
    """매일 오전 07:00 KST에 시나리오 등장 종목의 가격 추적을 자동 실행.
    미국장 마감(~05:00 KST) 이후라 직전 미국·한국 세션을 모두 반영하며,
    수동 '추적 실행' 없이도 매일 적중률이 갱신된다. (주말 포함 — 금요일 미국장
    데이터가 토요일 새벽에 들어오므로 매일 점검)
    track_scenario_stocks_performance는 블로킹(~20초)이지만 이 데몬 스레드에서만
    돌아 요청 처리/이벤트 루프를 막지 않는다."""
    global _LAST_SCENARIO_TRACK_DATE
    import datetime as _dt
    while True:
        try:
            now = _dt.datetime.now()
            today = now.strftime("%Y-%m-%d")
            # catch-up: 07시 정각이 아니라 '07시 이후 처음 살아있는 시점'에 그날 1회 실행.
            #   (노트북이 07:00~07:59에 안 켜져 있으면 통째로 스킵되던 버그 — 대부분의 아침 누락 원인)
            if now.hour >= 7 and _LAST_SCENARIO_TRACK_DATE != today:
                try:
                    from ai_engine import track_scenario_stocks_performance
                    r = track_scenario_stocks_performance()
                    _LAST_SCENARIO_TRACK_DATE = today
                    print(f"[scenario track] 자동 추적 완료: {r.get('updated_now', 0)}건 갱신 ({today})")
                    # [노이즈 절감] 시나리오 적중률 텔레그램 발송 비활성 — 앱 내 시나리오 화면에서 확인.
                    #   추적 계산(track_scenario_stocks_performance)은 유지 = 적중률 데이터는 계속 갱신됨.
                except Exception as e:
                    print(f"[scenario track] 자동 추적 오류: {e}")
                # AI추천 사후 성과(d1/d3/d7) 측정 — AI 호출 없이 가격만 사용
                try:
                    from ai_engine import track_ai_recommendation_outcomes
                    ar = track_ai_recommendation_outcomes()
                    print(f"[ai-rec track] AI추천 성과 측정: {ar.get('updated_now', 0)}건 갱신 ({today})")
                except Exception as e:
                    print(f"[ai-rec track] 오류: {e}")
                # 자체 ML 통합 학습샘플 보강 — 추천 종목의 판단시점 지표+결과를 과거 데이터로 채움
                try:
                    from ml_model import track_ml_sample_outcomes
                    ms = track_ml_sample_outcomes()
                    print(f"[ml sample] 학습샘플 보강: {ms.get('updated_now', 0)}건 ({today})")
                except Exception as e:
                    print(f"[ml sample] 오류: {e}")
                # 자체 ML 자동 재학습 — 샘플 보강 직후 1회 (scikit-learn 로컬·무과금).
                #   MIN_SAMPLES 미만 horizon은 train_model이 알아서 보류(trained=False).
                try:
                    import os as _os
                    from ml_model import train_all, _model_path, HORIZONS
                    # 학습 전, 어떤 horizon이 아직 '모델 없음'이었는지 기록(첫 학습 감지용)
                    _was_missing = {h for h in HORIZONS if not _os.path.exists(_model_path(h))}
                    _tr = train_all()
                    _done = {h: r.get("samples") for h, r in _tr.items() if r.get("trained")}
                    print(f"[ml train] 자동 재학습: {_done or '학습된 모델 없음(데이터 부족)'} ({today})")
                    # 직전엔 모델이 없었는데 이번에 처음 학습된 horizon → 텔레그램 1회 알림
                    _newly = [h for h in _was_missing if _tr.get(h, {}).get("trained")]
                    if _newly:
                        _label = {"d3": "단타(d3)", "d7": "스윙(d7)", "d20": "중장기(d20)"}
                        _lines = [f"• {_label.get(h, h)}: 표본 {_tr[h].get('samples')}건, AUC {_tr[h].get('cv_auc')}" for h in _newly]
                        try:
                            from telegram_bot import send_message
                            send_message("🤖 <b>자체 ML 모델 신규 학습 완료</b>\n" + "\n".join(_lines) +
                                         "\n\n성과 탭의 'ML 모델 현황'에서 확인하세요.")
                        except Exception as _te:
                            print(f"[ml train] 텔레그램 알림 실패: {_te}")
                except Exception as e:
                    print(f"[ml train] 오류: {e}")
                # 패턴 스크리너 백테스트(+1/+3/+7일) — 그동안 수동 실행만 가능했던 것을 자동화
                try:
                    from ai_engine import backtest_screener_picks
                    bt = backtest_screener_picks()
                    print(f"[screener bt] 스크리너 백테스트 갱신: {(bt or {}).get('backtested', 0)}건 ({today})")
                except Exception as e:
                    print(f"[screener bt] 오류: {e}")
                # 보유 종목 일별 스냅샷 (특정일 보유 복원용) — KR 현재가로 평가손익 기록
                try:
                    from db import save_portfolio_snapshot
                    def _kr_price(tk):
                        if str(tk).strip().isdigit():
                            from data_kr import get_kr_stock_price
                            d = get_kr_stock_price(str(tk).strip())
                            return float((d or {}).get("price") or 0) or None
                        return None
                    sr = save_portfolio_snapshot(price_lookup=_kr_price)
                    print(f"[pf snapshot] 보유 스냅샷 저장: {sr.get('saved', 0)}건 ({today})")
                except Exception as e:
                    print(f"[pf snapshot] 오류: {e}")
                # EV/EBITDA 일별 스냅 — 보유+즐겨찾기 US 종목 (자체 밴드 누적, 종목당 딜레이로 yfinance 보호)
                try:
                    from db import get_db_conn
                    from valuation_score import snapshot_ev_ebitda_for
                    _conn = get_db_conn(); _cur = _conn.cursor()
                    _us = set()
                    for _tbl in ("portfolio", "favorites"):
                        try:
                            for _row in _cur.execute(f"SELECT ticker FROM {_tbl}").fetchall():
                                _t = str(_row["ticker"]).strip().upper()
                                if _t and not _t.isdigit():   # US만 (EV/EBITDA는 US만 존재)
                                    _us.add(_t)
                        except Exception:
                            pass
                    _conn.close()
                    if _us:
                        _es = snapshot_ev_ebitda_for(list(_us))
                        print(f"[ev snap] EV/EBITDA 일별 스냅: {_es.get('saved', 0)}/{_es.get('requested', 0)}건 ({today})")
                except Exception as e:
                    print(f"[ev snap] 오류: {e}")
                # 내 패턴 스크리너 — 매일 자동 실행(교차검증에 '패턴스크리너' 엔진이 매일 기여, 회당 ~5원)
                try:
                    from ai_engine import screen_by_my_pattern
                    from db import save_screener_picks
                    _pr = screen_by_my_pattern()
                    if _pr.get("top_picks"):
                        save_screener_picks(_pr["top_picks"])
                        print(f"[pattern screen] 자동 스크리닝 저장: {len(_pr['top_picks'])}건 ({today})")
                    elif _pr.get("error"):
                        print(f"[pattern screen] 스킵: {_pr['error']}")
                except Exception as e:
                    print(f"[pattern screen] 오류: {e}")
        except Exception:
            pass
        _time.sleep(300)   # 5분마다 체크


@app.on_event("startup")
def start_scenario_tracking_scheduler():
    t = _threading.Thread(target=_scenario_tracking_loop, daemon=True)
    t.start()
    print("[scenario track] 시나리오 적중률 추적 스케줄러 시작 (매일 07:00)")


# ── 10-b1b. 메인 시나리오 아침 보충 (평일 08~11시 그날 1회 — 부팅·상시가동 무관) ──
_LAST_MAIN_SCENARIO_DATE = ""
_MAIN_SCENARIO_ATTEMPTS: dict = {}   # {date: 시도횟수} — 실패 무한 재시도(과금 폭주) 방지

def _main_scenario_morning_loop():
    """평일 아침(08~11시) 오늘 메인 시나리오 캐시가 없으면 1회 생성.
    06:10 미국장 슬롯을 PC가 꺼져 놓치거나 월요일(06:10 슬롯 없음)인 빈틈을 메운다.

    [비용 가드 v3.110.2] 07-06 폭주 사후분석: 캐시 만료 + 생성 실패(파싱)가 겹치자
    5분마다 무한 재시도 + 대시보드 자동생성과 중복 → 15분에 9회(422원) 과금.
    → ①시간창 08~11시 제한(기존 hour>=8은 사실상 종일 조건이었음)
      ②하루 최대 3회 시도 후 그날 중단  ③TTL 12→16h(저녁까지 커버, 밤 재생성 차단)."""
    global _LAST_MAIN_SCENARIO_DATE
    import datetime as _dt
    _time.sleep(20)   # 서버 안정화 후 시작
    while True:
        try:
            now = _dt.datetime.now()
            today = now.strftime("%Y-%m-%d")
            if (now.weekday() < 5 and 8 <= now.hour < 11
                    and _LAST_MAIN_SCENARIO_DATE != today
                    and _MAIN_SCENARIO_ATTEMPTS.get(today, 0) < 3):
                from db import load_ai_cache, save_ai_cache, save_daily_market_log
                existing = load_ai_cache("market_scenarios_latest")
                if existing and "error" not in existing:
                    _LAST_MAIN_SCENARIO_DATE = today   # 이미 있음 → 생성 스킵(비용 0)
                    print(f"[main scenario] 오늘 메인 시나리오 이미 존재 → 보충 스킵 ({today})")
                else:
                    _MAIN_SCENARIO_ATTEMPTS[today] = _MAIN_SCENARIO_ATTEMPTS.get(today, 0) + 1
                    from ai_engine import generate_market_scenarios
                    res = generate_market_scenarios()
                    if res and "error" not in res:
                        save_ai_cache("market_scenarios_latest", res, 16)   # 16h — 아침 생성이 밤까지 커버
                        try:
                            save_daily_market_log("scenarios", res)   # 역사 누적도 함께
                        except Exception:
                            pass
                        _LAST_MAIN_SCENARIO_DATE = today
                        print(f"[main scenario] 아침 보충 생성 완료 ({today})")
                    else:
                        print(f"[main scenario] 아침 보충 실패 ({_MAIN_SCENARIO_ATTEMPTS[today]}/3회) — "
                              f"{'오늘 중단' if _MAIN_SCENARIO_ATTEMPTS[today] >= 3 else '다음 틱 재시도'} ({today})")
        except Exception as e:
            print(f"[main scenario] 보충 루프 오류: {e}")
        _time.sleep(300)   # 5분마다 체크


@app.on_event("startup")
def start_main_scenario_morning_scheduler():
    t = _threading.Thread(target=_main_scenario_morning_loop, daemon=True)
    t.start()
    print("[main scenario] 메인 시나리오 아침 보충 스케줄러 시작 (평일 08:00 이후 1회)")


# ── 10-b2. 복합 스크리너 OHLC 캐시 워밍 (첫 '전체' 호출 120초 타임아웃 방지) ────────
def _screener_warm_loop():
    """복합 스크리너의 무거운 '전체' 섹터 OHLC를 캐시 TTL(2h) 만료 전에 미리 채운다.
    서버 시작 직후 1회 + 이후 110분마다. 사용자의 첫 스크리닝이 즉시 응답하게 한다."""
    while True:
        try:
            from api.routers.screener import warm_screener_cache
            # US '전체'는 종목군이 방대하고 상폐/정크 티커가 많아 yfinance가 장시간 매달림 → KR만 워밍.
            # (US는 사용자가 특정 섹터 선택 시 on-demand로 캐싱; timeout+서킷으로 보호)
            r = warm_screener_cache(sectors=("전체",), markets=("KR",))
            print(f"[screener warm] 캐시 워밍 완료: {r}")
        except Exception as e:
            print(f"[screener warm] 워밍 오류: {e}")
        _time.sleep(6600)   # 110분 (TTL 7200초보다 짧게 → 만료 전 재충전)


@app.on_event("startup")
def start_screener_warm_scheduler():
    t = _threading.Thread(target=_screener_warm_loop, daemon=True)
    t.start()
    print("[screener warm] 복합 스크리너 캐시 워밍 스케줄러 시작 (시작 시 + 110분마다)")


# ── 10-b3. 리서치 텔레그램 채널 워처 (이슈 자동 수집·요약·푸시) ────────────────────
def _research_watch_loop():
    """RESEARCH_TG_CHANNELS 설정 시, 25분마다 리서치 채널의 신규 글을 요약해 텔레그램 푸시."""
    import os
    if not os.environ.get("RESEARCH_TG_CHANNELS", "").strip():
        print("[research watch] RESEARCH_TG_CHANNELS 미설정 — 워처 비활성")
        return
    _time.sleep(30)   # 서버 안정화 후 시작
    while True:
        try:
            from research_watcher import run_research_watch
            # [노이즈 절감] 수집·AI 요약(학습/시나리오 자동등록)은 유지하되 텔레그램 푸시는 OFF.
            r = run_research_watch(push=False)
            print(f"[research watch] {r}")
        except Exception as e:
            print(f"[research watch] 오류: {e}")
        _time.sleep(1500)   # 25분


@app.on_event("startup")
def start_research_watch_scheduler():
    t = _threading.Thread(target=_research_watch_loop, daemon=True)
    t.start()
    print("[research watch] 리서치 채널 워처 스케줄러 시작 (설정 시 25분마다)")


# ── 10-b4. 관심종목 촉매 알림(B) + 실적 임박 경고(C) ──────────────────────────────
def _watchlist_alert_loop():
    """평일 장중 15분마다 관심종목 급변동 스캔, 1일 1회 실적 임박 경고."""
    import datetime as _dt
    _time.sleep(45)
    _last_earnings_date = ""
    while True:
        try:
            now = _dt.datetime.now()
            wd = now.weekday()
            # 촉매 스캔: 평일 09~익일 06시(KR장+US장 커버) 15분마다
            if wd <= 4 and (now.hour >= 9 or now.hour <= 6):
                try:
                    from watchlist_alerts import run_catalyst_scan
                    run_catalyst_scan(push=True)
                except Exception as e:
                    print(f"[catalyst] 오류: {e}")
            # 실적 경고: 매일 08시대 1회
            today = now.strftime("%Y-%m-%d")
            if now.hour == 8 and _last_earnings_date != today:
                try:
                    from watchlist_alerts import run_earnings_alert
                    r = run_earnings_alert(push=True, within=2)
                    _last_earnings_date = today
                    print(f"[earnings] {r}")
                except Exception as e:
                    print(f"[earnings] 오류: {e}")
        except Exception:
            pass
        _time.sleep(900)   # 15분


@app.on_event("startup")
def start_watchlist_alert_scheduler():
    t = _threading.Thread(target=_watchlist_alert_loop, daemon=True)
    t.start()
    print("[watchlist] 촉매/실적 알림 스케줄러 시작 (장중 15분 / 실적 08시)")


# ── 10-c. 외국인·기관 수급 일일 스냅샷 스케줄러 (세력 자금 이동 추적용) ──────────
_LAST_SUPPLY_SNAPSHOT_DATE = ""
_SUPPLY_SNAPSHOT_ATTEMPTS: dict = {}   # {date: 시도횟수} — 휴장일 무한 재시도 방지
_SUPPLY_SNAPSHOT_NEXT_TS = 0.0         # 실패 후 다음 시도 허용 시각 — 재시도 10분 간격

def _supply_snapshot_loop():
    """평일 장 마감(15:45 KST) 이후 '아무 때나' 외국인·기관 수급 스냅샷을 DB에 적재.
    매일 쌓여야 day-over-day 세력 자금 이동/이상급증(detect_supply_rotation·detect_abnormal_supply)이 동작한다.

    [강건화] 과거엔 15:45~15:59 15분 창에만 트리거돼, 노트북 배포 특성상 그 순간 백엔드가
    안 떠 있으면 그날치를 영영 놓쳤다(6/23 이후 전면 중단의 원인). 이제:
      ① 창 확대: 15:45 이후면 저녁·밤 아무 때나 오늘치 미적재 시 즉시 적재.
      ② 시작 시 캐치업: 루프 첫 iteration에서 바로 조건 평가 → 뒤늦게 켜도 그날치 확보.
    DB에 오늘치가 이미 있으면(재시작 후에도) 건너뛴다.
    [v3.110.3] 07-06 실측: KIS 가집계가 15:55경에야 발행돼 기존 2분×5회(15:46~54) 창이
    전부 헛스윙 → 실패 시 재시도를 10분 간격·최대 8회로 변경(15:45~17시대 커버)."""
    global _LAST_SUPPLY_SNAPSHOT_DATE, _SUPPLY_SNAPSHOT_NEXT_TS
    import datetime as _dt
    while True:
        try:
            now = _dt.datetime.now()
            today = now.strftime("%Y-%m-%d")
            after_close = now.hour > 15 or (now.hour == 15 and now.minute >= 45)
            if (now.weekday() < 5 and after_close and _LAST_SUPPLY_SNAPSHOT_DATE != today
                    and _time.time() >= _SUPPLY_SNAPSHOT_NEXT_TS):
                # 재시작 대비: DB에 오늘치가 이미 있으면 재적재하지 않고 완료 처리
                already = False
                try:
                    from db import load_frgn_inst_snapshot_dates
                    already = today in (load_frgn_inst_snapshot_dates(1) or [])
                except Exception:
                    pass
                if already:
                    _LAST_SUPPLY_SNAPSHOT_DATE = today
                elif _SUPPLY_SNAPSHOT_ATTEMPTS.get(today, 0) < 8:
                    _SUPPLY_SNAPSHOT_ATTEMPTS[today] = _SUPPLY_SNAPSHOT_ATTEMPTS.get(today, 0) + 1
                    try:
                        from data_kr import snapshot_frgn_inst_today, snapshot_sector_flow_today
                        r = snapshot_frgn_inst_today()
                        sr = snapshot_sector_flow_today()
                        saved = int(r.get("saved", 0) or 0)
                        if saved > 0:
                            _LAST_SUPPLY_SNAPSHOT_DATE = today   # 성공 시에만 완료 처리
                            print(f"[supply snapshot] 종목 {saved}건 / 섹터 {sr.get('sectors', 0)}개 ({today})")
                        else:
                            _SUPPLY_SNAPSHOT_NEXT_TS = _time.time() + 600   # 발행 지연 대비 10분 뒤 재시도
                            print(f"[supply snapshot] 데이터 없음(발행 지연/휴장) — 10분 후 재시도 {_SUPPLY_SNAPSHOT_ATTEMPTS[today]}/8 ({today})")
                    except Exception as e:
                        _SUPPLY_SNAPSHOT_NEXT_TS = _time.time() + 600   # 오류도 10분 간격으로만 재시도
                        print(f"[supply snapshot] 오류(10분 후 재시도): {e}")
        except Exception:
            pass
        _time.sleep(120)


@app.on_event("startup")
def start_supply_snapshot_scheduler():
    t = _threading.Thread(target=_supply_snapshot_loop, daemon=True)
    t.start()
    print("[supply snapshot] 수급 스냅샷 스케줄러 시작 (평일 15:45 이후 캐치업)")


# ── 10-d. 전 유저 패턴 학습 정기 재빌드 (Phase 6) ──────────────────────────────
def _pattern_rebuild_loop():
    """서버 시작 60초 후 1회 + 매일 04:00 KST에 전 유저 거래 통합 패턴 프로파일 재빌드.
    거래 변경 시에도 즉시 재빌드되지만, 신규 유저 데이터·서버 재시작 누락 방지용 안전망.
    build_pattern_profile는 순수 DB 집계라 Gemini 비용이 들지 않는다."""
    import datetime as _dt
    _time.sleep(60)
    try:
        from db import _rebuild_pattern_profile_bg
        _rebuild_pattern_profile_bg()
        print("[pattern] 시작 시 전 유저 패턴 학습 재빌드 완료")
    except Exception as e:
        print(f"[pattern] 시작 시 재빌드 오류: {e}")
    _last = ""
    while True:
        try:
            now = _dt.datetime.now()
            today = now.strftime("%Y-%m-%d")
            if now.hour == 4 and _last != today:
                from db import _rebuild_pattern_profile_bg
                _rebuild_pattern_profile_bg()
                _last = today
                print(f"[pattern] 일일 전 유저 패턴 학습 재빌드 완료 ({today})")
        except Exception as e:
            print(f"[pattern] 일일 재빌드 오류: {e}")
        _time.sleep(600)


@app.on_event("startup")
def start_pattern_rebuild_scheduler():
    t = _threading.Thread(target=_pattern_rebuild_loop, daemon=True)
    t.start()
    print("[pattern] 전 유저 패턴 학습 스케줄러 시작 (시작 시 + 매일 04:00)")


@app.on_event("startup")
def resume_gap_bulk_job():
    """서버 재시작으로 중단된 시간외 갭 일괄 분석 작업이 있으면 이어서 진행."""
    try:
        from api.routers.ai import resume_gap_bulk_job_if_any
        resume_gap_bulk_job_if_any()
    except Exception as e:
        print(f"[gap bulk] 재개 시도 오류: {e}")


@app.on_event("startup")
def resume_sector_backfill():
    """서버 재시작으로 중단된 섹터 흐름 백필이 있으면 자동 이어하기."""
    try:
        from data_kr import resume_sector_backfill_if_any
        resume_sector_backfill_if_any()
    except Exception as e:
        print(f"[sector backfill] 재개 시도 오류: {e}")

# ── 8. 백그라운드 태스크 ───────────────────────────────────────────────────────
import asyncio
from api.background import price_alert_loop

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(price_alert_loop())
    from api.agent import ai_trading_loop
    asyncio.create_task(ai_trading_loop())
    # FDR 미국 섹터 캐시 갱신 (백그라운드 스레드 — 완료까지 수분 소요)
    import threading
    def _refresh_fdr():
        try:
            from db import refresh_us_fdr_sector_cache
            refresh_us_fdr_sector_cache()
        except Exception:
            pass
    threading.Thread(target=_refresh_fdr, daemon=True).start()


@app.get("/api/config-status", tags=["시스템"])
def config_status():
    """각 외부 서비스 설정 여부를 확인합니다."""
    return {
        "gemini":   bool(os.environ.get("GEMINI_API_KEY")),
        "kis":      bool(os.environ.get("KIS_APP_KEY")),
        "gspread":  bool(os.environ.get("GSPREAD_CREDENTIALS")),
        "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
    }
