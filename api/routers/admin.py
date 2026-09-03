"""관리자 기능 라우터 — 섹터DB 초기화, 텔레그램 브리핑 등."""
import asyncio
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List

from api.auth import require_admin, get_current_user

router = APIRouter()


# ── 앱 버전 ──────────────────────────────────────────────────────────────────

@router.get("/version")
async def get_version():
    from version import APP_VERSION
    return {"version": APP_VERSION}


@router.get("/cache-status")
async def get_cache_status(_admin: dict = Depends(require_admin)):
    """KRX 가격 캐시 상태 확인."""
    try:
        from api.main import KRX_PRICE_CACHE, _KRX_CACHE_UPDATED
        import time
        return {
            "cached_stocks": len(KRX_PRICE_CACHE),
            "last_updated_sec_ago": round(time.time() - _KRX_CACHE_UPDATED, 1) if _KRX_CACHE_UPDATED else None,
            "sample": {k: v for k, v in list(KRX_PRICE_CACHE.items())[:3]} if KRX_PRICE_CACHE else {}
        }
    except Exception as e:
        return {"error": str(e)}


# ── 섹터DB 초기화 ─────────────────────────────────────────────────────────────

@router.post("/init-sector-kr")
async def init_sector_kr(_admin: dict = Depends(require_admin)):
    """sectors_kr.py 기본 데이터를 GSheet 섹터DB 탭에 업로드 (덮어쓰기)."""
    from db import init_sector_sheet
    ok, msg = await asyncio.to_thread(init_sector_sheet)
    return {"success": ok, "message": msg}


@router.post("/init-sector-us")
async def init_sector_us(_admin: dict = Depends(require_admin)):
    """sectors_us.py 기본 데이터를 GSheet 섹터DB_US 탭에 업로드 (덮어쓰기)."""
    from db import init_us_sector_sheet
    ok, msg = await asyncio.to_thread(init_us_sector_sheet)
    return {"success": ok, "message": msg}


# ── 연결 테스트 ───────────────────────────────────────────────────────────────

@router.get("/test-connection")
async def test_connection(_admin: dict = Depends(require_admin)):
    """GSheet 연결 테스트."""
    from db import test_connection_and_write
    ok, msg = await asyncio.to_thread(test_connection_and_write)
    return {"success": ok, "message": msg}


# ── 텔레그램 장 마감 브리핑 발송 ──────────────────────────────────────────────

class DailyBriefRequest(BaseModel):
    favorites: List[dict]


@router.post("/daily-brief/send")
async def send_daily_brief(req: DailyBriefRequest, _user: dict = Depends(get_current_user)):
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


# ── AI 사용량 통계 & 프로바이더 설정 ──────────────────────────────────────────

@router.get("/ai-stats")
async def get_ai_stats(days: int = 7, _admin: dict = Depends(require_admin)):
    """ai_usage.jsonl 기반 프로바이더별 토큰/비용/속도 통계 반환."""
    import json, os
    from datetime import datetime, timedelta
    from collections import defaultdict

    log_path = os.path.join("data_csv", "ai_usage.jsonl")
    if not os.path.exists(log_path):
        return {"error": "로그 파일 없음", "records": 0}

    cutoff = datetime.now() - timedelta(days=days)
    stats = defaultdict(lambda: {
        "calls": 0, "total_tokens": 0, "in_tokens": 0, "out_tokens": 0,
        "cost_usd": 0.0, "latency_sum": 0.0, "latency_count": 0,
        "search_calls": 0, "models": defaultdict(int)
    })
    total_records = 0

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    # _log_llm_usage가 "%Y-%m-%d %H:%M:%S"(초 포함)로 기록하는데 여기서
                    # 초 없는 포맷으로 파싱하면 매 줄이 ValueError로 스킵되어 항상 0건으로
                    # 보이는 버그가 있었음 — 실제 기록 포맷에 맞춤.
                    ts = datetime.strptime(rec["ts"], "%Y-%m-%d %H:%M:%S")
                    if ts < cutoff:
                        continue
                    total_records += 1
                    p = rec.get("provider", "unknown")
                    s = stats[p]
                    s["calls"] += 1
                    s["total_tokens"] += rec.get("total", 0)
                    s["in_tokens"] += rec.get("in", 0)
                    s["out_tokens"] += rec.get("out", 0)
                    s["cost_usd"] += rec.get("cost_usd", 0.0)
                    lat = rec.get("latency_sec", 0.0)
                    if lat and lat > 0:
                        s["latency_sum"] += lat
                        s["latency_count"] += 1
                    if rec.get("search"):
                        s["search_calls"] += 1
                    mdl = rec.get("model", "unknown")
                    s["models"][mdl] += 1
                except Exception:
                    continue
    except Exception as e:
        return {"error": str(e)}

    result = {}
    for provider, s in stats.items():
        avg_lat = round(s["latency_sum"] / s["latency_count"], 3) if s["latency_count"] else None
        avg_cost = round(s["cost_usd"] / s["calls"] * 1000, 4) if s["calls"] else 0  # 밀리달러
        result[provider] = {
            "calls": s["calls"],
            "total_tokens": s["total_tokens"],
            "in_tokens": s["in_tokens"],
            "out_tokens": s["out_tokens"],
            "cost_usd_total": round(s["cost_usd"], 6),
            "cost_krw_total": round(s["cost_usd"] * 1380, 1),
            "avg_cost_per_call_usd": round(s["cost_usd"] / s["calls"], 6) if s["calls"] else 0,
            "avg_latency_sec": avg_lat,
            "search_calls": s["search_calls"],
            "models": dict(s["models"]),
        }

    # 현재 프로바이더 설정
    import os as _os
    current_provider = _os.environ.get("AI_PROVIDER", "gemini")
    current_model_openai = _os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    return {
        "period_days": days,
        "total_records": total_records,
        "current_provider": current_provider,
        "current_openai_model": current_model_openai,
        "stats": result,
    }


@router.get("/ai-provider")
async def get_ai_provider(_admin: dict = Depends(require_admin)):
    """현재 AI 프로바이더 설정 확인."""
    import os
    return {
        "provider": os.environ.get("AI_PROVIDER", "gemini"),
        "openai_model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "gemini_key_set": bool(os.environ.get("GEMINI_API_KEY")),
        "openai_key_set": bool(os.environ.get("OPENAI_API_KEY")),
    }


class ProviderSwitchRequest(BaseModel):
    provider: str   # "openai" | "gemini" | "benchmark"
    openai_model: str = ""  # "gpt-4o-mini" | "gpt-4o" | ""


@router.post("/ai-provider/switch")
async def switch_ai_provider(req: ProviderSwitchRequest, _admin: dict = Depends(require_admin)):
    """런타임에 AI 프로바이더를 전환 (재시작 없이 즉시 적용)."""
    import os
    valid = {"openai", "gemini", "benchmark"}
    if req.provider not in valid:
        return {"success": False, "error": f"유효하지 않은 provider: {req.provider}. 허용값: {valid}"}

    os.environ["AI_PROVIDER"] = req.provider
    if req.openai_model:
        os.environ["OPENAI_MODEL"] = req.openai_model

    return {
        "success": True,
        "provider": os.environ["AI_PROVIDER"],
        "openai_model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "message": f"AI 프로바이더가 '{req.provider}'로 즉시 전환되었습니다.",
    }


@router.post("/ai-benchmark/run")
async def run_ai_benchmark(_admin: dict = Depends(require_admin)):
    """OpenAI vs Gemini 단발 벤치마크 — recommend_entry_price 함수로 성능 비교."""
    import os, time, asyncio
    from ai_engine import recommend_entry_price

    # 원래 프로바이더는 루프 시작 "전"에 잡아둬야 한다 — 루프 안에서 매번
    # os.environ["AI_PROVIDER"]를 덮어쓰므로, 끝난 뒤에 읽으면 마지막으로 시도한
    # provider("gemini")가 "원래 값"인 것처럼 오인되어 벤치마크를 한 번 돌릴
    # 때마다 운영 중인 프로바이더가 gemini로 영구히 바뀌어버리는 버그가 있었음.
    original = os.environ.get("AI_PROVIDER", "gemini")

    results = {}
    for provider in ("openai", "gemini"):
        os.environ["AI_PROVIDER"] = provider
        t0 = time.perf_counter()
        try:
            res = await asyncio.to_thread(
                recommend_entry_price,
                "005930", "삼성전자", "국내", 74500, 88800, 58000
            )
            elapsed = round(time.perf_counter() - t0, 3)
            results[provider] = {
                "status": "ok",
                "result": res,
                "latency_sec": elapsed,
            }
        except Exception as e:
            results[provider] = {"status": "error", "error": str(e)}

    # 원래 프로바이더 복원
    os.environ["AI_PROVIDER"] = original

    return {
        "benchmark_target": "recommend_entry_price(삼성전자, 74500원)",
        "results": results,
    }
