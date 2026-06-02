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
    memo:        str = ""
    sector:      str = ""


class FavoriteMemoRequest(BaseModel):
    ticker: str
    memo:   str = ""


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

class UpdateTradeTagRequest(BaseModel):
    ticker:       str
    sell_date:    str
    trade_source: str
    trade_type:   str

class UpdateTradeBuyDateRequest(BaseModel):
    ticker:    str
    sell_date: str
    buy_date:  str   # "YYYY-MM-DD HH:MM" 또는 "YYYY-MM-DD"

class UpdatePortfolioBuyTimeRequest(BaseModel):
    ticker:   str
    buy_time: str    # "YYYY-MM-DD HH:MM" 또는 "YYYY-MM-DD"
    owner:    str = "USER"

class UpdateTradeBuyReasonRequest(BaseModel):
    ticker:     str
    sell_date:  str
    buy_reason: str


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


class TelegramConfigRequest(BaseModel):
    token:   str
    chat_id: str


# ── 즐겨찾기 ─────────────────────────────────────────────────────────────────

@router.get("/favorites")
async def list_favorites():
    from db import load_favorites
    records, msg = await asyncio.to_thread(load_favorites)
    return {"data": records or [], "message": msg}


@router.post("/favorites")
async def add_favorite(req: FavoriteRequest):
    from db import save_favorite
    ok, msg = await asyncio.to_thread(save_favorite, req.market_type, req.ticker, req.name, req.memo, req.sector)
    return {"success": ok, "message": msg}


@router.post("/favorites/memo")
async def update_favorite_memo(req: FavoriteMemoRequest):
    from db import update_favorite_memo
    ok, msg = await asyncio.to_thread(update_favorite_memo, req.ticker, req.memo)
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

@router.get("/portfolio/debug")
async def debug_portfolio():
    """포트폴리오 로드 디버그용 엔드포인트"""
    import traceback
    try:
        from db import _get_spreadsheet
        sh, msg = await asyncio.to_thread(_get_spreadsheet)
        if not sh:
            return {"error": f"스프레드시트 접근 실패: {msg}"}
        worksheets = await asyncio.to_thread(lambda: [ws.title for ws in sh.worksheets()])
        try:
            ws = sh.worksheet("현재포트폴리오")
            from db import safe_get_all_records
            records = await asyncio.to_thread(safe_get_all_records, ws)
            return {"worksheets": worksheets, "record_count": len(records), "sample": records[:2] if records else []}
        except Exception as e:
            return {"worksheets": worksheets, "error": str(e), "trace": traceback.format_exc()}
    except Exception as e:
        return {"fatal_error": str(e), "trace": traceback.format_exc()}


@router.get("/portfolio")
async def load_portfolio():
    from db import load_portfolio_from_gsheet
    data = await asyncio.to_thread(load_portfolio_from_gsheet)
    return data or []


@router.get("/portfolio/agent")
async def load_agent_portfolio():
    from db import load_portfolio_from_gsheet
    data = await asyncio.to_thread(load_portfolio_from_gsheet, owner="AI_AGENT")
    return data or []


@router.get("/portfolio/agent/scan-logs")
async def load_agent_scan_logs():
    from db import load_agent_scan_logs_from_gsheet
    data = await asyncio.to_thread(load_agent_scan_logs_from_gsheet)
    return data or []


@router.post("/portfolio/agent/scan-now")
async def run_agent_scan_now():
    """AI 에이전트 1회 스캔 즉시 실행 (30분 주기를 기다리지 않고 수동 점검).
    휴장이어도 force로 진행하여 즐겨찾기·보유종목을 분석하고 고민일지를 남긴다."""
    from api.agent import _run_one_scan
    try:
        summary = await asyncio.wait_for(asyncio.to_thread(_run_one_scan, True), timeout=300)
        return {"success": True, "summary": summary}
    except asyncio.TimeoutError:
        return {"success": False, "message": "스캔 시간 초과(5분). 잠시 후 다시 시도해주세요."}
    except Exception as e:
        return {"success": False, "message": str(e)}


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
    df, msg = await asyncio.to_thread(load_trade_history_from_gsheet, owner="USER")
    if df is None or (hasattr(df, "empty") and df.empty):
        return {"data": [], "message": msg}
    return {"data": df.to_dict(orient="records"), "message": msg}


@router.get("/trades/agent")
async def load_agent_trades():
    from db import load_trade_history_from_gsheet
    df, msg = await asyncio.to_thread(load_trade_history_from_gsheet, owner="AI_AGENT")
    if df is None or (hasattr(df, "empty") and df.empty):
        return {"data": [], "message": msg}
    return {"data": df.to_dict(orient="records"), "message": msg}


@router.post("/trades")
async def save_trade(req: TradeRecordRequest):
    from db import save_trade_record, match_screener_for_trade
    owner = str(req.trade.get("owner", "USER")).upper()
    ok, msg = await asyncio.to_thread(save_trade_record, req.trade, owner)
    is_leading = "리딩방" in str(req.trade.get("trade_source", ""))
    if ok and is_leading:
        sell_date = str(req.trade.get("sell_date", ""))[:10]
        await asyncio.to_thread(match_screener_for_trade, req.trade.get("ticker", ""), sell_date)
    return {"success": ok, "message": msg}


@router.patch("/trades")
async def update_trade_tag(req: UpdateTradeTagRequest):
    from db import update_trade_source_type
    ok, msg = await asyncio.to_thread(update_trade_source_type, req.ticker, req.sell_date, req.trade_source, req.trade_type)
    return {"success": ok, "message": msg}


@router.patch("/trades/buy-date")
async def update_trade_buy_date_ep(req: UpdateTradeBuyDateRequest):
    """거래내역의 매수 시각(buy_date) 수정 — 패턴 학습 정확도 보정용."""
    from db import update_trade_buy_date
    ok, msg = await asyncio.to_thread(update_trade_buy_date, req.ticker, req.sell_date, req.buy_date)
    return {"success": ok, "message": msg}


@router.patch("/portfolio/buy-time")
async def update_portfolio_buy_time_ep(req: UpdatePortfolioBuyTimeRequest):
    """보유종목의 매수 시각(updated_time) 수정."""
    from db import update_portfolio_buy_time
    ok, msg = await asyncio.to_thread(update_portfolio_buy_time, req.ticker, req.owner, req.buy_time)
    return {"success": ok, "message": msg}


@router.patch("/trades/buy-reason")
async def update_trade_buy_reason_ep(req: UpdateTradeBuyReasonRequest):
    """거래내역의 매수 근거(리딩방 추천 사유 등) 수정."""
    from db import update_trade_buy_reason
    ok, msg = await asyncio.to_thread(update_trade_buy_reason, req.ticker, req.sell_date, req.buy_reason)
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


@router.get("/telegram/config")
async def get_telegram_config():
    from db import load_telegram_config
    token, chat_id = await asyncio.to_thread(load_telegram_config)
    # 보안상 마스킹 처리
    masked_token = ""
    if token:
        parts = token.split(":")
        if len(parts) == 2:
            bot_id, secret = parts
            masked_secret = secret[:3] + "*" * (len(secret) - 6) + secret[-3:] if len(secret) > 6 else "******"
            masked_token = f"{bot_id}:{masked_secret}"
        else:
            masked_token = token[:5] + "*" * (len(token) - 8) + token[-3:] if len(token) > 8 else "******"
            
    masked_chat_id = ""
    if chat_id:
        masked_chat_id = chat_id[:3] + "*" * (len(chat_id) - 5) + chat_id[-2:] if len(chat_id) > 5 else "******"
        
    return {
        "token": token,
        "chat_id": chat_id,
        "masked_token": masked_token,
        "masked_chat_id": masked_chat_id
    }


@router.post("/telegram/config")
async def save_and_test_telegram(req: TelegramConfigRequest):
    from db import save_telegram_config
    # 1. 설정 저장
    ok, msg = await asyncio.to_thread(save_telegram_config, req.token, req.chat_id)
    if not ok:
        return {"success": False, "message": f"설정 저장 실패: {msg}"}
        
    # 2. 테스트 메시지 전송
    from telegram_bot import send_message
    test_text = (
        "🎉 <b>[스톡시 텔레그램 테스트]</b>\n"
        "텔레그램 연동 및 가격 알림 서비스가 성공적으로 활성화되었습니다! 🚀\n\n"
        "앞으로 AI 추천 타점 도달 및 개별 알림 조건 발생 시 실시간 푸시 알림이 발송됩니다."
    )
    send_ok = await asyncio.to_thread(send_message, test_text)
    if send_ok:
        return {"success": True, "message": "텔레그램 설정 저장 및 웰컴 테스트 메시지 발송에 성공했습니다. 폰을 확인해 보세요!"}
    else:
        return {"success": False, "message": "설정은 성공적으로 저장되었으나, 텔레그램 테스트 발송에 실패했습니다. 봇 토큰과 Chat ID가 정확한지 확인해 주세요."}
