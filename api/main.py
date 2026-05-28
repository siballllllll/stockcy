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
