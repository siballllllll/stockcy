import os
import json as _json
import gspread
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# 구글 스프레드시트 API 호출 429 초과 방지용 메모리 캐시 및 TTL(60초) 정의
_GSHEET_CACHE = {}
_GSHEET_CACHE_TTL = timedelta(seconds=60)

@st.cache_resource
def get_gsheet_client():
    """Google Sheets 클라이언트를 초기화하고 캐싱합니다."""
    try:
        creds_json = os.getenv("GSPREAD_CREDENTIALS", "")
        creds_dict = _json.loads(creds_json) if creds_json else {}

        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

        gc = gspread.service_account_from_dict(creds_dict)
        return gc
    except Exception as e:
        return None

def _get_spreadsheet():
    gc = get_gsheet_client()
    if not gc:
        return None, "구글 시트 인증 실패. .env의 GSPREAD_CREDENTIALS 설정을 확인해주세요."
    try:
        # 환경변수에 spreadsheet_id가 있으면 직접 지정 (빠르고 안정적)
        sheet_id = os.getenv("GSPREAD_SPREADSHEET_ID", "")
        if sheet_id:
            return gc.open_by_key(sheet_id), "성공"
        # fallback: 공유된 첫 번째 시트 사용
        spreadsheets = gc.openall()
        if not spreadsheets:
            return None, "봇 계정에 공유된 스프레드시트가 없습니다. 구글 시트를 만들고 봇 이메일을 공유에 추가하거나, secrets에 spreadsheet_id를 추가해주세요."
        return spreadsheets[0], "성공"
    except Exception as e:
        return None, f"스프레드시트 접근 오류: {e}"

def _get_or_create_worksheet(sh, title, headers):
    try:
        ws = sh.worksheet(title)
        # 만약 탭은 존재하지만 내용이 완전히 비어있다면 헤더를 써줍니다
        first_row = ws.row_values(1)
        if not first_row:
            ws.update("A1", [headers])
        return ws
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=20)
        ws.update("A1", [headers])
        return ws

def save_portfolio_to_gsheet(portfolio_list, current_prices_df=None, owner="USER"):
    """현재 포트폴리오 스냅샷을 '현재포트폴리오' 탭에 저장합니다. (Owner별 병합)"""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg

    try:
        headers = ["소유자", "저장시간", "티커", "종목명", "수량", "매수가($)", "현재가($)", "수익금($)", "수익률(%)", "등급"]
        ws = _get_or_create_worksheet(sh, "현재포트폴리오", headers)
        
        # 기존 데이터 가져와서 다른 소유자 데이터만 유지
        all_records = ws.get_all_records()
        other_records = [r for r in all_records if str(r.get("소유자", "USER")).upper() != owner.upper()]
        
        ws.clear()
        ws.append_row(headers)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 다른 소유자 데이터 복구
        for r in other_records:
            ws.append_row([
                r.get("소유자", "USER"), r.get("저장시간", ""), r.get("티커", ""), r.get("종목명", ""),
                r.get("수량", 0), r.get("매수가($)", 0), r.get("현재가($)", 0),
                r.get("수익금($)", 0), r.get("수익률(%)", 0), r.get("등급", "-")
            ])
            
        # 내 데이터 저장
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

            ws.append_row([owner.upper(), now, ticker, name, qty,
                           round(bp, 2), round(cp, 2),
                           round(profit, 2), round(profit_pct, 2), rating])

        # 캐시 무효화
        _GSHEET_CACHE.pop(f"portfolio_{owner}", None)
        return True, f"'{sh.title}' > '현재포트폴리오' 탭에 {len(portfolio_list)}개 종목 저장 완료!"
    except Exception as e:
        return False, f"저장 오류: {e}"

def load_portfolio_from_gsheet(owner="USER"):
    """'현재포트폴리오' 탭에서 포트폴리오 목록을 불러옵니다."""
    now = datetime.now()
    cache_key = f"portfolio_{owner}"
    if cache_key in _GSHEET_CACHE:
        cached_data, cached_time = _GSHEET_CACHE[cache_key]
        if now - cached_time < _GSHEET_CACHE_TTL:
            return cached_data

    sh, msg = _get_spreadsheet()
    if not sh:
        return []
    try:
        ws = sh.worksheet("현재포트폴리오")
        records = ws.get_all_records()
        portfolio_list = []
        for r in records:
            if str(r.get("소유자", "USER")).upper() != owner.upper():
                continue
            ticker = str(r.get("티커", ""))
            if ticker.isdigit() and len(ticker) < 6:
                ticker = ticker.zfill(6)
            portfolio_list.append({
                "ticker": ticker,
                "name": str(r.get("종목명", "")),
                "buy_price": float(r.get("매수가($)", 0) or 0),
                "quantity": float(r.get("수량", 0) or 0),
                "buy_date": str(r.get("저장시간", "")),
                "rating": str(r.get("등급", "-")),
                "owner": str(r.get("소유자", "USER")).upper()
            })
        _GSHEET_CACHE[cache_key] = (portfolio_list, now)
        return portfolio_list
    except Exception as e:
        import traceback
        traceback.print_exc()
        return [{"ticker": "ERROR", "name": f"에러: {str(e)}", "buy_price": 0, "quantity": 0}]

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
        result = []
        for r in records:
            if not r.get("티커"): continue
            ticker = str(r.get("티커", ""))
            if ticker.isdigit() and len(ticker) < 6:
                ticker = ticker.zfill(6)
            result.append({
                "ticker":    ticker,
                "name":      str(r.get("종목명", "")),
                "buy_price": float(r.get("매수가($)", 0) or 0),
                "quantity":  int(r.get("수량", 0) or 0),
                "buy_date":  str(r.get("저장시간", "")),
                "rating":    str(r.get("등급", "-")),
            })
        return result
    except Exception:
        return []


def save_trade_record(trade, owner="USER"):
    """완료된 거래 1건을 '거래내역' 탭에 기록합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg

    try:
        headers = ["소유자", "매도시간", "티커", "종목명", "수량", "매수가($)", "매도가($)", "수익금($)", "수익률(%)", "결과", "학습포인트"]
        ws = _get_or_create_worksheet(sh, "거래내역", headers)
        ws.append_row([
            owner.upper(),
            trade.get("sell_date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            trade.get("ticker", ""),
            trade.get("name", ""),
            trade.get("quantity", 0),
            round(float(trade.get("buy_price", 0)), 2),
            round(float(trade.get("sell_price", 0)), 2),
            round(float(trade.get("profit", 0)), 2),
            round(float(trade.get("profit_pct", 0)), 2),
            trade.get("result", ""),
            trade.get("learning_point", "")
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
            if len(row) >= 3 and str(row[1]).strip() == str(sell_date).strip() and str(row[2]).strip() == str(ticker).strip():
                ws.delete_rows(i + 1)  # gspread는 1-indexed
                return True, "구글 시트에서 삭제 완료"
        return False, "해당 거래를 구글 시트에서 찾지 못했습니다."
    except gspread.WorksheetNotFound:
        return False, "거래내역 탭이 없습니다."
    except Exception as e:
        return False, f"삭제 오류: {e}"

def update_trade_learning_point(ticker: str, sell_date: str, learning_point: str):
    """'거래내역' 탭에서 특정 거래의 '학습포인트' 열을 업데이트합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        ws = sh.worksheet("거래내역")
        rows = ws.get_all_values()
        headers = rows[0]
        try:
            lp_col_idx = headers.index("학습포인트") + 1
        except ValueError:
            return False, "'학습포인트' 컬럼이 없습니다."

        for i in range(len(rows) - 1, 0, -1):
            row = rows[i]
            if len(row) >= 3 and str(row[1]).strip() == str(sell_date).strip() and str(row[2]).strip() == str(ticker).strip():
                ws.update_cell(i + 1, lp_col_idx, learning_point)
                return True, "학습포인트 저장 완료"
        return False, "해당 거래를 찾을 수 없습니다."
    except Exception as e:
        return False, f"업데이트 오류: {e}"


def load_trade_history_from_gsheet(owner="USER"):
    """'거래내역' 탭에서 모든 거래 기록을 DataFrame으로 불러옵니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return None, msg

    try:
        ws = sh.worksheet("거래내역")
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame(), "구글 시트의 거래내역 탭이 비어있습니다."
        
        filtered = []
        for r in records:
            if str(r.get("소유자", "USER")).upper() != owner.upper():
                continue
            t = str(r.get("티커", ""))
            if t.isdigit() and len(t) < 6:
                r["티커"] = t.zfill(6)
            filtered.append(r)
                
        return pd.DataFrame(filtered), "성공"
    except gspread.WorksheetNotFound:
        return pd.DataFrame(), "거래내역 탭이 아직 없습니다. 매도 기록 시 자동으로 생성됩니다."
    except Exception as e:
        return None, f"로드 오류: {e}"

# ── 모의투자 계좌 잔고 관리 ──
def load_virtual_balances():
    """'모의투자계좌' 탭에서 소유자별 현금 잔고를 불러옵니다."""
    now = datetime.now()
    cache_key = "virtual_balances"
    if cache_key in _GSHEET_CACHE:
        cached_data, cached_time = _GSHEET_CACHE[cache_key]
        if now - cached_time < _GSHEET_CACHE_TTL:
            return cached_data

    sh, msg = _get_spreadsheet()
    if not sh:
        return {"USER": 10000000, "AI": 10000000}
    try:
        ws = sh.worksheet("모의투자계좌")
        records = ws.get_all_records()
        balances = {"USER": 10000000, "AI": 10000000}
        for r in records:
            owner = str(r.get("소유자", "")).upper()
            if owner:
                balances[owner] = float(r.get("잔고(₩)", 10000000))
        _GSHEET_CACHE[cache_key] = (balances, now)
        return balances
    except gspread.WorksheetNotFound:
        return {"USER": 10000000, "AI": 10000000}
    except Exception:
        return {"USER": 10000000, "AI": 10000000}

def save_virtual_balance(owner: str, balance: float):
    """'모의투자계좌' 탭에 소유자의 현금 잔고를 저장합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False
    try:
        headers = ["소유자", "잔고(₩)", "최근업데이트"]
        ws = _get_or_create_worksheet(sh, "모의투자계좌", headers)
        records = ws.get_all_records()
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        found = False
        rows_to_update = []
        
        for idx, r in enumerate(records):
            if str(r.get("소유자", "")).upper() == owner.upper():
                found = True
                ws.update_cell(idx + 2, 2, balance)
                ws.update_cell(idx + 2, 3, now)
                break
        
        if not found:
            ws.append_row([owner.upper(), balance, now])
            
        _GSHEET_CACHE.pop("virtual_balances", None)
        return True
    except Exception:
        return False

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
        _GSHEET_CACHE.pop("favorites", None)
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
            _GSHEET_CACHE.pop("favorites", None)
            return True, "즐겨찾기에서 삭제되었습니다."
        return False, "목록에서 종목을 찾을 수 없습니다."
    except Exception as e:
        return False, f"삭제 오류: {e}"

def load_favorites():
    """'즐겨찾기' 탭에서 모든 종목을 불러옵니다."""
    now = datetime.now()
    cache_key = "favorites"
    if cache_key in _GSHEET_CACHE:
        cached_data, cached_time = _GSHEET_CACHE[cache_key]
        if now - cached_time < _GSHEET_CACHE_TTL:
            return cached_data, "성공"

    sh, msg = _get_spreadsheet()
    if not sh: return [], msg
    try:
        ws = sh.worksheet("즐겨찾기")
        records = ws.get_all_records()
        # 티커 항상 문자열로, 국내 종목 6자리 0 패딩
        for r in records:
            t = str(r.get("티커", ""))
            r["티커"] = t.zfill(6) if t.isdigit() and len(t) <= 6 else t
        _GSHEET_CACHE[cache_key] = (records, now)
        return records, "성공"
    except gspread.WorksheetNotFound:
        return [], "즐겨찾기 목록이 비어있습니다."
    except Exception as e:
        return [], f"로드 오류: {e}"


def is_favorite(ticker):
    """특정 종목이 즐겨찾기에 있는지 확인합니다."""
    favs, _ = load_favorites()
    return any(str(f.get('티커', '')) == str(ticker) for f in favs)


def log_agent_scan(ticker: str, name: str, current_price: float, position: str, action: str, confidence: int, reason: str):
    """AI 자율매매 에이전트의 고민/스캔 이력을 'AI스캔로그' 탭에 저장합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["스캔시간", "티커", "종목명", "현재가", "보유상태", "AI판단", "신뢰도(%)", "판단이유"]
        ws = _get_or_create_worksheet(sh, "AI스캔로그", headers)
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([
            now, ticker, name, round(float(current_price), 2),
            position, action, int(confidence), reason
        ])
        
        # 최대 100건만 유지 (구글 시트 성능 최적화)
        rows = ws.get_all_values()
        if len(rows) > 105:
            ws.delete_rows(2, len(rows) - 101)
            
        return True, "성공"
    except Exception as e:
        return False, f"스캔로그 저장 실패: {e}"


def load_agent_scan_logs_from_gsheet():
    """'AI스캔로그' 탭에서 에이전트의 스캔 로그 목록을 불러옵니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return []
    try:
        ws = sh.worksheet("AI스캔로그")
        records = ws.get_all_records()
        scan_logs = []
        for r in records:
            ticker = str(r.get("티커", ""))
            if ticker.isdigit() and len(ticker) < 6:
                ticker = ticker.zfill(6)
            scan_logs.append({
                "scan_time": str(r.get("스캔시간", "")),
                "ticker": ticker,
                "name": str(r.get("종목명", "")),
                "price": float(r.get("현재가", 0) or 0),
                "position": str(r.get("보유상태", "NONE")),
                "action": str(r.get("AI판단", "HOLD")),
                "confidence": int(r.get("신뢰도(%)", 0) or 0),
                "reason": str(r.get("판단이유", ""))
            })
        # 최신 순으로 정렬하여 반환
        scan_logs.reverse()
        return scan_logs
    except Exception:
        return []


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


# FDR Industry(한국어) → (한국어 섹터, 한국어 서브섹터) 매핑
# FDR StockListing은 Sector 없이 Industry 한국어 텍스트만 제공
_FDR_IND_MAP: dict = {
    # ── AI·반도체 ─────────────────────────────────────────────
    "반도체":                               ("AI·반도체",           "반도체"),
    "반도체 장비 및 테스트":               ("AI·반도체",           "반도체 장비·소재"),
    "전자 장비 및 부품":                   ("AI·반도체",           "전자부품"),
    "전화 및 소형 장치":                   ("AI·반도체",           "전자부품"),
    "컴퓨터 및 전자 제품 소매":            ("AI·반도체",           "전자·컴퓨터 유통"),
    # ── 빅테크·AI소프트 ──────────────────────────────────────
    "소프트웨어":                           ("빅테크·AI소프트",     "소프트웨어"),
    "IT 서비스 및 컨설팅":                 ("빅테크·AI소프트",     "IT서비스"),
    "컴퓨터 하드웨어":                     ("빅테크·AI소프트",     "컴퓨터 하드웨어"),
    "온라인 서비스":                        ("빅테크·AI소프트",     "인터넷·콘텐츠"),
    "전문 정보 서비스":                     ("빅테크·AI소프트",     "IT서비스"),
    "통합 하드웨어 및 소프트웨어":         ("빅테크·AI소프트",     "IT서비스"),
    "사무기기":                             ("빅테크·AI소프트",     "컴퓨터 하드웨어"),
    # ── 소셜미디어·디지털광고 ────────────────────────────────
    "광고 및 마케팅":                       ("소셜미디어·디지털광고","광고대행"),
    # ── 바이오·헬스케어 ──────────────────────────────────────
    "생명 공학 및 의학 연구":              ("바이오·헬스케어",     "바이오테크"),
    "제약":                                 ("바이오·헬스케어",     "제약"),
    "첨단 의료 장비 및 기술":              ("바이오·헬스케어",     "의료기기"),
    "의료 장비, 물품 및 유통":             ("바이오·헬스케어",     "의료기기·용품"),
    "의료 시설 및 서비스":                 ("바이오·헬스케어",     "의료시설"),
    "의료 관리":                            ("바이오·헬스케어",     "헬스케어 보험"),
    "의약품 소매":                          ("바이오·헬스케어",     "의약품 소매"),
    # ── 방산·우주 ─────────────────────────────────────────────
    "항공우주 및 방위":                    ("방산·우주",            "항공·방산"),
    # ── 금융·핀테크 ──────────────────────────────────────────
    "은행":                                 ("금융·핀테크",         "종합은행"),
    "생명 및 건강 보험":                   ("금융·핀테크",         "생명보험"),
    "손해보험":                             ("금융·핀테크",         "손해보험"),
    "복합보험 및 중개인":                  ("금융·핀테크",         "복합보험"),
    "재보험":                               ("금융·핀테크",         "재보험"),
    "투자 관리 및 펀드 운영":              ("금융·핀테크",         "자산운용"),
    "투자 은행 및 중개 서비스":            ("금융·핀테크",         "자본시장"),
    "금융, 상품 시장 운영 및 서비스 제공": ("금융·핀테크",         "금융데이터·거래소"),
    "소비자 대출":                          ("금융·핀테크",         "신용서비스"),
    "핀테크":                               ("금융·핀테크",         "핀테크"),
    "기타 핀테크 인프라":                  ("금융·핀테크",         "핀테크 인프라"),
    "기업 금융 서비스":                     ("금융·핀테크",         "자본시장"),
    "다각적 투자 서비스":                  ("금융·핀테크",         "투자서비스"),
    "투자 지주 회사":                       ("금융·핀테크",         "자산운용"),
    "온라인 소액 투자 중개":               ("금융·핀테크",         "핀테크"),
    "블록 체인 및 암호화폐":               ("금융·핀테크",         "암호화폐·블록체인"),
    # ── EV·로봇·자율주행 ─────────────────────────────────────
    "자동차 및 트럭 제조":                 ("EV·로봇·자율주행",    "자동차 제조"),
    "자동차, 트럭 및 오토바이 부품":       ("EV·로봇·자율주행",    "자동차 부품"),
    "자동차 차량, 부품 및 서비스 소매":    ("EV·로봇·자율주행",    "자동차 딜러"),
    "타이어 및 고무 제품":                  ("EV·로봇·자율주행",    "자동차 부품"),
    # ── 소비재·유통 ──────────────────────────────────────────
    "기타 전문 소매":                       ("소비재·유통",         "전문 소매"),
    "의류 및 액세서리":                     ("소비재·유통",         "의류 제조"),
    "의류 및 액세서리 소매":               ("소비재·유통",         "의류 소매"),
    "직물 및 가죽제품":                     ("소비재·유통",         "의류 제조"),
    "제화":                                 ("소비재·유통",         "의류 소매"),
    "백화점":                               ("소비재·유통",         "백화점·유통"),
    "할인점":                               ("소비재·유통",         "할인점"),
    "식품 소매 및 유통":                   ("소비재·유통",         "식료품점"),
    "레스토랑 및 바":                       ("소비재·유통",         "외식업"),
    "가전제품, 도구 및 가정 용품":         ("소비재·유통",         "소비자가전"),
    "가정용 전자 제품":                     ("소비재·유통",         "소비자가전"),
    "가정용 제품":                           ("소비재·유통",         "생활·개인용품"),
    "가정용 가구":                           ("소비재·유통",         "생활·개인용품"),
    "가정용 가구 소매":                     ("소비재·유통",         "생활·개인용품"),
    "개인 생활 필수 용품":                  ("소비재·유통",         "생활·개인용품"),
    "소비재 대기업":                        ("소비재·유통",         "생활·개인용품"),
    "식품 가공":                             ("소비재·유통",         "가공식품"),
    "무알콜 음료":                           ("소비재·유통",         "비알코올음료"),
    "양조업":                               ("소비재·유통",         "주류"),
    "증류주 및 포도주":                     ("소비재·유통",         "주류"),
    "담배":                                 ("소비재·유통",         "담배"),
    "주택 개조 제품 및 서비스 소매":        ("소비재·유통",         "홈인테리어 소매"),
    "개인 서비스":                           ("소비재·유통",         "개인서비스"),
    "기타 교육 서비스 제공":               ("소비재·유통",         "교육·훈련"),
    "전문 및 비즈니스 교육":               ("소비재·유통",         "교육·훈련"),
    "초, 중, 고등 교육기관":               ("소비재·유통",         "교육·훈련"),
    "오락용 제품":                           ("소비재·유통",         "레저"),
    "여가 및 오락시설":                     ("소비재·유통",         "레저"),
    "장난감 및 어린이 제품":               ("소비재·유통",         "레저"),
    # ── 미디어·엔터·게임 ─────────────────────────────────────
    "엔터테인먼트 제작":                    ("미디어·엔터·게임",    "엔터테인먼트"),
    "방송":                                 ("미디어·엔터·게임",    "방송"),
    "소비자 출판":                           ("미디어·엔터·게임",    "출판·미디어"),
    "상업 인쇄 서비스":                     ("미디어·엔터·게임",    "출판·미디어"),
    # ── 통신·네트워크 ────────────────────────────────────────
    "무선 통신 서비스":                     ("통신·네트워크",       "통신서비스"),
    "통합 통신 서비스":                     ("통신·네트워크",       "통신서비스"),
    "통신 및 네트워킹":                     ("통신·네트워크",       "네트워크 장비"),
    # ── 항공·여행·관광 ───────────────────────────────────────
    "항공사":                               ("항공·여행·관광",      "항공사"),
    "호텔, 모텔 및 크루즈 라인":           ("항공·여행·관광",      "호텔·모텔"),
    "지상 및 해상 여객 운송":              ("항공·여행·관광",      "여행서비스"),
    "공항 운영 및 서비스":                  ("항공·여행·관광",      "여행서비스"),
    "카지노 및 도박":                       ("항공·여행·관광",      "리조트·카지노"),
    # ── 에너지·원자력 ────────────────────────────────────────
    "오일 및 가스 시추":                   ("에너지·원자력",       "석유·가스 탐사"),
    "오일, 가스 탐사 및 생산":             ("에너지·원자력",       "석유·가스 탐사"),
    "통합 오일 및 가스":                   ("에너지·원자력",       "석유·가스 통합"),
    "오일, 가스 정제 및 마케팅":           ("에너지·원자력",       "정유·마케팅"),
    "오일 관련 서비스 및 장비":            ("에너지·원자력",       "석유·가스 장비"),
    "오일 및 가스 수송 서비스":            ("에너지·원자력",       "석유·가스 미드스트림"),
    "우라늄":                               ("에너지·원자력",       "우라늄"),
    "재생 가능 에너지 장비 및 서비스":     ("에너지·원자력",       "태양광"),
    "재생 가능 연료":                       ("에너지·원자력",       "태양광"),
    "석탄":                                 ("에너지·원자력",       "석탄"),
    # ── 전력 인프라·그리드 ───────────────────────────────────
    "전력 유틸리티":                        ("전력 인프라·그리드",  "규제 전력"),
    "민자 발전 사업":                       ("전력 인프라·그리드",  "독립발전사"),
    "복합 유틸리티":                        ("전력 인프라·그리드",  "다각화 유틸리티"),
    "수자원 유틸리티":                      ("전력 인프라·그리드",  "규제 수도"),
    "천연가스 유틸리티":                    ("전력 인프라·그리드",  "규제 가스"),
    "전기 부품 및 장비":                   ("전력 인프라·그리드",  "전기장비·부품"),
    "중전기장비":                           ("전력 인프라·그리드",  "전기장비·부품"),
    # ── 리츠·부동산 ──────────────────────────────────────────
    "복합부동산 REITs":                     ("리츠·부동산",         "다각화 리츠"),
    "상업용 REITs":                         ("리츠·부동산",         "오피스 리츠"),
    "주거용 REITs":                         ("리츠·부동산",         "주거 리츠"),
    "특수 REITs":                           ("리츠·부동산",         "특수 리츠"),
    "부동산 서비스":                        ("리츠·부동산",         "부동산 서비스"),
    "부동산 임대, 개발 및 운영":           ("리츠·부동산",         "복합 부동산"),
    # ── 전통 산업·소재 ───────────────────────────────────────
    "산업용 기계 및 장비":                 ("전통 산업·소재",      "산업기계"),
    "중장비 및 차량":                       ("전통 산업·소재",      "농기계·중장비"),
    "건설 및 엔지니어링":                  ("전통 산업·소재",      "엔지니어링·건설"),
    "건설 자재":                             ("전통 산업·소재",      "건설 소재"),
    "건설 자재 및 비품":                   ("전통 산업·소재",      "건설 소재"),
    "주택 건설":                             ("전통 산업·소재",      "건설 소재"),
    "환경 서비스 및 장비":                  ("전통 산업·소재",      "폐기물관리"),
    "고용 서비스":                           ("전통 산업·소재",      "인력파견"),
    "경영 지원 서비스":                     ("전통 산업·소재",      "비즈니스서비스"),
    "다각적 산업용 제품 도매":              ("전통 산업·소재",      "비즈니스서비스"),
    "비즈니스 지원 용품":                   ("전통 산업·소재",      "비즈니스서비스"),
    "지상 화물 및 물류":                   ("전통 산업·소재",      "물류·택배"),
    "배달, 우편, 항공 화물 및 육상 물류": ("전통 산업·소재",      "물류·택배"),
    "해양 화물 및 물류":                   ("전통 산업·소재",      "해운"),
    "항만 운영 및 서비스":                  ("전통 산업·소재",      "해운"),
    "상품 화학":                             ("전통 산업·소재",      "화학"),
    "다각적 화학 산업":                     ("전통 산업·소재",      "화학"),
    "특수 화학제":                           ("전통 산업·소재",      "특수화학"),
    "철 및 강철":                           ("전통 산업·소재",      "철강"),
    "알루미늄":                             ("전통 산업·소재",      "알루미늄"),
    "농화학제":                             ("전통 산업·소재",      "농업 소재"),
    "어업 및 농업":                         ("전통 산업·소재",      "농산물"),
    "용기(종이 제외) 및 포장재":           ("전통 산업·소재",      "포장재"),
    "종이 제품":                             ("전통 산업·소재",      "제지"),
    "종이 포장재":                           ("전통 산업·소재",      "제지"),
    "임업 및 목재 제품":                   ("전통 산업·소재",      "목재"),
    # ── 광업·귀금속·원자재 ───────────────────────────────────
    "금":                                   ("광업·귀금속·원자재",  "금광"),
    "금 제외 귀금속 및 광물":              ("광업·귀금속·원자재",  "귀금속·광물"),
    "다각적 채굴":                           ("광업·귀금속·원자재",  "기타 광업"),
    "특수 채굴 및 금속":                   ("광업·귀금속·원자재",  "기타 광업"),
    "채굴 지원 서비스 및 장비":            ("광업·귀금속·원자재",  "기타 광업"),
}


@st.cache_data(ttl=43200)
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

    # FDR 전종목으로 보강: Industry → (한국어섹터, 서브섹터) 직접 매핑
    # FDR StockListing은 Sector 컬럼 없이 Industry만 제공
    try:
        import FinanceDataReader as _fdr
        import pandas as _pd
        existing = {s["ticker"] for subs in raw.values() for stks in subs.values() for s in stks}
        _frames = []
        for _mkt, _exch in [("NASDAQ", "NASDAQ"), ("NYSE", "NYSE"), ("AMEX", "AMEX")]:
            try:
                _df = _fdr.StockListing(_mkt).copy()
                _df["_exchange"] = _exch
                _frames.append(_df)
            except Exception:
                continue
        if _frames:
            _all = _pd.concat(_frames, ignore_index=True)
            _all.columns = [str(c).strip() for c in _all.columns]
            _cols = {c.lower(): c for c in _all.columns}
            _sym  = _cols.get("symbol",   _cols.get("code",     _cols.get("ticker")))
            _name = _cols.get("name",     _cols.get("longname", _cols.get("shortname")))
            _ind  = _cols.get("industry", _cols.get("industrycode"))
            if _sym and _ind:
                for _, _row in _all.iterrows():
                    _ticker = str(_row.get(_sym, "")).strip().upper()
                    if not _ticker or not (1 <= len(_ticker) <= 5) or not _ticker.isalpha():
                        continue
                    if _ticker in existing:
                        continue
                    _industry = str(_row.get(_ind, "") if _ind else "").strip()
                    _mapping  = _FDR_IND_MAP.get(_industry)
                    if not _mapping:
                        continue
                    _kr_sec, _kr_sub = _mapping
                    if _kr_sec not in raw:
                        continue
                    _sname = str(_row.get(_name, _ticker) if _name else _ticker).strip()
                    _exch2 = str(_row.get("_exchange", "NASDAQ"))
                    raw[_kr_sec].setdefault(_kr_sub, []).append(
                        {"name": _sname, "ticker": _ticker, "exchange": _exch2}
                    )
                    existing.add(_ticker)
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


def save_price_alert(market: str, ticker: str, name: str,
                     alert_type: str, target_price: float) -> tuple:
    """가격 알림을 '알림설정' 탭에 저장합니다. 동일 ticker+alert_type은 덮어씁니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["설정시간", "시장", "티커", "종목명", "알림유형", "목표가", "상태"]
        ws = _get_or_create_worksheet(sh, "알림설정", headers)
        existing = ws.get_all_records()
        for i in range(len(existing) - 1, -1, -1):
            r = existing[i]
            if str(r.get("티커")) == str(ticker) and r.get("알림유형") == alert_type:
                ws.delete_rows(i + 2)
                break
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            market, ticker, name, alert_type,
            round(float(target_price), 4),
            "활성",
        ])
        return True, f"[{name}] {alert_type} 알림이 설정되었습니다."
    except Exception as e:
        return False, f"알림 저장 오류: {e}"


def load_price_alerts() -> list:
    """'알림설정' 탭에서 활성 알림 목록을 반환합니다."""
    sh, _ = _get_spreadsheet()
    if not sh:
        return []
    try:
        ws = sh.worksheet("알림설정")
        records = ws.get_all_records()
        result = []
        for r in records:
            if str(r.get("상태", "")) != "활성":
                continue
            ticker = str(r.get("티커", ""))
            if ticker.isdigit() and len(ticker) < 6:
                ticker = ticker.zfill(6)
            try:
                tp = float(str(r.get("목표가", 0)).replace(",", ""))
            except (ValueError, TypeError):
                tp = 0.0
            result.append({
                "market":     str(r.get("시장", "")),
                "ticker":     ticker,
                "name":       str(r.get("종목명", "")),
                "alert_type": str(r.get("알림유형", "")),
                "target_price": tp,
            })
        return result
    except gspread.WorksheetNotFound:
        return []
    except Exception:
        return []


def delete_price_alert(ticker: str, alert_type: str) -> tuple:
    """'알림설정' 탭에서 특정 알림을 삭제합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        ws = sh.worksheet("알림설정")
        records = ws.get_all_records()
        for i in range(len(records) - 1, -1, -1):
            r = records[i]
            if str(r.get("티커")) == str(ticker) and r.get("알림유형") == alert_type:
                ws.delete_rows(i + 2)
                return True, "알림이 삭제되었습니다."
        return False, "알림을 찾을 수 없습니다."
    except gspread.WorksheetNotFound:
        return False, "알림설정 탭이 없습니다."
    except Exception as e:
        return False, f"삭제 오류: {e}"

def update_price_alert_status(ticker: str, alert_type: str, new_status: str) -> bool:
    """알림 상태를 업데이트합니다 (예: 활성 -> 완료)."""
    sh, _ = _get_spreadsheet()
    if not sh:
        return False
    try:
        ws = sh.worksheet("알림설정")
        records = ws.get_all_records()
        for i, r in enumerate(records):
            if str(r.get("티커")) == str(ticker) and r.get("알림유형") == alert_type:
                # 상태 컬럼 찾기
                header = ws.row_values(1)
                try:
                    status_col = header.index("상태") + 1
                    ws.update_cell(i + 2, status_col, new_status)
                    return True
                except ValueError:
                    return False
        return False
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


def save_telegram_config(token: str, chat_id: str) -> tuple[bool, str]:
    """텔레그램 봇 토큰 및 Chat ID를 '텔레그램설정' 탭에 저장합니다 (기존 설정은 덮어씀)."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["저장시간", "토큰", "챗아이디"]
        ws = _get_or_create_worksheet(sh, "텔레그램설정", headers)
        ws.clear()
        ws.append_row(headers)
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            token.strip(),
            chat_id.strip()
        ])
        return True, "텔레그램 설정이 구글 시트에 성공적으로 저장되었습니다."
    except Exception as e:
        return False, f"텔레그램 설정 저장 중 오류 발생: {e}"


def load_telegram_config() -> tuple[str, str]:
    """'텔레그램설정' 탭에서 저장된 텔레그램 토큰과 챗아이디를 불러옵니다. 없으면 환경변수 fallback."""
    sh, _ = _get_spreadsheet()
    if sh:
        try:
            ws = sh.worksheet("텔레그램설정")
            records = ws.get_all_records()
            if records:
                row = records[0]
                token = str(row.get("토큰", "")).strip()
                chat_id = str(row.get("챗아이디", "")).strip()
                if token and chat_id:
                    return token, chat_id
        except Exception:
            pass
            
    # 환경변수 fallback
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    return token, chat_id

