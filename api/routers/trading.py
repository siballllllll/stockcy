from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncio
from typing import Optional

router = APIRouter()

class BuyRequest(BaseModel):
    owner: str = "USER"
    ticker: str
    name: str
    buy_price: float
    quantity: float
    rating: str = "-"

class SellRequest(BaseModel):
    owner: str = "USER"
    ticker: str
    name: str
    sell_price: float
    quantity: float

@router.get("/trading/balances")
async def get_balances():
    from db import load_virtual_balances
    balances = await asyncio.to_thread(load_virtual_balances)
    return {"data": balances}

@router.post("/trading/buy")
async def execute_buy(req: BuyRequest):
    from db import load_virtual_balances, save_virtual_balance, load_portfolio_from_gsheet, save_portfolio_to_gsheet
    
    total_cost = req.buy_price * req.quantity
    
    # 1. Check and deduct balance
    balances = await asyncio.to_thread(load_virtual_balances)
    owner_bal = balances.get(req.owner.upper(), 10000000)
    
    if owner_bal < total_cost:
        raise HTTPException(status_code=400, detail=f"잔액 부족 (필요: {total_cost}, 보유: {owner_bal})")
        
    new_bal = owner_bal - total_cost
    await asyncio.to_thread(save_virtual_balance, req.owner.upper(), new_bal)
    
    # 2. Update portfolio
    pf = await asyncio.to_thread(load_portfolio_from_gsheet, req.owner.upper())
    
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
        
    ok, msg = await asyncio.to_thread(save_portfolio_to_gsheet, pf, None, req.owner.upper())
    return {"success": ok, "message": "매수 체결 완료", "new_balance": new_bal}

@router.post("/trading/sell")
async def execute_sell(req: SellRequest):
    from db import load_virtual_balances, save_virtual_balance, load_portfolio_from_gsheet, save_portfolio_to_gsheet, save_trade_record
    
    pf = await asyncio.to_thread(load_portfolio_from_gsheet, req.owner.upper())
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
    owner_bal = balances.get(req.owner.upper(), 10000000)
    new_bal = owner_bal + revenue
    await asyncio.to_thread(save_virtual_balance, req.owner.upper(), new_bal)
    
    # Remove from portfolio
    existing["quantity"] -= req.quantity
    if existing["quantity"] <= 0:
        pf.remove(existing)
        
    await asyncio.to_thread(save_portfolio_to_gsheet, pf, None, req.owner.upper())
    
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
    await asyncio.to_thread(save_trade_record, trade, req.owner.upper())

    # LEADING 거래는 스크리너 추천 종목 여부 자동 체크
    if req.owner.upper() == "LEADING":
        from db import match_screener_for_trade
        await asyncio.to_thread(match_screener_for_trade, req.ticker, sell_date_str)

    return {"success": True, "message": "매도 체결 완료", "profit": profit, "new_balance": new_bal}
