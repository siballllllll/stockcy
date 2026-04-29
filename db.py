import gspread
import streamlit as st
import pandas as pd
from datetime import datetime

@st.cache_resource
def get_gsheet_client():
    """Google Sheets 클라이언트를 초기화하고 캐싱합니다."""
    try:
        # st.secrets에 저장된 gspread 딕셔너리 파싱
        # user가 넣은 형태에 맞춰 credentials 키가 있는지 확인
        if "credentials" in st.secrets["gspread"]:
            creds_dict = dict(st.secrets["gspread"]["credentials"])
        else:
            creds_dict = dict(st.secrets["gspread"])
            
        # JSON 문자열에 포함된 리터럴 '\n'을 실제 줄바꿈으로 치환 (PEM 파싱 에러 방지)
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            
        gc = gspread.service_account_from_dict(creds_dict)
        return gc
    except Exception as e:
        st.error(f"구글 시트 인증 실패: {e}")
        return None

def test_connection_and_write():
    gc = get_gsheet_client()
    if not gc: return False, "클라이언트 인증에 실패했습니다. secrets.toml 정보를 확인해주세요."
    
    try:
        # 봇에게 권한이 부여된 스프레드시트 목록을 모두 가져옵니다.
        spreadsheets = gc.openall()
        if not spreadsheets:
            return False, "봇 계정(stockcy-bot@...)에 공유된 스프레드시트가 없습니다. 구글 시트를 만들고 우측 상단 '공유'에서 봇 이메일 주소를 추가해주세요!"
            
        # 공유된 첫 번째 스프레드시트를 타겟으로 잡습니다.
        sh = spreadsheets[0]
        worksheet = sh.sheet1 # 첫 번째 시트 탭
        
        # 시트가 완전히 비어있다면 헤더 추가
        if not worksheet.get_all_values():
            worksheet.append_row(["시간", "종목명", "추천가", "목표가", "상태"])
            
        # 임의의 테스트 데이터 행 추가
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([now, "테스트_엔비디아", "$ 1,000", "$ 1,050", "모니터링중"])
        
        return True, f"성공! 구글 시트 '{sh.title}'에 테스트 데이터가 실시간으로 입력되었습니다. 지금 브라우저에서 시트를 확인해보세요!"
    except Exception as e:
        return False, f"에러 발생: {e}"
