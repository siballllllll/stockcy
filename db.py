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
        headers = ["저장시간", "티커", "종목명", "수량", "매수가($)", "현재가($)", "수익금($)", "수익률(%)"]
        ws = _get_or_create_worksheet(sh, "현재포트폴리오", headers)
        ws.clear()
        ws.append_row(headers)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in portfolio_list:
            ticker = item["ticker"]
            bp = item["buy_price"]
            qty = item["quantity"]
            name = item.get("name", ticker)

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
                           round(profit, 2), round(profit_pct, 2)])

        return True, f"'{sh.title}' > '현재포트폴리오' 탭에 {len(portfolio_list)}개 종목 저장 완료!"
    except Exception as e:
        return False, f"저장 오류: {e}"

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
