"""시장 전체 눌림목 후보 [v3.219.0].

패턴 스크리너의 후보가 즐겨찾기 25종목에 갇혀 있던 것을 푼다(10-29, 최근 15일 픽 91%가 즐겨찾기).
즐겨찾기를 넣은 이유(v3.106.0)는 "내 승리 패턴 = 거래량 조용한 눌림목인데 거래량·등락률 순위엔
급등주만 잡힌다"였다. 그 문제를 즐겨찾기 대신 **시장 전체에서 눌림목을 먼저 추려** 푼다.

  1) 네이버 시가총액 목록으로 코스피·코스닥 보통주 전체(시총 1,000억+)를 받는다
     (FDR StockListing은 이름만 오고 가격·시총이 비어 있다 — 10-29 확인).
  2) 종목마다 일봉 ~100개를 받아 값싼 조건으로 거른다 — 상승 추세 안의 조정, 거래량 조용,
     RSI 중립 이하, 5일 급등 아님(스크리너 하드 필터와 같은 독성 구간 제외).
  3) 상위 N개를 파일로 남긴다. 스크리너는 이 파일을 읽어 기존 채점에 넣는다(산식 불변).

1,300종목 일봉 수집이 2분가량이라 하루 한 번 장 마감 뒤에만 만든다.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import requests

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_csv", "pullback_universe.json")
PATH_US = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_csv", "pullback_universe_us.json")
MIN_VALUE_USD_M = 20         # 미국: 20일 평균 거래대금 $2,000만 이상
_LIST_H = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"}
_CHART_H = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}
MIN_MARCAP_EOK = 1000        # 시가총액 1,000억 이상
MIN_VALUE_EOK = 10           # 20일 평균 거래대금 10억 이상 — 실제로 사고팔 수 있는 종목만
TOP_N = 40


def _num(x) -> float:
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return 0.0


def _listing() -> list:
    def page(args):
        m, p = args
        r = requests.get(f"https://m.stock.naver.com/api/stocks/marketValue/{m}?page={p}&pageSize=100",
                         headers=_LIST_H, timeout=10)
        return r.json()

    out = []
    for m in ("KOSPI", "KOSDAQ"):
        first = page((m, 1))
        total = int(first.get("totalCount") or 0)
        pages = [(m, p) for p in range(2, (total + 99) // 100 + 1)]
        with ThreadPoolExecutor(6) as ex:
            rest = list(ex.map(page, pages))
        for j in [first] + rest:
            for s in j.get("stocks", []):
                code = str(s.get("itemCode", ""))
                name = str(s.get("stockName", ""))
                if (s.get("stockEndType") != "stock" or not code.isdigit() or not code.endswith("0")
                        or "스팩" in name or _num(s.get("marketValue")) < MIN_MARCAP_EOK
                        or (s.get("tradeStopType") or {}).get("name") not in (None, "TRADING")):
                    continue   # ETF·우선주(끝자리≠0)·스팩·소형주·거래정지 제외
                out.append({"code": code, "name": name, "market": m,
                            "marcap_eok": _num(s.get("marketValue"))})
    return out


def _bars(code: str) -> list:
    s = (date.today() - timedelta(days=160)).strftime("%Y%m%d") + "000000"
    e = date.today().strftime("%Y%m%d") + "235959"
    try:
        r = requests.get(f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
                         f"?startDateTime={s}&endDateTime={e}", headers=_CHART_H, timeout=8)
        rows = r.json() if r.ok else []
        return sorted(rows, key=lambda x: x.get("localDate", "")) if isinstance(rows, list) else []
    except Exception:
        return []


def _rsi(closes: list, n: int = 14):
    if len(closes) <= n:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[-n - 1:-1], closes[-n:]):
        d = b - a
        gains += max(d, 0)
        losses += max(-d, 0)
    if losses == 0:
        return 100.0
    return round(100 - 100 / (1 + gains / losses), 1)


def evaluate(rows: list) -> dict | None:
    """네이버 일봉(국내)으로 눌림목 조건 판정."""
    closes = [float(r.get("closePrice") or 0) for r in rows]
    vols = [float(r.get("accumulatedTradingVolume") or 0) for r in rows]
    return evaluate_series(closes, vols)


def evaluate_series(closes: list, vols: list, value_div: float = 1e8, min_value: float = MIN_VALUE_EOK,
                    max_vr: float = 0.8) -> dict | None:
    """종가·거래량 목록으로 눌림목 조건 판정. 통과하면 지표와 정렬 점수, 아니면 None.
    국내·미국이 같은 조건을 쓴다 — 거래대금 단위만 다르다(국내 억 원, 미국 백만 달러)."""
    if len(closes) < 65 or min(closes[-65:]) <= 0:
        return None
    c = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    ma60_prev = sum(closes[-65:-5]) / 60
    hi20 = max(closes[-20:])
    v5, v20 = sum(vols[-5:]) / 5, sum(vols[-20:]) / 20
    value_eok = sum(cl * v for cl, v in zip(closes[-20:], vols[-20:])) / 20 / value_div
    vr = v5 / v20 if v20 > 0 else None
    mom5 = (c / closes[-6] - 1) * 100
    dd = (c / hi20 - 1) * 100
    rsi = _rsi(closes)
    ok = (value_eok >= min_value
          and ma20 > ma60 and ma60 >= ma60_prev          # 상승 추세(중기선이 오르는 중)
          and c >= ma60 * 0.97                           # 추세가 꺾일 만큼 깨지진 않음
          and ma20 * 0.92 <= c <= ma20 * 1.02            # 20일선 근처로 내려옴
          and -20 <= dd <= -4                            # 최근 고점에서 4~20% 조정
          and vr is not None and vr <= max_vr            # 거래량 조용(내 승리 패턴 0.2~0.5)
          and rsi is not None and 30 <= rsi <= 55
          and mom5 < 5)                                  # 5일 급등은 스크리너 하드 필터 독성 구간
    if not ok:
        return None
    # 정렬: 거래량이 조용할수록, RSI가 내 승리 구간 가운데(43)에 가까울수록 앞
    rank = round((1 - vr) + (1 - abs(rsi - 43) / 15), 3)
    return {"close": c, "rsi": rsi, "vol_ratio": round(vr, 2), "mom5": round(mom5, 2),
            "drawdown": round(dd, 2), "to_ma20": round((c / ma20 - 1) * 100, 2),
            "value_eok": round(value_eok, 1), "rank": rank}


def build(top_n: int = TOP_N) -> dict:
    t0 = time.time()
    stocks = _listing()
    with ThreadPoolExecutor(8) as ex:
        bars = list(ex.map(lambda s: _bars(s["code"]), stocks))
    picked, fetched = [], 0
    for s, rows in zip(stocks, bars):
        if rows:
            fetched += 1
        ev = evaluate(rows) if rows else None
        if ev:
            picked.append({**s, **ev})
    picked.sort(key=lambda x: x["rank"], reverse=True)
    out = {"built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "scanned": len(stocks), "fetched": fetched, "passed": len(picked),
           "seconds": round(time.time() - t0, 1), "stocks": picked[:top_n]}
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, PATH)
    print(f"[pullback universe] {len(stocks)}종목 스캔 → 통과 {len(picked)} → 상위 {len(out['stocks'])} "
          f"({out['seconds']}초)")
    return out


def _bars_us_naver(sym: str) -> list:
    """네이버 해외 일봉 — Yahoo 속도 제한 때의 대체 경로. 거래소 접미사가 달라(나스닥 .O, 일부 .K,
    뉴욕은 없음) 차례로 시도한다. 반환은 (종가, 거래량) 목록."""
    s0 = (date.today() - timedelta(days=240)).strftime("%Y%m%d") + "0000"
    e0 = date.today().strftime("%Y%m%d") + "2359"
    for code in (sym, f"{sym}.O", f"{sym}.K"):
        try:
            r = requests.get(f"https://api.stock.naver.com/chart/foreign/item/{code}/day"
                             f"?startDateTime={s0}&endDateTime={e0}", headers=_LIST_H, timeout=8)
            rows = r.json() if r.ok else []
            if isinstance(rows, list) and rows:
                rows = sorted(rows, key=lambda x: x.get("localDate", ""))
                return [(float(x.get("closePrice") or 0), float(x.get("accumulatedTradingVolume") or 0)) for x in rows]
        except Exception:
            pass
    return []


def build_us(top_n: int = TOP_N) -> dict:
    """미국 눌림목 후보 — S&P500 전체를 yfinance로 한 번에 받는다(실측 503종목 12초).
    조건은 국내와 같다. 채점 패턴은 국내 매매에서 배운 것이라 미국에 맞는지는 V29로 따로 잰다."""
    import FinanceDataReader as fdr
    import yfinance as yf
    t0 = time.time()
    sp = fdr.StockListing("S&P500")
    names = {str(r.Symbol).replace(".", "-"): str(r.Name) for r in sp.itertuples()}
    df = yf.download(list(names), period="8mo", interval="1d", progress=False, threads=True,
                     group_by="column", auto_adjust=False, timeout=30)
    series = {}
    for tk in names:
        try:
            c = df["Close"][tk]; v = df["Volume"][tk]
        except Exception:
            continue
        both = [(float(a), float(b)) for a, b in zip(c, v) if a == a and b == b]   # NaN 제외(장 전 빈 행)
        if both:
            series[tk] = both
    source = "yahoo"
    if len(series) < len(names) // 2:
        # Yahoo 속도 제한(10-29 실측: 연달아 받으면 전부 빈 값) → 네이버 해외 일봉으로
        print(f"[pullback universe US] Yahoo {len(series)}/{len(names)}종목 — 네이버로 대체 수집")
        with ThreadPoolExecutor(8) as ex:
            got = list(ex.map(_bars_us_naver, list(names)))
        series = {tk: b for tk, b in zip(names, got) if b}
        source = "naver"
    picked, fetched = [], 0
    for tk, nm in names.items():
        both = series.get(tk)
        if not both:
            continue
        fetched += 1
        ev = evaluate_series([a for a, _ in both], [b for _, b in both], value_div=1e6, min_value=MIN_VALUE_USD_M,
                             max_vr=1.0)   # 10-29 실측: 실적 시즌엔 0.8이면 503종목 중 1개만 통과 → 미국만 1.0
        if ev:
            picked.append({"code": tk, "name": nm, "market": "US", **ev})
    if fetched < len(names) // 2:
        # Yahoo 속도 제한(YFRateLimitError)이면 전부 비어 온다 — 빈 목록으로 덮어쓰지 않는다
        raise RuntimeError(f"미국 일봉 수집 실패({fetched}/{len(names)}) — 속도 제한 의심, 다음 주기에 재시도")
    picked.sort(key=lambda x: x["rank"], reverse=True)
    out = {"built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "scanned": len(names), "fetched": fetched, "passed": len(picked), "source": source,
           "seconds": round(time.time() - t0, 1), "stocks": picked[:top_n]}
    tmp = PATH_US + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, PATH_US)
    print(f"[pullback universe US] {len(names)}종목 스캔 → 통과 {len(picked)} → 상위 {len(out['stocks'])} "
          f"({out['seconds']}초)")
    return out


def load(max_age_days: int = 4, market: str = "kr") -> list:
    """최근에 만든 후보만 쓴다 — 오래된 목록으로 고르면 이미 지난 눌림목을 고른다."""
    try:
        with open(PATH_US if market == "us" else PATH, encoding="utf-8") as f:
            j = json.load(f)
        built = datetime.strptime(j["built_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - built > timedelta(days=max_age_days):
            return []
        return j.get("stocks", [])
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    r = build_us() if "us" in sys.argv[1:] else build()
    for s in r["stocks"][:15]:
        print(s["code"], s["name"], s["rsi"], s["vol_ratio"], s["drawdown"], s["mom5"])
