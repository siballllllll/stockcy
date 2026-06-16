"""[DART 전자공시 Open API 연동] — KR 결정론 밸류 보강 (무료·공식)

KIS엔 없는 현금흐름표를 DART에서 받아 FCF·EV/EBITDA를 계산한다.
- corp_code 매핑: corpCode.xml(전종목 고유번호) 다운로드·캐시
- 재무제표: fnlttSinglAcntAll(단일회사 전체 재무제표, 연결 우선→별도)
인증키: .env의 DART_API_KEY (오타 호환: DARK_API_KEY).
"""

import os
import io
import zipfile
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import st_compat as st


def _dart_key() -> str:
    return os.getenv("DART_API_KEY") or os.getenv("DARK_API_KEY") or ""


@st.cache_data(ttl=86400, show_spinner=False)  # 고유번호 매핑은 거의 안 바뀜 — 24h
def _corp_code_map() -> dict:
    """DART corpCode.xml → {stock_code(6자리): corp_code(8자리)}."""
    key = _dart_key()
    if not key:
        return {}
    try:
        r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                         params={"crtfc_key": key}, timeout=25)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        root = ET.fromstring(z.read(z.namelist()[0]))
        m = {}
        for el in root.iter("list"):
            sc = (el.findtext("stock_code") or "").strip()
            cc = (el.findtext("corp_code") or "").strip()
            if sc and len(sc) == 6 and cc:
                m[sc] = cc
        return m
    except Exception as e:
        print(f"[DART corpCode] 실패: {repr(e)[:120]}")
        return {}


def get_corp_code(stock_code: str):
    return _corp_code_map().get(str(stock_code).strip().zfill(6))


def _num(s):
    try:
        return float(str(s).replace(",", "")) if s not in (None, "", "-") else None
    except (TypeError, ValueError):
        return None


def _parse(items: list, year: int, fs_div: str) -> dict:
    """재무제표 계정 리스트 → FCF·EBITDA·순부채 원시값(원). 계정명은 회사별 표기차가 있어 부분일치."""
    def find(sj, *names):
        for nm in names:
            for it in items:
                if it.get("sj_div") == sj and nm in (it.get("account_nm") or ""):
                    v = _num(it.get("thstrm_amount"))
                    if v is not None:
                        return v
        return None

    cfo   = find("CF", "영업활동현금흐름", "영업활동으로인한현금흐름")
    capex = find("CF", "유형자산의 취득", "유형자산의취득", "유형자산취득")
    dep   = find("CF", "감가상각")
    op    = find("IS", "영업이익")
    bonds = find("BS", "사채") or 0
    stdbt = find("BS", "단기차입금") or 0
    ltdbt = find("BS", "장기차입금") or 0
    cash  = find("BS", "현금및현금성자산", "현금및현금성자산및")

    # capex는 부호 관행이 회사마다 달라(유출 양수/음수) abs로 통일 후 차감
    fcf = (cfo - abs(capex)) if (cfo is not None and capex is not None) else None
    ebitda = (op + dep) if (op is not None and dep is not None) else op  # 감가상각 없으면 EBIT
    debt = (bonds or 0) + (stdbt or 0) + (ltdbt or 0)
    net_debt = (debt - cash) if cash is not None else None

    return {"fcf": fcf, "ebitda": ebitda, "net_debt": net_debt, "op_profit": op,
            "cfo": cfo, "capex": capex, "depreciation": dep,
            "year": year, "fs_div": fs_div, "has_dep": dep is not None}


def get_kr_financials_dart(stock_code: str) -> dict:
    """DART 단일회사 전체 재무제표 → FCF·EBITDA·순부채(원). 최신 사업보고서 우선.
    캐시는 호출측(valuation_score 24h)에 위임 — 실패 결과를 박지 않기 위해 무캐시."""
    key = _dart_key()
    cc = get_corp_code(stock_code)
    if not key or not cc:
        return {}
    y = datetime.now().year
    for year in (y - 1, y - 2):              # 최신 연차 미제출 대비 직전년도 폴백
        for fs_div in ("CFS", "OFS"):        # 연결 우선 → 없으면 별도
            try:
                r = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
                    params={"crtfc_key": key, "corp_code": cc, "bsns_year": str(year),
                            "reprt_code": "11011", "fs_div": fs_div}, timeout=15)
                d = r.json()
            except Exception:
                continue
            if d.get("status") == "000" and d.get("list"):
                parsed = _parse(d["list"], year, fs_div)
                # FCF나 EBITDA 중 하나라도 나오면 채택
                if parsed.get("fcf") is not None or parsed.get("ebitda") is not None:
                    return parsed
    return {}
