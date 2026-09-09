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
        from ai_engine import _call_llm
        joined = "\n\n---\n\n".join(f"[{p['channel']}] {p['text']}" for p in new_posts[:12])
        prompt = (
            "다음은 증권사 리서치/이슈 텔레그램 채널의 최신 글들입니다. 투자 관점에서 핵심만 추려주세요.\n"
            "절대로 한자(漢字)를 사용하지 마세요. 한글/영문만.\n"
            "의미있는 이슈만(중복·잡담·광고 제외). 각 이슈: 한 줄 요약, 관련 섹터, 관련 종목(종목명+티커), 단기 방향(긍정/부정/중립).\n"
            "종목은 반드시 회사명과 티커를 함께. 국내=6자리 숫자코드, 미국=영문심볼.\n\n"
            "【종목 선정 규칙 — 매우 중요】\n"
            "- ⛔ **지수·업종 전반 이야기에는 종목을 붙이지 마세요.** '코스피 7,000p 돌파', "
            "'반도체 업종 저평가', 'AI 관련주 강세' 같은 글은 특정 회사의 이슈가 아닙니다. "
            "이런 이슈는 stocks를 **빈 배열 []** 로 두세요.\n"
            "- ✅ 종목을 넣어도 되는 경우는 **그 회사에 직접 닿는 사실**이 글에 있을 때뿐입니다 — "
            "수주·계약·실적·신제품·공시·증설·규제·소송처럼 회사 이름과 함께 언급된 구체적 사건.\n"
            "- ⛔ 대형주(삼성전자·SK하이닉스·현대차·POSCO홀딩스 등)를 습관적으로 넣지 마세요. "
            "그 회사 이름이 글에 직접 등장하고 그 회사의 사건일 때만 넣습니다.\n"
            "- 한 이슈당 종목은 **최대 3개**. 확실한 것만 남기고 애매하면 빼세요. "
            "빈 배열이 틀린 종목을 넣는 것보다 낫습니다.\n\n"
            'JSON 배열로만 출력: [{"issue":"이슈 한 줄", "sector":"섹터", '
            '"stocks":[{"name":"회사명", "ticker":"티커"}], "direction":"긍정"}]\n'
            "(stocks 예시는 형식일 뿐입니다. 실제 글에 근거가 없으면 빈 배열로 두세요.)\n\n"
            + joined
        )
        # [절충] provider="gemini" 고정 — 이 프롬프트는 최상위 JSON '배열'을 요구하는데,
        # OpenAI는 response_mime_type=json일 때 json_object 모드(최상위가 반드시 객체)로 동작해
        # {"issues":[...]}처럼 감싸서 낸다. _parse_json_array가 첫 '['~마지막 ']'을 잘라내 대개
        # 통과하지만, 배열이 둘 이상 섞이면 조용히 0건이 되므로 평상시엔 Gemini를 쓴다.
        # 단 _call_llm 경유이므로 Gemini가 죽으면 OpenAI로 failover는 된다(완전 실패보다는 나음).
        resp = _call_llm(prompt, use_search=False, temperature=0.4, provider="gemini",
                         response_mime_type="application/json", max_output_tokens=4000)
        # 응답 객체(LLMResponse 또는 GenerateContentResponse) → .text 로 추출
        if isinstance(resp, str):
            raw = resp
        else:
            raw = getattr(resp, "text", None) or ""
        issues = _parse_json_array(raw)
    except Exception as e:
        print(f"[research watch] AI 요약 실패: {e}")

    # 종목 정규화 (stocks:[{name,ticker}] 우선, 구버전 tickers:[..] 호환)
    def _stocks_of(it):
        out = []
        for s in (it.get("stocks") or []):
            if isinstance(s, dict):
                out.append({"name": str(s.get("name") or "").strip(), "ticker": str(s.get("ticker") or "").strip()})
        for t in (it.get("tickers") or []):   # 구버전 호환
            out.append({"name": "", "ticker": str(t).strip()})
        return out

    def _norm_ticker(t):
        t = str(t).strip().upper()
        if t.isdigit():
            return t.zfill(6)
        return t if (t.isalpha() and 1 <= len(t) <= 5) else None

    # 이슈→시나리오 자동 등록 (티커 있는 이슈만) → 교차검증·적중률 추적에 반영
    #
    # [v3.168.0] 지수·시장 전반 이슈는 등록하지 않는다.
    # 이 등록분은 scenario_stocks로 들어가 SHADOW_C의 '이슈 연관' 판정 재료가 되는데,
    # 시장 코멘터리에까지 대형주를 붙이면서 국내 1,073종목이 '재료 있음'으로 잡혀
    # 그 조건이 변별력을 잃고 있었다(실측: 14일간 삼성전자가 154개 시나리오에 등장).
    # 프롬프트로 1차 차단하고, 여기서 한 번 더 거른다.
    # 지수·시장 전반을 가리키는 표현 — 이런 글은 특정 회사의 이슈가 아니다
    _INDEX_WORDS = ("코스피", "코스닥", "나스닥", "s&p", "다우", "지수", "증시",
                    "시장 전반", "업종 전반", "섹터 전반", "업종이", "업종은", "업종 전체",
                    "관련주 강세", "관련주 약세", "테마 강세", "테마 약세")
    # 실측에서 과다 태깅된 대형주 — 글에 회사 이름이 직접 나올 때만 등록한다.
    # (14일간 삼성전자 154개·현대차 125개 시나리오에 등장했고, 대부분 지수·업종 코멘터리였다)
    _MEGA = {"005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차",
             "005490": "POSCO홀딩스", "000270": "기아", "373220": "LG에너지솔루션",
             "207940": "삼성바이오로직스", "005935": "삼성전자우", "006400": "삼성SDI",
             "010130": "고려아연", "004020": "현대제철", "096770": "SK이노베이션"}
    registered = 0
    skipped_index = 0
    skipped_mega = 0
    try:
        from db import save_scenario_stocks
        for it in issues:
            issue_txt_raw = str(it.get("issue", ""))
            low = issue_txt_raw.lower()
            # 지수·업종 전반 이야기인데 종목이 붙어 있으면 등록하지 않는다
            if any(w in low for w in _INDEX_WORDS):
                skipped_index += 1
                continue
            valid = []
            role = "피해" if "부정" in str(it.get("direction", "")) else "수혜"
            for s in _stocks_of(it)[:3]:          # 한 이슈당 최대 3종목
                tk = _norm_ticker(s["ticker"])
                if not tk:
                    continue
                # 대형주는 글에 이름이 직접 등장할 때만 — 습관적 태깅 차단
                if tk in _MEGA and _MEGA[tk] not in issue_txt_raw and (s.get("name") or "") not in issue_txt_raw:
                    skipped_mega += 1
                    continue
                valid.append({"ticker": tk, "name": s["name"] or tk, "role": role, "horizon": ""})
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
                # 종목명(티커) 형태로 표시 — 이름 있으면 이름, 없으면 티커
                names = []
                for s in _stocks_of(it):
                    nm, tk = s.get("name"), s.get("ticker")
                    if nm and tk:
                        names.append(f"{nm}({tk})")
                    elif nm or tk:
                        names.append(nm or tk)
                stock_str = ", ".join(names)
                d = str(it.get("direction", ""))
                emoji = "🔺" if "긍정" in d else ("🔻" if "부정" in d else "▪️")
                meta = it.get("sector", "") or ""
                if stock_str:
                    meta = f"{meta} · {stock_str}" if meta else stock_str
                lines.append(f"{emoji} {it.get('issue', '')}" + (f"\n   <i>{meta}</i>" if meta else ""))
            send_message("\n\n".join(lines))
        except Exception as e:
            print(f"[research watch] 텔레그램 발송 실패: {e}")

    # 중복 방지 상태 저장 (최근 500개 id 유지)
    new_ids = list(seen) + [p["id"] for p in new_posts]
    save_ai_cache("research_seen", {"ids": new_ids[-500:]}, ttl_hours=72)

    return {"new": len(new_posts), "posts": len(posts), "issues": len(issues),
            "registered": registered, "skipped_index": skipped_index,
            "skipped_mega": skipped_mega}
