"""
포트폴리오 / 즐겨찾기 / 거래내역 / 가격 알림 라우터
모든 데이터는 Google Sheets (db.py) 에 저장됩니다.
"""
import asyncio
from fastapi import APIRouter, Body
from pydantic import BaseModel
from typing import Any, List, Optional

router = APIRouter()


# ── Pydantic 모델 ─────────────────────────────────────────────────────────────

class FavoriteRequest(BaseModel):
    market_type: str   # "국내" | "미국"
    ticker:      str
    name:        str


class PortfolioSaveRequest(BaseModel):
    portfolio_list:  List[dict]
    current_prices:  Optional[Any] = None   # DataFrame JSON 또는 None


class AiPortfolioSaveRequest(BaseModel):
    portfolio_list: List[dict]


class TradeRecordRequest(BaseModel):
    trade: dict


class DeleteTradeRequest(BaseModel):
    ticker:    str
    sell_date: str


class AlertRequest(BaseModel):
    market:       str
    ticker:       str
    name:         str
    alert_type:   str   # "목표가 도달" | "손절가 도달" 등
    target_price: float


class DeleteAlertRequest(BaseModel):
    ticker:     str
    alert_type: str


class AiLogRequest(BaseModel):
    rec_type:    str
    ticker:      str
    name:        str
    rating:      str
    buy_target:  str
    sell_target: str
    stop_loss:   str


class TradeAnalysisSaveRequest(BaseModel):
    analysis: dict


class TradeAnalysisRecordRequest(BaseModel):
    trade_data:      dict
    analysis_result: dict


# ── 즐겨찾기 ─────────────────────────────────────────────────────────────────

@router.get("/favorites")
async def list_favorites():
    from db import load_favorites
    records, msg = await asyncio.to_thread(load_favorites)
    return {"data": records or [], "message": msg}


@router.post("/favorites")
async def add_favorite(req: FavoriteRequest):
    from db import save_favorite
    ok, msg = await asyncio.to_thread(save_favorite, req.market_type, req.ticker, req.name)
    return {"success": ok, "message": msg}


@router.delete("/favorites/{ticker}")
async def remove_favorite(ticker: str):
    from db import remove_favorite
    ok, msg = await asyncio.to_thread(remove_favorite, ticker)
    return {"success": ok, "message": msg}


@router.get("/favorites/{ticker}/check")
async def check_favorite(ticker: str):
    from db import is_favorite
    result = await asyncio.to_thread(is_favorite, ticker)
    return {"is_favorite": result}


# ── 포트폴리오 ────────────────────────────────────────────────────────────────

@router.get("/portfolio")
async def load_portfolio():
    from db import load_portfolio_from_gsheet
    data = await asyncio.to_thread(load_portfolio_from_gsheet)
    return data or []


@router.post("/portfolio")
async def save_portfolio(req: PortfolioSaveRequest):
    from db import save_portfolio_to_gsheet
    import pandas as pd
    prices_df = None
    if req.current_prices:
        try:
            prices_df = pd.DataFrame(req.current_prices)
        except Exception:
            prices_df = None
    ok, msg = await asyncio.to_thread(
        save_portfolio_to_gsheet, req.portfolio_list, prices_df
    )
    return {"success": ok, "message": msg}


@router.get("/portfolio/ai")
async def load_ai_portfolio():
    from db import load_ai_portfolio_from_gsheet
    data = await asyncio.to_thread(load_ai_portfolio_from_gsheet)
    return data or []


@router.post("/portfolio/ai")
async def save_ai_portfolio(req: AiPortfolioSaveRequest):
    from db import save_ai_portfolio_to_gsheet
    ok, msg = await asyncio.to_thread(save_ai_portfolio_to_gsheet, req.portfolio_list)
    return {"success": ok, "message": msg}


# ── 거래 내역 ─────────────────────────────────────────────────────────────────

@router.get("/trades")
async def load_trades():
    from db import load_trade_history_from_gsheet
    df, msg = await asyncio.to_thread(load_trade_history_from_gsheet)
    if df is None or (hasattr(df, "empty") and df.empty):
        return {"data": [], "message": msg}
    return {"data": df.to_dict(orient="records"), "message": msg}


@router.post("/trades")
async def save_trade(req: TradeRecordRequest):
    from db import save_trade_record
    ok, msg = await asyncio.to_thread(save_trade_record, req.trade)
    return {"success": ok, "message": msg}


@router.delete("/trades")
async def delete_trade(req: DeleteTradeRequest):
    from db import delete_trade_from_gsheet
    ok, msg = await asyncio.to_thread(delete_trade_from_gsheet, req.ticker, req.sell_date)
    return {"success": ok, "message": msg}


# ── AI 추천 로그 ──────────────────────────────────────────────────────────────

@router.post("/ai-log")
async def log_recommendation(req: AiLogRequest):
    from db import log_ai_recommendation
    ok, msg = await asyncio.to_thread(
        log_ai_recommendation,
        req.rec_type, req.ticker, req.name, req.rating,
        req.buy_target, req.sell_target, req.stop_loss,
    )
    return {"success": ok, "message": msg}


# ── 가격 알림 설정 ────────────────────────────────────────────────────────────

@router.get("/alerts")
async def load_alerts():
    from db import load_price_alerts
    data = await asyncio.to_thread(load_price_alerts)
    return data or []


@router.post("/alerts")
async def save_alert(req: AlertRequest):
    from db import save_price_alert
    ok, msg = await asyncio.to_thread(
        save_price_alert,
        req.market, req.ticker, req.name, req.alert_type, req.target_price,
    )
    return {"success": ok, "message": msg}


@router.delete("/alerts")
async def delete_alert(req: DeleteAlertRequest):
    from db import delete_price_alert
    ok, msg = await asyncio.to_thread(delete_price_alert, req.ticker, req.alert_type)
    return {"success": ok, "message": msg}


# ── 매매 분석 일지 ────────────────────────────────────────────────────────────

@router.post("/trade-analysis")
async def save_trade_analysis(req: TradeAnalysisSaveRequest):
    from db import save_trade_analysis
    ok, msg = await asyncio.to_thread(save_trade_analysis, req.analysis)
    return {"success": ok, "message": msg}


@router.get("/trade-analysis")
async def load_trade_analysis():
    from db import load_trade_analysis
    data, msg = await asyncio.to_thread(load_trade_analysis)
    return {"data": data, "message": msg}


@router.post("/trade-analysis/record")
async def save_trade_analysis_record(req: TradeAnalysisRecordRequest):
    from db import save_trade_analysis_record
    ok, msg = await asyncio.to_thread(
        save_trade_analysis_record, req.trade_data, req.analysis_result
    )
    return {"success": ok, "message": msg}


@router.get("/trade-analysis/records")
async def load_trade_analysis_records():
    from db import load_trade_analysis_records
    data, msg = await asyncio.to_thread(load_trade_analysis_records)
    return {"data": data or [], "message": msg}
