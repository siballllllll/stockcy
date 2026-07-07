"""섀도우 리그 (v3.118.0) — 사용자에게 안 보이는 대조군 AI 트레이더들.

목적: 메인 에이전트(Gemini 하이브리드)와 같은 시장·같은 시각에 서로 다른 전략으로
가상매매하는 섀도우 2개를 병행 운용 → "어떤 매매 형태의 승률이 실제로 높은가"를
대조군으로 실측. 성적이 검증되면(전략당 실현 30건+) 승자 규칙의 메인 이식을 제안.

원칙:
- Gemini 호출 0 (결정론 규칙 + 로컬 ML만) → 추가 과금 없음.
- 메인 스캔이 이미 수집한 지표(decision._indicators)를 재사용 — 신규 다운로드는
  섀도우 보유 종목 시세 조회(종목당 1회)뿐.
- 저장은 기존 테이블 재사용(portfolio/trade_history/virtual_balances, owner=SHADOW_*).
  UI는 AI_AGENT만 조회하므로 화면에 자동으로 안 보임.

전략 프로파일:
- SHADOW_A "순수 눌림목": 실측 승률 62~71% 구간(볼린저 하단+눌림+조용한 거래량)을
  기계적으로 매수. 감·해설 없이 데이터 규칙만.
- SHADOW_B "ML 순종": 자체 ML 7일 확률 55%+ 종목만, 확률로 사이징. ML을 그대로
  믿으면 얼마나 버는지 측정(사후검증의 실전판).
청산(공통, 결정론): 실질 -5% 손절 / +8% 익절 / 10일 타임스탑(d7 호라이즌 정합).
"""
import logging
from datetime import datetime

logger = logging.getLogger("shadow_league")

SHADOW_START_CASH = 10_000_000.0
SHADOW_DAILY_BUY_CAP = 5      # 메인(3회)보다 완화 — 가상이므로 표본 축적 우선
SHADOW_BUDGET_FRAC = 0.12     # 포지션당 현금 12% (메인과 동일 기준)
EXIT_STOP = -5.0              # 실질 손절 %
EXIT_TAKE = 8.0               # 실질 익절 %
EXIT_DAYS = 10                # 타임스탑 (달력일 ≈ 7거래일, d7 호라이즌 정합)

SHADOWS = ("SHADOW_A", "SHADOW_B")


def _conn():
    from db import get_db_conn
    return get_db_conn()


def _fee(market: str) -> float:
    return 0.21 if market == "국내" else 0.15   # 왕복 수수료+거래세 %


def _cash(cur, owner: str) -> float:
    cur.execute("SELECT balance FROM virtual_balances WHERE owner=?", (owner,))
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT OR REPLACE INTO virtual_balances (owner, balance, updated_time) VALUES (?, ?, ?)",
                    (owner, SHADOW_START_CASH, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        return SHADOW_START_CASH
    return float(row["balance"])


def _set_cash(cur, owner: str, amount: float):
    cur.execute("INSERT OR REPLACE INTO virtual_balances (owner, balance, updated_time) VALUES (?, ?, ?)",
                (owner, float(amount), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


def _holdings(cur, owner: str) -> list:
    cur.execute("SELECT ticker, name, quantity, buy_price, updated_time FROM portfolio WHERE UPPER(owner)=?",
                (owner.upper(),))
    return [dict(r) for r in cur.fetchall()]


def _today_buys(cur, owner: str) -> int:
    cur.execute("SELECT COUNT(*) AS n FROM portfolio WHERE UPPER(owner)=? AND substr(updated_time,1,10)=?",
                (owner.upper(), datetime.now().strftime("%Y-%m-%d")))
    row = cur.fetchone()
    return int(row["n"] if row else 0)


def _buy(cur, owner: str, tk: str, name: str, market: str, price: float, qty: int, note: str, usdkrw: float):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cost = price * qty * (1 + (0.00015 if market == "국내" else 0.0007))
    if market == "미국":
        cost *= usdkrw
    cash = _cash(cur, owner)
    if cash < cost or qty < 1:
        return False
    _set_cash(cur, owner, cash - cost)
    cur.execute(
        """INSERT OR REPLACE INTO portfolio (owner, ticker, name, quantity, buy_price, rating,
               updated_time, trade_source, trade_type, buy_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, '섀도우', '가상', ?)""",
        (owner, tk, name, qty, float(price), f"섀도우 자동 매수 ({owner})", now, note))
    return True


def _sell(cur, owner: str, h: dict, market: str, price: float, reason: str, usdkrw: float):
    qty = float(h["quantity"]); bp = float(h["buy_price"]); sp = float(price)
    buy_fee = 0.00015 if market == "국내" else 0.0007
    sell_fee = 0.00195 if market == "국내" else 0.0008
    invested = bp * qty * (1 + buy_fee)
    returned = sp * qty * (1 - sell_fee)
    profit = returned - invested
    pct = (profit / invested * 100) if invested > 0 else 0.0
    revenue = returned * (usdkrw if market == "미국" else 1.0)
    _set_cash(cur, owner, _cash(cur, owner) + revenue)
    cur.execute(
        """INSERT INTO trade_history (owner, sell_date, ticker, name, quantity, buy_price, sell_price,
               profit, profit_pct, result, learning_point, trade_source, trade_type, buy_date, buy_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '섀도우', '가상', ?, '')""",
        (owner, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), h["ticker"], h["name"], qty, bp, sp,
         profit, pct, "수익" if profit >= 0 else "손실", reason, str(h.get("updated_time") or "")))
    cur.execute("DELETE FROM portfolio WHERE UPPER(owner)=? AND ticker=?", (owner.upper(), h["ticker"]))
    return pct


def _price_of(tk: str, market: str):
    try:
        if market == "국내":
            from data_kr import get_kr_stock_price
            return float((get_kr_stock_price(tk) or {}).get("price", 0))
        from data import get_us_stock_detail
        return float((get_us_stock_detail(tk) or {}).get("price", 0))
    except Exception:
        return 0.0


def _wants_buy(owner: str, ind: dict) -> tuple:
    """전략별 매수 판정 → (매수여부, 사이징 배수, 근거 한 줄)."""
    bb = ind.get("bb_pctb"); m5 = ind.get("mom_5"); vr = ind.get("vol_ratio")
    rsi = ind.get("rsi"); ml7 = ind.get("ml_d7")
    if owner == "SHADOW_A":
        # 순수 눌림목 — 실측 승률 62~71% 구간의 기계적 재현
        ok = (bb is not None and bb < 0.25 and m5 is not None and m5 <= -3
              and (vr is None or vr < 2.0) and (rsi is None or rsi < 55))
        return ok, 1.0, f"눌림목 규칙(bb {bb}·5일 {m5}%·거래량 {vr}배)"
    if owner == "SHADOW_B":
        # ML 순종 — 7일 확률 55%+만, 확률만큼 사이징
        ok = ml7 is not None and ml7 >= 55.0
        mult = 1.0 + min(0.5, max(0.0, ((ml7 or 55) - 55) / 20.0)) if ok else 1.0
        return ok, mult, f"ML d7 {ml7}%"
    return False, 1.0, ""


def run_shadow_cycle(candidates: list, kr_open: bool, us_open: bool, force: bool = False, usdkrw: float = 1450.0) -> dict:
    """1주기 섀도우 운용 — 메인 스캔 직후 호출. candidates: 메인 루프가 수집한
    [{ticker, name, market, price, ind}] (ind = decision._indicators, ml_d7 포함)."""
    out = {}
    conn = _conn(); cur = conn.cursor()
    try:
        today = datetime.now()
        for owner in SHADOWS:
            summary = {"sell": 0, "buy": 0}
            # 1) 보유 청산 판정 (결정론: 손절 -5 / 익절 +8 / 10일 타임스탑)
            for h in _holdings(cur, owner):
                tk = str(h["ticker"])
                market = "국내" if tk.isdigit() else "미국"
                if (market == "국내" and not kr_open and not force) or (market == "미국" and not us_open and not force):
                    continue
                px = _price_of(tk, market)
                if px <= 0 or not h.get("buy_price"):
                    continue
                net = (px - float(h["buy_price"])) / float(h["buy_price"]) * 100.0 - _fee(market)
                held_days = 0
                try:
                    held_days = (today - datetime.strptime(str(h["updated_time"])[:10], "%Y-%m-%d")).days
                except Exception:
                    pass
                reason = None
                if net <= EXIT_STOP:
                    reason = f"손절 {net:+.2f}%"
                elif net >= EXIT_TAKE:
                    reason = f"익절 {net:+.2f}%"
                elif held_days >= EXIT_DAYS:
                    reason = f"타임스탑 {held_days}일 ({net:+.2f}%)"
                if reason:
                    _sell(cur, owner, h, market, px, reason, usdkrw)
                    summary["sell"] += 1
            # 2) 신규 매수 판정 — 메인 스캔이 수집한 후보 재사용 (다운로드 0)
            held = {str(h["ticker"]) for h in _holdings(cur, owner)}
            buys_left = SHADOW_DAILY_BUY_CAP - _today_buys(cur, owner)
            for c in candidates:
                if buys_left <= 0:
                    break
                tk = str(c.get("ticker") or "")
                if not tk or tk in held:
                    continue
                _mkt = c.get("market") or ("국내" if tk.isdigit() else "미국")
                # 개장 게이트 — 후보는 메인 루프에서 이미 걸러지지만 방어적으로 재확인
                if not force and ((_mkt == "국내" and not kr_open) or (_mkt == "미국" and not us_open)):
                    continue
                ind = c.get("ind") or {}
                ok, mult, note = _wants_buy(owner, ind)
                if not ok:
                    continue
                price = float(c.get("price") or 0)
                if price <= 0:
                    continue
                market = c.get("market") or ("국내" if tk.isdigit() else "미국")
                cash = _cash(cur, owner)
                budget = min(cash * SHADOW_BUDGET_FRAC * mult, cash * 0.25)
                px_krw = price * (usdkrw if market == "미국" else 1.0)
                qty = int(budget // px_krw) if px_krw > 0 else 0
                if qty < 1 and px_krw <= budget * 1.5 and px_krw <= cash * 0.25:
                    qty = 1
                if qty < 1:
                    continue
                if _buy(cur, owner, tk, c.get("name") or tk, market, price, qty, note, usdkrw):
                    held.add(tk)
                    buys_left -= 1
                    summary["buy"] += 1
            conn.commit()
            out[owner] = summary
    except Exception as e:
        logger.error(f"[shadow] cycle 오류: {e}")
    finally:
        conn.close()
    return out


def shadow_league_status() -> dict:
    """리그 성적표 — 메인(AI_AGENT) vs 섀도우들의 실현 성적 비교 (/performance용)."""
    conn = _conn(); cur = conn.cursor()
    out = {"as_of": datetime.now().strftime("%Y-%m-%d %H:%M"), "players": []}
    label = {"AI_AGENT": "메인 (Gemini 하이브리드)", "SHADOW_A": "섀도우 A (순수 눌림목)",
             "SHADOW_B": "섀도우 B (ML 순종)"}
    try:
        for owner in ("AI_AGENT",) + SHADOWS:
            cur.execute(
                """SELECT COUNT(*) n,
                          ROUND(AVG(CASE WHEN profit_pct > 0 THEN 100.0 ELSE 0 END), 1) win,
                          ROUND(AVG(profit_pct), 2) avg_pct, ROUND(SUM(profit), 0) total_profit
                   FROM trade_history WHERE owner=?""", (owner,))
            r = dict(cur.fetchone() or {})
            cur.execute("SELECT COUNT(*) n FROM portfolio WHERE UPPER(owner)=?", (owner.upper(),))
            open_n = int((cur.fetchone() or {"n": 0})["n"])
            cur.execute("SELECT balance FROM virtual_balances WHERE owner=?",
                        ("AI" if owner == "AI_AGENT" else owner,))
            b = cur.fetchone()
            out["players"].append({
                "owner": owner, "label": label.get(owner, owner),
                "realized_trades": int(r.get("n") or 0),
                "win_rate": r.get("win"), "avg_pct": r.get("avg_pct"),
                "total_profit": r.get("total_profit"),
                "open_positions": open_n,
                "cash": round(float(b["balance"]), 0) if b else None,
            })
    except Exception as e:
        out["error"] = str(e)
    finally:
        conn.close()
    return out
