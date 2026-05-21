"""
AI 분석 라우터 — Gemini AI 엔진 연동.

장기 실행 작업(30~120초)은 Server-Sent Events(SSE)로 스트리밍합니다.
프론트엔드는 EventSource API 또는 fetch+ReadableStream으로 수신합니다.

SSE 이벤트 형식:
  data: {"status": "running", "message": "진행 메시지"}\n\n
  data: {"status": "done",    "result":  { ... }}\n\n
  data: {"status": "error",   "message": "오류 메시지"}\n\n
"""
import asyncio
import json
from fastapi import APIRouter, Body, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any

router = APIRouter()


# ── Pydantic 요청 모델 ────────────────────────────────────────────────────────

class StockReportRequest(BaseModel):
    ticker: str
    current_price: float
    change_pct: float


class KrStockReportRequest(BaseModel):
    code:          str
    name:          str
    price_data:    dict
    investor_data: list = []


class SellTimingRequest(BaseModel):
    ticker:        str
    name:          str
    avg_price:     float
    current_price: float
    market:        str = "KR"


class CustomIssueRequest(BaseModel):
    keyword: str


class ScenarioDetailRequest(BaseModel):
    issue_title:       str
    scenario_title:    str
    economic_analysis: str
    rising:            list = []
    falling:           list = []


class HotStockRequest(BaseModel):
    context: str = ""


class RealtimePicksRequest(BaseModel):
    market_data:   dict
    volume_rank:   list = []
    change_rank:   list = []
    hot_sectors:   list = []
    investor_rank: list = []


# ── SSE 유틸 ──────────────────────────────────────────────────────────────────

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _sse_stream(task_fn, *args, progress_msg: str = "AI 분석 중...", **kwargs):
    """
    blocking 함수를 별도 스레드에서 실행하고 SSE로 결과를 스트리밍합니다.
    """
    yield _sse({"status": "running", "message": progress_msg})
    try:
        result = await asyncio.to_thread(task_fn, *args, **kwargs)
        yield _sse({"status": "done", "result": result})
    except Exception as exc:
        yield _sse({"status": "error", "message": str(exc)})


def _sse_response(generator) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":      "keep-alive",
        },
    )


# ── AI 캐시 CRUD ─────────────────────────────────────────────────────────────

@router.get("/cache/{cache_key}")
def get_ai_cache(cache_key: str):
    from db import load_ai_cache
    data = load_ai_cache(cache_key)
    if data is None:
        return {"hit": False}
    return {"hit": True, "data": data}


@router.delete("/cache/{cache_key}")
def delete_cache(cache_key: str):
    from db import delete_ai_cache
    ok = delete_ai_cache(cache_key)
    return {"success": ok}


# ── 매크로 분석: 일간 주도 섹터 브리핑 (SSE) ──────────────────────────────────

@router.get("/daily-briefing")
async def daily_briefing():
    """Google Search Grounding 기반 주도 섹터 브리핑 (SSE)."""
    from ai_engine import generate_daily_briefing

    async def _gen():
        async for chunk in _sse_stream(
            generate_daily_briefing,
            progress_msg="🔍 Google Search 기반 주도 섹터 분석 중...",
        ):
            yield chunk

    return _sse_response(_gen())


# ── 매크로 분석: 마인드맵 ─────────────────────────────────────────────────────

@router.get("/mindmap")
async def mindmap():
    """급등/급락 인과관계 Mermaid 마인드맵 생성 (SSE)."""
    from ai_engine import generate_mindmap_data

    async def _gen():
        yield _sse({"status": "running", "message": "📊 마인드맵 생성 중..."})
        try:
            code = await asyncio.to_thread(generate_mindmap_data)
            yield _sse({"status": "done", "result": {"mermaid": code}})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 시나리오 분석: 오늘의 매크로 시나리오 ────────────────────────────────────

@router.get("/scenarios")
async def market_scenarios(use_cache: bool = Query(True)):
    """6대 매크로 이슈 A/B 시나리오 분석 (SSE). GSheet 캐시 우선 사용."""
    from ai_engine import generate_market_scenarios
    from db import load_ai_cache, save_ai_cache

    CACHE_KEY = "market_scenarios_latest"

    async def _gen():
        # 캐시 확인
        if use_cache:
            cached = await asyncio.to_thread(load_ai_cache, CACHE_KEY)
            if cached and "error" not in cached:
                yield _sse({"status": "done", "result": cached, "from_cache": True})
                return

        yield _sse({"status": "running", "message": "🔍 Google Search로 오늘의 매크로 이슈 분석 중... (최대 2분 소요)"})
        try:
            result = await asyncio.to_thread(generate_market_scenarios)
            if "error" not in result:
                await asyncio.to_thread(save_ai_cache, CACHE_KEY, result, 12)
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 시나리오 분석: 커스텀 이슈 ───────────────────────────────────────────────

@router.post("/scenarios/custom")
async def custom_issue_scenario(req: CustomIssueRequest):
    """사용자 지정 이슈 키워드 A/B 시나리오 (SSE)."""
    from ai_engine import analyze_custom_issue
    from db import load_ai_cache

    async def _gen():
        # 이전 캐시 확인
        ci_key = f"ci_{req.keyword[:40]}"
        cached = await asyncio.to_thread(load_ai_cache, ci_key)
        if cached:
            yield _sse({"status": "done", "result": cached.get("result", cached), "from_cache": True})
            return

        yield _sse({"status": "running", "message": f"🔍 [{req.keyword}] 이슈 분석 중..."})
        try:
            result = await asyncio.to_thread(analyze_custom_issue, req.keyword)
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 시나리오 심층 분석 ────────────────────────────────────────────────────────

@router.post("/scenarios/detail")
async def scenario_detail(req: ScenarioDetailRequest):
    """특정 시나리오 심층 분석 (SSE)."""
    from ai_engine import generate_scenario_detail

    async def _gen():
        yield _sse({"status": "running", "message": "🔎 심층 분석 중... (최대 2분 소요)"})
        try:
            result = await asyncio.to_thread(
                generate_scenario_detail,
                req.issue_title,
                req.scenario_title,
                req.economic_analysis,
                req.rising,
                req.falling,
            )
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 미국 종목 AI 분석 리포트 ─────────────────────────────────────────────────

@router.post("/stock-report")
async def us_stock_report(req: StockReportRequest):
    """미국 종목 AI 수급·단타·중장기 분석 (SSE)."""
    from ai_engine import generate_stock_report

    async def _gen():
        yield _sse({"status": "running", "message": f"🔍 {req.ticker} 분석 중..."})
        try:
            result = await asyncio.to_thread(
                generate_stock_report,
                req.ticker,
                req.current_price,
                req.change_pct,
            )
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 국내 종목 AI 분석 리포트 ─────────────────────────────────────────────────

@router.post("/kr-stock-report")
async def kr_stock_report(req: KrStockReportRequest):
    """국내 종목 AI 수급 분석 및 단타 타점 리포트 (SSE)."""
    from ai_engine import generate_kr_stock_report

    async def _gen():
        yield _sse({"status": "running", "message": f"🔍 {req.name}({req.code}) 분석 중..."})
        try:
            result = await asyncio.to_thread(
                generate_kr_stock_report,
                req.code,
                req.name,
                req.price_data,
                req.investor_data,
            )
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 매도 타이밍 분석 ─────────────────────────────────────────────────────────

@router.post("/sell-timing")
async def sell_timing(req: SellTimingRequest):
    """보유 종목 AI 매도 타이밍 분석 (SSE)."""
    from ai_engine import analyze_sell_timing

    async def _gen():
        yield _sse({"status": "running", "message": f"📈 {req.name} 매도 타이밍 분석 중..."})
        try:
            result = await asyncio.to_thread(
                analyze_sell_timing,
                req.ticker,
                req.name,
                req.avg_price,
                req.current_price,
                req.market,
            )
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 미국 단타 핫 종목 발굴 ────────────────────────────────────────────────────

@router.post("/hot-stock-us")
async def hot_stock_us(req: HotStockRequest):
    """Google Search 기반 오늘의 미국 단타 유망 종목 발굴 (SSE)."""
    from ai_engine import discover_hot_day_trading_stock

    async def _gen():
        yield _sse({"status": "running", "message": "🚀 오늘의 미국 단타 유망주 발굴 중..."})
        try:
            result = await asyncio.to_thread(
                discover_hot_day_trading_stock, req.context
            )
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 국내 실시간 픽 (거래량+등락률+테마 종합) ─────────────────────────────────

@router.post("/realtime-picks-kr")
async def realtime_picks_kr(req: RealtimePicksRequest):
    """테마·수급·기술 시그널 종합 AI 국내 픽 3종목 (SSE)."""
    from ai_engine import generate_realtime_picks

    async def _gen():
        yield _sse({"status": "running", "message": "🔥 국내 실시간 AI 픽 분석 중..."})
        try:
            mkt_data = req.market_data
            vol_rank = req.volume_rank
            chg_rank = req.change_rank
            hot_secs = req.hot_sectors
            inv_rank = req.investor_rank

            # 클라이언트가 빈 데이터만 보낸 경우 백엔드에서 직접 수집
            if not mkt_data or not vol_rank:
                yield _sse({"status": "running", "message": "📊 실시간 시장 데이터 수집 중..."})
                try:
                    from data_kr import (
                        get_kr_market_index, get_kr_volume_ranking,
                        get_kr_change_ranking, get_kr_frgn_inst_rank
                    )
                    from ai_engine import analyze_kr_hot_sectors
                    mkt_data = await asyncio.to_thread(get_kr_market_index) or {}
                    vol_rank = await asyncio.to_thread(get_kr_volume_ranking) or []
                    
                    chg_j = await asyncio.to_thread(get_kr_change_ranking, "J") or []
                    chg_q = await asyncio.to_thread(get_kr_change_ranking, "Q") or []
                    chg_rank = chg_j + chg_q
                    
                    yield _sse({"status": "running", "message": "🔥 핫 섹터 발굴 및 수급 분석 중..."})
                    try:
                        hs_res = await asyncio.to_thread(analyze_kr_hot_sectors)
                        if isinstance(hs_res, dict):
                            hot_secs = hs_res.get("sectors", [])
                    except Exception: pass
                    
                    try:
                        inv_j = await asyncio.to_thread(get_kr_frgn_inst_rank, "J", 30) or []
                        inv_q = await asyncio.to_thread(get_kr_frgn_inst_rank, "Q", 30) or []
                        inv_rank = inv_j + inv_q
                    except Exception: pass
                except Exception as e:
                    yield _sse({"status": "running", "message": f"⚠️ 데이터 수집 지연: {str(e)}"})

            yield _sse({"status": "running", "message": "🤖 AI 타점 및 매매 전략 생성 중 (약 30~50초)..."})
            result = await asyncio.to_thread(
                generate_realtime_picks,
                mkt_data,
                vol_rank,
                chg_rank,
                hot_secs or None,
                inv_rank or None,
            )
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 섹터 로테이션 분석 ────────────────────────────────────────────────────────

@router.get("/sector-rotation")
async def sector_rotation():
    """국내 핫 섹터 탐지 및 대장주 분석 (SSE). 시장 데이터를 자동 수집합니다."""
    from ai_engine import analyze_sector_rotation

    async def _gen():
        yield _sse({"status": "running", "message": "📊 시장 데이터 수집 중..."})
        try:
            try:
                from data_kr import (
                    get_kr_market_index, get_kr_volume_ranking,
                    get_kr_change_ranking, get_kr_frgn_inst_rank,
                )
                indices = await asyncio.to_thread(get_kr_market_index)
                kospi  = indices.get("KOSPI", {})
                kosdaq = indices.get("KOSDAQ", {})
                vol_r  = await asyncio.to_thread(get_kr_volume_ranking)          # 인자 없음
                chg_r  = await asyncio.to_thread(get_kr_change_ranking, "J")     # J=KOSPI
                inv_r  = await asyncio.to_thread(get_kr_frgn_inst_rank, "J")
                raw = (
                    f"KOSPI: {kospi}\nKOSDAQ: {kosdaq}\n"
                    f"거래량 상위: {(vol_r or [])[:10]}\n"
                    f"등락률 상위: {(chg_r or [])[:10]}\n"
                    f"외국인·기관 수급: {(inv_r or [])[:10]}"
                )
            except Exception:
                raw = "실시간 데이터 조회 실패 — 구글 검색으로 보완하여 분석"
            yield _sse({"status": "running", "message": "📊 섹터 로테이션 분석 중... (1~2분 소요)"})
            result = await asyncio.to_thread(analyze_sector_rotation, "국내 주식", raw)
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 종목 분석 이력 저장 ───────────────────────────────────────────────────────

class AnalysisHistoryRequest(BaseModel):
    market:        str
    ticker:        str
    name:          str
    current_price: Any = None
    analysis:      dict


@router.post("/analysis-history")
async def save_analysis_history(req: AnalysisHistoryRequest):
    """종목 AI 분석 결과를 GSheet 이력에 저장."""
    from db import save_stock_analysis_history
    ok = await asyncio.to_thread(
        save_stock_analysis_history,
        req.market, req.ticker, req.name, req.current_price, req.analysis,
    )
    return {"success": ok}


@router.get("/analysis-history/{ticker}")
async def load_analysis_history(ticker: str, limit: int = Query(10)):
    """종목 분석 이력 조회."""
    from db import load_stock_analysis_history
    records = await asyncio.to_thread(load_stock_analysis_history, ticker, limit)
    return records or []
