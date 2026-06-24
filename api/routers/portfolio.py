"""
포트폴리오 / 즐겨찾기 / 거래내역 / 가격 알림 라우터
모든 데이터는 로컬 SQLite(db.py) + Google Sheets 백업에 저장됩니다.

[Phase 1c] 멀티유저: 모든 엔드포인트는 로그인 필수이며, owner 는 클라이언트가 아닌
로그인 세션(current_user)에서 강제로 결정된다. 클라이언트가 보내는 owner 값은 무시한다.
※ favorites / price_alerts / trade_analysis 테이블은 아직 owner 컬럼이 없어 전역 공유 상태이며,
  유저별 격리는 Phase 3(스키마 마이그레이션)에서 처리한다. 여기서는 로그인만 요구한다.
"""
import asyncio
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from typing import Any, List, Optional

from api.auth import get_current_user, require_admin

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
    owner:    str = "USER"   # (무시됨 — owner 는 세션에서 결정. 하위호환용 필드)

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


class CustomScenarioSaveRequest(BaseModel):
    keyword:     str
    title:       str = ""
    payload:     dict          # 시나리오 전체(이슈 객체)
    searched_at: str = ""


class RecentSearchRequest(BaseModel):
    keyword: str


# ── 즐겨찾기 (전역 공유 — Phase 3에서 유저별 격리 예정) ───────────────────────

@router.get("/favorites")
async def list_favorites(user: dict = Depends(get_current_user)):
    from db import load_favorites
    records, msg = await asyncio.to_thread(load_favorites, user["username"])
    return {"data": records or [], "message": msg}


@router.post("/favorites")
async def add_favorite(req: FavoriteRequest, user: dict = Depends(get_current_user)):
    from db import save_favorite
    ok, msg = await asyncio.to_thread(save_favorite, req.market_type, req.ticker, req.name, req.memo, req.sector, user["username"])
    return {"success": ok, "message": msg}


@router.post("/favorites/memo")
async def update_favorite_memo(req: FavoriteMemoRequest, user: dict = Depends(get_current_user)):
    from db import update_favorite_memo
    ok, msg = await asyncio.to_thread(update_favorite_memo, req.ticker, req.memo, user["username"])
    return {"success": ok, "message": msg}


@router.delete("/favorites/{ticker}")
async def remove_favorite(ticker: str, user: dict = Depends(get_current_user)):
    from db import remove_favorite
    ok, msg = await asyncio.to_thread(remove_favorite, ticker, user["username"])
    return {"success": ok, "message": msg}


@router.get("/favorites/{ticker}/check")
async def check_favorite(ticker: str, user: dict = Depends(get_current_user)):
    from db import is_favorite
    result = await asyncio.to_thread(is_favorite, ticker, user["username"])
    return {"is_favorite": result}


# ── 포트폴리오 ────────────────────────────────────────────────────────────────

@router.get("/portfolio/debug")
async def debug_portfolio(user: dict = Depends(get_current_user)):
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
async def load_portfolio(user: dict = Depends(get_current_user)):
    from db import load_portfolio_from_gsheet
    data = await asyncio.to_thread(load_portfolio_from_gsheet, owner=user["username"])
    return data or []


@router.get("/portfolio/agent")
async def load_agent_portfolio(user: dict = Depends(get_current_user)):
    from db import load_portfolio_from_gsheet
    data = await asyncio.to_thread(load_portfolio_from_gsheet, owner="AI_AGENT")
    return data or []


@router.get("/portfolio/agent/balance")
async def load_agent_balance(user: dict = Depends(get_current_user)):
    """AI 에이전트의 현금 잔액(예수금) 반환. 초기 시드 1천만원."""
    from db import load_virtual_balances
    balances = await asyncio.to_thread(load_virtual_balances)
    return {"cash": float(balances.get("AI", 10000000.0)), "seed": 10000000.0}


@router.get("/portfolio/agent/scan-logs")
async def load_agent_scan_logs(user: dict = Depends(get_current_user)):
    from db import load_agent_scan_logs_from_gsheet
    data = await asyncio.to_thread(load_agent_scan_logs_from_gsheet)
    return data or []


@router.post("/portfolio/agent/scan-now")
async def run_agent_scan_now(user: dict = Depends(get_current_user)):
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


@router.get("/prices/toss-bulk")
async def toss_prices_bulk(symbols: str, user: dict = Depends(get_current_user)):
    """토스 통합 현재가(국내+미국 한 번에). {symbol: price} 반환.

    D단계: 평가용 현재가 소스. 토스 prices는 lastPrice만 주므로(등락률 없음)
    평가금액 계산에 사용하고, 등락률/세부 표시는 기존 소스를 유지한다.
    """
    import toss_api
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    if not syms:
        return {}
    return await asyncio.to_thread(toss_api.get_prices, syms)


@router.get("/stocks/orderbook")
async def stock_orderbook(symbol: str, user: dict = Depends(get_current_user)):
    """토스 호가창. {asks:[{price,volume}], bids:[...], currency}."""
    import toss_api
    return await asyncio.to_thread(toss_api.get_orderbook, symbol)


@router.get("/stocks/trades")
async def stock_trades(symbol: str, count: int = 30, user: dict = Depends(get_current_user)):
    """토스 최근 체결 내역. [{price, volume, timestamp}] (최신순, 최대 50)."""
    import toss_api
    return await asyncio.to_thread(toss_api.get_trades, symbol, count)


@router.get("/stocks/price-limits")
async def stock_price_limits(symbol: str, user: dict = Depends(get_current_user)):
    """토스 상/하한가. {upper, lower, currency} (미국은 None)."""
    import toss_api
    return await asyncio.to_thread(toss_api.get_price_limits, symbol)


@router.get("/stocks/master")
async def stock_master(symbols: str, user: dict = Depends(get_current_user)):
    """토스 종목 마스터. {symbol: {name, english_name, market, security_type, status, list_date, delist_date, shares}}."""
    import toss_api
    syms = [s.strip() for s in symbols.split(",") if s.strip()][:200]
    if not syms:
        return {}
    return await asyncio.to_thread(toss_api.get_stock_master, syms)


@router.get("/market/calendar")
async def market_calendar(market: str = "KR", user: dict = Depends(get_current_user)):
    """토스 장 운영 정보. {date, is_open, next_business_day, prev_business_day}."""
    import toss_api
    return await asyncio.to_thread(toss_api.get_market_calendar, market)


@router.get("/stocks/warnings")
async def stock_warnings(symbols: str, user: dict = Depends(get_current_user)):
    """토스 종목 경고정보 벌크. {symbol: [{type,type_kr,severe,start,end}]} (경고 있는 종목만).

    경고 API는 종목당 1콜이라 보유종목·후보 등 소수 심볼에만 사용한다.
    """
    import toss_api
    syms = [s.strip() for s in symbols.split(",") if s.strip()][:40]   # 과다 호출 방지 상한
    if not syms:
        return {}
    return await asyncio.to_thread(toss_api.get_warning_flags, syms)


@router.get("/portfolio/toss/holdings")
async def load_toss_holdings(_admin: dict = Depends(require_admin)):
    """토스증권 실계좌 보유종목 조회 (관리자 전용).

    ⚠️ 토스 API 키(.env)는 관리자 본인 계좌 1개에 묶이므로 require_admin 게이트 필수.
    일반유저는 접근 불가 — 본인 잔고는 기존처럼 수동 입력한다.
    """
    import toss_api
    holdings = await asyncio.to_thread(toss_api.get_holdings)
    accounts = await asyncio.to_thread(toss_api.get_accounts)
    connected = bool(accounts)
    return {"connected": connected, "holdings": holdings}


@router.post("/portfolio")
async def save_portfolio(req: PortfolioSaveRequest, user: dict = Depends(get_current_user)):
    from db import save_portfolio_to_gsheet
    import pandas as pd
    prices_df = None
    if req.current_prices:
        try:
            prices_df = pd.DataFrame(req.current_prices)
        except Exception:
            prices_df = None
    ok, msg = await asyncio.to_thread(
        save_portfolio_to_gsheet, req.portfolio_list, prices_df, user["username"]
    )
    return {"success": ok, "message": msg}


@router.get("/portfolio/ai")
async def load_ai_portfolio(user: dict = Depends(get_current_user)):
    from db import load_ai_portfolio_from_gsheet
    data = await asyncio.to_thread(load_ai_portfolio_from_gsheet)
    return data or []


@router.post("/portfolio/ai")
async def save_ai_portfolio(req: AiPortfolioSaveRequest, user: dict = Depends(get_current_user)):
    from db import save_ai_portfolio_to_gsheet
    ok, msg = await asyncio.to_thread(save_ai_portfolio_to_gsheet, req.portfolio_list)
    return {"success": ok, "message": msg}


# ── 거래 내역 ─────────────────────────────────────────────────────────────────

@router.get("/trades")
async def load_trades(user: dict = Depends(get_current_user)):
    from db import load_trade_history_from_gsheet
    df, msg = await asyncio.to_thread(load_trade_history_from_gsheet, owner=user["username"])
    if df is None or (hasattr(df, "empty") and df.empty):
        return {"data": [], "message": msg}
    return {"data": df.to_dict(orient="records"), "message": msg}


@router.get("/trades/agent")
async def load_agent_trades(user: dict = Depends(get_current_user)):
    from db import load_trade_history_from_gsheet
    df, msg = await asyncio.to_thread(load_trade_history_from_gsheet, owner="AI_AGENT")
    if df is None or (hasattr(df, "empty") and df.empty):
        return {"data": [], "message": msg}
    return {"data": df.to_dict(orient="records"), "message": msg}


@router.post("/trades")
async def save_trade(req: TradeRecordRequest, user: dict = Depends(get_current_user)):
    from db import save_trade_record, match_screener_for_trade
    owner = user["username"]   # 세션에서 강제 — 클라이언트 owner 무시
    ok, msg = await asyncio.to_thread(save_trade_record, req.trade, owner)
    is_leading = "리딩방" in str(req.trade.get("trade_source", ""))
    if ok and is_leading:
        sell_date = str(req.trade.get("sell_date", ""))[:10]
        await asyncio.to_thread(match_screener_for_trade, req.trade.get("ticker", ""), sell_date)
    return {"success": ok, "message": msg}


@router.patch("/trades")
async def update_trade_tag(req: UpdateTradeTagRequest, user: dict = Depends(get_current_user)):
    from db import update_trade_source_type
    ok, msg = await asyncio.to_thread(update_trade_source_type, req.ticker, req.sell_date, req.trade_source, req.trade_type, user["username"])
    return {"success": ok, "message": msg}


@router.patch("/trades/buy-date")
async def update_trade_buy_date_ep(req: UpdateTradeBuyDateRequest, user: dict = Depends(get_current_user)):
    """거래내역의 매수 시각(buy_date) 수정 — 패턴 학습 정확도 보정용."""
    from db import update_trade_buy_date
    ok, msg = await asyncio.to_thread(update_trade_buy_date, req.ticker, req.sell_date, req.buy_date, user["username"])
    return {"success": ok, "message": msg}


@router.patch("/portfolio/buy-time")
async def update_portfolio_buy_time_ep(req: UpdatePortfolioBuyTimeRequest, user: dict = Depends(get_current_user)):
    """보유종목의 매수 시각(updated_time) 수정."""
    from db import update_portfolio_buy_time
    ok, msg = await asyncio.to_thread(update_portfolio_buy_time, req.ticker, user["username"], req.buy_time)
    return {"success": ok, "message": msg}


@router.patch("/trades/buy-reason")
async def update_trade_buy_reason_ep(req: UpdateTradeBuyReasonRequest, user: dict = Depends(get_current_user)):
    """거래내역의 매수 근거(리딩방 추천 사유 등) 수정."""
    from db import update_trade_buy_reason
    ok, msg = await asyncio.to_thread(update_trade_buy_reason, req.ticker, req.sell_date, req.buy_reason, user["username"])
    return {"success": ok, "message": msg}


@router.delete("/trades")
async def delete_trade(req: DeleteTradeRequest, user: dict = Depends(get_current_user)):
    from db import delete_trade_from_gsheet
    ok, msg = await asyncio.to_thread(delete_trade_from_gsheet, req.ticker, req.sell_date, user["username"])
    return {"success": ok, "message": msg}


# ── AI 추천 로그 (전역 로그) ──────────────────────────────────────────────────

@router.post("/ai-log")
async def log_recommendation(req: AiLogRequest, user: dict = Depends(get_current_user)):
    from db import log_ai_recommendation
    ok, msg = await asyncio.to_thread(
        log_ai_recommendation,
        req.rec_type, req.ticker, req.name, req.rating,
        req.buy_target, req.sell_target, req.stop_loss,
    )
    return {"success": ok, "message": msg}


# ── 가격 알림 설정 (전역 공유 — Phase 3에서 유저별 격리 예정) ─────────────────

@router.get("/alerts")
async def load_alerts(user: dict = Depends(get_current_user)):
    from db import load_price_alerts
    data = await asyncio.to_thread(load_price_alerts, user["username"])
    return data or []


@router.post("/alerts")
async def save_alert(req: AlertRequest, user: dict = Depends(get_current_user)):
    from db import save_price_alert
    ok, msg = await asyncio.to_thread(
        save_price_alert,
        req.market, req.ticker, req.name, req.alert_type, req.target_price, user["username"],
    )
    return {"success": ok, "message": msg}


@router.delete("/alerts")
async def delete_alert(req: DeleteAlertRequest, user: dict = Depends(get_current_user)):
    from db import delete_price_alert
    ok, msg = await asyncio.to_thread(delete_price_alert, req.ticker, req.alert_type, user["username"])
    return {"success": ok, "message": msg}


# ── 매매 분석 일지 (전역 공유 — Phase 3에서 유저별 격리 예정) ─────────────────

@router.post("/trade-analysis")
async def save_trade_analysis(req: TradeAnalysisSaveRequest, user: dict = Depends(get_current_user)):
    from db import save_trade_analysis
    ok, msg = await asyncio.to_thread(save_trade_analysis, req.analysis, user["username"])
    return {"success": ok, "message": msg}


@router.get("/trade-analysis")
async def load_trade_analysis(user: dict = Depends(get_current_user)):
    from db import load_trade_analysis
    data, msg = await asyncio.to_thread(load_trade_analysis, user["username"])
    return {"data": data, "message": msg}


@router.post("/trade-analysis/record")
async def save_trade_analysis_record(req: TradeAnalysisRecordRequest, user: dict = Depends(get_current_user)):
    from db import save_trade_analysis_record
    ok, msg = await asyncio.to_thread(
        save_trade_analysis_record, req.trade_data, req.analysis_result, user["username"]
    )
    return {"success": ok, "message": msg}


@router.get("/trade-analysis/records")
async def load_trade_analysis_records(user: dict = Depends(get_current_user)):
    from db import load_trade_analysis_records
    data, msg = await asyncio.to_thread(load_trade_analysis_records, user["username"])
    return {"data": data or [], "message": msg}


# ── 텔레그램 설정 (전역 봇 — 관리자 전용. 유저별 알림은 Phase 5) ──────────────

@router.get("/telegram/config")
async def get_telegram_config(_admin: dict = Depends(require_admin)):
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
async def save_and_test_telegram(req: TelegramConfigRequest, _admin: dict = Depends(require_admin)):
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


# ── 커스텀 시나리오 (유저별 서버 영속 — 브라우저 localStorage 대체) ────────────

@router.get("/custom-scenarios")
async def list_custom_scenarios(user: dict = Depends(get_current_user)):
    from db import load_custom_scenarios
    data = await asyncio.to_thread(load_custom_scenarios, user["username"])
    return {"data": data or []}


@router.post("/custom-scenarios")
async def add_custom_scenario(req: CustomScenarioSaveRequest, user: dict = Depends(get_current_user)):
    from db import save_custom_scenario
    ok, result = await asyncio.to_thread(
        save_custom_scenario, user["username"], req.keyword, req.title, req.payload, req.searched_at
    )
    return {"success": ok, "id": result if ok else None, "message": "" if ok else str(result)}


@router.delete("/custom-scenarios/{sid}")
async def remove_custom_scenario(sid: int, user: dict = Depends(get_current_user)):
    from db import delete_custom_scenario
    ok, msg = await asyncio.to_thread(delete_custom_scenario, user["username"], sid)
    return {"success": ok, "message": msg}


# ── 최근 검색어 (유저별 서버 영속) ──────────────────────────────────────────────

@router.get("/recent-searches")
async def list_recent_searches(user: dict = Depends(get_current_user)):
    from db import load_recent_searches
    data = await asyncio.to_thread(load_recent_searches, user["username"])
    return {"data": data or []}


@router.post("/recent-searches")
async def add_recent_search(req: RecentSearchRequest, user: dict = Depends(get_current_user)):
    from db import save_recent_search
    ok, msg = await asyncio.to_thread(save_recent_search, user["username"], req.keyword)
    return {"success": ok, "message": msg}
