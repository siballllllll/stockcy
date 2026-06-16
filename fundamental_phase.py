"""[재무 국면 분류 — 결정론] 가치 함정 vs 순환 바닥/턴어라운드 1차 구분

단일 스냅샷(지금 적자/FCF-)만으론 '영원히 나쁨'과 '지금이 가장 힘든 시기'가 구분 안 된다.
다년 시계열 + 재무 생존력으로 국면을 분류한다(완벽한 예측 아님 — 확률을 쌓는 용도).

신호(중요도순):
  ① 생존력   : 부채비율 + 영업흑자/영업현금흐름 → 트로프를 버틸 체력 (★가장 핵심)
  ② 변곡     : 최근 영업이익이 직전 저점 대비 반등 중인가
  ③ 순환성   : 장기 매출 추이가 진동(순환)이냐 우하향(구조적)이냐
  ④ 자산가치 : PBR(바닥에선 PER보다 신뢰)

데이터: KIS 손익계산서(다년 매출·영업이익) + 재무비율(부채·BPS) + 현재가(PBR) + DART 영업현금흐름.
"""

def _kis_income_series(code: str) -> list:
    """KIS 손익계산서(연간) → [{year, revenue, op, ni}] 오름차순. 연차(최빈 월말)만 사용."""
    from data_kr import _get   # 토큰 무효 시 재발급 재시도 포함
    code = str(code).strip().zfill(6)
    d = _get(
        "/uapi/domestic-stock/v1/finance/income-statement", "FHKST66430200",
        {"fid_div_cls_code": "0", "fid_cond_mrkt_div_code": "J", "fid_input_iscd": code},
        debug_label="손익계산서",
    )
    rows = (d or {}).get("output") or []
    if not rows:
        return []

    def _f(v):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return None

    # 연차 보고 월(대부분 12월) 최빈값만 — 분기/부분기(예: 202603) 혼입 제거
    months = [str(it.get("stac_yymm", ""))[4:6] for it in rows if it.get("stac_yymm")]
    if not months:
        return []
    dom = max(set(months), key=months.count)
    out = []
    for it in rows:
        ym = str(it.get("stac_yymm", ""))
        if len(ym) >= 6 and ym[4:6] == dom:
            rev, op, ni = _f(it.get("sale_account")), _f(it.get("bsop_prti")), _f(it.get("thtr_ntin"))
            if rev is not None and op is not None:
                out.append({"year": ym[:4], "revenue": rev, "op": op, "ni": ni})
    out.sort(key=lambda x: x["year"])
    return out[-6:]   # 최근 6년


def classify_fundamental_phase(code: str) -> dict:
    """재무 국면 1차 분류. 반환: {phase, reason, signals, series}. 데이터 부족 시 phase=None."""
    series = _kis_income_series(code)
    if len(series) < 3:
        return {"phase": None, "reason": "다년 재무 데이터 부족", "signals": {}, "series": series}

    ops = [s["op"] for s in series]
    revs = [s["revenue"] for s in series]
    latest_op, prev_op = ops[-1], ops[-2]
    trough = min(ops)
    peak = max(ops)

    # 보조 재무 (생존력·PBR)
    debt_ratio = pbr = cfo = None
    try:
        from data_kr import get_kr_financials_kis, get_kr_stock_price
        fin = get_kr_financials_kis(code) or {}
        debt_ratio = fin.get("debt_ratio")
        bps = fin.get("bps")
        price = float((get_kr_stock_price(code) or {}).get("price") or 0)
        if bps and bps > 0 and price > 0:
            pbr = round(price / bps, 2)
    except Exception:
        pass
    try:
        from dart import get_kr_financials_dart
        cfo = (get_kr_financials_dart(code) or {}).get("cfo")
    except Exception:
        pass

    core = _classify_core(ops, revs, debt_ratio, pbr, cfo)
    core["series"] = [{"y": s["year"], "op억": round(s["op"])} for s in series]
    return core


def _classify_core(ops: list, revs: list, debt_ratio=None, pbr=None, cfo=None) -> dict:
    """국면 판정 코어(KR/US 공용). ops·revs는 오름차순(과거→최근). 반환 {phase, reason, signals}."""
    latest_op, prev_op = ops[-1], ops[-2]
    trough, peak = min(ops), max(ops)
    op_positive = latest_op > 0
    rebounding = latest_op > prev_op and latest_op > trough * 1.15   # 바닥에서 명확히 반등
    at_trough = latest_op <= trough * 1.10                          # 아직 바닥권
    n = len(revs) - 1
    rev_cagr = ((revs[-1] / revs[0]) ** (1 / n) - 1) if (revs[0] > 0 and n > 0) else None
    structural = (rev_cagr is not None and rev_cagr < -0.02 and latest_op < prev_op)
    # 순환성: '실제 하락 사이클'이 있었을 때만(단순 우상향 성장주가 진폭만으로 순환 오분류되는 것 방지)
    had_decline = any(ops[i] < ops[i - 1] * 0.8 for i in range(1, len(ops)))
    cyclical = had_decline and (trough <= 0 or (peak > 0 and trough > 0 and peak / trough >= 2.5))
    survivable = ((debt_ratio is None or debt_ratio < 200)
                  and (op_positive or (cfo is not None and cfo > 0)))

    if op_positive and not structural and (rebounding or latest_op >= peak * 0.8):
        phase = "정상·양호"
    elif structural and not rebounding:
        phase = "구조적 쇠퇴 의심"
    elif (rebounding or (at_trough and cyclical)) and survivable:
        phase = "순환 바닥 → 회복 신호" if rebounding else "순환 바닥 (회복 대기)"
    elif not survivable:
        phase = "재무 취약 (가치 함정 주의)"
    else:
        phase = "일시 부진"

    signals = {"op_positive": op_positive, "rebounding": rebounding, "at_trough": at_trough,
               "rev_cagr_pct": round(rev_cagr * 100, 1) if rev_cagr is not None else None,
               "structural": structural, "cyclical": cyclical, "survivable": survivable,
               "debt_ratio": debt_ratio, "pbr": pbr}
    return {"phase": phase, "reason": _build_reason(phase, signals), "signals": signals}


def _build_reason(phase: str, s: dict) -> str:
    bits = []
    bits.append("반등 중" if s["rebounding"] else ("바닥권" if s["at_trough"] else "추세 안정"))
    if s["structural"]:
        bits.append(f"매출 다년 우하향({s['rev_cagr_pct']}%)")
    elif s["cyclical"]:
        bits.append("순환 업종(이익 진폭 큼)")
    bits.append("생존력 양호" if s["survivable"] else "생존력 취약(고부채/적자)")
    if s["pbr"] is not None:
        bits.append(f"PBR {s['pbr']}")
    return " · ".join(bits)


def build_kr_factsheet(code: str) -> str:
    """AI 프롬프트 주입용 — DART·KIS 실데이터 재무 팩트시트(국면 포함). 데이터 없으면 ''."""
    ph = classify_fundamental_phase(code) or {}
    if not ph.get("phase"):
        return ""
    sig = ph.get("signals", {})
    series = ph.get("series", [])

    fcf = ebitda = net_debt = None
    try:
        from dart import get_kr_financials_dart
        fd = get_kr_financials_dart(code) or {}
        fcf, ebitda, net_debt = fd.get("fcf"), fd.get("ebitda"), fd.get("net_debt")
    except Exception:
        pass
    roe = None
    try:
        from data_kr import get_kr_financials_kis
        roe = (get_kr_financials_kis(code) or {}).get("roe")
    except Exception:
        pass

    op_trend = " → ".join(f"{s['y']}:{s['op억'] / 10000:.1f}조" for s in series)
    L = ["[재무 팩트시트 — DART·KIS 실데이터 (추측 금지, 아래 숫자로만 판단)]",
         f"- 재무 국면(결정론): {ph['phase']} — {ph['reason']}",
         f"- 영업이익 추이: {op_trend}"]
    if sig.get("rev_cagr_pct") is not None:
        L.append(f"- 매출 장기성장 CAGR: {sig['rev_cagr_pct']}%")
    if roe is not None:
        L.append(f"- ROE: {roe}%")
    if sig.get("debt_ratio") is not None:
        L.append(f"- 부채비율: {sig['debt_ratio']}%")
    if sig.get("pbr") is not None:
        L.append(f"- PBR: {sig['pbr']} (1.0 미만이면 자산가치 이하)")
    if fcf is not None:
        L.append(f"- FCF(영업현금흐름−CAPEX): {fcf / 1e12:+.1f}조원")
    if ebitda and net_debt is not None:
        L.append(f"- EBITDA: {ebitda / 1e12:.1f}조 / 순부채: {net_debt / 1e12:+.1f}조 (음수=순현금)")
    L.append("※ '순환 바닥'이면 현 부진이 사이클 저점일 수 있으니 '구조적 쇠퇴'와 구분해 판단하고, "
             "'구조적 쇠퇴 의심'·'재무 취약'이면 보수적으로 차감하세요. 재무 수치를 지어내지 말 것.")
    return "\n".join(L)


# ── US (yfinance) 경로 ────────────────────────────────────────────────────────
def _yf_income_series(ticker: str) -> list:
    """yfinance income_stmt(연간) → [{year, revenue, op}] 오름차순(과거→최근)."""
    import yfinance as yf
    try:
        fin = yf.Ticker(ticker).income_stmt
    except Exception:
        return []
    if fin is None or getattr(fin, "empty", True):
        return []
    out = []
    for c in reversed(list(fin.columns)):   # 컬럼은 최신순 → 과거순으로
        try:
            rev = fin.loc["Total Revenue", c] if "Total Revenue" in fin.index else None
            op = fin.loc["Operating Income", c] if "Operating Income" in fin.index else None
            if rev is not None and op is not None and rev == rev and op == op:  # NaN 제외
                out.append({"year": str(c)[:4], "revenue": float(rev), "op": float(op)})
        except Exception:
            pass
    return out


def classify_us_phase(ticker: str) -> dict:
    """US 재무 국면 분류(yfinance). {phase, reason, signals, series}."""
    series = _yf_income_series(ticker)
    if len(series) < 3:
        return {"phase": None, "reason": "다년 재무 데이터 부족", "signals": {}, "series": series}
    ops = [s["op"] for s in series]
    revs = [s["revenue"] for s in series]
    info = {}
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception:
        pass
    pbr = round(info["priceToBook"], 2) if info.get("priceToBook") else None
    core = _classify_core(ops, revs, info.get("debtToEquity"), pbr, info.get("operatingCashflow"))
    core["series"] = [{"y": s["year"], "op_b": round(s["op"] / 1e9, 1)} for s in series]
    return core


def build_us_factsheet(ticker: str) -> str:
    """AI 프롬프트 주입용 — yfinance 실데이터 재무 팩트시트(국면 포함). 데이터 없으면 ''."""
    ph = classify_us_phase(ticker)
    if not ph or not ph.get("phase"):
        return ""
    sig, series = ph["signals"], ph["series"]
    info = {}
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception:
        pass
    fcf, mcap = info.get("freeCashflow"), info.get("marketCap")
    fcfy = (fcf / mcap * 100) if (fcf and mcap) else None
    eve, roe = info.get("enterpriseToEbitda"), info.get("returnOnEquity")

    op_trend = " → ".join(f"{s['y']}:{s['op_b']:+.1f}B" for s in series)
    L = ["[재무 팩트시트 — yfinance 실데이터 (추측 금지, 아래 숫자로만 판단)]",
         f"- 재무 국면(결정론): {ph['phase']} — {ph['reason']}",
         f"- 영업이익 추이($B): {op_trend}"]
    if sig.get("rev_cagr_pct") is not None:
        L.append(f"- 매출 장기성장 CAGR: {sig['rev_cagr_pct']}%")
    if roe is not None:
        L.append(f"- ROE: {round(roe * 100, 1)}%")
    if sig.get("pbr") is not None:
        L.append(f"- PBR: {sig['pbr']} (1.0 미만이면 자산가치 이하)")
    if fcfy is not None:
        L.append(f"- FCF Yield: {fcfy:+.1f}%")
    if eve is not None:
        L.append(f"- EV/EBITDA: {round(eve, 1)}")
    L.append("※ '순환 바닥'이면 현 부진이 사이클 저점일 수 있으니 '구조적 쇠퇴'와 구분해 판단하고, "
             "'구조적 쇠퇴 의심'·'재무 취약'이면 보수적으로 차감하세요. 재무 수치를 지어내지 말 것.")
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv; load_dotenv()
    for code in (sys.argv[1:] or ["005930", "000270", "005490"]):
        r = classify_fundamental_phase(code)
        line = f"{code}: [{r['phase']}] {r['reason']}  series={r['series']}"
        sys.stdout.buffer.write((line + "\n").encode("utf-8"))
