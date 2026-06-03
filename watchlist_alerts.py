"""관심종목 기반 실시간 촉매 알림(B) + 실적 캘린더 인지(C).

B) run_catalyst_scan: 관심종목의 당일 급변동(이상징후) 감지 → 텔레그램 즉시 알림(일 1회/종목 중복방지)
C) load_earnings_calendar / run_earnings_alert: US 관심종목 실적일 인지 → 임박 시 경고
"""
import os
from datetime import datetime


def _watchlist() -> list:
    """관심종목(로컬 SQLite) → [{ticker, name, market}] (market: kr/us)."""
    try:
        from db import load_favorites
        recs, _ = load_favorites()
        out = []
        for r in recs:
            t = str(r.get("티커", "")).strip()
            if not t:
                continue
            mkt = "kr" if str(r.get("시장", "")) == "국내" else "us"
            out.append({"ticker": t.upper() if mkt == "us" else t, "name": r.get("종목명", t), "market": mkt})
        return out
    except Exception as e:
        print(f"[catalyst] watchlist 로드 실패: {e}")
        return []


# ── B. 실시간 촉매(급변동) 알림 ────────────────────────────────────────────────
def run_catalyst_scan(push: bool = True, thr_kr: float = None, thr_us: float = None) -> dict:
    """관심종목 중 당일 |등락률| 임계 초과 종목을 촉매 후보로 텔레그램 알림(일 1회 중복방지)."""
    thr_kr = thr_kr if thr_kr is not None else float(os.environ.get("CATALYST_MOVE_PCT_KR", "5.0"))
    thr_us = thr_us if thr_us is not None else float(os.environ.get("CATALYST_MOVE_PCT_US", "4.0"))

    wl = _watchlist()
    if not wl:
        return {"movers": 0, "msg": "관심종목 없음"}

    moves = {}  # ticker -> change_pct
    # KR: 인메모리 캐시
    try:
        from api.main import KRX_PRICE_CACHE
        for w in wl:
            if w["market"] == "kr":
                c = KRX_PRICE_CACHE.get(str(w["ticker"]).zfill(6))
                if c and c.get("change_pct") is not None:
                    moves[w["ticker"]] = float(c["change_pct"])
    except Exception:
        pass
    # US: KIS 벌크
    us = [w for w in wl if w["market"] == "us"]
    if us:
        try:
            from db import us_ticker_exchange_map
            from data_kr import get_us_prices_bulk_kis
            exmap = us_ticker_exchange_map()
            pairs = tuple(sorted((w["ticker"], exmap.get(w["ticker"], "NASDAQ")) for w in us))
            res = get_us_prices_bulk_kis(pairs)
            for t, v in (res or {}).items():
                if v and v.get("change_pct") is not None:
                    moves[t] = float(v["change_pct"])
        except Exception as e:
            print(f"[catalyst] US 시세 실패: {e}")

    name_map = {w["ticker"]: w["name"] for w in wl}
    mkt_map = {w["ticker"]: w["market"] for w in wl}
    today = datetime.now().strftime("%Y-%m-%d")

    from db import load_ai_cache, save_ai_cache
    seen_key = f"catalyst_alerted_{today}"
    alerted = set((load_ai_cache(seen_key) or {}).get("tickers", []))

    movers = []
    for t, chg in moves.items():
        thr = thr_kr if mkt_map.get(t) == "kr" else thr_us
        if abs(chg) >= thr and t not in alerted:
            movers.append({"ticker": t, "name": name_map.get(t, t), "change_pct": chg, "market": mkt_map.get(t)})

    if not movers:
        return {"movers": 0, "checked": len(moves)}

    movers.sort(key=lambda x: -abs(x["change_pct"]))
    if push:
        try:
            from telegram_bot import send_message
            lines = ["⚡ <b>관심종목 급변동 — 촉매 확인</b>"]
            for m in movers[:15]:
                arrow = "🔺" if m["change_pct"] > 0 else "🔻"
                flag = "🇰🇷" if m["market"] == "kr" else "🇺🇸"
                lines.append(f"{arrow} {flag} {m['name']} ({m['ticker']})  {m['change_pct']:+.2f}%")
            send_message("\n".join(lines))
        except Exception as e:
            print(f"[catalyst] 발송 실패: {e}")

    save_ai_cache(seen_key, {"tickers": list(alerted) + [m["ticker"] for m in movers]}, ttl_hours=24)
    return {"movers": len(movers), "checked": len(moves)}


# ── C. 실적 캘린더 인지 (US) ───────────────────────────────────────────────────
def load_earnings_calendar(days: int = 10) -> dict:
    """US 관심종목의 다가오는 실적일(향후 N일) 목록. yfinance 기반(12시간 캐시는 _cached 래퍼)."""
    wl = [w for w in _watchlist() if w["market"] == "us"]
    if not wl:
        return {"upcoming": [], "note": "US 관심종목 없음"}
    name_map = {w["ticker"]: w["name"] for w in wl}
    upcoming = _earnings_for(tuple(sorted(w["ticker"] for w in wl)))
    today = datetime.now().date()
    out = []
    for tk, dstr in (upcoming or {}).items():
        try:
            d = datetime.strptime(dstr, "%Y-%m-%d").date()
            dd = (d - today).days
            if 0 <= dd <= days:
                out.append({"ticker": tk, "name": name_map.get(tk, tk), "date": dstr, "d_day": dd})
        except Exception:
            continue
    out.sort(key=lambda x: x["d_day"])
    return {"upcoming": out}


def _earnings_for(tickers: tuple) -> dict:
    """티커별 다음 실적일(YYYY-MM-DD). yfinance Ticker.calendar 사용 + st_compat 캐시."""
    import st_compat as st

    @st.cache_data(ttl=43200)  # 12시간
    def _impl(tks: tuple) -> dict:
        import yfinance as yf
        res = {}
        for t in tks:
            try:
                cal = yf.Ticker(t).calendar
                ed = None
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if isinstance(ed, (list, tuple)) and ed:
                        ed = ed[0]
                if ed is not None:
                    res[t] = ed.strftime("%Y-%m-%d") if hasattr(ed, "strftime") else str(ed)[:10]
            except Exception:
                continue
        return res

    return _impl(tickers)


def run_earnings_alert(push: bool = True, within: int = 2) -> dict:
    """실적 D-within 이내 US 관심종목 경고 텔레그램(일 1회 중복방지)."""
    cal = load_earnings_calendar(days=within)
    soon = [e for e in cal.get("upcoming", []) if e["d_day"] <= within]
    if not soon:
        return {"alerts": 0}
    today = datetime.now().strftime("%Y-%m-%d")
    from db import load_ai_cache, save_ai_cache
    key = f"earnings_alerted_{today}"
    alerted = set((load_ai_cache(key) or {}).get("tickers", []))
    new = [e for e in soon if e["ticker"] not in alerted]
    if not new:
        return {"alerts": 0}
    if push:
        try:
            from telegram_bot import send_message
            lines = ["📅 <b>실적 임박 경고 (US 관심종목)</b>"]
            for e in new:
                dd = "오늘" if e["d_day"] == 0 else f"D-{e['d_day']}"
                lines.append(f"⚠️ {e['name']} ({e['ticker']}) — 실적 {dd} ({e['date']})")
            lines.append("\n보유 중이면 실적 변동성에 유의하세요.")
            send_message("\n".join(lines))
        except Exception as e:
            print(f"[earnings] 발송 실패: {e}")
    save_ai_cache(key, {"tickers": list(alerted) + [e["ticker"] for e in new]}, ttl_hours=24)
    return {"alerts": len(new)}
