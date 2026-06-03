import os
import requests


def _get_credentials() -> tuple[str, str] | tuple[None, None]:
    try:
        from db import load_telegram_config
        token, chat_id = load_telegram_config()
        if token and chat_id:
            return token, chat_id
    except Exception:
        pass
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        return token, chat_id
    return None, None


def send_message(text: str, chat_id: str | None = None) -> bool:
    """텔레그램 봇으로 메시지를 전송합니다. (공유 봇 토큰 + 대상 chat_id)
    chat_id 를 주면 그 사용자에게, 없으면 전역 기본 챗(관리자)으로 보냅니다.
    봇 토큰이나 대상 챗이 없으면 False."""
    token, default_chat = _get_credentials()
    if not token:
        return False
    target = (chat_id or "").strip() or default_chat
    if not target:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": target, "text": text, "parse_mode": "HTML"},
            timeout=8,
        )
        return resp.ok
    except Exception:
        return False


def send_price_alert(market: str, ticker: str, name: str,
                     alert_type: str, current_price: float, target_price: float,
                     chat_id: str | None = None) -> bool:
    """가격 알림 전용 포맷 메시지를 전송합니다. chat_id 주면 해당 사용자에게 발송."""
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
        "AI매수가 도달": "🟢",
        "AI목표가 도달": "🚀",
        "AI손절가 도달": "🔴",
    }
    emoji = emoji_map.get(alert_type, "🔔")

    text = (
        f"{emoji} <b>[스톡시 알림]</b> {flag}\n"
        f"<b>{name}</b> ({ticker})\n"
        f"<b>{alert_type}</b> 도달\n"
        f"목표가: {currency}{fmt(target_price)}\n"
        f"현재가: {currency}{fmt(current_price)}"
    )
    return send_message(text, chat_id)


def is_configured() -> bool:
    """환경변수에 텔레그램 설정이 있는지 확인합니다."""
    token, _ = _get_credentials()
    return token is not None
