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
import time
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
    code:            str
    name:            str
    price_data:      dict
    investor_data:   list = []
    pattern_context: str | None = None   # 패턴 스크리너에서 호출 시 매칭 컨텍스트


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
    market_data:   dict = {}
    volume_rank:   list = []
    change_rank:   list = []
    hot_sectors:   list = []
    investor_rank: list = []


class BoxPatternRequest(BaseModel):
    ticker:     str
    name:       str
    price_data: dict
    market:     str = "KR"



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
        from ai_engine import _override_targets
        # 캐시 확인
        if use_cache:
            cached = await asyncio.to_thread(load_ai_cache, CACHE_KEY)
            if cached and "error" not in cached:
                # 캐시 데이터에도 타점 재계산 (구버전 캐시 호환)
                try:
                    await asyncio.to_thread(_override_targets, cached)
                except Exception:
                    pass
                yield _sse({"status": "done", "result": cached, "from_cache": True})
                return

        yield _sse({"status": "running", "message": "🔍 Google Search로 오늘의 매크로 이슈 분석 중... (최대 2분 소요)"})
        try:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(generate_market_scenarios),
                    timeout=130,
                )
            except asyncio.TimeoutError:
                yield _sse({"status": "error", "message": "AI 시나리오 분석 시간이 초과됐습니다 (130초). 잠시 후 다시 시도해주세요."})
                return
            if "error" not in result:
                await asyncio.to_thread(save_ai_cache, CACHE_KEY, result, 12)
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 시나리오 분석: 커스텀 이슈 ───────────────────────────────────────────────

def _extract_scenario_stocks(result: dict) -> list:
    """시나리오 결과 dict에서 등장한 모든 종목 평탄화."""
    stocks = []
    issues = result.get("issues") or [result]
    for issue in issues:
        for sc in issue.get("scenarios", []) or []:
            for group, role in [("rising_stocks", "수혜"), ("falling_stocks", "피해"), ("theme_stocks", "테마")]:
                for s in sc.get(group, []) or []:
                    ticker = str(s.get("ticker") or "").strip()
                    name = str(s.get("name") or ticker).strip()
                    if ticker and name:
                        stocks.append({"ticker": ticker, "name": name, "role": role})
    # 중복 제거 (티커 단위)
    seen = set()
    deduped = []
    for s in stocks:
        if s["ticker"] not in seen:
            seen.add(s["ticker"])
            deduped.append(s)
    return deduped


@router.post("/scenarios/custom")
async def custom_issue_scenario(req: CustomIssueRequest):
    """사용자 지정 이슈 키워드 A/B 시나리오 (SSE)."""
    from ai_engine import analyze_custom_issue
    from db import load_ai_cache, save_scenario_stocks

    async def _gen():
        # 이전 캐시 확인
        ci_key = f"ci_{req.keyword[:40]}"
        cached = await asyncio.to_thread(load_ai_cache, ci_key)
        if cached:
            res = cached.get("result", cached)
            # 캐시여도 저장은 한 번 더 (첫 등장만 기록되도록 DB에서 dedup)
            stocks = _extract_scenario_stocks(res)
            if stocks:
                await asyncio.to_thread(save_scenario_stocks, req.keyword, res.get("title", req.keyword), stocks)
            yield _sse({"status": "done", "result": res, "from_cache": True})
            return

        yield _sse({"status": "running", "message": f"🔍 [{req.keyword}] 이슈 분석 중..."})
        try:
            result = await asyncio.to_thread(analyze_custom_issue, req.keyword)
            stocks = _extract_scenario_stocks(result)
            if stocks:
                await asyncio.to_thread(save_scenario_stocks, req.keyword, result.get("title", req.keyword), stocks)
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
    """미국 종목 AI 수급·단타·중장기 분석 (SSE). 캐시 12시간 적용."""
    from ai_engine import generate_stock_report
    from db import load_ai_cache, save_ai_cache

    CACHE_KEY = f"sr_us_{req.ticker.upper()}"

    async def _gen():
        # 1차 캐시 로드
        cached = await asyncio.to_thread(load_ai_cache, CACHE_KEY)
        if cached:
            yield _sse({"status": "done", "result": cached, "from_cache": True})
            return

        yield _sse({"status": "running", "message": f"🔍 {req.ticker} 분석 중..."})
        try:
            result = await asyncio.to_thread(
                generate_stock_report,
                req.ticker,
                req.current_price,
                req.change_pct,
            )
            # 2차 캐시 저장 (파싱 실패/분석 오류 결과는 캐시하지 않아 일시적 오류가 12시간 고착되는 것 방지)
            if result and "error" not in result and result.get("rating") != "분석 오류":
                await asyncio.to_thread(save_ai_cache, CACHE_KEY, result, 12)
                
            # AI 가격 알림 자동 등록
            try:
                await asyncio.to_thread(
                    auto_register_ai_alerts,
                    "미국",
                    req.ticker,
                    result.get("name_kr", result.get("name", req.ticker)),
                    result.get("buy_target"),
                    result.get("sell_target"),
                    result.get("stop_loss")
                )
            except Exception:
                pass

            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 국내 종목 AI 분석 리포트 ─────────────────────────────────────────────────

@router.post("/kr-stock-report")
async def kr_stock_report(req: KrStockReportRequest):
    """국내 종목 AI 수급 분석 및 단타 타점 리포트 (SSE). 캐시 12시간 적용."""
    from ai_engine import generate_kr_stock_report
    from db import load_ai_cache, save_ai_cache

    CACHE_KEY = f"sr_kr_{req.code}"

    async def _gen():
        # 1차 캐시 로드
        cached = await asyncio.to_thread(load_ai_cache, CACHE_KEY)
        if cached:
            yield _sse({"status": "done", "result": cached, "from_cache": True})
            return

        yield _sse({"status": "running", "message": f"🔍 {req.name}({req.code}) 분석 중..."})
        try:
            result = await asyncio.to_thread(
                generate_kr_stock_report,
                req.code,
                req.name,
                req.price_data,
                req.investor_data,
                req.pattern_context,
            )
            # 2차 캐시 저장 (파싱 실패/분석 오류 결과는 캐시하지 않아 일시적 오류가 12시간 고착되는 것 방지)
            if result and "error" not in result and result.get("rating") != "분석 오류":
                await asyncio.to_thread(save_ai_cache, CACHE_KEY, result, 12)
                
            # AI 가격 알림 자동 등록
            try:
                await asyncio.to_thread(
                    auto_register_ai_alerts,
                    "국내",
                    req.code,
                    req.name,
                    result.get("buy_target"),
                    result.get("sell_target"),
                    result.get("stop_loss")
                )
            except Exception:
                pass

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
                yield _sse({"status": "running", "message": "📊 실시간 시장 데이터 병렬 수집 중..."})
                try:
                    from data_kr import (
                        get_kr_market_index, get_kr_volume_ranking,
                        get_kr_change_ranking, get_kr_frgn_inst_rank
                    )
                    from ai_engine import analyze_kr_hot_sectors  # 백그라운드 갱신용

                    # 시장 데이터 병렬 수집 (각 태스크에 개별 타임아웃 → KIS API 무응답 시 영구 대기 방지)
                    mkt_task   = asyncio.wait_for(asyncio.to_thread(get_kr_market_index),          timeout=20)
                    vol_task   = asyncio.wait_for(asyncio.to_thread(get_kr_volume_ranking),        timeout=20)
                    chg_j_task = asyncio.wait_for(asyncio.to_thread(get_kr_change_ranking, "J"),   timeout=20)
                    chg_q_task = asyncio.wait_for(asyncio.to_thread(get_kr_change_ranking, "Q"),   timeout=20)
                    mkt_res, vol_res, chg_j, chg_q = await asyncio.gather(
                        mkt_task, vol_task, chg_j_task, chg_q_task,
                        return_exceptions=True
                    )
                    mkt_data = mkt_res if isinstance(mkt_res, dict) else {}
                    vol_rank = vol_res if isinstance(vol_res, list) else []
                    chg_rank = (chg_j if isinstance(chg_j, list) else []) + (chg_q if isinstance(chg_q, list) else [])

                    # 핫 섹터: 캐시 즉시 확인 (블로킹 없음)
                    # 캐시 미스면 AI가 직접 구글 검색으로 핫 섹터를 파악하므로 생략해도 무방
                    from ai_engine import get_hot_sectors_nowait
                    hs_cached = await asyncio.to_thread(get_hot_sectors_nowait)
                    if hs_cached:
                        hot_secs = hs_cached.get("sectors", [])
                        yield _sse({"status": "running", "message": "✅ 핫 섹터 캐시 적중 — 수급 데이터 수집 중..."})
                    else:
                        # 캐시 없음 → 백그라운드에서 갱신 (다음 요청 때 활용)
                        asyncio.create_task(asyncio.to_thread(analyze_kr_hot_sectors))
                        yield _sse({"status": "running", "message": "⚡ 수급 데이터 수집 중 (핫 섹터는 AI가 직접 검색)..."})

                    # 수급 데이터 수집
                    inv_j_task = asyncio.wait_for(asyncio.to_thread(get_kr_frgn_inst_rank, "J", 30), timeout=25)
                    inv_q_task = asyncio.wait_for(asyncio.to_thread(get_kr_frgn_inst_rank, "Q", 30), timeout=25)
                    inv_j, inv_q = await asyncio.gather(inv_j_task, inv_q_task, return_exceptions=True)
                    inv_rank = (inv_j if isinstance(inv_j, list) else []) + (inv_q if isinstance(inv_q, list) else [])
                except Exception as e:
                    yield _sse({"status": "running", "message": f"⚠️ 데이터 수집 지연: {str(e)[:60]}"})

            t0_picks = time.monotonic()
            yield _sse({"status": "running", "message": "🤖 AI 타점 및 매매 전략 생성 중 (최대 3분)..."})
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        generate_realtime_picks,
                        mkt_data,
                        vol_rank,
                        chg_rank,
                        hot_secs or None,
                        inv_rank or None,
                    ),
                    timeout=240,
                )
            except asyncio.TimeoutError:
                yield _sse({"status": "error", "message": "AI 분석 시간이 초과됐습니다 (3분). 잠시 후 다시 시도해주세요."})
                return
            elapsed = time.monotonic() - t0_picks
            print(f"[KR-picks] generate_realtime_picks: {elapsed:.1f}s")
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── 미국 실시간 픽 (거래량+등락률 종합) ──────────────────────────────────────

@router.post("/realtime-picks-us")
async def realtime_picks_us(req: RealtimePicksRequest):
    """테마·수급 기반 미국 실시간 픽 3종목 (SSE)."""
    from ai_engine import generate_us_realtime_picks

    async def _gen():
        yield _sse({"status": "running", "message": "🇺🇸 US 실시간 시장 데이터 수집 중..."})
        try:
            mkt_data = req.market_data
            vol_rank = req.volume_rank
            chg_rank = req.change_rank

            if not mkt_data or not vol_rank:
                yield _sse({"status": "running", "message": "📊 미국 지수 데이터 수집 중..."})
                try:
                    from data import get_us_market_indices
                    indices = await asyncio.to_thread(get_us_market_indices)
                    mkt_data = {
                        "S&P500": indices.get("S&P 500", {}),
                        "NASDAQ": indices.get("NASDAQ",  {}),
                        "DOW":    indices.get("DOW",     {}),
                    }
                except Exception:
                    mkt_data = {}

                yield _sse({"status": "running", "message": "📈 US 종목 실시간 데이터 수집 중 (약 20초)..."})
                try:
                    import yfinance as yf
                    from sectors_us import US_SECTOR_MAP

                    # 섹터당 상위 2종목씩 수집 (~50개)
                    tickers: list[str] = []
                    for sector_stocks in US_SECTOR_MAP.values():
                        for sub_stocks in sector_stocks.values():
                            for s in sub_stocks[:2]:
                                if s["ticker"] not in tickers:
                                    tickers.append(s["ticker"])
                    tickers = tickers[:50]

                    # yfinance 배치 다운로드 (2일치로 등락률 계산)
                    def _batch_fetch():
                        return yf.download(
                            tickers, period="2d", interval="1d",
                            progress=False, auto_adjust=True
                        )

                    raw = await asyncio.to_thread(_batch_fetch)
                    stock_list: list[dict] = []

                    if not raw.empty:
                        close_df  = raw["Close"]
                        volume_df = raw["Volume"]
                        # 단일 티커면 Series → DataFrame 변환
                        if hasattr(close_df, "values") and close_df.ndim == 1:
                            close_df  = close_df.to_frame(name=tickers[0])
                            volume_df = volume_df.to_frame(name=tickers[0])

                        for t in tickers:
                            try:
                                closes = close_df[t].dropna()
                                vols   = volume_df[t].dropna()
                                if len(closes) < 2:
                                    continue
                                curr = float(closes.iloc[-1])
                                prev = float(closes.iloc[-2])
                                vol  = int(vols.iloc[-1]) if not vols.empty else 0
                                chg  = round((curr - prev) / prev * 100, 2) if prev > 0 else 0
                                stock_list.append({
                                    "티커":      t,
                                    "현재가($)": round(curr, 2),
                                    "등락률(%)": chg,
                                    "거래량":    vol,
                                })
                            except Exception:
                                continue

                    chg_rank = sorted(stock_list, key=lambda x: x["등락률(%)"], reverse=True)
                    vol_rank = sorted(stock_list, key=lambda x: x["거래량"],    reverse=True)
                except Exception as e:
                    yield _sse({"status": "running", "message": f"⚠️ 종목 데이터 수집 지연: {e}"})
                    vol_rank, chg_rank = [], []

            yield _sse({"status": "running", "message": "🤖 AI 미국 타점 분석 중 (약 30~50초)..."})
            result = await asyncio.to_thread(
                generate_us_realtime_picks,
                mkt_data,
                vol_rank,
                chg_rank,
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


# ── AI 매수가 추천 ─────────────────────────────────────────────────────────────

class RecommendEntryRequest(BaseModel):
    ticker: str
    name: str
    market: str
    current_price: float
    w52_high: float = None
    w52_low: float = None

@router.post("/recommend-entry")
async def recommend_entry(req: RecommendEntryRequest):
    """미매수 관심종목 매수가 추천 (SSE)"""
    from ai_engine import recommend_entry_price

    async def _gen():
        yield _sse({"status": "running", "message": f"🤖 {req.name} 최적 매수 타점 분석 중..."})
        try:
            result = await asyncio.to_thread(
                recommend_entry_price,
                req.ticker,
                req.name,
                req.market,
                req.current_price,
                req.w52_high,
                req.w52_low
            )
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


# ── AI 거래 사후 분석 (Postmortem) ──────────────────────────────────────────────

class PostmortemRequest(BaseModel):
    ticker: str
    name: str
    market: str
    buy_price: float
    sell_price: float
    buy_date: str
    sell_date: str
    profit_pct: float
    owner: str = "USER"

@router.post("/postmortem")
async def postmortem_analysis(req: PostmortemRequest):
    """특정 거래에 대한 AI 사후 분석 (SSE)"""
    from ai_engine import analyze_trade_postmortem

    async def _gen():
        yield _sse({"status": "running", "message": f"🤖 {req.name} 거래 복기(Postmortem) 분석 중..."})
        try:
            result = await asyncio.to_thread(
                analyze_trade_postmortem,
                req.ticker,
                req.name,
                req.market,
                req.buy_price,
                req.sell_price,
                req.buy_date,
                req.sell_date,
                req.profit_pct,
                req.owner
            )
            # 성공적으로 분석이 완료되면 DB의 학습포인트도 업데이트
            if result and result.get("learning_point") and result.get("learning_point") != "-":
                from db import update_trade_learning_point
                # 백그라운드 스레드에서 DB 업데이트
                await asyncio.to_thread(
                    update_trade_learning_point, 
                    req.ticker, 
                    req.sell_date, 
                    result["learning_point"]
                )

            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


import re

def parse_price_value(text: str) -> float | None:
    """텍스트 형태의 AI 추천 타점 정보에서 실수를 안전하게 추출하는 정교한 파서."""
    if not text or text == "-" or "실패" in text or "불가" in text or "관망" in text:
        return None
    # 숫자 패턴 추출 (쉼표 제거 후 점이 있는 소수도 처리)
    matches = re.findall(r'[0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?', text)
    if not matches:
        return None
    
    raw_num = matches[0].replace(",", "")
    try:
        return float(raw_num)
    except ValueError:
        return None


def auto_register_ai_alerts(market: str, ticker: str, name: str, buy_target: str, sell_target: str, stop_loss: str):
    """AI가 도출한 매수/목표/손절 가격 타점을 '알림설정' 탭에 자동으로 영속 등록합니다."""
    from db import save_price_alert
    
    buy_p = parse_price_value(buy_target)
    sell_p = parse_price_value(sell_target)
    stop_p = parse_price_value(stop_loss)
    
    # 각 유효 타점별 가격 저장
    if buy_p:
        save_price_alert(market, ticker, name, "AI매수가 도달", buy_p)
    if sell_p:
        save_price_alert(market, ticker, name, "AI목표가 도달", sell_p)
    if stop_p:
        save_price_alert(market, ticker, name, "AI손절가 도달", stop_p)


@router.post("/box-pattern")
async def box_pattern_analysis(req: BoxPatternRequest):
    """지지선/저항선 및 AI 박스권·수급 심층 분석 (SSE). 캐시 12시간 적용."""
    from ai_engine import analyze_box_pattern
    from db import load_ai_cache, save_ai_cache

    CACHE_KEY = f"box_{req.ticker.upper()}"

    async def _gen():
        # 1차 캐시 로드
        cached = await asyncio.to_thread(load_ai_cache, CACHE_KEY)
        if cached:
            yield _sse({"status": "done", "result": cached, "from_cache": True})
            return

        yield _sse({"status": "running", "message": "📦 차트 데이터 분석 및 세력 수급 추적 중..."})
        try:
            result = await asyncio.to_thread(
                analyze_box_pattern,
                req.ticker,
                req.name,
                req.price_data,
                req.market
            )
            # 2차 캐시 저장 (파싱 실패/분석 오류 결과는 캐시하지 않아 일시적 오류가 12시간 고착되는 것 방지)
            if result and "error" not in result and result.get("rating") != "분석 오류":
                await asyncio.to_thread(save_ai_cache, CACHE_KEY, result, 12)
                
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


class ShadowSectorRequest(BaseModel):
    ticker: str
    name: str
    market: str = "KR"
    force_update: bool = False


@router.post("/shadow-sector")
async def shadow_sector_analysis(req: ShadowSectorRequest):
    """실시간 AI 쉐도우 섹터 & 찌라시 팩트 체커 분석 (SSE). 캐시 12시간 적용."""
    from ai_engine import analyze_shadow_sector_catalyst
    from db import load_ai_cache, save_ai_cache

    CACHE_KEY = f"ss_{req.ticker.upper()}"

    async def _gen():
        # 1차: 캐시 로드 (force_update가 아닐 때만 적용)
        if not req.force_update:
            cached = await asyncio.to_thread(load_ai_cache, CACHE_KEY)
            if cached:
                yield _sse({"status": "done", "result": cached, "from_cache": True})
                return

        yield _sse({"status": "running", "message": "🔍 실시간 공시 및 밸류체인 추적 중..."})
        await asyncio.sleep(0.5)
        yield _sse({"status": "running", "message": "🤖 AI 팩트 교차 검증 및 신뢰 등급 분석 중..."})
        
        try:
            result = await asyncio.to_thread(
                analyze_shadow_sector_catalyst,
                req.ticker,
                req.name,
                req.market
            )
            # 2차: 캐시 저장
            if result and "error" not in result and result.get("shadow_sector") != "데이터 로드 실패":
                await asyncio.to_thread(save_ai_cache, CACHE_KEY, result, 12)
                
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


class ShadowDiscoverRequest(BaseModel):
    keyword: str


@router.post("/shadow-discover")
async def shadow_discover_analysis(req: ShadowDiscoverRequest):
    """실시간 AI 쉐도우 종목 발굴 즉석 탐색기 (SSE). 캐시 12시간 적용."""
    from ai_engine import discover_shadow_stocks
    from db import load_ai_cache, save_ai_cache
    import hashlib

    # 검색 키워드 해시 처리하여 캐시 키 생성
    keyword_hash = hashlib.md5(req.keyword.strip().lower().encode("utf-8")).hexdigest()
    CACHE_KEY = f"sd_{keyword_hash}"

    async def _gen():
        # 1차: 캐시 로드
        cached = await asyncio.to_thread(load_ai_cache, CACHE_KEY)
        if cached:
            yield _sse({"status": "done", "result": cached, "from_cache": True})
            return

        yield _sse({"status": "running", "message": "📡 실시간 구글 RAG 정보망 수집 중..."})
        await asyncio.sleep(0.5)
        yield _sse({"status": "running", "message": "🔍 숨겨진 지분 관계 및 자회사 얽힘 판독 중..."})
        await asyncio.sleep(0.5)
        yield _sse({"status": "running", "message": "🤖 AI 교차 검증 및 지분 족보 조립 중..."})

        try:
            result = await asyncio.to_thread(
                discover_shadow_stocks,
                req.keyword
            )
            # 2차: 캐시 저장
            if result and "error" not in result and len(result.get("stocks", [])) > 0:
                await asyncio.to_thread(save_ai_cache, CACHE_KEY, result, 12)

            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


class OvernightGapRequest(BaseModel):
    ticker: str
    name: str
    market: str = "KR"
    force_update: bool = False


@router.post("/overnight-gap")
async def overnight_gap_analysis(req: OvernightGapRequest):
    """실시간 AI 시간외 긴급 진단 & 익일 갭 예측 (SSE). 캐시 2시간 적용."""
    from ai_engine import analyze_overnight_gap_risk
    from db import load_ai_cache, save_ai_cache

    CACHE_KEY = f"gap_{req.ticker.upper()}"

    async def _gen():
        # 1차: 캐시 로드 (force_update가 아닐 때만 적용)
        if not req.force_update:
            cached = await asyncio.to_thread(load_ai_cache, CACHE_KEY)
            if cached:
                yield _sse({"status": "done", "result": cached, "from_cache": True})
                return

        yield _sse({"status": "running", "message": "🌙 시간외 돌발 공시 및 최신 뉴스망 탐색 중..."})
        await asyncio.sleep(0.5)
        yield _sse({"status": "running", "message": "📊 익일 시초가 갭상/갭하 영향력 연산 중..."})
        await asyncio.sleep(0.5)
        yield _sse({"status": "running", "message": "🤖 시간외 단일가 대응 행동 지침 수립 중..."})

        try:
            result = await asyncio.to_thread(
                analyze_overnight_gap_risk,
                req.ticker,
                req.name,
                req.market
            )
            # 2차: 캐시 저장
            if result and "error" not in result:
                await asyncio.to_thread(save_ai_cache, CACHE_KEY, result, 2) # 2시간 신선 캐시

            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


class OvernightGapBulkRequest(BaseModel):
    tickers: list[str]


@router.post("/overnight-gap-bulk")
async def overnight_gap_bulk_analysis(req: OvernightGapBulkRequest):
    """관심/보유 종목 일괄 갭 분석용 API. 캐시된 갭 정보가 있는 것들만 고속 반환합니다.
    사용자의 수동 '일괄 분석기 작동' 트리거 발생 시 캐시되지 않은 항목들도 큐에 태울 수 있습니다.
    """
    from db import load_ai_cache
    results = {}
    
    # 1. 캐시된 갭 정보 일괄 로드
    for t in req.tickers:
        t_upper = str(t).upper().strip()
        if not t_upper:
            continue
        cached = load_ai_cache(f"gap_{t_upper}")
        if cached:
            results[t_upper] = cached
            
    return {"status": "success", "results": results}


# ── 리딩방 패턴 AI 분석 ────────────────────────────────────────────────────────

@router.post("/pattern-screener")
async def pattern_screener():
    """내 거래 패턴 기반 오늘의 단기 추천 종목 (SSE)."""
    from ai_engine import screen_by_my_pattern

    async def _gen():
        yield _sse({"status": "running", "message": "📊 패턴 프로파일 로드 중..."})
        try:
            result = await asyncio.to_thread(screen_by_my_pattern)
            if "error" in result:
                yield _sse({"status": "error", "message": result["error"]})
            else:
                # 추천 결과 DB 저장 (피드백 루프용)
                if result.get("top_picks"):
                    from db import save_screener_picks
                    await asyncio.to_thread(save_screener_picks, result["top_picks"])
                yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


@router.get("/screener-feedback-stats")
async def get_screener_feedback_stats():
    """스크리너 피드백 통계 조회 — 추천 이력 + 리딩방 매칭/비매칭 성과."""
    from db import load_screener_feedback_stats
    stats = await asyncio.to_thread(load_screener_feedback_stats)
    return {"stats": stats}


@router.post("/screener-backtest/run")
async def run_screener_backtest():
    """패턴 스크리너 추천 종목의 +1/+3/+7일 사후 성과 백테스트 실행."""
    from ai_engine import backtest_screener_picks
    result = await asyncio.to_thread(backtest_screener_picks)
    return result


@router.get("/screener-backtest/stats")
async def get_screener_backtest_stats():
    """저장된 백테스트 통계 조회."""
    from db import load_backtest_stats
    stats = await asyncio.to_thread(load_backtest_stats)
    return stats


@router.get("/agent-daily-issues")
async def get_agent_daily_issues(days: int = 2):
    """에이전트가 자동 분석한 오늘의 핫이슈/심리 조회."""
    from db import load_agent_daily_issues
    issues = await asyncio.to_thread(load_agent_daily_issues, days)
    return {"issues": issues}


@router.get("/agent-scenarios")
async def get_agent_scenarios(days: int = 1):
    """에이전트가 자동 생성한 시나리오 조회 (시나리오 탭 표시용)."""
    from db import load_agent_scenarios
    scenarios = await asyncio.to_thread(load_agent_scenarios, days)
    return {"scenarios": scenarios}


@router.post("/agent-daily-issues/refresh")
async def refresh_agent_daily_issues():
    """오늘의 이슈 즉시 재분석 (수동 트리거)."""
    from ai_engine import analyze_agent_daily_issues
    return await asyncio.to_thread(analyze_agent_daily_issues)


@router.get("/agent-learning")
async def get_agent_learning():
    """AI 에이전트 자기학습 요약 — 조건별 승률 규칙 (다른 AI 기능 공용)."""
    from db import load_agent_learning_summary
    return await asyncio.to_thread(load_agent_learning_summary)


@router.post("/capital-rotation")
async def capital_rotation(ticker: str = ""):
    """보유 종목 자금 회전 분석 — 홀딩/차익실현/로테이션 판단 (SSE). ticker 지정 시 단일 종목."""
    from ai_engine import analyze_capital_rotation

    async def _gen():
        msg = f"💼 {ticker} 진단 중..." if ticker else "💼 보유 종목 지표 + 수급 데이터 분석 중..."
        yield _sse({"status": "running", "message": msg})
        try:
            result = await asyncio.to_thread(analyze_capital_rotation, "USER", ticker)
            if "error" in result:
                yield _sse({"status": "error", "message": result["error"]})
            else:
                yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


@router.post("/alert/send-daily")
async def send_daily_alert_now():
    """텔레그램 일일 알림 즉시 발송 (수동 트리거)."""
    from ai_engine import send_daily_alert
    return await asyncio.to_thread(send_daily_alert)


@router.get("/alert/preview-daily")
async def preview_daily_alert():
    """일일 알림 메시지 미리보기 (발송 안 함)."""
    from ai_engine import compose_daily_alert_message
    text, meta = await asyncio.to_thread(compose_daily_alert_message)
    return {"preview": text, "meta": meta}


@router.post("/scenario-tracking/run")
async def run_scenario_tracking():
    """시나리오 등장 종목의 사후 가격 추적 실행."""
    from ai_engine import track_scenario_stocks_performance
    return await asyncio.to_thread(track_scenario_stocks_performance)


@router.get("/scenario-tracking/stats")
async def get_scenario_tracking_stats():
    """시나리오 적중률 통계 조회 (최근 추적 결과)."""
    from ai_engine import track_scenario_stocks_performance
    return await asyncio.to_thread(track_scenario_stocks_performance)


@router.get("/entry-timing")
async def get_entry_timing(source: str = "leading", market: str = "kr"):
    """시간대별 진입 타이밍 통계 (source: leading/personal/all, market: kr/us)."""
    from ai_engine import analyze_entry_timing
    result = await asyncio.to_thread(analyze_entry_timing, source, market)
    return result


@router.post("/pattern-profile/build")
async def build_pattern_profile_endpoint():
    """패턴 프로파일(전체/개인/리딩방) + 수급 흐름 패턴을 즉시 재빌드합니다."""
    from ai_engine import build_pattern_profile, build_supply_flow_patterns
    try:
        profile_all      = await asyncio.to_thread(build_pattern_profile, 'all')
        profile_personal = await asyncio.to_thread(build_pattern_profile, 'personal')
        profile_leading  = await asyncio.to_thread(build_pattern_profile, 'leading')
        flow             = await asyncio.to_thread(build_supply_flow_patterns)
        if "error" in profile_all:
            return {"success": False, "message": profile_all["error"]}
        return {"success": True, "profile": profile_all,
                "personal_trades": profile_personal.get("total_trades"),
                "leading_trades":  profile_leading.get("total_trades"),
                "supply_flow_patterns": flow.get("total", 0)}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/supply-flow-patterns")
async def get_supply_flow_patterns():
    """리딩방 수급 이동 시퀀스 패턴 조회."""
    from db import load_supply_flow_patterns
    patterns = await asyncio.to_thread(load_supply_flow_patterns)
    return {"patterns": patterns, "total": len(patterns)}


@router.post("/supply-rotation-detect")
async def supply_rotation_detect():
    """실시간 수급 이동 감지 — 오늘 거래량·등락률·뉴스 종합 분석 (SSE)."""
    from ai_engine import detect_realtime_supply_rotation

    async def _gen():
        yield _sse({"status": "running", "message": "📡 실시간 시장 데이터 수집 중..."})
        try:
            result = await asyncio.to_thread(detect_realtime_supply_rotation)
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


@router.post("/supply-rotation-detect/us")
async def supply_rotation_detect_us():
    """미국 주식 수급 이동 감지 — yfinance institutional/insider/volume 기반 (SSE)."""
    from ai_engine import detect_us_supply_rotation

    async def _gen():
        yield _sse({"status": "running", "message": "📡 미국 종목 yfinance 데이터 수집 중..."})
        try:
            result = await asyncio.to_thread(detect_us_supply_rotation)
            yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())


@router.get("/pattern-profile")
async def get_pattern_profile():
    """저장된 패턴 프로파일 조회."""
    from db import load_pattern_profile
    profile = await asyncio.to_thread(load_pattern_profile)
    return {"profile": profile}


@router.post("/leading-room-patterns")
async def leading_room_patterns():
    """리딩방 거래 내역 기술적 패턴 AI 분석 (SSE)."""
    from ai_engine import analyze_leading_room_patterns

    async def _gen():
        yield _sse({"status": "running", "message": "📊 리딩방 거래 기록 및 지표 수집 중... (종목 수에 따라 30초~1분 소요)"})
        try:
            result = await asyncio.to_thread(analyze_leading_room_patterns)
            if "error" in result:
                yield _sse({"status": "error", "message": result["error"]})
            else:
                yield _sse({"status": "done", "result": result})
        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return _sse_response(_gen())





