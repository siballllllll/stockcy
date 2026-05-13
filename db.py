import gspread
import streamlit as st
import pandas as pd
from datetime import datetime

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

    return _enrich_with_krx(raw)


@st.cache_data(ttl=300)
def load_us_sector_map() -> dict:
    """Google Sheets 섹터DB_US 탭 → sectors_us.py → FDR 전종목 업종 순으로 병합.

    1. 구글 시트 / sectors_us.py 로 큐레이션 섹터맵 로드
    2. FDR(FinanceDataReader) 업종 분류로 전종목 자동 보강
       - 기존 섹터에 없는 업종만 추가 (중복 방지)
       - 기존 세부섹터에 없는 종목만 추가
    """
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
