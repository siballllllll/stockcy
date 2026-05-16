import requests
import pandas as pd
import time
import streamlit as st
from datetime import datetime, timedelta

# KIS API 설정 (기존 secrets 활용)
KIS_BASE = "https://openapi.koreainvestment.com:9443"
APP_KEY = st.secrets["kis"]["app_key"]
APP_SECRET = st.secrets["kis"]["app_secret"]

def get_access_token():
    url = f"{KIS_BASE}/oauth2/tokenP"
    payload = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    res = requests.post(url, json=payload)
    return res.json().get("access_token")

def fetch_kis_5min_data(ticker, end_date_time):
    """
    KIS API FHKST03010200 엔드포인트를 사용하여 
    특정 시점 이전의 5분봉 데이터(최대 100~120개)를 가져온다.
    """
    token = get_access_token()
    url = f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    
    # KIS API 파라미터 설정
    # FID_INPUT_HOUR_1: 데이터 수집 종료 시간 (HHMMSS)
    # FID_ETC_CLS_CODE: 기타 구분 (보통 0)
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_HOUR_1": end_date_time.strftime("%H%M%S"),
        "FID_PW_DATA_INCU_YN": "N" # 당일 데이터 포함 여부
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST03010200", # 분봉 조회 TR
        "custtype": "P"
    }
    
    res = requests.get(url, headers=headers, params=params)
    data = res.json()
    
    if data.get("rt_cd") != "0":
        return None, data.get("msg1")
    
    return data.get("output2"), None

def download_stock_data_full(ticker, days_goal=365):
    """
    루프를 돌며 과거 날짜로 이동하며 데이터를 이어붙인다.
    days_goal 만큼의 일수를 채울 때까지 반복.
    """
    all_data = []
    current_end_time = datetime.now()
    collected_days = set()
    
    print(f"开始 수집: {ticker} (목표: {days_goal}일치)")
    
    while len(collected_days) < days_goal:
        output, err = fetch_kis_5min_data(ticker, current_end_time)
        if not output:
            print(f"⚠️ 수집 중단 ({ticker}): {err}")
            break
            
        df_chunk = pd.DataFrame(output)
        if df_chunk.empty:
            break
            
        # 데이터 정제 (KIS는 stck_bsop_date, t_ms_t_m 등의 명칭 사용)
        df_chunk['datetime'] = pd.to_datetime(df_chunk['stck_bsop_date'] + df_chunk['stck_cntg_hour'], format='%Y%m%d%H%M%S')
        all_data.append(df_chunk)
        
        # 수집된 고유 일자 업데이트
        new_days = df_chunk['stck_bsop_date'].unique()
        collected_days.update(new_days)
        
        # 다음 호출을 위해 current_end_time을 수집된 데이터의 가장 과거 시점으로 업데이트
        oldest_dt = df_chunk['datetime'].min()
        current_end_time = oldest_dt - timedelta(minutes=5)
        
        print(f"   진행: {len(collected_days)}/{days_goal}일 확보됨... ({oldest_dt})", end="\r")
        
        # API 과부하 방지
        time.sleep(0.2)
        
        # KIS API가 더 이상 과거 데이터를 주지 않을 경우 (보통 30~100일 한계)
        if len(all_data) > 1 and all_data[-1].iloc[-1]['datetime'] == all_data[-2].iloc[-1]['datetime']:
            break

    if not all_data:
        return pd.DataFrame()
        
    final_df = pd.concat(all_data).drop_duplicates('datetime').sort_values('datetime')
    return final_df
