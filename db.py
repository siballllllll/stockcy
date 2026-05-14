import gspread
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

@st.cache_resource
def get_gsheet_client():
    """Google Sheets 클라이언트를 초기화하고 캐싱합니다."""
    try:
        if "credentials" in st.secrets["gspread"]:
            creds_dict = dict(st.secrets["gspread"]["credentials"])
        else:
            creds_dict = dict(st.secrets["gspread"])

        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

        gc = gspread.service_account_from_dict(creds_dict)
        return gc
    except Exception as e:
        return None

def _get_spreadsheet():
    gc = get_gsheet_client()
    if not gc:
        return None, "구글 시트 인증 실패. secrets.toml의 gspread 설정을 확인해주세요."
    try:
        # secrets에 spreadsheet_id가 있으면 직접 지정 (빠르고 안정적)
        try:
            sheet_id = st.secrets["gspread"]["spreadsheet_id"]
            return gc.open_by_key(sheet_id), "성공"
        except KeyError:
            pass
        # fallback: 공유된 첫 번째 시트 사용
        spreadsheets = gc.openall()
        if not spreadsheets:
            return None, "봇 계정에 공유된 스프레드시트가 없습니다. 구글 시트를 만들고 봇 이메일을 공유에 추가하거나, secrets에 spreadsheet_id를 추가해주세요."
        return spreadsheets[0], "성공"
    except Exception as e:
        return None, f"스프레드시트 접근 오류: {e}"

def _get_or_create_worksheet(sh, title, headers):
    """시트 탭이 없으면 생성하고 헤더를 추가합니다."""
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=20)
        ws.append_row(headers)
    return ws

def save_portfolio_to_gsheet(portfolio_list, current_prices_df=None):
    """현재 포트폴리오 스냅샷을 '현재포트폴리오' 탭에 저장합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg

    try:
        headers = ["저장시간", "티커", "종목명", "수량", "매수가($)", "현재가($)", "수익금($)", "수익률(%)", "등급"]
        ws = _get_or_create_worksheet(sh, "현재포트폴리오", headers)
        ws.clear()
        ws.append_row(headers)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in portfolio_list:
            ticker = item["ticker"]
            bp = item["buy_price"]
            qty = item["quantity"]
            name = item.get("name", ticker)
            rating = item.get("rating", "-")

            cp = bp
            profit, profit_pct = 0.0, 0.0
            if current_prices_df is not None and not current_prices_df.empty:
                if ticker in current_prices_df["심볼"].values:
                    cp = current_prices_df[current_prices_df["심볼"] == ticker].iloc[0]["현재가($)"]
                    invested = bp * qty
                    profit = (cp * qty) - invested
                    profit_pct = (profit / invested * 100) if invested > 0 else 0

            ws.append_row([now, ticker, name, qty,
                           round(bp, 2), round(cp, 2),
                           round(profit, 2), round(profit_pct, 2), rating])

        return True, f"'{sh.title}' > '현재포트폴리오' 탭에 {len(portfolio_list)}개 종목 저장 완료!"
    except Exception as e:
        return False, f"저장 오류: {e}"

def load_portfolio_from_gsheet():
    """'현재포트폴리오' 탭에서 포트폴리오 목록을 불러옵니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return []
    try:
        ws = sh.worksheet("현재포트폴리오")
        records = ws.get_all_records()
        portfolio_list = []
        for r in records:
            portfolio_list.append({
                "ticker": str(r.get("티커", "")),
                "name": str(r.get("종목명", "")),
                "buy_price": float(r.get("매수가($)", 0) or 0),
                "quantity": int(r.get("수량", 0) or 0),
                "buy_date": str(r.get("저장시간", "")),
                "rating": str(r.get("등급", "-")),
            })
        return portfolio_list
    except Exception:
        return []

def save_ai_portfolio_to_gsheet(portfolio_list):
    """AI 자동 추천 종목 목록을 'AI추천포트폴리오' 탭에 저장합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["저장시간", "티커", "종목명", "수량", "매수가($)", "등급"]
        ws = _get_or_create_worksheet(sh, "AI추천포트폴리오", headers)
        ws.clear()
        ws.append_row(headers)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in portfolio_list:
            ws.append_row([
                now,
                item["ticker"],
                item.get("name", item["ticker"]),
                item.get("quantity", 0),
                round(float(item.get("buy_price", 0)), 2),
                item.get("rating", "-"),
            ])
        return True, f"AI 추천 포트폴리오 {len(portfolio_list)}개 저장 완료!"
    except Exception as e:
        return False, f"저장 오류: {e}"


def load_ai_portfolio_from_gsheet():
    """'AI추천포트폴리오' 탭에서 목록을 불러옵니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return []
    try:
        ws = sh.worksheet("AI추천포트폴리오")
        records = ws.get_all_records()
        return [
            {
                "ticker":    str(r.get("티커", "")),
                "name":      str(r.get("종목명", "")),
                "buy_price": float(r.get("매수가($)", 0) or 0),
                "quantity":  int(r.get("수량", 0) or 0),
                "buy_date":  str(r.get("저장시간", "")),
                "rating":    str(r.get("등급", "-")),
            }
            for r in records if r.get("티커")
        ]
    except Exception:
        return []


def save_trade_record(trade):
    """완료된 거래 1건을 '거래내역' 탭에 기록합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg

    try:
        headers = ["매도시간", "티커", "종목명", "수량", "매수가($)", "매도가($)", "수익금($)", "수익률(%)", "결과"]
        ws = _get_or_create_worksheet(sh, "거래내역", headers)
        ws.append_row([
            trade.get("sell_date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            trade.get("ticker", ""),
            trade.get("name", ""),
            trade.get("quantity", 0),
            round(float(trade.get("buy_price", 0)), 2),
            round(float(trade.get("sell_price", 0)), 2),
            round(float(trade.get("profit", 0)), 2),
            round(float(trade.get("profit_pct", 0)), 2),
            trade.get("result", "")
        ])
        return True, "거래 내역이 구글 시트에 기록되었습니다."
    except Exception as e:
        return False, f"기록 오류: {e}"

def delete_trade_from_gsheet(ticker: str, sell_date: str):
    """'거래내역' 탭에서 ticker + sell_date가 일치하는 행을 삭제합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        ws = sh.worksheet("거래내역")
        rows = ws.get_all_values()
        # 헤더 제외, 역순으로 찾아서 삭제 (인덱스 밀림 방지)
        for i in range(len(rows) - 1, 0, -1):
            row = rows[i]
            if len(row) >= 2 and str(row[0]).strip() == str(sell_date).strip() and str(row[1]).strip() == str(ticker).strip():
                ws.delete_rows(i + 1)  # gspread는 1-indexed
                return True, "구글 시트에서 삭제 완료"
        return False, "해당 거래를 구글 시트에서 찾지 못했습니다."
    except gspread.WorksheetNotFound:
        return False, "거래내역 탭이 없습니다."
    except Exception as e:
        return False, f"삭제 오류: {e}"


def load_trade_history_from_gsheet():
    """'거래내역' 탭에서 모든 거래 기록을 DataFrame으로 불러옵니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return None, msg

    try:
        ws = sh.worksheet("거래내역")
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame(), "구글 시트의 거래내역 탭이 비어있습니다."
        return pd.DataFrame(records), "성공"
    except gspread.WorksheetNotFound:
        return pd.DataFrame(), "거래내역 탭이 아직 없습니다. 매도 기록 시 자동으로 생성됩니다."
    except Exception as e:
        return None, f"로드 오류: {e}"

def log_ai_recommendation(rec_type: str, ticker: str, name: str, rating: str,
                           buy_target: str, sell_target: str, stop_loss: str):
    """AI 추천 내역을 'AI추천로그' 탭에 자동 기록합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["기록시간", "유형", "티커", "종목명", "등급/추천", "매수가", "목표가", "손절가"]
        ws = _get_or_create_worksheet(sh, "AI추천로그", headers)
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            rec_type,
            ticker,
            name,
            rating,
            str(buy_target),
            str(sell_target),
            str(stop_loss),
        ])
        return True, "AI 추천 로그 기록 완료"
    except Exception as e:
        return False, f"로그 기록 오류: {e}"
 
 
def save_favorite(market_type: str, ticker: str, name: str):
    """종목을 '즐겨찾기' 탭에 추가합니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return False, msg
    try:
        headers = ["추가시간", "시장", "티커", "종목명"]
        ws = _get_or_create_worksheet(sh, "즐겨찾기", headers)
        
        # 중복 체크
        existing = ws.get_all_records()
        if any(r["티커"] == ticker for r in existing):
            return True, "이미 즐겨찾기에 등록된 종목입니다."
            
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            market_type, ticker, name
        ])
        return True, f"[{name}] 즐겨찾기에 추가되었습니다."
    except Exception as e:
        return False, f"저장 오류: {e}"

def remove_favorite(ticker: str):
    """종목을 '즐겨찾기' 탭에서 삭제합니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return False, msg
    try:
        ws = sh.worksheet("즐겨찾기")
        cells = ws.find(ticker)
        if cells:
            ws.delete_rows(cells.row)
            return True, "즐겨찾기에서 삭제되었습니다."
        return False, "목록에서 종목을 찾을 수 없습니다."
    except Exception as e:
        return False, f"삭제 오류: {e}"

def load_favorites():
    """'즐겨찾기' 탭에서 모든 종목을 불러옵니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return [], msg
    try:
        ws = sh.worksheet("즐겨찾기")
        records = ws.get_all_records()
        return records, "성공"
    except gspread.WorksheetNotFound:
        return [], "즐겨찾기 목록이 비어있습니다."
    except Exception as e:
        return [], f"로드 오류: {e}"


def is_favorite(ticker):
    """특정 종목이 즐겨찾기에 있는지 확인합니다."""
    favs, _ = load_favorites()
    return any(str(f.get('티커', '')) == str(ticker) for f in favs)


def _enrich_with_krx(raw_map: dict) -> dict:
    """FinanceDataReader(KRX)로 섹터 맵의 코드·suffix를 자동 보정."""
    try:
        from data_kr import get_kr_name_to_code_map
        name_map = get_kr_name_to_code_map()
    except Exception:
        name_map = {}
    if not name_map:
        return raw_map
    enriched: dict = {}
    for sector, subsectors in raw_map.items():
        enriched[sector] = {}
        for sub, stocks in subsectors.items():
            enriched_stocks = []
            for s in stocks:
                info = name_map.get(s["name"])
                enriched_stocks.append(
                    {"name": s["name"], "code": info["code"], "suffix": info["suffix"]}
                    if info else s.copy()
                )
            enriched[sector][sub] = enriched_stocks
    return enriched


@st.cache_data(ttl=300)
def load_sector_map() -> dict:
    """Google Sheets 섹터DB 탭 → sectors_kr.py → FDR 전종목 업종 순으로 병합.

    1. 구글 시트 / sectors_kr.py 로 테마 섹터맵 로드
    2. FDR(FinanceDataReader) 업종 분류로 전종목 자동 보강
       - 기존 섹터에 없는 업종만 추가 (중복 방지)
       - 기존 세부섹터에 없는 종목만 추가
    """
    from sectors_kr import KR_SECTOR_MAP
    try:
        sh, _ = _get_spreadsheet()
        if sh is None:
            raise Exception("no sheet")
        try:
            ws = sh.worksheet("섹터DB")
        except gspread.WorksheetNotFound:
            raise Exception("섹터DB 탭 없음")
        rows = ws.get_all_records()
        if not rows:
            raise Exception("empty")
        sector_map: dict = {}
        for row in rows:
            sec  = str(row.get("섹터",    "")).strip()
            sub  = str(row.get("세부섹터", "")).strip()
            name = str(row.get("종목명",   "")).strip()
            code = str(row.get("종목코드", "")).strip()
            sfx  = str(row.get("suffix",   ".KS")).strip()
            if not all([sec, sub, name, code]):
                continue
            sector_map.setdefault(sec, {}).setdefault(sub, []).append(
                {"name": name, "code": code, "suffix": sfx}
            )
        if not sector_map:
            raise Exception("파싱 결과 빈 맵")
        raw = KR_SECTOR_MAP if len(KR_SECTOR_MAP) >= len(sector_map) else sector_map
    except Exception:
        raw = KR_SECTOR_MAP

    # ── FDR 전종목 업종 자동 병합 ────────────────────────────────────────
    try:
        from data_kr import get_kr_fdr_sector_map
        fdr_map = get_kr_fdr_sector_map()
        if fdr_map:
            existing_codes: set = {
                s["code"]
                for subs in raw.values()
                for stocks in subs.values()
                for s in stocks
                if isinstance(s, dict) and s.get("code")
            }
            for sector, subs in fdr_map.items():
                for sub, stocks in subs.items():
                    new_stocks = [
                        s for s in stocks
                        if s.get("code") and s["code"] not in existing_codes
                    ]
                    if not new_stocks:
                        continue
                    if sector not in raw:
                        raw[sector] = {}
                    if sub not in raw[sector]:
                        raw[sector][sub] = []
                    raw[sector][sub].extend(new_stocks)
                    existing_codes.update(s["code"] for s in new_stocks)
    except Exception:
        pass

    # ── 키워드 자동 분류 (테마 섹터 보강) ────────────────────────────────
    try:
        from data_kr import get_kr_fdr_sector_map as _fdr_kr
        from sector_auto_classifier import enrich_sector_map_kr
        fdr_all_list: list = []
        fdr_raw = _fdr_kr()
        for _sec, _subs in fdr_raw.items():
            for _sub, _stks in _subs.items():
                for _s in _stks:
                    fdr_all_list.append({**_s, "industry": _sec})
        raw = enrich_sector_map_kr(raw, fdr_all_list)
    except Exception:
        pass

    # ── 상장폐지 종목 제거 — pykrx 현재 거래 종목 기준 필터링 ──────────────
    try:
        from pykrx import stock as _pykrx
        import datetime as _dt
        _today = _dt.date.today().strftime("%Y%m%d")
        _active: set = set()
        for _mkt in ["KOSPI", "KOSDAQ"]:
            try:
                _active.update(_pykrx.get_market_ticker_list(_today, market=_mkt))
            except Exception:
                pass
        if _active:
            for _sec in list(raw.keys()):
                for _sub in list(raw[_sec].keys()):
                    raw[_sec][_sub] = [s for s in raw[_sec][_sub] if s.get("code") in _active]
                    if not raw[_sec][_sub]:
                        del raw[_sec][_sub]
                if not raw[_sec]:
                    del raw[_sec]
    except Exception:
        pass

    return _enrich_with_krx(raw)


# FDR 영문 섹터 → 한국어 섹터 매핑
_FDR_TO_KR_SECTOR = {
    "Technology":             "빅테크·AI소프트",
    "Healthcare":             "바이오·헬스케어",
    "Financial Services":     "금융·핀테크",
    "Financials":             "금융·핀테크",
    "Finance":                "금융·핀테크",
    "Consumer Cyclical":      "소비재·유통",
    "Consumer Discretionary": "소비재·유통",
    "Consumer Defensive":     "소비재·유통",
    "Consumer Staples":       "소비재·유통",
    "Communication Services": "통신·네트워크",
    "Communications":         "통신·네트워크",
    "Energy":                 "에너지·원자력",
    "Industrials":            "전통 산업·소재",
    "Industrial":             "전통 산업·소재",
    "Basic Materials":        "광업·귀금속·원자재",
    "Materials":              "광업·귀금속·원자재",
    "Real Estate":            "리츠·부동산",
    "Utilities":              "전력 인프라·그리드",
}

# FDR 영문 업종(Industry) → 한국어 세부섹터 매핑
_FDR_TO_KR_INDUSTRY = {
    "Semiconductors":                           "반도체",
    "Semiconductor Equipment & Materials":      "반도체 장비·소재",
    "Software—Application":                     "소프트웨어·앱",
    "Software—Infrastructure":                  "소프트웨어·인프라",
    "Information Technology Services":          "IT서비스",
    "Computer Hardware":                        "컴퓨터 하드웨어",
    "Electronic Components":                    "전자부품",
    "Internet Content & Information":           "인터넷·콘텐츠",
    "Electronics & Computer Distribution":      "전자·컴퓨터 유통",
    "Scientific & Technical Instruments":       "계측·기술장비",
    "Biotechnology":                            "바이오테크",
    "Drug Manufacturers—General":               "제약 대형",
    "Drug Manufacturers—Specialty & Generic":   "제약 중소형",
    "Medical Devices":                          "의료기기",
    "Medical Instruments & Supplies":           "의료기기·용품",
    "Diagnostics & Research":                   "진단·연구",
    "Healthcare Plans":                         "헬스케어 보험",
    "Health Information Services":              "헬스케어 IT",
    "Banks—Diversified":                        "종합은행",
    "Banks—Regional":                           "지역은행",
    "Insurance—Life":                           "생명보험",
    "Insurance—Property & Casualty":            "손해보험",
    "Insurance—Diversified":                    "복합보험",
    "Asset Management":                         "자산운용",
    "Capital Markets":                          "자본시장",
    "Credit Services":                          "신용서비스",
    "Mortgage Finance":                         "모기지금융",
    "Electronic Gaming & Multimedia":           "게임·멀티미디어",
    "Telecom Services":                         "통신서비스",
    "Entertainment":                            "엔터테인먼트",
    "Broadcasting":                             "방송",
    "Publishing":                               "출판·미디어",
    "Advertising Agencies":                     "광고대행",
    "Auto Manufacturers":                       "자동차 제조",
    "Auto Parts":                               "자동차 부품",
    "Specialty Retail":                         "전문 소매",
    "Apparel Retail":                           "의류 소매",
    "Apparel Manufacturing":                    "의류 제조",
    "Department Stores":                        "백화점·유통",
    "Discount Stores":                          "할인점",
    "Grocery Stores":                           "식료품점",
    "Restaurants":                              "외식업",
    "Travel Services":                          "여행서비스",
    "Airlines":                                 "항공사",
    "Hotels & Motels":                          "호텔·모텔",
    "Lodging":                                  "숙박",
    "Resorts & Casinos":                        "리조트·카지노",
    "Leisure":                                  "레저",
    "Oil & Gas E&P":                            "석유·가스 탐사",
    "Oil & Gas Integrated":                     "석유·가스 통합",
    "Oil & Gas Refining & Marketing":           "정유·마케팅",
    "Oil & Gas Equipment & Services":           "석유·가스 장비",
    "Oil & Gas Midstream":                      "석유·가스 미드스트림",
    "Uranium":                                  "우라늄",
    "Solar":                                    "태양광",
    "Utilities—Regulated Electric":             "규제 전력",
    "Utilities—Renewable":                      "재생에너지",
    "Utilities—Independent Power Producers":    "독립발전사",
    "Utilities—Diversified":                    "다각화 유틸리티",
    "Utilities—Regulated Gas":                  "규제 가스",
    "Utilities—Regulated Water":                "규제 수도",
    "Gold":                                     "금광",
    "Silver":                                   "은광",
    "Copper":                                   "구리·광물",
    "Steel":                                    "철강",
    "Aluminum":                                 "알루미늄",
    "Other Industrial Metals & Mining":         "기타 광업",
    "Agricultural Inputs":                      "농업 소재",
    "Chemicals":                                "화학",
    "Specialty Chemicals":                      "특수화학",
    "Building Materials":                       "건설 소재",
    "Aerospace & Defense":                      "항공·방산",
    "Industrial Machinery":                     "산업기계",
    "Farm & Heavy Construction Machinery":      "농기계·중장비",
    "Electrical Equipment & Parts":             "전기장비·부품",
    "Engineering & Construction":               "엔지니어링·건설",
    "Waste Management":                         "폐기물관리",
    "Staffing & Employment Services":           "인력파견",
    "Business Services":                        "비즈니스서비스",
    "Rental & Leasing Services":                "임대·리스",
    "Security & Protection Services":           "보안서비스",
    "Trucking":                                 "트럭운송",
    "Railroads":                                "철도",
    "Marine Shipping":                          "해운",
    "Integrated Freight & Logistics":           "물류·택배",
    "REIT—Diversified":                         "다각화 리츠",
    "REIT—Office":                              "오피스 리츠",
    "REIT—Industrial":                          "산업 리츠",
    "REIT—Retail":                              "리테일 리츠",
    "REIT—Residential":                         "주거 리츠",
    "REIT—Mortgage":                            "모기지 리츠",
    "REIT—Specialty":                           "특수 리츠",
    "REIT—Healthcare Facilities":               "헬스케어 리츠",
    "REIT—Hotel & Motel":                       "호텔 리츠",
    "Real Estate Services":                     "부동산 서비스",
    "Real Estate—Diversified":                  "복합 부동산",
    "Consumer Electronics":                     "소비자가전",
    "Packaging & Containers":                   "포장재",
    "Paper & Paper Products":                   "제지",
    "Lumber & Wood Production":                 "목재",
    "Personal Services":                        "개인서비스",
    "Education & Training Services":            "교육·훈련",
    "Medical Care Facilities":                  "의료시설",
    "Pharmaceutical Retailers":                 "의약품 소매",
}


@st.cache_data(ttl=300)
def load_us_sector_map() -> dict:
    """Google Sheets 섹터DB_US 탭 → sectors_us.py → FDR 전종목 업종 순으로 병합."""
    try:
        sh, _ = _get_spreadsheet()
        if sh is None:
            raise Exception("no sheet")
        try:
            ws = sh.worksheet("섹터DB_US")
        except gspread.WorksheetNotFound:
            raise Exception("섹터DB_US 탭 없음")
        rows = ws.get_all_records()
        if not rows:
            raise Exception("empty")
        sector_map: dict = {}
        for row in rows:
            sec      = str(row.get("섹터",    "")).strip()
            sub      = str(row.get("세부섹터", "")).strip()
            name     = str(row.get("종목명",   "")).strip()
            ticker   = str(row.get("티커",    "")).strip()
            exchange = str(row.get("exchange", "NASDAQ")).strip()
            if not all([sec, sub, name, ticker]):
                continue
            sector_map.setdefault(sec, {}).setdefault(sub, []).append(
                {"name": name, "ticker": ticker, "exchange": exchange}
            )
        if not sector_map:
            raise Exception("파싱 결과 빈 맵")
        raw = sector_map
    except Exception:
        from sectors_us import US_SECTOR_MAP
        raw = US_SECTOR_MAP

    # FDR 전종목으로 보강: 기존에 없는 종목만 해당 한국어 섹터에 추가
    try:
        from data_kr import get_us_fdr_sector_map
        fdr_map = get_us_fdr_sector_map()
        # 이미 등록된 티커 집합 (중복 방지)
        existing = {s["ticker"] for subs in raw.values() for stks in subs.values() for s in stks}
        for fdr_sec, fdr_subs in fdr_map.items():
            kr_sec = _FDR_TO_KR_SECTOR.get(fdr_sec)
            if not kr_sec or kr_sec not in raw:
                continue
            for fdr_sub, fdr_stocks in fdr_subs.items():
                kr_sub = _FDR_TO_KR_INDUSTRY.get(fdr_sub, fdr_sub)
                new = [s for s in fdr_stocks if s["ticker"] not in existing]
                if not new:
                    continue
                raw[kr_sec].setdefault(kr_sub, []).extend(new)
                for s in new:
                    existing.add(s["ticker"])
    except Exception:
        pass

    return raw


def init_us_sector_sheet():
    """sectors_us.py 기본 데이터를 Google Sheets 섹터DB_US 탭에 업로드 (덮어쓰기)."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        from sectors_us import US_SECTOR_MAP
        headers = ["섹터", "세부섹터", "종목명", "티커", "exchange"]
        ws = _get_or_create_worksheet(sh, "섹터DB_US", headers)
        ws.clear()
        ws.append_row(headers)
        rows_to_add = []
        for sec, subs in US_SECTOR_MAP.items():
            for sub, stocks in subs.items():
                for s in stocks:
                    rows_to_add.append([sec, sub, s["name"], s["ticker"], s["exchange"]])
        if rows_to_add:
            ws.append_rows(rows_to_add)
        load_us_sector_map.clear()
        return True, f"섹터DB_US에 {len(rows_to_add)}개 종목 업로드 완료!"
    except Exception as e:
        return False, f"업로드 오류: {e}"


def init_sector_sheet():
    """sectors_kr.py 기본 데이터를 Google Sheets 섹터DB 탭에 업로드 (덮어쓰기)."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        from sectors_kr import KR_SECTOR_MAP
        headers = ["섹터", "세부섹터", "종목명", "종목코드", "suffix"]
        ws = _get_or_create_worksheet(sh, "섹터DB", headers)
        ws.clear()
        ws.append_row(headers)
        rows_to_add = []
        for sec, subs in KR_SECTOR_MAP.items():
            for sub, stocks in subs.items():
                for s in stocks:
                    rows_to_add.append([sec, sub, s["name"], s["code"], s["suffix"]])
        if rows_to_add:
            ws.append_rows(rows_to_add)
        load_sector_map.clear()
        return True, f"섹터DB에 {len(rows_to_add)}개 종목 업로드 완료!"
    except Exception as e:
        return False, f"업로드 오류: {e}"


def save_trade_analysis_record(trade_data: dict, analysis_result: dict):
    """AI 거래 분석 결과를 '거래분석DB' 탭에 개별 저장합니다 (중복 방지)."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = [
            "분석시간", "티커", "종목명", "매도일", "수익률(%)", "결과",
            "섹터", "섹터특성", "사회적요인", "수급요인", "기술적요인",
            "성공이유", "실패이유", "교훈"
        ]
        ws = _get_or_create_worksheet(sh, "거래분석DB", headers)

        ticker = str(trade_data.get("ticker", ""))
        sell_date = str(trade_data.get("sell_date", ""))[:10]

        # 중복 체크
        existing = ws.get_all_records()
        for r in existing:
            if str(r.get("티커", "")) == ticker and str(r.get("매도일", ""))[:10] == sell_date:
                return True, "이미 저장된 분석입니다."

        trades_list = analysis_result.get("trades", [])
        tr = trades_list[0] if trades_list else {}

        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ticker,
            str(trade_data.get("name", "")),
            sell_date,
            round(float(trade_data.get("profit_pct", 0)), 2),
            str(trade_data.get("result", "")),
            str(tr.get("sector", "")),
            str(tr.get("sector_characteristic", "")),
            str(tr.get("social_factor", "")),
            str(tr.get("institutional_factor", "")),
            str(tr.get("technical_factor", "")),
            str(tr.get("success_reason", "")),
            str(tr.get("failure_reason", "")),
            str(tr.get("lesson", "")),
        ])
        return True, "거래 분석이 '거래분석DB'에 저장되었습니다."
    except Exception as e:
        return False, f"저장 오류: {e}"


def load_trade_analysis_records():
    """'거래분석DB' 탭에서 모든 분석 기록을 로드합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return [], msg
    try:
        ws = sh.worksheet("거래분석DB")
        records = ws.get_all_records()
        return records, "성공"
    except gspread.WorksheetNotFound:
        return [], "아직 저장된 분석 기록이 없습니다."
    except Exception as e:
        return [], f"로드 오류: {e}"


def save_trade_analysis(analysis: dict):
    """AI 거래 분석 결과를 '매매분석일지' 탭에 저장합니다."""
    import json as _json
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["분석시간", "총거래", "승", "패", "승률(%)", "성공패턴", "실패패턴", "핵심인사이트", "향후전략", "종목별분석(JSON)"]
        ws = _get_or_create_worksheet(sh, "매매분석일지", headers)
        summary = analysis.get("summary", {})
        total = summary.get("total", 0)
        wins = summary.get("win_count", 0)
        losses = summary.get("loss_count", 0)
        win_rate = round(wins / total * 100, 1) if total > 0 else 0
        insights = " | ".join(summary.get("key_insights", []))
        trades_json = _json.dumps(analysis.get("trades", []), ensure_ascii=False)
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total, wins, losses, win_rate,
            summary.get("win_pattern", ""),
            summary.get("loss_pattern", ""),
            insights,
            summary.get("future_strategy", ""),
            trades_json,
        ])
        return True, "매매 분석 결과가 구글 시트 '매매분석일지' 탭에 저장되었습니다."
    except Exception as e:
        return False, f"저장 오류: {e}"


def load_trade_analysis():
    """'매매분석일지' 탭에서 가장 최근 분석 결과를 불러옵니다."""
    import json as _json
    sh, msg = _get_spreadsheet()
    if not sh:
        return None, msg
    try:
        ws = sh.worksheet("매매분석일지")
        records = ws.get_all_records()
        if not records:
            return None, "저장된 분석 결과가 없습니다."
        last = records[-1]
        trades_raw = last.get("종목별분석(JSON)", "[]")
        try:
            trades = _json.loads(trades_raw)
        except Exception:
            trades = []
        return {
            "analyzed_at": last.get("분석시간", ""),
            "summary": {
                "total": last.get("총거래", 0),
                "win_count": last.get("승", 0),
                "loss_count": last.get("패", 0),
                "win_rate": last.get("승률(%)", 0),
                "win_pattern": last.get("성공패턴", ""),
                "loss_pattern": last.get("실패패턴", ""),
                "key_insights": [i.strip() for i in str(last.get("핵심인사이트", "")).split("|") if i.strip()],
                "future_strategy": last.get("향후전략", ""),
            },
            "trades": trades,
        }, "성공"
    except gspread.WorksheetNotFound:
        return None, "아직 저장된 분석이 없습니다. AI 분석 후 저장하세요."
    except Exception as e:
        return None, f"로드 오류: {e}"


def test_connection_and_write():
    """연결 테스트용 함수 (하위 호환성 유지)."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg

    try:
        ws = sh.sheet1
        if not ws.get_all_values():
            ws.append_row(["시간", "종목명", "추천가", "목표가", "상태"])
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([now, "연결테스트_OK", "-", "-", "성공"])
        return True, f"연결 성공! '{sh.title}' 시트에 테스트 데이터가 입력되었습니다."
    except Exception as e:
        return False, f"에러 발생: {e}"


def save_ai_cache(cache_key: str, data: dict, ttl_hours: int = 12):
    """AI 생성 결과를 'AI캐시' 탭에 저장합니다 (기존 동일 키는 덮어씀)."""
    import json as _json
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["캐시키", "저장시간", "만료시간", "데이터"]
        ws = _get_or_create_worksheet(sh, "AI캐시", headers)
        # 기존 동일 키 행 삭제 (역순)
        rows = ws.get_all_values()
        for i in range(len(rows) - 1, 0, -1):
            if len(rows[i]) >= 1 and rows[i][0] == cache_key:
                ws.delete_rows(i + 1)
        now = datetime.now()
        expire = now + timedelta(hours=ttl_hours)
        ws.append_row([
            cache_key,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            expire.strftime("%Y-%m-%d %H:%M:%S"),
            _json.dumps(data, ensure_ascii=False),
        ])
        return True, "캐시 저장 완료"
    except Exception as e:
        return False, f"캐시 저장 오류: {e}"


def load_ai_cache(cache_key: str) -> dict | None:
    """'AI캐시' 탭에서 유효한 캐시를 로드합니다. 만료·없으면 None."""
    import json as _json
    sh, msg = _get_spreadsheet()
    if not sh:
        return None
    try:
        ws = sh.worksheet("AI캐시")
        rows = ws.get_all_records()
        for r in rows:
            if str(r.get("캐시키", "")) != cache_key:
                continue
            expire_str = str(r.get("만료시간", ""))
            if expire_str:
                try:
                    expire_dt = datetime.strptime(expire_str, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() > expire_dt:
                        return None
                except ValueError:
                    pass
            data_str = str(r.get("데이터", ""))
            if data_str:
                return _json.loads(data_str)
        return None
    except gspread.WorksheetNotFound:
        return None
    except Exception:
        return None


def delete_ai_cache(cache_key: str):
    """'AI캐시' 탭에서 특정 키의 캐시를 삭제합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False
    try:
        ws = sh.worksheet("AI캐시")
        rows = ws.get_all_values()
        for i in range(len(rows) - 1, 0, -1):
            if len(rows[i]) >= 1 and rows[i][0] == cache_key:
                ws.delete_rows(i + 1)
        return True
    except gspread.WorksheetNotFound:
        return True
    except Exception:
        return False


# ── 종목 AI 분석 이력 ──────────────────────────────────────────────────────────

_ANALYSIS_HISTORY_HEADERS = [
    "분석시간", "시장", "티커", "종목명", "현재가",
    "매수구간", "목표가", "손절가", "등급", "중장기등급", "단기전망률", "JSON",
]


def save_stock_analysis_history(market: str, ticker: str, name: str, current_price, analysis: dict) -> bool:
    """종목 AI 분석 결과를 '종목분석이력' 탭에 1행 추가 저장합니다."""
    sh, _ = _get_spreadsheet()
    if not sh:
        return False
    try:
        import json as _json
        ws = _get_or_create_worksheet(sh, "종목분석이력", _ANALYSIS_HISTORY_HEADERS)
        now = (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([
            now,
            market,
            ticker,
            name,
            str(current_price) if current_price else "",
            str(analysis.get("buy_target", "")),
            str(analysis.get("sell_target", "")),
            str(analysis.get("stop_loss", "")),
            str(analysis.get("rating", "")),
            str(analysis.get("long_term_rating", "")),
            str(analysis.get("short_term_view_pct", "")),
            _json.dumps(analysis, ensure_ascii=False)[:6000],
        ])
        return True
    except Exception:
        return False


def load_stock_analysis_history(ticker: str, limit: int = 10) -> list[dict]:
    """'종목분석이력' 탭에서 해당 티커의 최근 분석 기록을 반환합니다 (오래된→최신 순)."""
    sh, _ = _get_spreadsheet()
    if not sh:
        return []
    try:
        ws = sh.worksheet("종목분석이력")
        records = ws.get_all_records()
        hits = [r for r in records if str(r.get("티커", "")) == str(ticker)]
        return hits[-limit:] if len(hits) > limit else hits
    except Exception:
        return []
