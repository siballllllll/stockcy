"""
Stockcy FastAPI 서버 엔트리포인트

실행 방법:
  uvicorn api.main:app --reload --port 8000

⚠️  반드시 프로젝트 루트에서 실행해야 합니다 (data.py, db.py 등을 임포트하기 위해).
"""
import sys
import os

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
@app.get("/api/health", tags=["시스템"])
def health():
    return {"status": "ok", "app": f"Stockcy API v{APP_VERSION}"}

@app.get("/api/version", tags=["시스템"])
def get_version():
    return {"version": APP_VERSION}


# ── 8. 백그라운드 전종목 가격 캐시 스케줄러 ──────────────────────────────────
import threading as _threading
import time as _time

# 전종목 가격 인메모리 캐시: {"code": {"price": ..., "change_pct": ...}}
KRX_PRICE_CACHE: dict = {}
_KRX_CACHE_UPDATED: float = 0.0
_KRX_REFRESH_SEC = 90   # 90초마다 갱신


def _refresh_krx_prices():
    """FDR StockListing으로 전종목 가격을 갱신해 KRX_PRICE_CACHE에 저장."""
    global _KRX_CACHE_UPDATED
    try:
        import FinanceDataReader as fdr
        df = fdr.StockListing("KRX")
        if df is None or df.empty:
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
        KRX_PRICE_CACHE.update(tmp)
        _KRX_CACHE_UPDATED = _time.time()
        print(f"[KRX cache] {len(tmp)}종목 갱신 완료")
    except Exception as e:
        print(f"[KRX cache] 갱신 실패: {e}")


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


# ── 9. 일일 알림 자동 발송 스케줄러 ──────────────────────────────────────────
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
