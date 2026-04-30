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


@st.cache_data(ttl=60)
def get_kr_stock_price(stock_code: str):
    """국내 주식 현재가 및 기본 정보 조회 (1분 캐싱)"""
    data = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        "FHKST01010100",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": stock_code},
    )
    if not data:
        return None
    o = data["output"]
    return {
        "code": stock_code,
        "name": o.get("hts_kor_isnm", stock_code),
        "price": int(o.get("stck_prpr", 0) or 0),
        "change": int(o.get("prdy_vrss", 0) or 0),
        "change_pct": float(o.get("prdy_ctrt", 0) or 0),
        "sign": o.get("prdy_vrss_sign", "3"),  # 1:상한 2:상승 3:보합 4:하락 5:하한
        "volume": int(o.get("acml_vol", 0) or 0),
        "amount": int(o.get("acml_tr_pbmn", 0) or 0),
        "open": int(o.get("stck_oprc", 0) or 0),
        "high": int(o.get("stck_hgpr", 0) or 0),
        "low": int(o.get("stck_lwpr", 0) or 0),
        "w52_high": int(o.get("w52hgpr", 0) or 0),
        "w52_low": int(o.get("w52lwpr", 0) or 0),
        "per": o.get("per", "-"),
        "pbr": o.get("pbr", "-"),
        "market_cap": o.get("hts_avls", "-"),
    }


@st.cache_data(ttl=60)
def get_kr_investor_trend(stock_code: str):
    """종목별 외국인/기관/개인 순매수 동향 (최근 5영업일)"""
    data = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-investor",
        "FHKST01010900",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": stock_code},
    )
    if not data:
        return []
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


@st.cache_data(ttl=60)
def get_kr_market_index():
    """KOSPI / KOSDAQ 지수 실시간 조회"""
    result = {}
    for name, code in [("KOSPI", "0001"), ("KOSDAQ", "1001")]:
        data = _get(
            "/uapi/domestic-stock/v1/quotations/inquire-index-price",
            "FHPUP02100000",
            {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": code},
        )
        if data:
            o = data["output"]
            result[name] = {
                "index": float(o.get("bstp_nmix_prpr", 0) or 0),
                "change": float(o.get("bstp_nmix_prdy_vrss", 0) or 0),
                "change_pct": float(o.get("prdy_ctrt", 0) or 0),
            }
    return result


@st.cache_data(ttl=300)  # 5분 캐싱
def get_kr_volume_ranking():
    """거래량 상위 10개 종목 (KOSPI)"""
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
            "fid_trgt_exls_cls_code": "000000",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_input_date_1": "",
        },
    )
    if not data:
        return []
    results = []
    for item in data.get("output", [])[:10]:
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
