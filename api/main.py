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

# ── 2. Streamlit 모의 모듈 설치 (반드시 다른 임포트보다 먼저) ──────────────
#     이 라인이 sys.modules["streamlit"] 을 패치하여
#     이후 import 되는 data.py / db.py / ai_engine.py 등이
#     st.secrets / @st.cache_data 를 환경변수·TTL캐시로 자동 대체합니다.
import api.core.streamlit_mock  # noqa: F401

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
    screener
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
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.ngrok-free\.dev", # ngrok 도메인 변경 대비 동적 regex 허용
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

    if not tmp:
        return  # 파싱 결과가 비면 캐시 유지

    KRX_PRICE_CACHE.update(tmp)
    _KRX_CACHE_UPDATED = _time.time()
    if _KRX_FAIL_STREAK > 0:
        print(f"[KRX cache] 갱신 복구 — {len(tmp)}종목 (직전 {_KRX_FAIL_STREAK}회 실패 후)")
        _KRX_FAIL_STREAK = 0
    else:
        print(f"[KRX cache] {len(tmp)}종목 갱신 완료")


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
            try:
                from ai_engine import send_scenario_alert
                sres = send_scenario_alert()
                print(f"[scenario alert] 시작 시 발송: {sres}")
            except Exception as se:
                print(f"[scenario alert] 시작 시 발송 오류: {se}")
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
                    try:
                        from ai_engine import send_scenario_alert
                        sres = send_scenario_alert()
                        print(f"[scenario alert] {slot} 슬롯 발송: {sres}")
                    except Exception as se:
                        print(f"[scenario alert] {slot} 슬롯 발송 오류: {se}")
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
            if now.hour == 7 and _LAST_SCENARIO_TRACK_DATE != today:
                try:
                    from ai_engine import track_scenario_stocks_performance
                    r = track_scenario_stocks_performance()
                    _LAST_SCENARIO_TRACK_DATE = today
                    print(f"[scenario track] 자동 추적 완료: {r.get('updated_now', 0)}건 갱신 ({today})")
                    # 추적 직후 결과를 텔레그램으로 요약 발송 (US 포함 등장가 대비 수익률)
                    try:
                        from ai_engine import send_scenario_tracking_alert
                        tres = send_scenario_tracking_alert()
                        print(f"[scenario track] 텔레그램 발송: {tres}")
                    except Exception as te:
                        print(f"[scenario track] 텔레그램 발송 오류: {te}")
                except Exception as e:
                    print(f"[scenario track] 자동 추적 오류: {e}")
        except Exception:
            pass
        _time.sleep(300)   # 5분마다 체크


@app.on_event("startup")
def start_scenario_tracking_scheduler():
    t = _threading.Thread(target=_scenario_tracking_loop, daemon=True)
    t.start()
    print("[scenario track] 시나리오 적중률 추적 스케줄러 시작 (매일 07:00)")


@app.on_event("startup")
def resume_gap_bulk_job():
    """서버 재시작으로 중단된 시간외 갭 일괄 분석 작업이 있으면 이어서 진행."""
    try:
        from api.routers.ai import resume_gap_bulk_job_if_any
        resume_gap_bulk_job_if_any()
    except Exception as e:
        print(f"[gap bulk] 재개 시도 오류: {e}")

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
