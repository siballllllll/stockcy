"""리서치/이슈 텔레그램 채널 워처.

신한 등 공개 텔레그램 채널의 최신 글을 수집 → AI가 핵심 이슈·섹터·종목으로 요약 →
내 텔레그램으로 브리핑 푸시. 신규 글만 처리(중복 방지).

설정: .env 에 RESEARCH_TG_CHANNELS=채널핸들1,채널핸들2  (예: shinhan_research,또다른채널)
       (t.me/s/<핸들> 로 공개 접근 가능한 채널이어야 함)
"""
import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}


def _channels() -> list:
    raw = os.environ.get("RESEARCH_TG_CHANNELS", "")
    return [c.strip().lstrip("@") for c in raw.split(",") if c.strip()]


def fetch_research_posts(limit_per: int = 6) -> list:
    """설정된 리서치 텔레그램 채널들의 최근 글을 수집한다."""
    posts = []
    for ch in _channels():
        url = f"https://t.me/s/{ch}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=6)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            blocks = soup.find_all("div", class_="tgme_widget_message")
            picked = 0
            for b in reversed(blocks):   # 최신부터
                if picked >= limit_per:
                    break
                txt_el = b.find("div", class_="tgme_widget_message_text")
                if not txt_el:
                    continue
                text = txt_el.get_text(separator="\n", strip=True)
                if len(text) < 20:
                    continue
                mid = b.get("data-post") or hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
                posts.append({"channel": ch, "id": str(mid), "text": text[:1500]})
                picked += 1
        except Exception as e:
            print(f"[research watch] {ch} 수집 실패: {e}")
    return posts


def _parse_json_array(raw: str) -> list:
    """LLM 응답에서 JSON 배열을 견고하게 추출."""
    if not raw:
        return []
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("["):] if "[" in s else s
    i, j = s.find("["), s.rfind("]")
    if i == -1 or j == -1:
        return []
    try:
        return json.loads(s[i:j + 1])
    except Exception:
        return []


def run_research_watch(push: bool = True, limit_per: int = 6) -> dict:
    """채널 수집 → 신규 글만 AI 요약 → 텔레그램 브리핑 푸시."""
    if not _channels():
        return {"new": 0, "posts": 0, "issues": 0, "msg": "RESEARCH_TG_CHANNELS 미설정"}

    from db import load_ai_cache, save_ai_cache

    posts = fetch_research_posts(limit_per=limit_per)
    if not posts:
        return {"new": 0, "posts": 0, "issues": 0, "msg": "수집된 글 없음(채널 접근 실패 가능)"}

    seen = set((load_ai_cache("research_seen") or {}).get("ids", []))
    new_posts = [p for p in posts if p["id"] not in seen]
    if not new_posts:
        return {"new": 0, "posts": len(posts), "issues": 0, "msg": "신규 글 없음"}

    issues = []
    try:
        from ai_engine import _call_gemini
        joined = "\n\n---\n\n".join(f"[{p['channel']}] {p['text']}" for p in new_posts[:12])
        prompt = (
            "다음은 증권사 리서치/이슈 텔레그램 채널의 최신 글들입니다. 투자 관점에서 핵심만 추려주세요.\n"
            "절대로 한자(漢字)를 사용하지 마세요. 한글/영문만.\n"
            "의미있는 이슈만(중복·잡담·광고 제외). 각 이슈: 한 줄 요약, 관련 섹터, 관련 종목(있으면 티커), 단기 방향(긍정/부정/중립).\n"
            'JSON 배열로만 출력: [{"issue":"...","sector":"...","tickers":["..."],"direction":"긍정"}]\n\n'
            + joined
        )
        resp = _call_gemini(prompt, use_search=False, temperature=0.4,
                            response_mime_type="application/json", max_output_tokens=4000)
        # _call_gemini은 GenerateContentResponse 객체를 반환 → .text 로 추출
        if isinstance(resp, str):
            raw = resp
        else:
            raw = getattr(resp, "text", None) or ""
        issues = _parse_json_array(raw)
    except Exception as e:
        print(f"[research watch] AI 요약 실패: {e}")

    # 이슈→시나리오 자동 등록 (티커 있는 이슈만) → 교차검증·적중률 추적에 반영
    registered = 0
    try:
        from db import save_scenario_stocks
        for it in issues:
            valid = []
            for t in (it.get("tickers") or []):
                t = str(t).strip().upper()
                if t.isdigit():
                    t = t.zfill(6)
                elif not (t.isalpha() and 1 <= len(t) <= 5):
                    continue
                role = "피해" if "부정" in str(it.get("direction", "")) else "수혜"
                valid.append({"ticker": t, "name": t, "role": role, "horizon": ""})
            if valid:
                issue_txt = str(it.get("issue", ""))[:60]
                save_scenario_stocks(f"[리서치] {issue_txt}", issue_txt, valid)
                registered += len(valid)
    except Exception as e:
        print(f"[research watch] 시나리오 등록 실패: {e}")

    if push and issues:
        try:
            from telegram_bot import send_message
            lines = ["📑 <b>리서치 이슈 브리핑</b>"]
            for it in issues[:10]:
                tk = ", ".join(it.get("tickers") or [])
                d = str(it.get("direction", ""))
                emoji = "🔺" if "긍정" in d else ("🔻" if "부정" in d else "▪️")
                meta = it.get("sector", "") or ""
                if tk:
                    meta = f"{meta} · {tk}" if meta else tk
                lines.append(f"{emoji} {it.get('issue', '')}" + (f"\n   <i>{meta}</i>" if meta else ""))
            send_message("\n\n".join(lines))
        except Exception as e:
            print(f"[research watch] 텔레그램 발송 실패: {e}")

    # 중복 방지 상태 저장 (최근 500개 id 유지)
    new_ids = list(seen) + [p["id"] for p in new_posts]
    save_ai_cache("research_seen", {"ids": new_ids[-500:]}, ttl_hours=72)

    return {"new": len(new_posts), "posts": len(posts), "issues": len(issues), "registered": registered}
