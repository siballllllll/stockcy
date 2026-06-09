# data_kr v4
import os
import requests
import st_compat as st
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
                "appkey": os.getenv("KIS_APP_KEY", ""),
                "appsecret": os.getenv("KIS_APP_SECRET", ""),
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
        "appkey": os.getenv("KIS_APP_KEY", ""),
        "appsecret": os.getenv("KIS_APP_SECRET", ""),
        "tr_id": tr_id,
        "custtype": "P",
    }


def _get(path: str, tr_id: str, params: dict, debug_label: str | None = None):
    """KIS API GET 요청 공통 함수. 실패 시 None 반환.
    debug_label 지정 시 실패(rt_cd!=0)나 예외 사유를 콘솔/로그에 남겨 진단을 돕는다."""
    try:
        resp = requests.get(
            f"{KIS_BASE}{path}",
            headers=_headers(tr_id),
            params=params,
            timeout=10,
        )
        try:
            data = resp.json()
        except Exception:
            if debug_label:
                body = (resp.text or "")[:200].replace("\n", " ")
                print(f"[KIS {debug_label}] 비-JSON 응답 HTTP={resp.status_code} len={len(resp.text or '')} body={body!r}")
            return None
        if data.get("rt_cd") == "0":
            return data
        if debug_label:
            print(f"[KIS {debug_label}] 실패 rt_cd={data.get('rt_cd')} msg_cd={data.get('msg_cd')} msg={data.get('msg1')}")
        return None
    except Exception as e:
        if debug_label:
            print(f"[KIS {debug_label}] 요청 예외: {repr(e)[:140]}")
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
def _get_kr_etf_map() -> dict:
    """국내 ETF 이름→{code, suffix} 맵 (24시간 캐시). FDR ETF/KR → pykrx 폴백.
    국내 ETF는 모두 코스피 시장 상장이므로 suffix=.KS. 일반주식 리스팅(KOSPI/KOSDAQ)에는
    ETF가 빠져있어 KODEX·TIGER 등이 검색되지 않던 문제를 보완한다."""
    result: dict = {}
    # 1차: FinanceDataReader (ETF/KR)
    try:
        import FinanceDataReader as fdr
        df = fdr.StockListing("ETF/KR")
        if df is not None and not df.empty:
            cols = {str(c).strip().lower(): c for c in df.columns}
            code_col = cols.get("symbol") or cols.get("code") or cols.get("종목코드")
            name_col = cols.get("name") or cols.get("종목명")
            if code_col and name_col:
                for _, row in df.iterrows():
                    code = str(row.get(code_col, "")).strip()
                    name = str(row.get(name_col, "")).strip()
                    if name and len(code) == 6 and code.isdigit():
                        result[name] = {"code": code, "suffix": ".KS"}
        if result:
            return result
    except Exception:
        pass
    # 2차: pykrx
    try:
        from pykrx import stock as _pykrx
        import datetime
        today = datetime.date.today().strftime("%Y%m%d")
        for code in _pykrx.get_etf_ticker_list(today):
            name = _pykrx.get_etf_ticker_name(code)
            code = str(code).strip()
            if name and len(code) == 6 and code.isdigit():
                result[name] = {"code": code, "suffix": ".KS"}
    except Exception:
        pass
    return result


@st.cache_data(ttl=86400)
def get_kr_name_to_code_map() -> dict:
    """전체 KOSPI+KOSDAQ 일반주식 + 국내 ETF 이름→{code, suffix} 맵 반환 (24시간 캐시)."""
    result = _load_kr_base_universe()
    # 국내 ETF(KODEX·TIGER 등) 병합 — 일반주식 리스팅엔 ETF가 빠져있어 별도 병합.
    # ETF 조회 실패해도 일반주식 맵은 그대로 유지(오프라인/차단 환경 안전).
    try:
        for name, info in _get_kr_etf_map().items():
            result.setdefault(name, info)
    except Exception:
        pass
    return result


def _load_kr_base_universe() -> dict:
    """전체 KOSPI+KOSDAQ 일반주식 이름→{code, suffix} 맵.

    정적 JSON → FinanceDataReader → pykrx → KRX 직접 API 순으로 시도.
    네트워크 장애나 KRX 방화벽 차단 환경에서도 0.001초 만에 즉시 실행을 보장하기 위해
    로컬에 내장된 정적 JSON 로드(최후의 보루였으나 최선의 성능 보장)를 1순위로 배치합니다.
    """
    result: dict = {}

    # 1차: 번들된 정적 JSON (네트워크 불필요, 차단 환경 극복 1순위)
    try:
        import json, os
        _static = os.path.join(os.path.dirname(__file__), "kr_stocks_static.json")
        if os.path.exists(_static):
            with open(_static, "r", encoding="utf-8") as f:
                result = json.load(f)
            if result:
                return result
    except Exception:
        pass

    # 2차: pykrx (정적 파일이 없거나 누락 시 폴백)
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

    # 3차: FinanceDataReader
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

    # 4차: KRX 공개 API
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

    raise RuntimeError("전종목 맵 로딩 실패 (정적JSON·pykrx·FDR·KRX 모두 실패)")

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
                "appkey": os.getenv("KIS_APP_KEY", ""),
                "appsecret": os.getenv("KIS_APP_SECRET", ""),
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


@st.cache_data(ttl=86400)
def _get_kr_fundamental_map() -> dict:
    """전종목 PER/PBR 맵 (pykrx 펀더멘털, 24h 캐시) — KIS가 per/pbr을 비워 줄 때 보강용.
    KRX 직접 접근이 막힌 환경에서는 빈 맵을 반환(보강 없이 KIS/yfinance 값 그대로 사용)."""
    out: dict = {}
    try:
        from pykrx import stock as _pk
        import datetime as _dt
        for back in range(0, 7):   # 최근 거래일 탐색(주말·휴일 대비)
            day = (_dt.date.today() - _dt.timedelta(days=back)).strftime("%Y%m%d")
            try:
                df = _pk.get_market_fundamental(day, market="ALL")
            except Exception:
                df = None
            if df is not None and len(df):
                for code, row in df.iterrows():
                    try:
                        out[str(code).zfill(6)] = {
                            "per": float(row.get("PER", 0) or 0),
                            "pbr": float(row.get("PBR", 0) or 0),
                        }
                    except Exception:
                        continue
                break
    except Exception:
        pass
    return out


def _kr_val_missing(x) -> bool:
    """KIS per/pbr 값이 사실상 비어있는지 판정 ('', '-', '0', '0.00', 0 등)."""
    s = str(x).strip().replace(",", "")
    if s in ("", "-"):
        return True
    try:
        return float(s) == 0.0
    except Exception:
        return False


@st.cache_data(ttl=21600)
def _get_kr_per_pbr_naver(code: str) -> dict:
    """네이버 금융에서 단일 종목 PER/PBR 스크래핑 (KRX 직접 접근이 막힌 환경의 보강책, 6h 캐시).
    1차: 종목 메인 HTML의 안정적 태그(id="_per"/"_pbr"), 2차: m.stock 통합 JSON API. 실패 시 빈 dict.
    적자기업은 네이버도 PER을 'N/A'로 주므로 그대로 비워둔다."""
    import re as _re
    code = str(code).strip().zfill(6)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"}

    def _num(v):
        s = _re.sub(r"[^0-9.\-]", "", str(v or ""))
        try:
            return float(s) if s not in ("", "-", ".", "-.") else None
        except Exception:
            return None

    # 1차: 데스크톱 종목 메인 — <em id="_per">11.49</em> / <em id="_pbr">1.08</em> (수년째 안정적)
    try:
        r = requests.get(f"https://finance.naver.com/item/main.naver?code={code}", headers=headers, timeout=4)
        if r.ok:
            html = r.text
            out = {}
            mp = _re.search(r'id="_per"[^>]*>\s*([\-\d.,]+)', html)
            mb = _re.search(r'id="_pbr"[^>]*>\s*([\-\d.,]+)', html)
            if mp:
                p = _num(mp.group(1));  out["per"] = round(p, 2) if p else None
            if mb:
                b = _num(mb.group(1));  out["pbr"] = round(b, 2) if b else None
            if out.get("per") or out.get("pbr"):
                return out
    except Exception:
        pass

    # 2차: 모바일 통합 JSON API (totalInfos 안에 PER/PBR)
    try:
        r = requests.get(f"https://m.stock.naver.com/api/stock/{code}/integration", headers=headers, timeout=4)
        if r.ok:
            out = {}
            for item in (r.json().get("totalInfos") or []):
                key = str(item.get("key", "")).lower()
                lab = str(item.get("label", "")).upper()
                if key == "per" or lab == "PER":
                    p = _num(item.get("value"));  out["per"] = round(p, 2) if p else out.get("per")
                elif key == "pbr" or lab == "PBR":
                    b = _num(item.get("value"));  out["pbr"] = round(b, 2) if b else out.get("pbr")
            if out.get("per") or out.get("pbr"):
                return out
    except Exception:
        pass

    return {}


@st.cache_data(ttl=60)
def get_kr_stock_price(stock_code: str, with_fundamental: bool = False):
    """국내 주식 현재가 및 기본 정보 조회 (KIS API → yfinance 폴백, 1분 캐싱).
    with_fundamental=True일 때만 KIS가 비운 PER/PBR을 네이버/pykrx로 보강(느린 네트워크 호출).
    → 종목검색 상세에서만 True, 픽·시나리오 등 대량 반복 호출 경로는 False(지연 방지)."""
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
        # PER/PBR: KIS가 비워 주면(적자·일부 종목) 네이버 → pykrx 순으로 보강. ETF/적자는 원래 없음.
        # 단 with_fundamental=True(종목검색 상세)일 때만 — 대량 호출 경로의 네트워크 지연/튕김 방지.
        per_v, pbr_v = o.get("per", "-"), o.get("pbr", "-")
        if with_fundamental and (_kr_val_missing(per_v) or _kr_val_missing(pbr_v)):
            nv = _get_kr_per_pbr_naver(stock_code)   # 1차: 네이버 스크래핑(KRX 차단 환경에서도 동작)
            if nv:
                if _kr_val_missing(per_v) and nv.get("per"):
                    per_v = nv["per"]
                if _kr_val_missing(pbr_v) and nv.get("pbr"):
                    pbr_v = nv["pbr"]
            if _kr_val_missing(per_v) or _kr_val_missing(pbr_v):
                fm = _get_kr_fundamental_map().get(stock_code)   # 2차: pykrx(가능한 환경에서만)
                if fm:
                    if _kr_val_missing(per_v) and fm.get("per"):
                        per_v = round(fm["per"], 2)
                    if _kr_val_missing(pbr_v) and fm.get("pbr"):
                        pbr_v = round(fm["pbr"], 2)
        return {
            "code": stock_code,
            "name": o.get("hts_kor_isnm") or stock_code,
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
            "per": per_v,
            "pbr": pbr_v,
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
            ticker = f"{stock_code}{suffix}"
            raw = yf.download(ticker, period="2d", progress=False, timeout=1.5)
            if raw.empty:
                continue
            closes = raw["Close"].dropna()
            if closes.empty:
                continue
            price = round(float(closes.iloc[-1]))
            prev = round(float(closes.iloc[-2])) if len(closes) >= 2 else price
            change = round(price - prev)
            change_pct = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
            sign = "2" if change > 0 else "4" if change < 0 else "3"
            
            # Ticker 메타 데이터 수집 시도 (실패 시 기본 정보로 우회)
            tk = yf.Ticker(ticker)
            try:
                info = tk.info
                name = info.get("shortName") or info.get("longName") or stock_code
                per = round(info.get("trailingPE", 0) or info.get("forwardPE", 0) or 0, 1) or "-"
                pbr = round(info.get("priceToBook", 0) or 0, 2) or "-"
                market_cap = _format_market_cap(info.get("marketCap", 0) // 100000000) if info.get("marketCap") else "-"
            except Exception:
                name = stock_code
                per, pbr, market_cap = "-", "-", "-"
                
            return {
                "code": stock_code,
                "name": name,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "sign": sign,
                "volume": int(raw["Volume"].iloc[-1]) if "Volume" in raw.columns else 0,
                "amount": 0,
                "open": round(float(raw["Open"].iloc[-1])) if "Open" in raw.columns else price,
                "high": round(float(raw["High"].iloc[-1])) if "High" in raw.columns else price,
                "low": round(float(raw["Low"].iloc[-1])) if "Low" in raw.columns else price,
                "w52_high": price,
                "w52_low": price,
                "per": per,
                "pbr": pbr,
                "market_cap": market_cap,
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
    """종목별 외국인/기관/개인 순매수 동향 (최근 10영업일)
    KIS API → 네이버 금융 차트 API(외국인 보유율 변화 기반 추정) 순으로 시도."""
    # 1차: KIS API
    data = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-investor",
        "FHKST01010900",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": stock_code},
    )
    if data:
        results = []
        for item in data.get("output", [])[:10]:
            d = item.get("stck_bsop_date", "")
            if len(d) == 8:
                d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            
            close_val = int(item.get("stck_clpr", 0) or 0)
            change_pct = float(item.get("prdy_ctrt", 0) or 0)
            sign = item.get("prdy_vrss_sign", "")
            if sign in ("4", "5") and change_pct > 0:
                change_pct = -change_pct
                
            frgn = int(item.get("frgn_ntby_qty", 0) or 0)
            inst = int(item.get("orgn_ntby_qty", 0) or 0)
            prsn = int(item.get("prsn_ntby_qty", 0) or 0)
            
            results.append({
                "date": d,
                "close": close_val,
                "change_pct": change_pct,
                "foreign": frgn,
                "inst": inst,
                "individual": prsn,
                # 하위 호환용 한글 키
                "날짜": d,
                "개인": prsn,
                "외국인": frgn,
                "기관": inst,
                "종가": close_val,
                "등락률": change_pct
            })
        return results

    # 2차 폴백: 네이버 금융 차트 API — 외국인 보유율 변화로 순매수 추정
    try:
        import datetime as _dt2, requests as _req2
        _today = _dt2.date.today()
        _start = (_today - _dt2.timedelta(days=20)).strftime("%Y%m%d") + "000000"
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
                
                close_val = int(_rows[i].get("closePrice", 0) or 0)
                change_pct = float(_rows[i].get("fluctuationsRatio", 0.0) or 0.0)
                
                _d = str(_rows[i].get("localDate", ""))
                if len(_d) == 8:
                    _d = f"{_d[:4]}-{_d[4:6]}-{_d[6:]}"
                results.append({
                    "date": _d,
                    "close": close_val,
                    "change_pct": change_pct,
                    "foreign": _frgn,
                    "inst": 0,
                    "individual": 0,
                    # 하위 호환용 한글 키
                    "날짜": _d,
                    "외국인": _frgn,
                    "기관": 0,
                    "개인": 0,
                    "종가": close_val,
                    "등락률": change_pct,
                    "_estimated": True,
                })
            # 최신 10거래일만 반환
            return list(reversed(results))[:10]
    except Exception:
        pass

    return []


@st.cache_data(ttl=120, show_spinner=False)
def get_kr_investor_rank_bulk(stock_list: tuple) -> list:
    """거래량·등락률 상위 종목들의 오늘자 외국인·기관 순매수 집계 후 정렬.

    stock_list: ((code, name), ...) 튜플 — 캐시 키로 활용
    반환: [{'종목코드', '종목명', '외국인순매수', '기관순매수'}, ...]  합산 순매수 내림차순
    """
    import datetime as _dt3
    _today_str = _dt3.date.today().strftime("%Y-%m-%d")

    results = []
    for code, name in stock_list[:12]:
        try:
            trend = get_kr_investor_trend(str(code))
            if not trend:
                continue
            # 추정값(_estimated)이면 신뢰도 낮으므로 제외
            if trend[0].get("_estimated"):
                continue
            # 오늘 또는 가장 최근 영업일 데이터
            today_row = trend[0]
            frgn = int(today_row.get("외국인", 0) or 0)
            orgn = int(today_row.get("기관", 0) or 0)
            if frgn == 0 and orgn == 0:
                continue
            results.append({
                "종목코드": str(code),
                "종목명": str(name),
                "외국인순매수": frgn,
                "기관순매수": orgn,
            })
        except Exception:
            continue

    # 외국인 + 기관 합산 순매수 기준 내림차순 정렬
    results.sort(key=lambda x: x["외국인순매수"] + x["기관순매수"], reverse=True)
    return results


@st.cache_data(ttl=120, show_spinner=False)
def get_kr_frgn_inst_rank(market: str = "J", top_n: int = 30, sort: str = "buy") -> list:
    """KIS 외국인·기관 순매수/순매도 상위 종목 순위 (1회 API 호출, IP 화이트리스트 필요).

    market: "J"=KOSPI, "Q"=KOSDAQ
    sort: "buy"=순매수 많은 순, "sell"=순매도 많은 순
    반환: [{'종목코드', '종목명', '외국인순매수', '기관순매수'}, ...]
    """
    sort_code = "0" if sort == "buy" else "1"   # KIS: 0=순매수, 1=순매도
    iscd = "1001" if market == "Q" else "0001"   # 0001=코스피, 1001=코스닥
    data = _get(
        "/uapi/domestic-stock/v1/quotations/foreign-institution-total",
        "FHPTJ04400000",   # 국내기관·외국인 매매종목가집계 (외국인/기관 순매수 상위)
        debug_label=f"frgn_inst {market}/{sort}",
        params={
            "fid_cond_mrkt_div_code": "V",        # 시장구분
            "fid_cond_scr_div_code": "16449",     # 화면번호
            "fid_input_iscd": iscd,
            "fid_div_cls_code": "0",              # 0=수량 정렬
            "fid_rank_sort_cls_code": sort_code,  # 0=순매수 상위, 1=순매도 상위
            "fid_etc_cls_code": "0",
        },
    )
    if not data:
        return []

    results = []
    for item in (data.get("output") or [])[:top_n]:
        code = str(item.get("mksc_shrn_iscd") or item.get("stck_shrn_iscd") or "").strip()
        name = str(item.get("hts_kor_isnm") or "").strip()
        frgn = int(item.get("frgn_ntby_qty") or 0)
        orgn = int(item.get("orgn_ntby_qty") or 0)
        if not code or not name:
            continue
        results.append({
            "종목코드": code,
            "종목명": name,
            "외국인순매수": frgn,
            "기관순매수": orgn,
        })
    return results


def _classify_flow(item: dict) -> dict:
    """수급 항목을 세력 흐름 관점으로 분류: 합산 강도, 주도 주체, 동반매수/매도 구분."""
    frgn = int(item.get("외국인순매수", 0) or 0)
    orgn = int(item.get("기관순매수", 0) or 0)
    combined = frgn + orgn
    if frgn > 0 and orgn > 0:
        tag = "동반매수"
    elif frgn < 0 and orgn < 0:
        tag = "동반매도"
    else:
        tag = "엇갈림"
    return {
        "종목코드": item.get("종목코드"), "종목명": item.get("종목명"),
        "외국인순매수": frgn, "기관순매수": orgn, "합산": combined,
        "주도": "외국인" if abs(frgn) >= abs(orgn) else "기관", "구분": tag,
    }


def get_supply_power_flow(top_n: int = 12) -> dict:
    """실시간 외국인·기관(세력) 자금 흐름.
    시장별로 자금 유입(순매수 상위)·이탈(순매도 상위)을 외국인+기관 합산 강도로 정렬하고,
    외국인·기관이 함께 사들이는 '동반매수'(강한 세력 유입)를 별도로 추린다."""
    from datetime import datetime
    out = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "markets": {}}
    for mkt, label in (("J", "코스피"), ("Q", "코스닥")):
        buy = get_kr_frgn_inst_rank(mkt, top_n * 2, "buy") or []
        sell = get_kr_frgn_inst_rank(mkt, top_n * 2, "sell") or []
        inflow = sorted((_classify_flow(x) for x in buy), key=lambda x: x["합산"], reverse=True)
        outflow = sorted((_classify_flow(x) for x in sell), key=lambda x: x["합산"])
        out["markets"][mkt] = {
            "label": label,
            "inflow": inflow[:top_n],
            "outflow": outflow[:top_n],
            "strong_inflow": [x for x in inflow if x["구분"] == "동반매수"][:6],
            "strong_outflow": [x for x in outflow if x["구분"] == "동반매도"][:6],
        }
    return out


def snapshot_frgn_inst_today() -> dict:
    """오늘의 외국인·기관 수급(순매수+순매도 상위)을 DB에 스냅샷 저장 (히스토리 적재)."""
    from db import save_frgn_inst_snapshot
    total = 0
    for mkt in ("J", "Q"):
        rows = (get_kr_frgn_inst_rank(mkt, 40, "buy") or []) + (get_kr_frgn_inst_rank(mkt, 40, "sell") or [])
        seen = {}
        for r in rows:
            c = r.get("종목코드")
            if c and c not in seen:
                seen[c] = r
        total += save_frgn_inst_snapshot(mkt, list(seen.values()))
    return {"saved": total}


def detect_supply_rotation() -> dict:
    """최근 스냅샷 2일치를 비교해 세력 자금이 더 들어온/빠진 종목(combined 증감)을 감지.
    2일치 이상 쌓여야 동작 (매일 자동 스냅샷)."""
    from db import load_frgn_inst_snapshot_dates, load_frgn_inst_snapshot
    dates = load_frgn_inst_snapshot_dates(10)
    if len(dates) < 2:
        return {"available": False, "reason": "스냅샷 2거래일 이상 필요 — 매일 자동 적재 중입니다.",
                "have_dates": dates}
    today_d, prev_d = dates[0], dates[1]
    cur = {r["ticker"]: r for r in load_frgn_inst_snapshot(today_d)}
    prev = {r["ticker"]: r for r in load_frgn_inst_snapshot(prev_d)}
    recs = []
    for tk, c in cur.items():
        prev_comb = (prev.get(tk) or {}).get("combined", 0) or 0
        recs.append({"ticker": tk, "name": c["name"], "market": c["market"],
                     "today": c["combined"], "prev": prev_comb,
                     "delta": (c["combined"] or 0) - prev_comb})
    moved_in = sorted([r for r in recs if r["delta"] > 0], key=lambda x: x["delta"], reverse=True)
    moved_out = sorted([r for r in recs if r["delta"] < 0], key=lambda x: x["delta"])
    return {"available": True, "today": today_d, "prev": prev_d,
            "moved_in": moved_in[:10], "moved_out": moved_out[:10]}


_TICKER_SECTOR_MAP = None

def _ticker_to_sector_map() -> dict:
    """종목코드 → 업종(소분류) 매핑. get_kr_fdr_sector_map 기반(1회 캐시)."""
    global _TICKER_SECTOR_MAP
    if _TICKER_SECTOR_MAP:   # 비어있으면 다음에 재시도 (빈 맵은 캐시하지 않음)
        return _TICKER_SECTOR_MAP
    m = {}
    try:
        from db import load_sector_map   # 엔드포인트와 동일한 DB 캐시 섹터맵 사용
        smap = load_sector_map() or {}
        for big, subs in smap.items():
            for sub, stocks in (subs or {}).items():
                label = sub or big or "기타"
                for s in (stocks or []):
                    code = str(s.get("code", "")).strip().zfill(6)
                    if code:
                        m[code] = label
    except Exception as e:
        print(f"_ticker_to_sector_map error: {e}")
    if m:
        _TICKER_SECTOR_MAP = m
    return m


def _aggregate_by_sector(rows: list) -> list:
    """[{종목코드,외국인순매수,기관순매수}] → 섹터별 합산. combined_sum 내림차순."""
    smap = _ticker_to_sector_map()
    agg: dict = {}
    for r in rows:
        code = str(r.get("종목코드", "")).strip().zfill(6)
        sector = smap.get(code, "기타")
        a = agg.setdefault(sector, {"sector": sector, "frgn_sum": 0, "orgn_sum": 0, "combined_sum": 0, "stock_count": 0})
        f = int(r.get("외국인순매수", 0) or 0)
        o = int(r.get("기관순매수", 0) or 0)
        a["frgn_sum"] += f
        a["orgn_sum"] += o
        a["combined_sum"] += f + o
        a["stock_count"] += 1
    return sorted(agg.values(), key=lambda x: x["combined_sum"], reverse=True)


def snapshot_sector_flow_today() -> dict:
    """오늘의 외국인·기관 수급을 섹터별로 집계해 저장 (going-forward 히스토리)."""
    from db import save_sector_flow_snapshot
    from datetime import datetime
    rows = []
    for mkt in ("J", "Q"):
        rows += (get_kr_frgn_inst_rank(mkt, 100, "buy") or []) + (get_kr_frgn_inst_rank(mkt, 100, "sell") or [])
    seen = {}
    for r in rows:
        c = str(r.get("종목코드", "")).strip()
        if c and c not in seen:
            seen[c] = r
    agg = _aggregate_by_sector(list(seen.values()))
    today = datetime.now().strftime("%Y-%m-%d")
    n = save_sector_flow_snapshot(today, agg)
    return {"date": today, "sectors": n}


def backfill_sector_flow_pykrx(days: int = 20, throttle: float = 0.0, job: dict | None = None,
                               skip_existing: bool = True) -> dict:
    """과거 N거래일의 외국인+기관 순매수를 pykrx로 받아 섹터별 집계·저장 (과거 흐름 백필).
    KRX_ID/KRX_PW 환경변수(.env, data.krx.co.kr 무료계정) 필요.
    throttle: 거래일마다 sleep(초) — KRX 차단 방지. skip_existing: 이미 저장된 날짜는 건너뜀(재개/증분).
    job: 진행률을 기록할 dict(running/total/done/filled/current)."""
    import os as _os
    import time as _t
    from db import save_sector_flow_snapshot, load_sector_flow_dates
    from datetime import datetime, timedelta
    krx_id_set = bool(_os.getenv("KRX_ID")) and bool(_os.getenv("KRX_PW"))
    if not krx_id_set:
        return {"filled": 0, "error": "KRX_ID/KRX_PW 환경변수 미설정 — .env 추가 후 백엔드 재시작 필요"}
    try:
        from pykrx import stock
    except Exception as e:
        return {"error": f"pykrx 사용 불가: {e}", "filled": 0}

    existing = set(load_sector_flow_dates(3650)) if skip_existing else set()
    first_err = None
    filled, trading_seen, guard = 0, 0, 0
    d = datetime.now()
    # days = '오늘부터 N 거래일 뒤로'의 윈도우. 이미 있는 날은 건너뛰어 재개가 idempotent.
    while trading_seen < days and guard < days * 2 + 40:
        guard += 1
        d = d - timedelta(days=1)
        if d.weekday() >= 5:   # 주말 스킵
            continue
        trading_seen += 1
        ds, ds_iso = d.strftime("%Y%m%d"), d.strftime("%Y-%m-%d")
        if job is not None:
            job["done"] = trading_seen
        if ds_iso in existing:   # 이미 적재된 거래일은 건너뜀(커버됨)
            continue
        if job is not None:
            job["current"] = ds_iso
        try:
            per_code: dict = {}
            for mkt in ("KOSPI", "KOSDAQ"):
                for inv, fld in (("외국인", "frgn"), ("기관합계", "orgn")):
                    df = stock.get_market_net_purchases_of_equities(ds, ds, mkt, inv)
                    if throttle:
                        _t.sleep(throttle)
                    if df is None or getattr(df, "empty", True):
                        continue
                    col = "순매수거래량" if "순매수거래량" in df.columns else ("순매수" if "순매수" in df.columns else None)
                    if not col:
                        continue
                    for tk, row in df.iterrows():
                        code = str(tk).strip().zfill(6)
                        try:
                            net = int(row[col])
                        except Exception:
                            net = 0
                        per_code.setdefault(code, {"frgn": 0, "orgn": 0})[fld] = net
            if not per_code:
                continue
            rows = [{"종목코드": c, "외국인순매수": v["frgn"], "기관순매수": v["orgn"]} for c, v in per_code.items()]
            save_sector_flow_snapshot(ds_iso, _aggregate_by_sector(rows))
            filled += 1
            if job is not None:
                job["filled"] = filled
        except Exception as e:
            if first_err is None:
                first_err = repr(e)[:160]
            print(f"[sector backfill] {ds} 실패: {repr(e)[:120]}")
            continue
    return {"filled": filled, "krx_id_set": krx_id_set, "trading_days": trading_seen, "first_err": first_err}


# ── 백그라운드 대량 백필 작업 (throttle + 진행률 + 서버 재시작 자동 이어하기) ────
import threading as _bf_threading
_SECTOR_BF_JOB = {"running": False, "total": 0, "done": 0, "filled": 0, "current": "", "started_at": None}
_bf_lock = _bf_threading.Lock()
_SECTOR_BF_TARGET_KEY = "sector_backfill_target"   # 재시작 이어하기용 영속 타겟(ai_cache)


def _sector_backfill_worker(days: int, throttle: float):
    global _SECTOR_BF_JOB
    completed = False
    try:
        backfill_sector_flow_pykrx(days=days, throttle=throttle, job=_SECTOR_BF_JOB, skip_existing=True)
        completed = True   # 윈도우 한 바퀴 완주 → 타겟 정리(더 이상 재개 안 함)
    except Exception as e:
        print(f"[sector backfill] worker 오류: {e}")
    finally:
        _SECTOR_BF_JOB["running"] = False
        _SECTOR_BF_JOB["current"] = ""
        if completed:
            try:
                from db import delete_ai_cache, load_sector_flow_dates
                delete_ai_cache(_SECTOR_BF_TARGET_KEY)
                ds = load_sector_flow_dates(3650)
                print(f"[sector backfill] 완료 — 타겟 정리 (총 {days}거래일 윈도우, 적재 {len(ds)}일)")
                # 완료 텔레그램 알림
                try:
                    import telegram_bot as tg
                    if tg.is_configured():
                        rng = f"{ds[-1]} ~ {ds[0]}" if ds else "-"
                        tg.send_message(f"✅ 섹터 자금 흐름 백필 완료\n적재 거래일 {len(ds)}일 ({rng})\n시나리오 → 시장 인사이트 탭에서 섹터 추세·지속매집 분석 확인 가능")
                except Exception:
                    pass
            except Exception:
                pass


def start_sector_backfill_bg(days: int = 500, throttle: float = 0.25) -> dict:
    """대량 섹터 백필을 백그라운드에서 시작 (throttle로 KRX 차단 방지). 즉시 반환.
    타겟을 ai_cache에 영속화 → 서버 재시작/리로드로 끊겨도 시작 시 자동 이어하기."""
    from datetime import datetime
    global _SECTOR_BF_JOB
    with _bf_lock:
        if _SECTOR_BF_JOB["running"]:
            return {"status": "already_running", "job": dict(_SECTOR_BF_JOB)}
        try:
            from db import save_ai_cache
            save_ai_cache(_SECTOR_BF_TARGET_KEY, {"days": days, "throttle": throttle}, 720)  # 30일 보존
        except Exception:
            pass
        _SECTOR_BF_JOB.update({"running": True, "total": days, "done": 0, "filled": 0,
                               "current": "", "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        _bf_threading.Thread(target=_sector_backfill_worker, args=(days, throttle), daemon=True).start()
    return {"status": "started", "job": dict(_SECTOR_BF_JOB)}


def sector_backfill_status() -> dict:
    return dict(_SECTOR_BF_JOB)


def resume_sector_backfill_if_any() -> dict:
    """서버 시작 시 호출 — 영속 타겟이 남아있으면(미완료 백필) 백그라운드로 자동 이어하기.
    이미 적재된 날짜는 worker가 건너뛰므로 남은 부분만 채운다."""
    global _SECTOR_BF_JOB
    try:
        from db import load_ai_cache
        rec = load_ai_cache(_SECTOR_BF_TARGET_KEY)
    except Exception:
        return {"resumed": False}
    if not rec:
        return {"resumed": False}
    days = int(rec.get("days", 400) or 400)
    throttle = float(rec.get("throttle", 0.25) or 0.25)
    from datetime import datetime
    with _bf_lock:
        if _SECTOR_BF_JOB["running"]:
            return {"resumed": False, "reason": "already_running"}
        _SECTOR_BF_JOB.update({"running": True, "total": days, "done": 0, "filled": 0,
                               "current": "", "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        _bf_threading.Thread(target=_sector_backfill_worker, args=(days, throttle), daemon=True).start()
    print(f"[sector backfill] 서버 재시작 후 자동 이어하기 ({days}거래일 윈도우)")
    return {"resumed": True, "days": days}


def analyze_sector_flow_history(min_days: int = 5) -> dict:
    """전체 섹터 흐름 히스토리 분석 — 지속 매집/이탈 섹터, 일관성(유입비율), 최장 연속유입.
    백필이 쌓일수록 '어느 섹터에 세력이 꾸준히 들어왔다 빠졌다'는 패턴이 드러난다."""
    from db import load_sector_flow_series, load_sector_flow_dates
    dates_all = load_sector_flow_dates(3650)
    if len(dates_all) < min_days:
        return {"available": False, "reason": f"분석에 최소 {min_days}거래일 필요 (현재 {len(dates_all)}일)",
                "have_days": len(dates_all)}
    series = load_sector_flow_series(None, 3650)
    dates = sorted({r["snapshot_date"] for r in series})
    by_sec: dict = {}
    for r in series:
        by_sec.setdefault(r["sector"], {})[r["snapshot_date"]] = r.get("combined_sum", 0) or 0
    out = []
    for sec, dmap in by_sec.items():
        vals = [dmap.get(d, 0) for d in dates]
        n = len(vals)
        total = sum(vals)
        pos = sum(1 for v in vals if v > 0)
        best_streak = cur = 0
        for v in vals:
            if v > 0:
                cur += 1
                best_streak = max(best_streak, cur)
            else:
                cur = 0
        now_streak = 0
        for v in reversed(vals):
            if v > 0:
                now_streak += 1
            else:
                break
        out.append({"sector": sec, "days": n, "total": total,
                    "avg": round(total / n) if n else 0,
                    "pos_ratio": round(pos / n * 100, 1) if n else 0,
                    "best_streak": best_streak, "now_streak": now_streak})
    accumulation = sorted([x for x in out if x["total"] > 0],
                          key=lambda x: (x["pos_ratio"], x["total"]), reverse=True)
    distribution = sorted([x for x in out if x["total"] < 0],
                          key=lambda x: (x["pos_ratio"], x["total"]))
    return {"available": True, "period": f"{dates[0]} ~ {dates[-1]}", "days": len(dates),
            "accumulation": accumulation[:10], "distribution": distribution[:8]}


def detect_sector_rotation() -> dict:
    """최근 2거래일 섹터 흐름을 비교해 세력 자금이 들어온/빠진 섹터(섹터 로테이션) 감지."""
    from db import load_sector_flow_dates, load_sector_flow_snapshot
    dates = load_sector_flow_dates(30)
    if len(dates) < 2:
        return {"available": False, "reason": "섹터 흐름 2거래일 이상 필요 (백필/자동적재 중)", "have_dates": dates}
    today_d, prev_d = dates[0], dates[1]
    cur = {r["sector"]: r for r in load_sector_flow_snapshot(today_d)}
    prev = {r["sector"]: r for r in load_sector_flow_snapshot(prev_d)}
    recs = []
    for s, c in cur.items():
        pc = (prev.get(s) or {}).get("combined_sum", 0) or 0
        recs.append({"sector": s, "today": c["combined_sum"], "prev": pc, "delta": (c["combined_sum"] or 0) - pc})
    into = sorted([r for r in recs if r["delta"] > 0], key=lambda x: x["delta"], reverse=True)
    outof = sorted([r for r in recs if r["delta"] < 0], key=lambda x: x["delta"])
    top_today = sorted(cur.values(), key=lambda x: x["combined_sum"] or 0, reverse=True)[:8]
    return {"available": True, "today": today_d, "prev": prev_d,
            "into": into[:6], "outof": outof[:6], "top_today": top_today}


def compute_sector_trend(days: int = 10, top_n: int = 10) -> dict:
    """최근 N거래일 섹터별 세력 자금 추세. N일 누적·연속 유입일·일별 시계열 반환."""
    from db import load_sector_flow_series
    series = load_sector_flow_series(None, days)
    if not series:
        return {"dates": [], "sectors": [], "bottom": []}
    dates = sorted({r["snapshot_date"] for r in series})
    by_sec: dict = {}
    for r in series:
        by_sec.setdefault(r["sector"], {})[r["snapshot_date"]] = r.get("combined_sum", 0) or 0
    result = []
    for sec, dmap in by_sec.items():
        vals = [dmap.get(d, 0) for d in dates]
        total = sum(vals)
        days_pos = sum(1 for v in vals if v > 0)
        streak = 0   # 최근부터 연속 유입(양수)일 수
        for v in reversed(vals):
            if v > 0:
                streak += 1
            else:
                break
        result.append({"sector": sec, "total": total, "days_positive": days_pos,
                       "inflow_streak": streak, "series": vals})
    result.sort(key=lambda x: x["total"], reverse=True)
    return {"dates": dates, "sectors": result[:top_n],
            "bottom": sorted(result, key=lambda x: x["total"])[:5]}


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
        needed_syms = []
        sym_to_name = {}
        if "KOSPI" not in result:
            needed_syms.append("^KS11")
            sym_to_name["^KS11"] = "KOSPI"
        if "KOSDAQ" not in result:
            needed_syms.append("^KQ11")
            sym_to_name["^KQ11"] = "KOSDAQ"
            
        if needed_syms:
            try:
                raw = yf.download(needed_syms, period="2d", progress=False, timeout=1.5)
                if not raw.empty:
                    close_df = raw["Close"]
                    for sym in needed_syms:
                        try:
                            if len(needed_syms) == 1:
                                closes = close_df.dropna()
                            else:
                                closes = close_df[sym].dropna()
                            if not closes.empty and len(closes) >= 2:
                                price = float(closes.iloc[-1])
                                prev = float(closes.iloc[-2])
                                chg = round(price - prev, 2)
                                pct = round(chg / prev * 100, 2) if prev > 0 else 0.0
                                result[sym_to_name[sym]] = {"index": price, "change": chg, "change_pct": pct}
                        except Exception:
                            pass
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
                "FID_COND_MRKT_DIV_CODE": "J",
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

    # ── yfinance 기간 설정 (물리적 한계 극대화: 1m은 7d, 5m은 60d) ────────────────────────────
    if interval <= 1:
        yf_interval, period = "1m",  "7d"
    elif interval <= 5:
        yf_interval, period = "5m",  "60d"
    elif interval <= 15:
        yf_interval, period = "15m", "60d"
    else:
        yf_interval, period = "30m", "60d"

    # ── 1차: yfinance 데이터 (과거 + 오늘 일부 포함 가능) ──────────────────────────
    df_all = pd.DataFrame()
    for suffix in [".KS", ".KQ"]:
        try:
            raw = yf.Ticker(f"{stock_code}{suffix}").history(
                period=period, interval=yf_interval, auto_adjust=True, timeout=1.5
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
    df_concat = pd.concat([df_all, df_kis])
    if df_concat.empty or "datetime" not in df_concat.columns:
        return pd.DataFrame()
    df = df_concat.drop_duplicates("datetime", keep="last").sort_values("datetime").reset_index(drop=True)
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
        notes.append(f"전일 대비 {vol_ratio:.1f}x")

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


_BULK_CACHE: dict = {}    # {cache_key: (timestamp, result)}
_FDR_CACHE:  dict = {}    # {"krx": (timestamp, DataFrame)}
_BULK_TTL = 60            # 종목별 캐시 TTL (초)
_FDR_TTL  = 120           # FDR 전종목 캐시 TTL (초)

def _get_fdr_krx():
    """FDR StockListing("KRX") — 0.6초로 전종목 가격 반환, 2분 캐시."""
    import time as _t
    cached = _FDR_CACHE.get("krx")
    if cached and (_t.time() - cached[0]) < _FDR_TTL:
        return cached[1]
    try:
        import FinanceDataReader as fdr
        df = fdr.StockListing("KRX")
        _FDR_CACHE["krx"] = (_t.time(), df)
        return df
    except Exception:
        return None

def get_kr_prices_bulk(tickers_tuple: tuple) -> dict:
    """섹터 패널용 종목 일괄 시세 조회 (code → {name, price, change_pct}).
    FDR StockListing 우선(0.6초), 소량(10개 미만)은 KIS 직접 조회."""
    import time as _time
    cache_key = tickers_tuple
    cached = _BULK_CACHE.get(cache_key)
    if cached and (_time.time() - cached[0]) < _BULK_TTL:
        return cached[1]

    import yfinance as yf
    import pandas as pd
    results = {}
    _default_status = {"status_code": "55", "mrkt_warn": "00", "short_over": "N",
                       "managed": "N", "halt": "N", "vi_type": "N", "vi_ovtm": "N"}

    # 10개 미만은 KIS 개별 조회 (정확도 우선)
    if len(tickers_tuple) < 10:
        yf_tickers = []
        for code, yf_ticker in tickers_tuple:
            kis = get_kr_stock_price(code)
            if kis and kis.get("price", 0) > 0:
                results[code] = {"name": kis.get("name", code),
                                 "price": kis["price"], "change_pct": kis["change_pct"],
                                 **_default_status}
            else:
                yf_tickers.append((code, yf_ticker))
    else:
        # 10개 이상 — FDR StockListing으로 직행 (0.6초로 전종목 커버)
        fdr_df = _get_fdr_krx()
        if fdr_df is not None and not fdr_df.empty:
            fdr_map = {}
            for _, row in fdr_df.iterrows():
                code = str(row.get("Code", "")).strip().zfill(6)
                try:
                    price = int(row.get("Close", 0) or 0)
                    chg_pct = round(float(row.get("ChagesRatio", 0) or 0), 2)
                    if price > 0:
                        fdr_map[code] = {"name": code, "price": price,
                                         "change_pct": chg_pct, **_default_status}
                except Exception:
                    pass
            for code, _ in tickers_tuple:
                if code not in results and code in fdr_map:
                    results[code] = fdr_map[code]
        yf_tickers = [(code, yf_t) for code, yf_t in tickers_tuple if code not in results]

    # FDR에서 못 가져온 종목은 yfinance 배치 폴백
    if yf_tickers:
        try:
            codes_only = [code for code, _ in yf_tickers]
            all_tickers = [c + ".KS" for c in codes_only] + [c + ".KQ" for c in codes_only]
            raw = yf.download(all_tickers, period="2d", progress=False, timeout=15)
            if not raw.empty:
                close_df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
                for code in codes_only:
                    if code in results:
                        continue
                    for suffix in [".KS", ".KQ"]:
                        yt = code + suffix
                        if yt not in close_df.columns:
                            continue
                        try:
                            closes = close_df[yt].dropna()
                            if len(closes) >= 2:
                                price = round(float(closes.iloc[-1]))
                                prev  = float(closes.iloc[-2])
                                results[code] = {"name": code, "price": price,
                                                 "change_pct": round(((price-prev)/prev*100) if prev>0 else 0.0, 2),
                                                 **_default_status}
                                break
                        except Exception:
                            pass
        except Exception:
            pass

    # 최종 실패 건 처리
    for code, _ in tickers_tuple:
        if code not in results:
            results[code] = {"name": code, "price": 0,
                             "change_pct": 0.0, **_default_status}

    import time as _time
    _BULK_CACHE[cache_key] = (_time.time(), results)
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
@st.cache_data(ttl=60)
def get_us_prices_bulk_kis(tickers_exchange_tuple: tuple) -> dict:
    """섹터 패널용 미국 종목 일괄 시세 조회.

    1차: KIS 해외시세 병렬 조회 (안정적 — yfinance DNS 불안정 회피)
    2차: KIS 누락 종목만 yfinance 배치 보완 (timeout 필수)
    60초 인메모리 캐시 → 같은 종목 재조회는 즉시.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not tickers_exchange_tuple:
        return {}

    tickers      = [t for t, _ in tickers_exchange_tuple]
    exchange_map = {t: e for t, e in tickers_exchange_tuple}
    results: dict = {}

    # ── 1차: KIS 해외시세 병렬 ────────────────────────────────────────
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
            base  = float(o.get("base", 0) or 0)   # 전일종가 — KIS 응답에 'rate' 필드가 없어 직접 계산
            if price > 0:
                chp = round((price - base) / base * 100, 2) if base > 0 else 0.0
                return ticker, {"price": price, "change_pct": chp}
        return ticker, None

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_kis_one, t): t for t in tickers}
        for fut in as_completed(futs):
            try:
                ticker, val = fut.result()
                if val:
                    results[ticker] = val
            except Exception:
                pass

    # ── 2차: KIS 누락분만 yfinance 배치 보완 (timeout 필수 — 무한 매달림 방지) ──
    missing = [t for t in tickers if t not in results]
    if missing:
        try:
            import yfinance as yf
            import pandas as _pd
            raw = yf.download(missing, period="2d", auto_adjust=True, progress=False, threads=True, timeout=8)
            if raw is not None and not raw.empty:
                is_multi = isinstance(raw.columns, _pd.MultiIndex)
                for ticker in missing:
                    try:
                        if is_multi:
                            close_s = raw["Close"][ticker].dropna() if ticker in raw["Close"].columns else _pd.Series(dtype=float)
                        else:
                            close_s = raw["Close"].dropna() if len(missing) == 1 else _pd.Series(dtype=float)
                        if close_s.empty:
                            continue
                        price = round(float(close_s.iloc[-1]), 2)
                        prev  = round(float(close_s.iloc[-2]), 2) if len(close_s) >= 2 else price
                        chp   = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
                        if price > 0:
                            results[ticker] = {"price": price, "change_pct": chp}
                    except Exception:
                        continue
        except Exception:
            pass

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
        "MAX": 15000, "max": 15000,
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
                **_hist_kw, interval=_yf_iv, auto_adjust=True, timeout=1.5
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
            df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True, timeout=1.5)
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
    """상단 티커 표시용 주요 국내 종목 시세 (yfinance 배치 최적화, 60초 캐시)"""
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
    tickers = [f"{code}{suffix}" for code, _, suffix in stocks]
    results = []
    try:
        raw = yf.download(tickers, period="2d", progress=False, timeout=1.5)
        if not raw.empty:
            close_df = raw["Close"]
            for code, name, suffix in stocks:
                try:
                    sym = f"{code}{suffix}"
                    closes = close_df[sym].dropna() if sym in close_df.columns else raw["Close"].dropna() if len(tickers) == 1 else None
                    if closes is not None and len(closes) >= 2:
                        price = round(float(closes.iloc[-1]))
                        prev = float(closes.iloc[-2])
                        pct = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
                        results.append({"name": name, "price": price, "pct": pct})
                except Exception:
                    pass
    except Exception:
        pass
    return results


# ── 미국 주식 랭킹 / 분봉 / 신호 ─────────────────────────────────────────────
_US_WATCHLIST = [
    "NVDA","TSLA","AAPL","MSFT","META","AMZN","GOOGL","AMD","PLTR","AVGO",
    "COIN","MSTR","ARM","SMCI","HOOD","INTC","MU","SOFI","RBLX","SNAP",
    "SQ","SHOP","BABA","PDD","TSM","QCOM","AMAT","JPM","BAC","LLY",
]


def _fetch_us_watchlist_data() -> list:
    import yfinance as yf
    import pandas as pd
    results = []
    try:
        raw = yf.download(_US_WATCHLIST, period="2d", progress=False, timeout=1.5)
        if not raw.empty:
            close_df = raw["Close"]
            volume_df = raw["Volume"] if "Volume" in raw.columns else None
            is_multi = isinstance(raw.columns, pd.MultiIndex)
            for ticker in _US_WATCHLIST:
                try:
                    if is_multi:
                        closes = close_df[ticker].dropna() if ticker in close_df.columns else pd.Series(dtype=float)
                        vols = volume_df[ticker].dropna() if volume_df is not None and ticker in volume_df.columns else pd.Series(dtype=int)
                    else:
                        closes = close_df.dropna() if len(_US_WATCHLIST) == 1 else pd.Series(dtype=float)
                        vols = volume_df.dropna() if volume_df is not None and len(_US_WATCHLIST) == 1 else pd.Series(dtype=int)
                    if not closes.empty:
                        price = round(float(closes.iloc[-1]), 2)
                        prev = round(float(closes.iloc[-2]), 2) if len(closes) >= 2 else price
                        chg = round(((price - prev) / prev * 100) if prev > 0 else 0.0, 2)
                        vol = int(vols.iloc[-1]) if not vols.empty else 0
                        results.append({
                            "티커":       ticker,
                            "현재가($)":  price,
                            "등락률(%)":  chg,
                            "거래량":     vol,
                            "거래량_비율": 1.0,
                        })
                except Exception:
                    pass
    except Exception:
        pass

    if not results:
        # yfinance 실패 시 KIS API 고속 폴백 (중요 10개만)
        from data_kr import get_us_stock_price_kis
        for ticker in _US_WATCHLIST[:10]:
            try:
                kis_res = None
                for exch in ["NASDAQ", "NYSE", "AMEX"]:
                    try:
                        kis_res = get_us_stock_price_kis(ticker, exch)
                        if kis_res and kis_res.get("price", 0) > 0:
                            break
                    except Exception:
                        pass
                if kis_res and kis_res.get("price", 0) > 0:
                    price = float(kis_res["price"])
                    chg = float(kis_res.get("change_pct", 0) or 0)
                    results.append({
                        "티커":       ticker,
                        "현재가($)":  price,
                        "등락률(%)":  chg,
                        "거래량":     int(kis_res.get("volume", 0) or 0),
                        "거래량_비율": 1.0,
                    })
            except Exception:
                continue
    return results


@st.cache_data(ttl=300, show_spinner=False)
def get_us_volume_ranking() -> list:
    """US 거래량 상위 종목 — watchlist yfinance 일괄 배치 조회"""
    results = _fetch_us_watchlist_data()
    results.sort(key=lambda x: x["거래량"], reverse=True)
    return results[:15]


@st.cache_data(ttl=300, show_spinner=False)
def get_us_change_ranking() -> list:
    """US 등락률 상위 종목 — watchlist yfinance 일괄 배치 조회"""
    results = _fetch_us_watchlist_data()
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
        raw = yf.Ticker(ticker).history(**_hist_kw, interval=_yf_iv, auto_adjust=True, timeout=1.5)
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
    # yfinance의 1분봉(1m)은 7일이 한계이며, 5분봉(5m) 이상은 60일이 물리적 제공 한계입니다.
    period = "7d" if yf_interval == "1m" else "60d"
    try:
        raw = yf.Ticker(ticker).history(period=period, interval=yf_interval, auto_adjust=True, prepost=True, timeout=1.5)
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
