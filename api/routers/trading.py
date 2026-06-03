"""
가상 매매(모의투자) 라우터.

[Phase 1c] owner 는 로그인 세션(current_user)에서 강제 결정한다. 클라이언트가 보내는
owner 필드는 무시한다. 잔고 조회도 본인 것만 반환한다.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import asyncio
from typing import Optional

from api.auth import get_current_user

router = APIRouter()

class BuyRequest(BaseModel):
    owner: str = "USER"   # (무시됨 — 세션에서 결정)
    ticker: str
    name: str
    buy_price: float
    quantity: float
    rating: str = "-"

class SellRequest(BaseModel):
    owner: str = "USER"   # (무시됨 — 세션에서 결정)
    ticker: str
    name: str
    sell_price: float
    quantity: float

@router.get("/trading/balances")
async def get_balances(user: dict = Depends(get_current_user)):
    from db import load_virtual_balances
    balances = await asyncio.to_thread(load_virtual_balances)
    # 본인 잔고만 노출 (관리자도 우선 본인 것만 — 전체 조회는 Phase 4 관리자 화면에서)
    me = user["username"].upper()
    return {"data": {me: balances.get(me, 10000000)}}

@router.post("/trading/buy")
async def execute_buy(req: BuyRequest, user: dict = Depends(get_current_user)):
    from db import load_virtual_balances, save_virtual_balance, load_portfolio_from_gsheet, save_portfolio_to_gsheet

    owner = user["username"].upper()
    total_cost = req.buy_price * req.quantity

    # 1. Check and deduct balance
    balances = await asyncio.to_thread(load_virtual_balances)
    owner_bal = balances.get(owner, 10000000)

    if owner_bal < total_cost:
        raise HTTPException(status_code=400, detail=f"잔액 부족 (필요: {total_cost}, 보유: {owner_bal})")

    new_bal = owner_bal - total_cost
    await asyncio.to_thread(save_virtual_balance, owner, new_bal)

    # 2. Update portfolio
    pf = await asyncio.to_thread(load_portfolio_from_gsheet, owner)

    existing = next((p for p in pf if p["ticker"] == req.ticker), None)
    if existing:
        old_qty = existing["quantity"]
        old_cost = existing["buy_price"] * old_qty
        new_qty = old_qty + req.quantity
        new_avg_price = (old_cost + total_cost) / new_qty
        existing["quantity"] = new_qty
        existing["buy_price"] = new_avg_price
    else:
        pf.append({
            "ticker": req.ticker,
            "name": req.name,
            "buy_price": req.buy_price,
            "quantity": req.quantity,
            "rating": req.rating,
        })

    ok, msg = await asyncio.to_thread(save_portfolio_to_gsheet, pf, None, owner)
    return {"success": ok, "message": "매수 체결 완료", "new_balance": new_bal}

@router.post("/trading/sell")
async def execute_sell(req: SellRequest, user: dict = Depends(get_current_user)):
    from db import load_virtual_balances, save_virtual_balance, load_portfolio_from_gsheet, save_portfolio_to_gsheet, save_trade_record

    owner = user["username"].upper()
    pf = await asyncio.to_thread(load_portfolio_from_gsheet, owner)
    existing = next((p for p in pf if p["ticker"] == req.ticker), None)

    if not existing:
        raise HTTPException(status_code=400, detail="보유하지 않은 종목입니다.")

    if existing["quantity"] < req.quantity:
        raise HTTPException(status_code=400, detail="보유 수량이 부족합니다.")

    # Calculate profit
    invested = existing["buy_price"] * req.quantity
    revenue = req.sell_price * req.quantity
    profit = revenue - invested
    profit_pct = (profit / invested * 100) if invested > 0 else 0

    # Add to balance
    balances = await asyncio.to_thread(load_virtual_balances)
    owner_bal = balances.get(owner, 10000000)
    new_bal = owner_bal + revenue
    await asyncio.to_thread(save_virtual_balance, owner, new_bal)

    # Remove from portfolio
    existing["quantity"] -= req.quantity
    if existing["quantity"] <= 0:
        pf.remove(existing)

    await asyncio.to_thread(save_portfolio_to_gsheet, pf, None, owner)

    # Save trade record
    from datetime import datetime as _dt
    sell_date_str = _dt.now().strftime("%Y-%m-%d")
    trade = {
        "ticker": req.ticker,
        "name": req.name,
        "quantity": req.quantity,
        "buy_price": existing["buy_price"],
        "sell_price": req.sell_price,
        "profit": profit,
        "profit_pct": profit_pct,
        "result": "익절" if profit > 0 else "손절"
    }
    await asyncio.to_thread(save_trade_record, trade, owner)

    return {"success": True, "message": "매도 체결 완료", "profit": profit, "new_balance": new_bal}
