# data_kr v4
import requests
import streamlit as st
import pandas as pd

KIS_BASE = "https://openapi.koreainvestment.com:9443"


@st.cache_data(ttl=43200)  # 12시간 캐싱 (KIS 토큰 유효기간 24시간)
def get_kis_token():
    """KIS Open API 액세스 토큰 발급"""
    try:
        resp = requests.post(
            f"{KIS_BASE}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": st.secrets["kis"]["app_key"],
                "appsecret": st.secrets["kis"]["app_secret"],
            },
            timeout=10,
        )
        data = resp.json()
        return data.get("access_token")
    except Exception:
        return None


def _headers(tr_id: str) -> dict:
    token = get_kis_token()
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": st.secrets["kis"]["app_key"],
        "appsecret": st.secrets["kis"]["app_secret"],
        "tr_id": tr_id,
        "custtype": "P",
    }


def _get(path: str, tr_id: str, params: dict):
    """KIS API GET 요청 공통 함수. 실패 시 None 반환."""
    try:
        resp = requests.get(
            f"{KIS_BASE}{path}",
            headers=_headers(tr_id),
            params=params,
            timeout=10,
        )
        data = resp.json()
        return data if data.get("rt_cd") == "0" else None
    except Exception:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def get_kr_fdr_sector_map() -> dict:
    """FDR 업종 컬럼으로 KOSPI+KOSDAQ 전종목 자동 섹터맵 생성.

    반환: {업종대분류: {업종소분류: [{name, code, suffix}]}}
    섹터 컬럼이 없어도 전종목을 '기타'로 포함.
    """
    try:
        import FinanceDataReader as fdr
        import pandas as pd
        frames = []
        for market, suffix in [("KOSPI", ".KS"), ("KOSDAQ", ".KQ")]:
            try:
                df = fdr.StockListing(market).copy()
                df["_suffix"] = suffix
                frames.append(df)
            except Exception:
                continue
        if not frames:
            return {}
        all_df = pd.concat(frames, ignore_index=True)

        cols = {c.lower(): c for c in all_df.columns}
        name_col   = cols.get("name",     cols.get("종목명", None))
        code_col   = cols.get("code",     cols.get("symbol", cols.get("종목코드", None)))
        sector_col = cols.get("sector",   cols.get("업종",   None))
        ind_col    = cols.get("industry", cols.get("세부업종", None))

        if not name_col or not code_col:
            return {}

        result: dict = {}
        for _, row in all_df.iterrows():
            name   = str(row.get(name_col, "")).strip()
            code   = str(row.get(code_col, "")).strip()
            suffix = str(row.get("_suffix", ".KS"))
            sector = str(row.get(sector_col, "") if sector_col else "").strip() or "기타"
            sub    = str(row.get(ind_col, "") if ind_col else "").strip() or sector

            if not name or not code or len(code) != 6 or not code.isdigit():
                continue
            result.setdefault(sector, {}).setdefault(sub, []).append(
                {"name": name, "code": code, "suffix": suffix}
            )
        return result
    except Exception:
        return {}


@st.cache_data(ttl=86400)
def get_kr_name_to_code_map() -> dict:
    """전체 KOSPI+KOSDAQ 종목 이름→{code, suffix} 맵 반환 (24시간 캐시).

    정적 JSON → FinanceDataReader → pykrx → KRX 직접 API 순으로 시도.
    해외 서버(Streamlit Cloud)에서도 동작하도록 여러 소스를 시도한다.
    """
    result: dict = {}

    # 0차: 번들된 정적 JSON (네트워크 불필요, 최우선)
    try:
        import json, os
        _static = os.path.join(os.path.dirname(__file__), "kr_stocks_static.json")
        with open(_static, "r", encoding="utf-8") as f:
            result = json.load(f)
        if result:
            return result
    except Exception:
        pass

    # 1차: FinanceDataReader (해외 서버에서도 동작)
    try:
        import FinanceDataReader as fdr
        for market, suffix in [("KOSPI", ".KS"), ("KOSDAQ", ".KQ")]:
            df = fdr.StockListing(market)
            for _, row in df.iterrows():
                name = str(row.get("Name", "")).strip()
                code = str(row.get("Code", "")).strip()
                if name and code and len(code) == 6 and code.isdigit():
                    result[name] = {"code": code, "suffix": suffix}
        if result:
            return result
    except Exception:
        pass

    # 2차: pykrx
    try:
        from pykrx import stock as _pykrx
        import datetime
        today = datetime.date.today().strftime("%Y%m%d")
        for market, suffix in [("KOSPI", ".KS"), ("KOSDAQ", ".KQ")]:
            tickers = _pykrx.get_market_ticker_list(today, market=market)
            for ticker in tickers:
                name = _pykrx.get_market_ticker_name(ticker)
                if name:
                    result[name] = {"code": ticker, "suffix": suffix}
        if result:
            return result
    except Exception:
        pass

    # 3차: KRX 공개 API (해외 IP 차단 가능성 있음)
    try:
        for mkt_id, suffix in [("STK", ".KS"), ("KSQ", ".KQ")]:
            resp = requests.post(
                "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
                data={
                    "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",
                    "locale": "ko_KR",
                    "mktId": mkt_id,
                    "share": "1",
                    "money": "1",
                    "csvxls_isNo": "false",
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "http://data.krx.co.kr/",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=15,
            )
            for item in resp.json().get("output", []):
                name = item.get("ISU_ABBRV", "").strip()
                code = item.get("ISU_SRT_CD", "").strip()
                if name and code and len(code) == 6 and code.isdigit():
                    result[name] = {"code": code, "suffix": suffix}
        if result:
            return result
    except Exception:
        pass

    raise RuntimeError("전종목 맵 로딩 실패 (FDR·pykrx·KRX 모두 실패)")

@st.cache_data(ttl=86400)
def get_kr_code_to_name_map() -> dict:
    """전체 KOSPI+KOSDAQ 종목 코드→이름 맵 반환 (24시간 캐시)."""
    name_to_code = get_kr_name_to_code_map()
    return {v["code"]: k for k, v in name_to_code.items()}


def get_kr_stock_name_kis(stock_code: str) -> tuple:
    """KIS API로 종목명 조회. (종목명 or None, 오류메시지) 반환. 캐시 없음."""
    try:
        token = get_kis_token()
        resp = requests.get(
            f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers={
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {token}",
                "appkey": st.secrets["kis"]["app_key"],
                "appsecret": st.secrets["kis"]["app_secret"],
                "tr_id": "FHKST01010100",
                "custtype": "P",
            },
            params={"fid_cond_mrkt_div_code": "J", "fid_input_iscd": stock_code},
            timeout=10,
        )
        data = resp.json()
        if data.get("rt_cd") == "0":
            return data["output"].get("hts_kor_isnm") or None, ""
        return None, data.get("msg1", f"rt_cd={data.get('rt_cd','?')}")
    except Exception as e:
        return None, str(e)


def _format_market_cap(amt_in_eok):
    if not amt_in_eok or amt_in_eok == '-':
        return '-'
    # 콤마 제거 후 숫자 여부 확인
    s_amt = str(amt_in_eok).replace(',', '')
    if not s_amt.isdigit():
        return str(amt_in_eok)
    
    amt = int(s_amt)
    jo = amt // 10000
    eok = amt % 10000
    
    if jo > 0:
        if eok == 0:
            return f"{jo:,}조"
        return f"{jo:,}조 {eok:,}억"
    return f"{amt:,}억"


@st.cache_data(ttl=60)
def get_kr_stock_price(stock_code: str):
    """국내 주식 현재가 및 기본 정보 조회 (KIS API → yfinance 폴백, 1분 캐싱)"""
    stock_code = str(stock_code) if stock_code else ""
    if stock_code.isdigit():
        stock_code = stock_code.zfill(6)  # 5자리 코드 앞에 0 채움 (e.g. 48770 → 048770)
    data = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        "FHKST01010100",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": stock_code},
    )
    if data:
        o = data["output"]
        return {
            "code": stock_code,
            "name": o.get("hts_kor_isnm", stock_code),
            "price": int(o.get("stck_prpr", 0) or 0),
            "change": int(o.get("prdy_vrss", 0) or 0),
            "change_pct": float(o.get("prdy_ctrt", 0) or 0),
            "sign": o.get("prdy_vrss_sign", "3"),
            "volume": int(o.get("acml_vol", 0) or 0),
            "amount": int(o.get("acml_tr_pbmn", 0) or 0),
            "open": int(o.get("stck_oprc", 0) or 0),
            "high": int(o.get("stck_hgpr", 0) or 0),
            "low": int(o.get("stck_lwpr", 0) or 0),
            "w52_high": int(o.get("w52_hgpr", 0) or 0),
            "w52_low": int(o.get("w52_lwpr", 0) or 0),
            "per": o.get("per", "-"),
            "pbr": o.get("pbr", "-"),
            "market_cap": _format_market_cap(o.get("hts_avls", "")),
            "status_code": o.get("iscd_stat_cls_code", "55"),
            "mrkt_warn": o.get("mrkt_warn_cls_code", "00"),
            "short_over": o.get("sltr_yn", "N"),
            "managed": o.get("mang_issu_cls_code", "N"),   # 실제 필드명
            "halt": o.get("temp_stop_yn", "N"),             # 실제 필드명
            "vi_type": o.get("vi_cls_code", "N"),           # "N"=없음
            "vi_ovtm": o.get("ovtm_vi_cls_code", "N"),     # 시간외 VI
        }

    # KIS API 실패 → yfinance 폴백 (.KS 우선, .KQ 차선)
    import yfinance as yf
    for suffix in [".KS", ".KQ"]:
        try:
            tk = yf.Ticker(f"{stock_code}{suffix}")
            fi = tk.fast_info
            info = tk.info
            price = round(fi.get("lastPrice", 0) or 0)
            prev  = fi.get("previousClose", 0) or 0
            if price <= 0:
                continue
            change     = round(price - prev)
            change_pct = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
            sign = "2" if change > 0 else "4" if change < 0 else "3"
            name = (info.get("shortName") or info.get("longName") or stock_code)
            return {
                "code": stock_code,
                "name": name,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "sign": sign,
                "volume": int(fi.get("lastVolume", 0) or 0),
                "amount": 0,
                "open":     round(fi.get("open", 0) or 0),
                "high":     round(fi.get("dayHigh", 0) or 0),
                "low":      round(fi.get("dayLow", 0) or 0),
                "w52_high": round(fi.get("fiftyTwoWeekHigh", 0) or 0),
                "w52_low":  round(fi.get("fiftyTwoWeekLow", 0) or 0),
                "per": round(info.get("trailingPE", 0) or 0, 1) or "-",
                "pbr": round(info.get("priceToBook", 0) or 0, 2) or "-",
                "market_cap": _format_market_cap(info.get("marketCap", 0) // 100000000) if info.get("marketCap") else "-",
                "_source": "yfinance",
            }
        except Exception:
            continue
    return None


@st.cache_data(ttl=300, show_spinner=False)
def _get_kr_shares_map() -> dict:
    """KOSPI+KOSDAQ 전 종목 코드→발행주식수 맵 (FDR, 24h 캐시)"""
    try:
        import FinanceDataReader as fdr
        result = {}
        for mkt in ["KOSPI", "KOSDAQ"]:
            df = fdr.StockListing(mkt)
            if "Code" in df.columns and "Stocks" in df.columns:
                for _, row in df.iterrows():
                    code = str(row["Code"]).zfill(6)
                    shares = int(row.get("Stocks", 0) or 0)
                    if shares > 0:
                        result[code] = shares
        return result
    except Exception:
        return {}


@st.cache_data(ttl=60)
def get_kr_investor_trend(stock_code: str):
    """종목별 외국인/기관/개인 순매수 동향 (최근 5영업일)
    KIS API → 네이버 금융 차트 API(외국인 보유율 변화 기반 추정) 순으로 시도."""
    # 1차: KIS API
    data = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-investor",
        "FHKST01010900",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": stock_code},
    )
    if data:
        results = []
        for item in data.get("output", [])[:5]:
            d = item.get("stck_bsop_date", "")
            if len(d) == 8:
                d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            results.append({
                "날짜": d,
                "개인": int(item.get("prsn_ntby_qty", 0) or 0),
                "외국인": int(item.get("frgn_ntby_qty", 0) or 0),
                "기관": int(item.get("orgn_ntby_qty", 0) or 0),
            })
        return results

    # 2차 폴백: 네이버 금융 차트 API — 외국인 보유율 변화로 순매수 추정
    try:
        import datetime as _dt2, requests as _req2
        _today = _dt2.date.today()
        _start = (_today - _dt2.timedelta(days=14)).strftime("%Y%m%d") + "000000"
        _end = _today.strftime("%Y%m%d") + "235959"
        _url = (
            f"https://api.stock.naver.com/chart/domestic/item/{stock_code}/day"
            f"?startDateTime={_start}&endDateTime={_end}"
        )
        _resp = _req2.get(_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://finance.naver.com/",
        }, timeout=4)
        if _resp.status_code == 200:
            _rows = _resp.json()
            _rows = sorted(_rows, key=lambda x: x.get("localDate", ""))
            # 발행주식수 조회 (FDR 캐시)
            _shares_map = _get_kr_shares_map()
            _total_shares = _shares_map.get(stock_code.zfill(6), 0)
            results = []
            for i in range(1, len(_rows)):
                _prev_r = _rows[i - 1].get("foreignRetentionRate") or 0
                _cur_r  = _rows[i].get("foreignRetentionRate") or 0
                _rate_chg = float(_cur_r) - float(_prev_r)
                _frgn = int(_rate_chg * _total_shares / 100) if _total_shares > 0 else 0
                _d = str(_rows[i].get("localDate", ""))
                if len(_d) == 8:
                    _d = f"{_d[:4]}-{_d[4:6]}-{_d[6:]}"
                results.append({
                    "날짜": _d,
                    "외국인": _frgn,
                    "기관": 0,
                    "개인": 0,
                    "_estimated": True,  # 추정값 표시용 플래그
                })
            # 최신 5거래일만 반환
            return list(reversed(results))[:5]
    except Exception:
        pass

    return []


@st.cache_data(ttl=60)
def get_kr_market_index():
    """KOSPI / KOSDAQ 지수 실시간 조회 (KIS → yfinance 폴백)"""
    result = {}
    for name, code in [("KOSPI", "0001"), ("KOSDAQ", "1001")]:
        data = _get(
            "/uapi/domestic-stock/v1/quotations/inquire-index-price",
            "FHPUP02100000",
            {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": code},
        )
        if data:
            o = data["output"]
            _idx = float(o.get("bstp_nmix_prpr", 0) or 0)
            _chg = float(o.get("bstp_nmix_prdy_vrss", 0) or 0)
            # prdy_ctrt 필드가 0으로 오는 경우 직접 계산
            _pct = float(o.get("bstp_nmix_prdy_ctrt", 0) or o.get("prdy_ctrt", 0) or 0)
            if _pct == 0 and _idx > 0 and _chg != 0:
                _prev = _idx - _chg
                _pct = round(_chg / _prev * 100, 2) if _prev > 0 else 0.0
            result[name] = {
                "index": _idx,
                "change": _chg,
                "change_pct": _pct,
            }

    # KIS 실패 시 yfinance 폴백 (^KS11=KOSPI, ^KQ11=KOSDAQ)
    if len(result) < 2:
        import yfinance as yf
        for _idx_name, _yf_sym in [("KOSPI", "^KS11"), ("KOSDAQ", "^KQ11")]:
            if _idx_name in result:
                continue
            try:
                _fi = yf.Ticker(_yf_sym).fast_info
                _price = _fi.get("lastPrice", 0) or 0
                _prev = _fi.get("previousClose", 0) or 0
                if _price > 0:
                    _chg = round(_price - _prev, 2)
                    _pct = round(_chg / _prev * 100, 2) if _prev > 0 else 0.0
                    result[_idx_name] = {"index": _price, "change": _chg, "change_pct": _pct}
            except Exception:
                pass
    return result


def _kis_minute_chart_raw(stock_code: str) -> pd.DataFrame:
    """KIS API 1분봉 원시 데이터 (당일 장 전체, 최대 14회 호출 × 30봉 = ~420봉)"""
    from datetime import datetime as _dt
    import pytz as _pytz
    _now = _dt.now(_pytz.timezone("Asia/Seoul"))
    _today = _now.strftime("%Y%m%d")
    _query_time = min(_now.strftime("%H%M%S"), "153000")

    all_rows: list = []
    _target_date = None
    for _ in range(14):
        data = _get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            "FHKST03010200",
            {
                "FID_ETC_CLS_CODE": "",
                "FID_INPUT_ISCD": stock_code,
                "FID_INPUT_HOUR_1": _query_time,
                "FID_PW_DATA_INCU_YN": "Y",
            },
        )
        if not data:
            break
            
        output2 = data.get("output2") or []
        if not output2:
            break
            
        if _target_date is None:
            _target_date = output2[0].get("stck_bsop_date")
            if not _target_date:
                break
                
        rows = [r for r in output2 if r.get("stck_bsop_date") == _target_date]
        if not rows:
            break
        all_rows.extend(rows)
        earliest = min(r.get("stck_cntg_hour", "235959") for r in rows)
        if earliest <= "090000":
            break
        h, m = int(earliest[:2]), int(earliest[2:4])
        total_min = h * 60 + m - 1
        _query_time = f"{total_min // 60:02d}{total_min % 60:02d}00"

    if not all_rows:
        return pd.DataFrame()

    parsed = []
    for r in all_rows:
        try:
            d, t = r.get("stck_bsop_date", ""), r.get("stck_cntg_hour", "")
            if not d or not t:
                continue
            parsed.append({
                "datetime": pd.to_datetime(f"{d} {t[:2]}:{t[2:4]}:{t[4:6]}"),
                "open":   float(r.get("stck_oprc") or 0),
                "high":   float(r.get("stck_hgpr") or 0),
                "low":    float(r.get("stck_lwpr") or 0),
                "close":  float(r.get("stck_prpr") or 0),
                "volume": int(r.get("cntg_vol") or 0),
            })
        except Exception:
            continue

    if not parsed:
        return pd.DataFrame()

    import datetime as _dtm
    df = pd.DataFrame(parsed)
    df = df.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)
    df = df[
        (df["datetime"].dt.time >= _dtm.time(9, 0)) &
        (df["datetime"].dt.time <= _dtm.time(15, 30))
    ]
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _kis_daily_chart_raw(stock_code: str, start_yyyymmdd: str, end_yyyymmdd: str, unit: str = "D") -> pd.DataFrame:
    """KIS API 일봉 데이터 (최대 10회 호출 × 100봉 = ~1000봉)"""
    all_rows: list = []
    query_end = end_yyyymmdd
    for _ in range(10):
        data = _get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            "FHKST03010100",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": stock_code,
                "FID_INPUT_DATE_1": start_yyyymmdd,
                "FID_INPUT_DATE_2": query_end,
                "FID_PERIOD_DIV_CODE": unit,
                "FID_ORG_ADJ_PRC": "1",
            },
        )
        if not data:
            break
        rows = data.get("output2") or []
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 100:
            break
        from datetime import datetime as _dt2, timedelta as _td2
        earliest = min((r.get("stck_bsop_date") or "99999999") for r in rows)
        prev = (_dt2.strptime(earliest, "%Y%m%d") - _td2(days=1)).strftime("%Y%m%d")
        if prev < start_yyyymmdd:
            break
        query_end = prev

    if not all_rows:
        return pd.DataFrame()

    parsed = []
    for r in all_rows:
        try:
            d = r.get("stck_bsop_date", "")
            if not d:
                continue
            parsed.append({
                "datetime": pd.to_datetime(d, format="%Y%m%d"),
                "open":   float(r.get("stck_oprc") or 0),
                "high":   float(r.get("stck_hgpr") or 0),
                "low":    float(r.get("stck_lwpr") or 0),
                "close":  float(r.get("stck_clpr") or 0),
                "volume": int(r.get("acml_vol") or 0),
            })
        except Exception:
            continue

    if not parsed:
        return pd.DataFrame()

    df = pd.DataFrame(parsed)
    df = df.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)
    return df.dropna(subset=["open", "high", "low", "close"])


@st.cache_data(ttl=60)
def get_kr_minute_chart(stock_code: str, interval: int = 5):
    """국내 주식 분봉 OHLCV — KIS(오늘) + yfinance(이전 날짜) 합산, 줌아웃 지원"""
    import datetime as _dtm
    import yfinance as yf
    from datetime import datetime as _dt
    import pytz as _pytz

    _now_kr = _dt.now(_pytz.timezone("Asia/Seoul")).replace(tzinfo=None)
    _today = _now_kr.date()

    # ── yfinance 기간 설정 ────────────────────────────────────────────────────
    if interval <= 1:
        yf_interval, period = "1m",  "5d"
    elif interval <= 5:
        yf_interval, period = "5m",  "30d"
    elif interval <= 15:
        yf_interval, period = "15m", "60d"
    else:
        yf_interval, period = "30m", "60d"

    # ── 1차: yfinance 데이터 (과거 + 오늘 일부 포함 가능) ──────────────────────────
    df_all = pd.DataFrame()
    for suffix in [".KS", ".KQ"]:
        try:
            raw = yf.Ticker(f"{stock_code}{suffix}").history(
                period=period, interval=yf_interval, auto_adjust=True
            )
            if raw.empty:
                continue
            if raw.index.tz is not None:
                raw.index = raw.index.tz_convert("Asia/Seoul").tz_localize(None)
            tmp = raw.reset_index()
            dt_col = next((c for c in tmp.columns if str(c).lower() in ("datetime", "date", "index")), None)
            if dt_col:
                tmp = tmp.rename(columns={dt_col: "datetime"})
                tmp.columns = [str(c).lower().strip() for c in tmp.columns]
                needed = ["datetime", "open", "high", "low", "close", "volume"]
                if all(c in tmp.columns for c in needed):
                    df_all = tmp[needed].copy()
                    break
        except Exception:
            continue

    # ── 2차: KIS API 오늘 실시간 데이터 ─────────────────────────────────────────────
    df_kis = pd.DataFrame()
    try:
        df_kis = _kis_minute_chart_raw(stock_code)
    except Exception:
        pass

    # ── 데이터 병합 (중복 제거 및 정렬) ───────────────────────────────────────────
    df = pd.concat([df_all, df_kis]).drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)
    
    if df.empty:
        return pd.DataFrame()

    # ── 장중 시간대 필터링 (9:00 ~ 15:30) ──────────────────────────────────────────
    df = df[
        (df["datetime"].dt.time >= _dtm.time(9, 0)) &
        (df["datetime"].dt.time <= _dtm.time(15, 30))
    ].copy()

    # ── 리샘플링 (원하는 분봉 단위로 변환) ─────────────────────────────────────────
    if interval > 1:
        # 시간축 기준을 9:00에 맞추기 위해 origin='start' 사용 고려 가능하나, 기본값도 보통 정시 기준
        df = df.set_index("datetime").resample(f"{interval}min").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna().reset_index()

    # ── 미래 데이터 및 중복 제거 최종 확인 ─────────────────────────────────────────
    df = df[df["datetime"] <= (_now_kr + _dtm.timedelta(minutes=1))].reset_index(drop=True)
    return df


@st.cache_data(ttl=90, show_spinner=False)
def get_kr_prebreakout_signal(stock_code: str) -> dict:
    """
    5분봉 데이터로 급등 직전 신호를 계산합니다.

    반환 필드:
      vol_accel   - 최근 30분 거래량 / 직전 30분 거래량 비율 (>2.0이면 급증)
      vol_ratio   - 오늘 전체 거래량 / 전일 동시간대 거래량 비율
      consol_break- 박스권 돌파 여부 (최근 6봉 고점 대비 현재가 위치)
      ma5_cross   - 현재가 > 5분봉 MA20 여부 (단기 추세 전환)
      candle_seq  - 최근 3봉 연속 양봉 여부
      signal_score- 0~5 점수 (높을수록 급등 직전 패턴)
      signal_label- 패턴 요약 텍스트
    """
    df = get_kr_minute_chart(stock_code, interval=5)
    if df.empty or len(df) < 12:
        return {"signal_score": 0, "signal_label": "데이터 부족", "vol_accel": 0}

    # ── 오늘 장중 데이터만 사용 ──
    from datetime import datetime as _dt
    import pytz as _pytz
    _now  = _dt.now(_pytz.timezone("Asia/Seoul")).replace(tzinfo=None)
    today = df[df["datetime"].dt.date == _now.date()].copy()
    if today.empty or len(today) < 6:
        return {"signal_score": 0, "signal_label": "장중 데이터 부족", "vol_accel": 0}

    today = today.reset_index(drop=True)
    n = len(today)

    # 1. 거래량 가속도: 최근 6봉(30분) vs 직전 6봉(30분)
    recent_vol = today["volume"].iloc[max(n-6, 0):].sum()
    prev_vol   = today["volume"].iloc[max(n-12, 0):max(n-6, 0)].sum()
    vol_accel  = round(recent_vol / prev_vol, 2) if prev_vol > 0 else 0.0

    # 2. 오늘 전체 거래량 vs 직전 데이터 평균 (같은 시간대 비교)
    all_today_vol = today["volume"].sum()
    prev_days = df[df["datetime"].dt.date < _now.date()]
    vol_ratio = 0.0
    if not prev_days.empty:
        cutoff_time = today["datetime"].iloc[-1].time()
        prev_same   = prev_days[prev_days["datetime"].dt.time <= cutoff_time]
        if not prev_same.empty:
            avg_prev = prev_same.groupby(prev_same["datetime"].dt.date)["volume"].sum().mean()
            vol_ratio = round(all_today_vol / avg_prev, 2) if avg_prev > 0 else 0.0

    # 3. 박스권 돌파 여부 (최근 6봉 고점 vs 현재가)
    box_high     = today["high"].iloc[max(n-7, 0):n-1].max() if n > 2 else 0
    cur_close    = today["close"].iloc[-1]
    consol_break = cur_close > box_high if box_high > 0 else False

    # 4. 단기 이평선(MA20봉) 위에 있는지
    ma20      = today["close"].rolling(20).mean().iloc[-1] if n >= 20 else today["close"].mean()
    ma5       = today["close"].rolling(5).mean().iloc[-1]  if n >= 5  else today["close"].mean()
    above_ma  = cur_close > ma20 and cur_close > ma5

    # 5. 최근 3봉 연속 양봉
    if n >= 3:
        last3 = today.iloc[-3:]
        candle_seq = all(last3["close"].values > last3["open"].values)
    else:
        candle_seq = False

    # 6. 종합 점수 (0~5)
    score = 0
    notes = []
    if vol_accel >= 2.5:
        score += 2
        notes.append(f"거래량가속 {vol_accel:.1f}x")
    elif vol_accel >= 1.5:
        score += 1
        notes.append(f"거래량증가 {vol_accel:.1f}x")

    if vol_ratio >= 3.0:
        score += 1
        notes.append(f"전일比 {vol_ratio:.1f}x")

    if consol_break:
        score += 1
        notes.append("박스권돌파")

    if candle_seq:
        score += 1
        notes.append("연속양봉")

    label = " · ".join(notes) if notes else "시그널 없음"

    return {
        "code":          stock_code,
        "vol_accel":     vol_accel,
        "vol_ratio":     vol_ratio,
        "consol_break":  consol_break,
        "above_ma":      above_ma,
        "candle_seq":    candle_seq,
        "signal_score":  score,
        "signal_label":  label,
        "cur_price":     int(cur_close),
    }


@st.cache_data(ttl=60, show_spinner=False)
def get_kr_prices_bulk(tickers_tuple: tuple) -> dict:
    """섹터 패널용 종목 일괄 시세 조회 (code → {price, change_pct, + 거래상태 필드}).
    KIS API inquire-price 우선, 실패 시 yfinance 폴백."""
    import yfinance as yf
    results = {}
    for code, yf_ticker in tickers_tuple:
        # 1차: KIS API (캐시 활용 — get_kr_stock_price 내부에 @st.cache_data 있음)
        kis = get_kr_stock_price(code)
        _kis_status = {}
        if kis:
            _kis_status = {
                "status_code": kis.get("status_code", "55"),
                "mrkt_warn":   kis.get("mrkt_warn", "00"),
                "short_over":  kis.get("short_over", "N"),
                "managed":     kis.get("managed", "N"),
                "halt":        kis.get("halt", "N"),
                "vi_type":     kis.get("vi_type", "N"),
                "vi_ovtm":     kis.get("vi_ovtm", "N"),
            }
            if kis.get("price", 0) > 0:
                results[code] = {"price": kis["price"], "change_pct": kis["change_pct"], **_kis_status}
                continue
        # 2차: yfinance 폴백 (거래정지 등 price=0 포함, KIS 상태 필드는 유지)
        try:
            fi = yf.Ticker(yf_ticker).fast_info
            price = round(fi.get("lastPrice", 0) or 0)
            reg_price = round(fi.get("regularMarketPrice", 0) or price)
            prev = fi.get("regularMarketPreviousClose", 0) or fi.get("previousClose", 0) or 0
            change_pct = round(((reg_price - prev) / prev * 100) if prev > 0 else 0.0, 2)
            results[code] = {"price": price, "change_pct": change_pct, **_kis_status}
        except Exception:
            results[code] = {"price": 0, "change_pct": 0.0, **_kis_status}
    return results


# ── 미국 주식 KIS API ────────────────────────────────────────────────────────
# 거래소 코드: sectors_us.py exchange → KIS EXCD
_KIS_EXCD = {"NASDAQ": "NAS", "NYSE": "NYS", "AMEX": "AMS"}


@st.cache_data(ttl=60)
def get_us_stock_price_kis(ticker: str, exchange: str = "NASDAQ"):
    """KIS API 해외주식 현재가 → yfinance 폴백"""
    excd = _KIS_EXCD.get(exchange.upper(), "NAS")
    data = _get(
        "/uapi/overseas-price/v1/quotations/price",
        "HHDFS76200200",
        {"AUTH": "", "EXCD": excd, "SYMB": ticker},
    )
    if data:
        o = data.get("output", {})
        price = float(o.get("last", 0) or 0)
        if price > 0:
            return {
                "name":       (o.get("name") or ticker).strip(),
                "price":      price,
                "change":     float(o.get("diff", 0) or 0),
                "change_pct": float(o.get("rate", 0) or 0),
                "sign":       o.get("sign", "3"),
                "volume":     int(o.get("tvol", 0) or 0),
                "open":       float(o.get("open", 0) or 0),
                "high":       float(o.get("high", 0) or 0),
                "low":        float(o.get("low", 0) or 0),
                "w52_high":   float(o.get("h52p", 0) or 0),
                "w52_low":    float(o.get("l52p", 0) or 0),
                "per":        o.get("perx", "-") or "-",
                "pbr":        o.get("pbry", "-") or "-",
                "market_cap": "-",
                "exchange":   exchange,
                "_source":    "kis",
            }
    # KIS 실패 → yfinance 폴백
    import yfinance as yf
    try:
        tk   = yf.Ticker(ticker)
        fi   = tk.fast_info
        info = tk.info
        p    = round(fi.get("lastPrice", 0) or 0, 2)
        prev = fi.get("previousClose", 0) or 0
        if p > 0:
            ch  = round(p - prev, 2)
            chp = round((ch / prev * 100) if prev > 0 else 0, 2)
            mktcap = info.get("marketCap", 0) or 0
            return {
                "name":       info.get("longName", ticker),
                "price":      p,
                "change":     ch,
                "change_pct": chp,
                "sign":       "2" if ch > 0 else "4" if ch < 0 else "3",
                "volume":     int(fi.get("lastVolume", 0) or 0),
                "open":       round(fi.get("open", 0) or 0, 2),
                "high":       round(fi.get("dayHigh", 0) or 0, 2),
                "low":        round(fi.get("dayLow", 0) or 0, 2),
                "w52_high":   round(fi.get("fiftyTwoWeekHigh", 0) or 0, 2),
                "w52_low":    round(fi.get("fiftyTwoWeekLow", 0) or 0, 2),
                "per":        round(info.get("trailingPE", 0) or 0, 1) or "-",
                "pbr":        round(info.get("priceToBook", 0) or 0, 2) or "-",
                "market_cap": f"${mktcap/1e9:.1f}B" if mktcap >= 1e9 else "-",
                "exchange":   exchange,
                "_source":    "yfinance",
            }
    except Exception:
        pass
    return None


@st.cache_data(ttl=60)
@st.cache_data(ttl=120)
def get_us_prices_bulk_kis(tickers_exchange_tuple: tuple) -> dict:
    """섹터 패널용 미국 종목 일괄 시세 조회.

    1차: yfinance 배치 다운로드 (청크 200개씩, 최대 5개 병렬) — 빠름
    2차: 누락 종목만 KIS API 병렬 보완
    """
    import yfinance as yf
    import pandas as _pd
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not tickers_exchange_tuple:
        return {}

    tickers      = [t for t, _ in tickers_exchange_tuple]
    exchange_map = {t: e for t, e in tickers_exchange_tuple}
    results: dict = {}

    # ── 1차: yfinance 배치 (청크 200개 × 병렬 5) ──────────────────────
    CHUNK = 200
    chunks = [tickers[i : i + CHUNK] for i in range(0, len(tickers), CHUNK)]

    def _fetch_chunk(chunk: list) -> dict:
        try:
            raw = yf.download(
                chunk,
                period="2d",
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if raw is None or raw.empty:
                return {}
            chunk_res: dict = {}
            cols = raw.columns
            is_multi = isinstance(cols, _pd.MultiIndex)
            for ticker in chunk:
                try:
                    if is_multi:
                        close_s = raw["Close"][ticker].dropna() if ticker in raw["Close"].columns else _pd.Series(dtype=float)
                    else:
                        close_s = raw["Close"].dropna() if len(chunk) == 1 else _pd.Series(dtype=float)
                    if close_s.empty:
                        continue
                    price = round(float(close_s.iloc[-1]), 2)
                    prev  = round(float(close_s.iloc[-2]), 2) if len(close_s) >= 2 else price
                    chp   = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
                    if price > 0:
                        chunk_res[ticker] = {"price": price, "change_pct": chp}
                except Exception:
                    continue
            return chunk_res
        except Exception:
            return {}

    workers = min(len(chunks), 5)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(_fetch_chunk, chunks):
            results.update(res)

    # ── 2차: 누락된 종목만 KIS API 병렬 보완 ─────────────────────────
    missing = [t for t in tickers if t not in results or results[t]["price"] == 0]

    def _kis_one(ticker: str):
        excd = _KIS_EXCD.get(exchange_map.get(ticker, "NASDAQ").upper(), "NAS")
        data = _get(
            "/uapi/overseas-price/v1/quotations/price",
            "HHDFS76200200",
            {"AUTH": "", "EXCD": excd, "SYMB": ticker},
        )
        if data:
            o     = data.get("output", {})
            price = float(o.get("last", 0) or 0)
            if price > 0:
                return ticker, {"price": price, "change_pct": float(o.get("rate", 0) or 0)}
        return ticker, {"price": 0.0, "change_pct": 0.0}

    if missing:
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(_kis_one, t): t for t in missing}
            for fut in as_completed(futs):
                try:
                    ticker, val = fut.result()
                    results[ticker] = val
                except Exception:
                    results[futs[fut]] = {"price": 0.0, "change_pct": 0.0}

    return results


@st.cache_data(ttl=60)  # 5분 -> 1분 단축
def get_kr_volume_ranking():
    """거래량 상위 10개 종목 (KIS API → pykrx 폴백)"""
    # 1차: KIS API
    data = _get(
        "/uapi/domestic-stock/v1/ranking/volume",
        "FHPST01710000",
        {
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20171",
            "fid_input_iscd": "0000",
            "fid_div_cls_code": "0",
            "fid_blng_cls_code": "0",
            "fid_trgt_cls_code": "111111111",
            "fid_trgt_exls_cls_code": "000000000",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_input_date_1": "",
        },
    )
    if data:
        raw_list = data.get("output") or data.get("output1") or []
        if raw_list:
            results = []
            for item in raw_list[:10]:
                change_pct = float(item.get("prdy_ctrt", 0) or 0)
                results.append({
                    "종목코드": item.get("mksc_shrn_iscd", ""),
                    "종목명": item.get("hts_kor_isnm", ""),
                    "현재가": f"₩{int(item.get('stck_prpr', 0) or 0):,}",
                    "등락률(%)": change_pct,
                    "거래량": f"{int(item.get('acml_vol', 0) or 0):,}주",
                    "상태": "상승 🔴" if change_pct > 0 else ("하락 🔵" if change_pct < 0 else "보합 ⚪"),
                })
            return results

    # 2차 폴백: FinanceDataReader (거래량 상위)
    try:
        import FinanceDataReader as fdr
        _df_v = fdr.StockListing("KOSPI")
        _df_v = _df_v.dropna(subset=["Volume", "Close"])
        _df_v = _df_v[_df_v["Volume"] > 0]
        _df_v = _df_v.sort_values("Volume", ascending=False).head(10)
        results = []
        for _, _row in _df_v.iterrows():
            _chg_pct = round(float(_row.get("ChagesRatio", 0) or 0), 2)
            results.append({
                "종목코드": str(_row["Code"]).zfill(6),
                "종목명": str(_row["Name"]),
                "현재가": f"₩{int(_row['Close']):,}",
                "등락률(%)": _chg_pct,
                "거래량": f"{int(_row['Volume']):,}주",
                "상태": "상승 🔴" if _chg_pct > 0 else ("하락 🔵" if _chg_pct < 0 else "보합 ⚪"),
            })
        return results
    except Exception:
        return []


@st.cache_data(ttl=60)
def get_kr_change_ranking(market: str = "J") -> list:
    """등락률 상위 20개 종목 (KIS 랭킹 API, J=KOSPI / Q=KOSDAQ)"""
    data = _get(
        "/uapi/domestic-stock/v1/ranking/fluctuation",
        "FHPST01700000",
        {
            "fid_cond_mrkt_div_code": market,
            "fid_cond_scr_div_code": "20170",
            "fid_input_iscd": "0000",
            "fid_rank_sort_cls_code": "0",   # 0=상승률순
            "fid_input_cnt_1": "0",
            "fid_prc_cls_code": "1",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_trgt_cls_code": "0",
            "fid_trgt_exls_cls_code": "0",
            "fid_div_cls_code": "0",
            "fid_rsfl_rate1": "",
            "fid_rsfl_rate2": "",
        },
    )
    if not data:
        # KIS 실패 → FinanceDataReader 폴백
        try:
            import FinanceDataReader as fdr
            _mkt_name = "KOSPI" if market == "J" else "KOSDAQ"
            _df = fdr.StockListing(_mkt_name)
            _df = _df.dropna(subset=["Close", "ChagesRatio"])
            _df = _df[_df["Close"] > 0]
            _df = _df.sort_values("ChagesRatio", ascending=False).head(20)
            results = []
            for _, _row in _df.iterrows():
                results.append({
                    "종목코드": str(_row["Code"]).zfill(6),
                    "종목명": str(_row["Name"]),
                    "현재가": int(_row["Close"]),
                    "등락률(%)": round(float(_row["ChagesRatio"]), 2),
                    "거래량": int(_row.get("Volume", 0) or 0),
                    "시장": _mkt_name,
                })
            return results
        except Exception:
            return []
    results = []
    for item in data.get("output", [])[:20]:
        change_pct = float(item.get("prdy_ctrt", 0) or 0)
        results.append({
            "종목코드": item.get("stck_shrn_iscd", "") or item.get("mksc_shrn_iscd", ""),
            "종목명": item.get("hts_kor_isnm", ""),
            "현재가": int(item.get("stck_prpr", 0) or 0),
            "등락률(%)": change_pct,
            "거래량": int(item.get("acml_vol", 0) or 0),
            "시장": "KOSPI" if market == "J" else "KOSDAQ",
        })
    return results


@st.cache_data(ttl=300)
def get_kr_daily_chart(stock_code: str, period: str = "3mo", unit: str = "D") -> pd.DataFrame:
    """국내 주식 일/주/월봉 데이터. unit: D, W, M"""
    from datetime import datetime as _dt, timedelta as _td

    _period_days = {
        "1d": 2, "3d": 5, "1w": 8, "15d": 22, "1mo": 35,
        "3mo": 95, "6mo": 185, "1y": 370,
        "2y": 740, "3y": 1100, "5y": 1830, "10y": 3650,
    }
    _days = _period_days.get(period, 95)
    _end_dt  = _dt.now()
    _start_dt = _end_dt - _td(days=_days)
    _start_str = _start_dt.strftime("%Y%m%d")
    _end_str   = _end_dt.strftime("%Y%m%d")

    # ── 1차: KIS API ──────────────────────────────────────────────────────────
    try:
        df = _kis_daily_chart_raw(stock_code, _start_str, _end_str, unit=unit)
        if not df.empty:
            return df
    except Exception:
        pass

    # ── 2차: yfinance 폴백 ────────────────────────────────────────────────────
    import yfinance as yf
    _custom_yf = {"15d", "3y"}
    if period in _custom_yf:
        _hist_kw = {"start": _start_dt.strftime("%Y-%m-%d"), "end": _end_dt.strftime("%Y-%m-%d")}
    else:
        _hist_kw = {"period": period}
    _yf_iv = "1d" if unit == "D" else "1wk" if unit == "W" else "1mo"
    for suffix in [".KS", ".KQ"]:
        try:
            raw = yf.Ticker(f"{stock_code}{suffix}").history(
                **_hist_kw, interval=_yf_iv, auto_adjust=True
            )
            if raw.empty:
                continue
            df = raw.reset_index()
            dt_col = next(
                (c for c in df.columns if str(c).lower() in ("date", "datetime")), None
            )
            if dt_col is None:
                continue
            df = df.rename(columns={dt_col: "datetime"})
            df.columns = [str(c).lower().strip() for c in df.columns]
            needed = ["datetime", "open", "high", "low", "close", "volume"]
            if not all(c in df.columns for c in needed):
                continue
            df["datetime"] = pd.to_datetime(df["datetime"])
            if df["datetime"].dt.tz is not None:
                df["datetime"] = df["datetime"].dt.tz_localize(None)
            return df[needed].dropna(subset=["open", "high", "low", "close"]).copy()
        except Exception:
            continue
    return pd.DataFrame()


@st.cache_data(ttl=60)
def get_kr_index_history(symbol: str, period: str = "1d") -> pd.DataFrame:
    """KOSPI(^KS11) / KOSDAQ(^KQ11) 지수 히스토리 (yfinance)"""
    import yfinance as yf
    _interval_map = {
        "1d":  "5m",
        "5d":  "30m",
        "1mo": "1d",
        "3mo": "1d",
        "1y":  "1d",
    }
    interval = _interval_map.get(period, "1d")
    for _attempt in range(2):
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
            if not df.empty:
                if df.index.tz is not None:
                    df.index = df.index.tz_convert("Asia/Seoul").tz_localize(None)
                df = df.reset_index()
                dt_col = "Datetime" if "Datetime" in df.columns else "Date"
                df = df[[dt_col, "Close"]].rename(columns={dt_col: "datetime", "Close": "close"})
                return df
        except Exception:
            pass
    return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def get_kr_major_tickers() -> list:
    """상단 티커 표시용 주요 국내 종목 시세 (yfinance, 60초 캐시)"""
    import yfinance as yf
    stocks = [
        ("005930", "삼성전자", ".KS"),
        ("000660", "SK하이닉스", ".KS"),
        ("005380", "현대차", ".KS"),
        ("373220", "LG에너지솔루션", ".KS"),
        ("035420", "NAVER", ".KS"),
        ("035720", "카카오", ".KS"),
        ("068270", "셀트리온", ".KS"),
        ("207940", "삼성바이오", ".KS"),
    ]
    results = []
    for code, name, suffix in stocks:
        try:
            fi = yf.Ticker(f"{code}{suffix}").fast_info
            price = round(fi.get("lastPrice") or 0)
            prev  = fi.get("previousClose") or 0
            if price <= 0:
                continue
            pct = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
            results.append({"name": name, "price": price, "pct": pct})
        except Exception:
            continue
    return results


# ── 미국 주식 랭킹 / 분봉 / 신호 ─────────────────────────────────────────────
_US_WATCHLIST = [
    "NVDA","TSLA","AAPL","MSFT","META","AMZN","GOOGL","AMD","PLTR","AVGO",
    "COIN","MSTR","ARM","SMCI","HOOD","INTC","MU","SOFI","RBLX","SNAP",
    "SQ","SHOP","BABA","PDD","TSM","QCOM","AMAT","JPM","BAC","LLY",
]


@st.cache_data(ttl=300, show_spinner=False)
def get_us_volume_ranking() -> list:
    """US 거래량 상위 종목 — watchlist yfinance 배치 조회"""
    import yfinance as yf
    results = []
    for ticker in _US_WATCHLIST:
        try:
            fi = yf.Ticker(ticker).fast_info
            price   = round(fi.get("lastPrice",              0) or 0, 2)
            prev    = fi.get("previousClose",                0) or 0
            vol     = int(fi.get("lastVolume",               0) or 0)
            avg_vol = int(fi.get("threeMonthAverageVolume",  0) or 0)
            if price <= 0 or vol <= 0:
                continue
            chg = round(((price - prev) / prev * 100) if prev > 0 else 0, 2)
            results.append({
                "티커":       ticker,
                "현재가($)":  price,
                "등락률(%)":  chg,
                "거래량":     vol,
                "거래량_비율": round(vol / avg_vol, 2) if avg_vol > 0 else 0,
            })
        except Exception:
            continue
    results.sort(key=lambda x: x["거래량"], reverse=True)
    return results[:15]


@st.cache_data(ttl=300, show_spinner=False)
def get_us_change_ranking() -> list:
    """US 등락률 상위 종목 — watchlist yfinance 배치 조회"""
    import yfinance as yf
    results = []
    for ticker in _US_WATCHLIST:
        try:
            fi = yf.Ticker(ticker).fast_info
            price = round(fi.get("lastPrice",     0) or 0, 2)
            prev  = fi.get("previousClose",       0) or 0
            vol   = int(fi.get("lastVolume",      0) or 0)
            if price <= 0:
                continue
            chg = round(((price - prev) / prev * 100) if prev > 0 else 0, 2)
            results.append({
                "티커":      ticker,
                "현재가($)": price,
                "등락률(%)": chg,
                "거래량":    vol,
            })
        except Exception:
            continue
    results.sort(key=lambda x: x["등락률(%)"], reverse=True)
    return results


@st.cache_data(ttl=86400, show_spinner=False)
def get_us_ticker_map() -> dict:
    """NASDAQ + NYSE + AMEX 전종목 티커→{name, exchange} 맵 반환 (24시간 캐시).

    FinanceDataReader StockListing → yfinance 인기종목 폴백 순으로 시도.
    """
    result: dict = {}

    # 1차: FinanceDataReader (일반주식 + ETF)
    try:
        import FinanceDataReader as fdr
        for market, exch in [("NASDAQ", "NASDAQ"), ("NYSE", "NYSE"), ("AMEX", "AMEX")]:
            try:
                df = fdr.StockListing(market)
                if df is None or df.empty:
                    continue
                df.columns = [str(c).strip() for c in df.columns]
                sym_col  = next((c for c in df.columns if c.upper() in ("SYMBOL", "CODE", "TICKER")), None)
                name_col = next((c for c in df.columns if c.upper() in ("NAME", "LONGNAME", "SHORTNAME")), None)
                if not sym_col:
                    continue
                for _, row in df.iterrows():
                    sym  = str(row.get(sym_col, "")).strip().upper()
                    name = str(row.get(name_col, sym)).strip() if name_col else sym
                    if sym and 1 <= len(sym) <= 5 and sym.isalpha():
                        result[sym] = {"name": name, "exchange": exch}
            except Exception:
                continue
        # ETF
        try:
            etf_df = fdr.StockListing("ETF/US")
            if etf_df is not None and not etf_df.empty:
                etf_df.columns = [str(c).strip() for c in etf_df.columns]
                sym_col  = next((c for c in etf_df.columns if c.upper() in ("SYMBOL", "CODE", "TICKER")), None)
                name_col = next((c for c in etf_df.columns if c.upper() in ("NAME", "LONGNAME", "SHORTNAME")), None)
                if sym_col:
                    for _, row in etf_df.iterrows():
                        sym  = str(row.get(sym_col, "")).strip().upper()
                        name = str(row.get(name_col, sym)).strip() if name_col else sym
                        if sym and 1 <= len(sym) <= 5:
                            result[sym] = {"name": name, "exchange": "ETF"}
        except Exception:
            pass
        if result:
            return result
    except Exception:
        pass

    # 폴백: 주요 종목 하드코딩
    fallback = [
        ("NVDA","엔비디아","NASDAQ"),("AAPL","애플","NASDAQ"),("MSFT","마이크로소프트","NASDAQ"),
        ("GOOGL","알파벳","NASDAQ"),("AMZN","아마존","NASDAQ"),("META","메타","NASDAQ"),
        ("TSLA","테슬라","NASDAQ"),("AVGO","브로드컴","NASDAQ"),("PLTR","팔란티어","NYSE"),
        ("AMD","AMD","NASDAQ"),("NFLX","넷플릭스","NASDAQ"),("CRM","세일즈포스","NYSE"),
        ("ORCL","오라클","NYSE"),("NOW","서비스나우","NYSE"),("COST","코스트코","NASDAQ"),
        ("JPM","JP모건","NYSE"),("V","비자","NYSE"),("MA","마스터카드","NYSE"),
        ("LLY","일라이릴리","NYSE"),("UNH","유나이티드헬스","NYSE"),
    ]
    for sym, name, exch in fallback:
        result[sym] = {"name": name, "exchange": exch}
    return result


@st.cache_data(ttl=86400, show_spinner=False)
def get_us_fdr_sector_map() -> dict:
    """FDR StockListing으로 NASDAQ+NYSE+AMEX+ETF 전종목 섹터맵 생성 (24시간 캐시).

    반환: {섹터: {세부섹터: [{name, ticker, exchange}]}}
    Sector/Industry 컬럼 없으면 빈 dict 반환.
    """
    try:
        import FinanceDataReader as fdr
        import pandas as pd
        frames = []
        # 일반 주식
        for market, exch in [("NASDAQ", "NASDAQ"), ("NYSE", "NYSE"), ("AMEX", "AMEX")]:
            try:
                df = fdr.StockListing(market).copy()
                df["_exchange"] = exch
                df["_is_etf"] = False
                frames.append(df)
            except Exception:
                continue
        # ETF
        try:
            etf_df = fdr.StockListing("ETF/US").copy()
            etf_df["_exchange"] = "ETF"
            etf_df["_is_etf"] = True
            frames.append(etf_df)
        except Exception:
            pass

        if not frames:
            return {}
        all_df = pd.concat(frames, ignore_index=True)
        all_df.columns = [str(c).strip() for c in all_df.columns]
        cols = {c.lower(): c for c in all_df.columns}

        sym_col    = cols.get("symbol",   cols.get("code",     cols.get("ticker",   None)))
        name_col   = cols.get("name",     cols.get("longname", cols.get("shortname", None)))
        sector_col = cols.get("sector",   None)
        ind_col    = cols.get("industry", cols.get("industrycode", None))

        if not sym_col:
            return {}

        result: dict = {}
        for _, row in all_df.iterrows():
            sym     = str(row.get(sym_col, "")).strip().upper()
            name    = str(row.get(name_col, sym)).strip() if name_col else sym
            exch    = str(row.get("_exchange", "NASDAQ"))
            is_etf  = bool(row.get("_is_etf", False))
            sector  = str(row.get(sector_col, "") if sector_col else "").strip()
            sub     = str(row.get(ind_col, "") if ind_col else "").strip()

            if not sym or not (1 <= len(sym) <= 5):
                continue
            # ETF는 알파벳+숫자 허용, 일반주식은 알파벳만
            if not is_etf and not sym.isalpha():
                continue

            if is_etf:
                sector = sector or "ETF"
                sub    = sub    or "ETF 전체"
            else:
                sector = sector or "기타"
                sub    = sub    or sector

            result.setdefault(sector, {}).setdefault(sub, []).append(
                {"name": name, "ticker": sym, "exchange": exch}
            )
        return result
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def get_us_daily_chart(ticker: str, period: str = "3mo", unit: str = "D") -> pd.DataFrame:
    """미국 주식 일/주/월봉 데이터 (yfinance). unit: D, W, M"""
    import yfinance as yf
    from datetime import datetime as _dt, timedelta as _td
    _custom = {"15d": 21, "3y": 1100}
    if period in _custom:
        _end = _dt.now()
        _start = (_end - _td(days=_custom[period])).strftime("%Y-%m-%d")
        _hist_kw = {"start": _start, "end": _end.strftime("%Y-%m-%d")}
    else:
        _hist_kw = {"period": period}
    _yf_iv = "1d" if unit == "D" else "1wk" if unit == "W" else "1mo"
    try:
        raw = yf.Ticker(ticker).history(**_hist_kw, interval=_yf_iv, auto_adjust=True)
        if raw.empty:
            return pd.DataFrame()
        df = raw.reset_index()
        dt_col = next((c for c in df.columns if str(c).lower() in ("datetime", "date")), None)
        if not dt_col:
            return pd.DataFrame()
        df = df.rename(columns={dt_col: "datetime"})
        df.columns = [str(c).lower().strip() for c in df.columns]
        needed = ["datetime", "open", "high", "low", "close", "volume"]
        if not all(c in df.columns for c in needed):
            return pd.DataFrame()
        df["datetime"] = pd.to_datetime(df["datetime"])
        if df["datetime"].dt.tz is not None:
            df["datetime"] = df["datetime"].dt.tz_localize(None)
        return df[needed].dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def get_us_minute_chart(ticker: str, interval: int = 5) -> pd.DataFrame:
    """미국 주식 분봉 데이터 (yfinance, 프리/애프터마켓 포함)"""
    import yfinance as yf
    _map = {1: "1m", 3: "5m", 5: "5m", 10: "15m", 15: "15m", 30: "30m", 60: "60m"}
    yf_interval = _map.get(interval, "5m")
    try:
        # prepost=True를 설정하여 프리마켓/애프터마켓 데이터 포함. period="5d"로 안정적 데이터 확보
        raw = yf.Ticker(ticker).history(period="5d", interval=yf_interval, auto_adjust=True, prepost=True)
        if raw.empty:
            return pd.DataFrame()
        df = raw.reset_index()
        dt_col = next((c for c in df.columns if str(c).lower() in ("datetime", "date")), None)
        if not dt_col:
            return pd.DataFrame()
        df = df.rename(columns={dt_col: "datetime"})
        df.columns = [str(c).lower().strip() for c in df.columns]
        needed = ["datetime", "open", "high", "low", "close", "volume"]
        if not all(c in df.columns for c in needed):
            return pd.DataFrame()
        
        df["datetime"] = pd.to_datetime(df["datetime"])
        if df["datetime"].dt.tz is not None:
            # 뉴욕 시간으로 변환
            df["datetime"] = df["datetime"].dt.tz_convert("America/New_York").dt.tz_localize(None)
        
        # 정규장 필터를 제거하여 모든 시간대 표시
        return df[needed].dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=90, show_spinner=False)
def get_us_prebreakout_signal(ticker: str) -> dict:
    """5분봉 기반 미국 주식 급등 직전 신호 (get_kr_prebreakout_signal의 US 버전)"""
    df = get_us_minute_chart(ticker, interval=5)
    if df.empty or len(df) < 6:
        return {"signal_score": 0, "signal_label": "데이터 부족", "vol_accel": 0}

    n = len(df)
    recent_vol = df["volume"].iloc[max(n-6, 0):].sum()
    prev_vol   = df["volume"].iloc[max(n-12, 0):max(n-6, 0)].sum()
    vol_accel  = round(recent_vol / prev_vol, 2) if prev_vol > 0 else 0.0

    box_high     = df["high"].iloc[max(n-7, 0):n-1].max() if n > 2 else 0
    cur_close    = df["close"].iloc[-1]
    consol_break = bool(cur_close > box_high) if box_high > 0 else False

    ma20     = df["close"].rolling(20).mean().iloc[-1] if n >= 20 else df["close"].mean()
    ma5      = df["close"].rolling(5).mean().iloc[-1]  if n >= 5  else df["close"].mean()
    above_ma = bool(cur_close > ma20 and cur_close > ma5)

    if n >= 3:
        last3      = df.iloc[-3:]
        candle_seq = bool(all(last3["close"].values > last3["open"].values))
    else:
        candle_seq = False

    score, notes = 0, []
    if vol_accel >= 2.5:
        score += 2; notes.append(f"거래량가속 {vol_accel:.1f}x")
    elif vol_accel >= 1.5:
        score += 1; notes.append(f"거래량증가 {vol_accel:.1f}x")
    if consol_break:
        score += 1; notes.append("박스권돌파")
    if candle_seq:
        score += 1; notes.append("연속양봉")
    if above_ma:
        score += 1; notes.append("이평선상위")

    return {
        "ticker":       ticker,
        "vol_accel":    vol_accel,
        "consol_break": consol_break,
        "above_ma":     above_ma,
        "candle_seq":   candle_seq,
        "signal_score": min(score, 5),
        "signal_label": " · ".join(notes) if notes else "시그널 없음",
        "cur_price":    round(float(cur_close), 2),
    }
