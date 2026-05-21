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

from api.routers import market_us, market_kr, ai, portfolio, admin

# ── 4. FastAPI 앱 생성 ───────────────────────────────────────────────────────
app = FastAPI(
    title="Stockcy API",
    version="1.0.0",
    description="Stockcy AI 트레이딩 대시보드 — FastAPI 백엔드",
)

# ── 5. CORS 설정 (Next.js 프론트와 통신) ─────────────────────────────────────
_allowed_origins = [
    "http://localhost:3000",   # Next.js dev
    "http://localhost:3001",
    os.environ.get("FRONTEND_URL", "http://localhost:3000"),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(_allowed_origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 6. 라우터 등록 ────────────────────────────────────────────────────────────
app.include_router(market_us.router,  prefix="/api/us",    tags=["미국 시장"])
app.include_router(market_kr.router,  prefix="/api/kr",    tags=["국내 시장"])
app.include_router(ai.router,         prefix="/api/ai",    tags=["AI 분석"])
app.include_router(portfolio.router,  prefix="/api",       tags=["포트폴리오·즐겨찾기"])
app.include_router(admin.router,      prefix="/api/admin", tags=["관리자"])

# ── 7. 헬스체크 ───────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["시스템"])
def health():
    return {"status": "ok", "app": "Stockcy API v1.0"}


@app.get("/api/config-status", tags=["시스템"])
def config_status():
    """각 외부 서비스 설정 여부를 확인합니다."""
    return {
        "gemini":   bool(os.environ.get("GEMINI_API_KEY")),
        "kis":      bool(os.environ.get("KIS_APP_KEY")),
        "gspread":  bool(os.environ.get("GSPREAD_CREDENTIALS")),
        "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
    }
