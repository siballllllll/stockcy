import requests
import streamlit as st


def _get_credentials() -> tuple[str, str] | tuple[None, None]:
    try:
        token = st.secrets["telegram"]["bot_token"]
        chat_id = str(st.secrets["telegram"]["chat_id"])
        return token, chat_id
    except Exception:
        return None, None


def send_message(text: str) -> bool:
    """텔레그램 봇으로 메시지를 전송합니다. secrets에 [telegram] 설정이 없으면 False 반환."""
    token, chat_id = _get_credentials()
    if not token:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=8,
        )
        return resp.ok
    except Exception:
        return False


def send_price_alert(market: str, ticker: str, name: str,
                     alert_type: str, current_price: float, target_price: float) -> bool:
    """가격 알림 전용 포맷 메시지를 전송합니다."""
    flag = "🇰🇷" if market == "국내" else "🇺🇸"
    currency = "₩" if market == "국내" else "$"

    if market == "국내":
        fmt = lambda p: f"{int(p):,}"
    else:
        fmt = lambda p: f"{p:,.2f}"

    emoji_map = {
        "상승돌파": "🚀",
        "하락돌파": "🔴",
        "매수진입": "🟢",
    }
    emoji = emoji_map.get(alert_type, "🔔")

    text = (
        f"{emoji} <b>[스톡시 알림]</b> {flag}\n"
        f"<b>{name}</b> ({ticker})\n"
        f"<b>{alert_type}</b> 도달\n"
        f"목표가: {currency}{fmt(target_price)}\n"
        f"현재가: {currency}{fmt(current_price)}"
    )
    return send_message(text)


def is_configured() -> bool:
    """secrets에 텔레그램 설정이 있는지 확인합니다."""
    token, _ = _get_credentials()
    return token is not None
