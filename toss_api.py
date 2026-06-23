"""toss_api — 토스증권 Open API 연동 모듈 (v1, 읽기 전용 단계)

A단계: OAuth2 토큰 발급 + 현재가 조회까지만.
주문(Order) 기능은 별도 단계에서 dry-run preview 게이트와 함께 추가한다.

환경변수(.env):
    TOSS_APP_KEY     — 토스증권 Open API Key
    TOSS_APP_SECRET  — 토스증권 Open API Secret

엔드포인트(공식 스펙 기준):
    POST /oauth2/token   (form-urlencoded, grant_type=client_credentials)
    GET  /api/v1/prices  (?symbols=005930,AAPL  / Authorization: Bearer)
"""
import os
import time
import requests

TOSS_BASE = "https://openapi.tossinvest.com"

# 토큰 캐시: (access_token, 만료 epoch초). 만료 60초 전이면 갱신한다.
_token_cache = {"token": None, "expires_at": 0.0}
_TOKEN_MARGIN = 60  # 만료 안전 마진(초)


def get_token() -> str | None:
    """토스증권 OAuth2 액세스 토큰 발급(+캐싱). 실패 시 None."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - _TOKEN_MARGIN:
        return _token_cache["token"]

    app_key = os.getenv("TOSS_APP_KEY", "")
    app_secret = os.getenv("TOSS_APP_SECRET", "")
    if not app_key or not app_secret:
        return None

    try:
        resp = requests.post(
            f"{TOSS_BASE}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": app_key,
                "client_secret": app_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            return None
        expires_in = int(data.get("expires_in", 3600))
        _token_cache["token"] = token
        _token_cache["expires_at"] = now + expires_in
        return token
    except Exception:
        return None


def _auth_headers() -> dict | None:
    token = get_token()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def get_prices(symbols: list[str] | str) -> dict[str, float]:
    """여러 종목 현재가 조회. {symbol: lastPrice(float)} 반환.

    symbols: ["005930", "AAPL"] 또는 "005930,AAPL"
    국내는 6자리 코드, 미국은 티커. 한 번에 최대 200개.
    """
    if isinstance(symbols, (list, tuple)):
        symbols_param = ",".join(str(s).strip() for s in symbols if str(s).strip())
    else:
        symbols_param = str(symbols).strip()
    if not symbols_param:
        return {}

    headers = _auth_headers()
    if not headers:
        return {}

    try:
        resp = requests.get(
            f"{TOSS_BASE}/api/v1/prices",
            params={"symbols": symbols_param},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {}

    out: dict[str, float] = {}
    for item in data.get("result", []) or []:
        sym = item.get("symbol") or item.get("code")
        raw = item.get("lastPrice")
        if sym is None or raw is None:
            continue
        try:
            out[str(sym)] = float(raw)
        except (TypeError, ValueError):
            continue
    return out


def get_price(symbol: str) -> float | None:
    """단일 종목 현재가. 실패 시 None."""
    return get_prices([symbol]).get(str(symbol).strip())


if __name__ == "__main__":
    # 최소 연동 테스트: venv/Scripts/python toss_api.py
    from dotenv import load_dotenv
    load_dotenv()

    print("[1] 토큰 발급 테스트 ...")
    tok = get_token()
    if not tok:
        print("  [FAIL] 토큰 발급 실패 — .env의 TOSS_APP_KEY/TOSS_APP_SECRET 확인")
        raise SystemExit(1)
    print(f"  [OK] 토큰 발급 성공 (앞 12자: {tok[:12]}...)")

    print("[2] 현재가 조회 테스트 (삼성전자 005930, 애플 AAPL) ...")
    prices = get_prices(["005930", "AAPL"])
    if not prices:
        print("  [FAIL] 현재가 조회 실패 — 권한/심볼 형식 확인")
        raise SystemExit(1)
    for sym, px in prices.items():
        print(f"  [OK] {sym}: {px:,.2f}")
