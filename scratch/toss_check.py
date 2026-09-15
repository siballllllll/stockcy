"""토스 Open API 접속 점검 (V5) — 고정 IP 등록 후 한 번에 확인.

    venv/Scripts/python scratch/toss_check.py

지금 나가는 IP를 먼저 보여주고 토큰 발급을 시도한다. 실패하면 '등록 안 된 IP'인지
'해외라서 막힌 것'인지를 구분해서 알려준다 — 둘 다 403 access_denied로 같은 얼굴을 해서
코드만 보고는 갈라지지 않는다.

콘솔이 cp949라 기호를 쓰면 UnicodeEncodeError로 죽는다. 출력은 ASCII 표식만 쓴다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# .env를 먼저 읽어야 한다. 안 읽으면 toss_api가 빈 키로 돌다가 요청도 안 보내고 None을
# 돌려줘, 접속이 멀쩡한데 '토큰 실패'로 보인다(2026-09-11에 실제로 이 함정에 빠졌다).
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def egress() -> tuple:
    """(IP, 국가코드) — 조회 실패면 (None, None)."""
    try:
        import requests
        j = requests.get("https://ipinfo.io/json", timeout=8).json()
        return j.get("ip"), (j.get("country") or "").upper()
    except Exception as e:
        print(f"   외부 IP 조회 실패: {str(e)[:70]}")
        return None, None


def main() -> int:
    print("토스 Open API 접속 점검")
    print("-" * 62)

    ip, cc = egress()
    where = {"KR": "한국", "JP": "일본", "US": "미국", "SG": "싱가포르"}.get(cc, cc or "?")
    print(f"현재 출구 IP  : {ip or '(조회 실패)'}   [{where}]")
    if cc and cc != "KR":
        print("   [!] 해외 IP다. 허용목록에 등록돼 있어도 국가 차단에 걸릴 수 있다.")
    print(f"등록할 값     : {ip}   (토스 개발자센터 IP 허용목록)")
    print()

    try:
        import toss_api
    except Exception as e:
        print(f"toss_api 임포트 실패: {e}")
        return 1

    if not os.getenv("TOSS_APP_KEY") or not os.getenv("TOSS_APP_SECRET"):
        print("토큰 발급     : 건너뜀 — .env에 TOSS_APP_KEY/SECRET이 없다.")
        print("   IP 문제가 아니다. 키부터 채울 것.")
        return 1

    tok = None
    try:
        tok = toss_api.get_token()
    except Exception as e:
        print(f"토큰 발급 예외: {str(e)[:200]}")

    if not tok:
        # get_token은 실패 사유를 남기지 않으므로 여기서 한 번 더 원시 호출해 응답을 본다.
        try:
            import requests
            r = requests.post(
                f"{toss_api.TOSS_BASE}/oauth2/token",
                data={"grant_type": "client_credentials",
                      "client_id": os.getenv("TOSS_APP_KEY", ""),
                      "client_secret": os.getenv("TOSS_APP_SECRET", "")},
                headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
            print(f"   원시 응답 HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"   원시 호출도 실패: {str(e)[:120]}")

    if not tok:
        print("토큰 발급     : 실패")
        print()
        print("   갈라 보는 법 —")
        print("   1) VPN을 끄고 다시 돌려서 성공하면, 등록한 IP가 안 먹은 것이다.")
        print(f"      (그때 출구 IP가 {ip} 와 다르면 등록값 자체가 틀렸다)")
        if cc and cc != "KR":
            print("   2) 끄면 되고 켜면 안 되는데 등록값이 맞다면, 국가 차단으로 봐야 한다.")
            print("      -> 일본 전용 IP로는 해결되지 않는다. 한국 지역 전용 IP를 찾을 것.")
        print("   3) 둘 다 실패하면 IP 문제가 아니다 — .env의 키/시크릿부터 확인.")
        return 1

    print(f"토큰 발급     : 성공 ({tok[:12]}...)")
    print()

    ok = 0
    for label, fn in (("현재가(삼성전자)", lambda: toss_api.get_price("005930")),
                      ("호가창", lambda: toss_api.get_orderbook("005930")),
                      ("장운영 달력", lambda: toss_api.get_market_calendar("KR"))):
        try:
            v = fn()
            # dict 응답은 ok 플래그가 진실 원천이다 — {"ok": False}도 truthy라 bool()로는 안 갈린다.
            good = (v.get("ok") is True) if isinstance(v, dict) else bool(v)
            ok += good
            print(f"   {'[OK]  ' if good else '[FAIL]'} {label:<16} {str(v)[:66]}")
        except Exception as e:
            print(f"   [FAIL] {label:<16} {str(e)[:66]}")

    print()
    if ok == 3:
        print("전부 정상 — 이 IP에서 V5는 해결됐다. VERIFY.md의 V5를 갱신할 것.")
        print("[!] 남은 과제는 그대로다: 화면이 조회 실패와 휴장을 구분하지 못한다.")
    else:
        print("토큰은 되는데 일부 조회가 실패 — IP가 아니라 엔드포인트 권한/장운영 쪽 문제.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
