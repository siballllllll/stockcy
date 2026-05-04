"""
sectors_kr.py 종목 코드 검증 스크립트 (로컬 실행용)
KIS API로 각 종목 코드의 실제 종목명을 조회해 저장된 이름과 비교합니다.

실행 방법:
  python validate_codes.py

결과:
  - mismatch_report.csv  : 코드-이름 불일치 목록
  - not_found_report.csv : 조회 실패 목록
"""

import requests
import time
import csv
import os

KIS_BASE = "https://openapi.koreainvestment.com:9443"


def _load_keys() -> tuple:
    """secrets.toml에서 KIS API 키 자동 로드 ([kis] 또는 [korea_invest] 섹션)."""
    secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".streamlit", "secrets.toml")
    tomllib = None
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            pass

    if tomllib and os.path.exists(secrets_path):
        with open(secrets_path, "rb") as f:
            data = tomllib.load(f)
        for section in ("kis", "korea_invest"):
            if section in data:
                key    = data[section].get("app_key", "")
                secret = data[section].get("app_secret", "")
                if key and "your_" not in key:
                    print(f"✅ secrets.toml [{section}] 섹션에서 KIS 키 로드 완료")
                    return key, secret

    # secrets.toml에 키가 없으면 직접 입력
    print("⚠️  secrets.toml에서 KIS 키를 찾지 못했습니다. 직접 입력해주세요.")
    key    = input("   APP_KEY    : ").strip()
    secret = input("   APP_SECRET : ").strip()
    return key, secret


def get_token(app_key: str, app_secret: str) -> str | None:
    try:
        resp = requests.post(
            f"{KIS_BASE}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": app_key,
                "appsecret": app_secret,
            },
            timeout=10,
        )
        return resp.json().get("access_token")
    except Exception as e:
        print(f"토큰 발급 실패: {e}")
        return None


def get_name(token: str, app_key: str, app_secret: str, code: str) -> tuple:
    """(종목명 or None, 에러메시지) 반환"""
    try:
        resp = requests.get(
            f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers={
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {token}",
                "appkey": app_key,
                "appsecret": app_secret,
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
    app_key, app_secret = _load_keys()
    if not app_key:
        print("❌ KIS 키가 없습니다.")
        return

    print("\n🔑 KIS API 토큰 발급 중...")
    token = get_token(app_key, app_secret)
    if not token:
        print("❌ 토큰 발급 실패. 키를 확인하세요.")
        return
    print("✅ 토큰 발급 완료\n")

    from sectors_kr import KR_SECTOR_MAP

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
        print(f"\r[{i:3d}/{total}] {code}  {info['name'][:14]:<14}", end="", flush=True)
        time.sleep(0.07)

        kis_name, err = get_name(token, app_key, app_secret, code)

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

    print("\n\n" + "=" * 60)
    print(f"✅ 검증 완료 : {total}개")
    print(f"❌ 불일치    : {len(mismatches)}건")
    print(f"⚠️  조회실패  : {len(not_found)}건")
    print("=" * 60)

    if mismatches:
        print("\n[불일치 목록]")
        for m in mismatches:
            print(f"  {m['코드']}  저장={m['저장명']}  →  KIS={m['KIS명']}  ({m['섹터']} › {m['서브섹터']})")
        with open("mismatch_report.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["코드", "저장명", "KIS명", "섹터", "서브섹터"])
            w.writeheader()
            w.writerows(mismatches)
        print("\n→ mismatch_report.csv 저장 완료")

    if not_found:
        with open("not_found_report.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["코드", "저장명", "섹터", "서브섹터", "오류"])
            w.writeheader()
            w.writerows(not_found)
        print(f"→ not_found_report.csv 저장 완료 ({len(not_found)}건)")


if __name__ == "__main__":
    main()
