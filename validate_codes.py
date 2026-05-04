"""
sectors_kr.py 종목 코드 검증 스크립트 (로컬 실행용)
KIS API로 각 종목 코드의 실제 종목명을 조회해 저장된 이름과 비교합니다.

실행 방법:
  python validate_codes.py

결과:
  - mismatch_report.csv  : 코드-이름 불일치 목록
  - not_found_report.csv : KIS API 조회 실패 목록
"""

import requests
import time
import csv

# ─────────────────────────────────────────────
# KIS API 인증 정보 (Streamlit Cloud secrets와 동일한 값 입력)
APP_KEY    = "여기에_앱키_입력"
APP_SECRET = "여기에_앱시크릿_입력"
# ─────────────────────────────────────────────

KIS_BASE = "https://openapi.koreainvestment.com:9443"


def get_token():
    resp = requests.post(
        f"{KIS_BASE}/oauth2/tokenP",
        json={
            "grant_type": "client_credentials",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
        },
        timeout=10,
    )
    return resp.json().get("access_token")


def get_name(token: str, code: str) -> tuple[str | None, str]:
    """종목명 조회. (이름 or None, 에러메시지) 반환"""
    try:
        resp = requests.get(
            f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers={
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {token}",
                "appkey": APP_KEY,
                "appsecret": APP_SECRET,
                "tr_id": "FHKST01010100",
                "custtype": "P",
            },
            params={
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": code,
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("rt_cd") == "0":
            return data["output"].get("hts_kor_isnm", ""), ""
        return None, data.get("msg1", f"rt_cd={data.get('rt_cd')}")
    except Exception as e:
        return None, str(e)


def main():
    if APP_KEY == "여기에_앱키_입력":
        print("❌ APP_KEY와 APP_SECRET을 스크립트 상단에 입력해주세요.")
        return

    print("🔑 KIS API 토큰 발급 중...")
    token = get_token()
    if not token:
        print("❌ 토큰 발급 실패. APP_KEY/APP_SECRET을 확인하세요.")
        return
    print("✅ 토큰 발급 완료\n")

    from sectors_kr import KR_SECTOR_MAP

    # 중복 코드 제거 (첫 번째 항목 기준)
    stocks: dict = {}
    for sector, subs in KR_SECTOR_MAP.items():
        for sub, items in subs.items():
            for s in items:
                code = s.get("code", "")
                if code and code not in stocks:
                    stocks[code] = {"name": s["name"], "sector": sector, "sub": sub}

    total = len(stocks)
    print(f"📋 검증 대상: {total}개 종목\n")

    mismatches = []
    not_found  = []

    for i, (code, info) in enumerate(stocks.items(), 1):
        print(f"\r[{i:3d}/{total}] {code} {info['name'][:12]:<12}", end="", flush=True)
        time.sleep(0.07)  # 초당 약 14건

        kis_name, err = get_name(token, code)

        if kis_name is None:
            not_found.append({
                "코드": code, "저장명": info["name"],
                "섹터": info["sector"], "서브섹터": info["sub"],
                "오류": err,
            })
        elif kis_name != info["name"]:
            mismatches.append({
                "코드": code, "저장명": info["name"], "KIS명": kis_name,
                "섹터": info["sector"], "서브섹터": info["sub"],
            })

    print("\n\n" + "="*60)
    print(f"✅ 검증 완료: {total}개")
    print(f"❌ 불일치:    {len(mismatches)}건")
    print(f"⚠️  조회실패:  {len(not_found)}건")
    print("="*60)

    if mismatches:
        print("\n[불일치 목록]")
        for m in mismatches:
            print(f"  {m['코드']}  저장={m['저장명']}  KIS={m['KIS명']}  ({m['섹터']} › {m['서브섹터']})")
        with open("mismatch_report.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["코드","저장명","KIS명","섹터","서브섹터"])
            w.writeheader(); w.writerows(mismatches)
        print("\n  → mismatch_report.csv 저장 완료")

    if not_found:
        with open("not_found_report.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["코드","저장명","섹터","서브섹터","오류"])
            w.writeheader(); w.writerows(not_found)
        print(f"\n  → not_found_report.csv 저장 완료 ({len(not_found)}건)")


if __name__ == "__main__":
    main()
