"""관리자 기능 라우터 — 섹터DB 초기화, 텔레그램 브리핑 등."""
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()


# ── 섹터DB 초기화 ─────────────────────────────────────────────────────────────

@router.post("/init-sector-kr")
async def init_sector_kr():
    """sectors_kr.py 기본 데이터를 GSheet 섹터DB 탭에 업로드 (덮어쓰기)."""
    from db import init_sector_sheet
    ok, msg = await asyncio.to_thread(init_sector_sheet)
    return {"success": ok, "message": msg}


@router.post("/init-sector-us")
async def init_sector_us():
    """sectors_us.py 기본 데이터를 GSheet 섹터DB_US 탭에 업로드 (덮어쓰기)."""
    from db import init_us_sector_sheet
    ok, msg = await asyncio.to_thread(init_us_sector_sheet)
    return {"success": ok, "message": msg}


# ── 연결 테스트 ───────────────────────────────────────────────────────────────

@router.get("/test-connection")
async def test_connection():
    """GSheet 연결 테스트."""
    from db import test_connection_and_write
    ok, msg = await asyncio.to_thread(test_connection_and_write)
    return {"success": ok, "message": msg}


# ── 텔레그램 장 마감 브리핑 발송 ──────────────────────────────────────────────

class DailyBriefRequest(BaseModel):
    favorites: List[dict]


@router.post("/daily-brief/send")
async def send_daily_brief(req: DailyBriefRequest):
    """즐겨찾기 기반 AI 매크로 브리핑을 텔레그램으로 발송."""
    import json
    from fastapi.responses import StreamingResponse

    async def _gen():
        status_messages = []

        def _status_cb(msg: str):
            status_messages.append(msg)

        yield f"data: {json.dumps({'status': 'running', 'message': '브리핑 생성 시작...'})}\n\n"

        try:
            from daily_brief import send_daily_brief_to_telegram
            result = await asyncio.to_thread(
                send_daily_brief_to_telegram,
                req.favorites,
                _status_cb,
            )
            yield f"data: {json.dumps({'status': 'done', 'result': result, 'logs': status_messages})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
