from google import genai
from google.genai import types
import streamlit as st
import requests
import urllib3
import json
import re
import time

# SSL 경고 무시 (방화벽 우회)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_market_news(category="general"):
    """Yahoo Finance를 활용해 최신 시장 뉴스를 가져옵니다."""
    import yfinance as yf
    try:
        news_items = []
        try:
            spy_news = yf.Ticker("SPY").news
            if spy_news:
                news_items.extend(spy_news[:5])
            qqq_news = yf.Ticker("QQQ").news
            if qqq_news:
                news_items.extend(qqq_news[:5])
        except Exception:
            pass

        if not news_items:
            return "최신 뉴스 데이터를 가져올 수 없습니다."

        extracted_news = []
        for item in news_items[:8]:
            content = item.get('content', item)
            headline = content.get('title', item.get('title', ''))
            summary = content.get('summary', item.get('summary', ''))

            url = ""
            if 'link' in item:
                url = item['link']
            elif 'canonicalUrl' in content:
                url = content['canonicalUrl'].get('url', '')
            elif 'clickThroughUrl' in content:
                url = content['clickThroughUrl'].get('url', '')

            if headline and url:
                extracted_news.append(f"Headline: {headline}\nSummary: {summary}\nURL: {url}")

        if not extracted_news:
            return "최신 뉴스 데이터를 파싱할 수 없습니다."

        return "\n\n".join(extracted_news)
    except Exception as e:
        return f"뉴스 데이터 로드 실패: {e}"


# 모델 폴백 순서
_MODEL_FALLBACK = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

# 할당량 소진 여부 (세션 중 반복 호출 방지)
_QUOTA_EXHAUSTED = False


def _call_gemini(prompt, use_search=False, temperature=0.7, response_mime_type=None):
    """Gemini API 호출 공통 헬퍼 (모델 폴백 + 재시도 포함)."""
    global _QUOTA_EXHAUSTED

    if _QUOTA_EXHAUSTED:
        raise Exception("QUOTA_EXHAUSTED: 오늘의 Gemini API 무료 할당량이 소진되었습니다. 내일 자정(한국 기준) 초기화됩니다.")

    api_key = st.secrets["gemini"]["api_key"]
    client = genai.Client(api_key=api_key)

    config_kwargs = {"temperature": temperature}
    if use_search:
        config_kwargs["tools"] = [{"google_search": {}}]
        # Google Search grounding과 JSON 응답 모드는 동시 사용 불가 → 무시
    elif response_mime_type:
        config_kwargs["response_mime_type"] = response_mime_type

    config = types.GenerateContentConfig(**config_kwargs)

    last_err = None
    exhausted_count = 0
    for model in _MODEL_FALLBACK:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                _QUOTA_EXHAUSTED = False  # 성공 시 플래그 초기화
                return response
            except Exception as api_err:
                err_str = str(api_err)
                last_err = api_err
                if ("503" in err_str or "UNAVAILABLE" in err_str) and attempt == 0:
                    time.sleep(3)
                    continue
                if ("400" in err_str or "INVALID_ARGUMENT" in err_str):
                    break  # 잘못된 요청 — 재시도 불필요
                if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                        or "404" in err_str or "NOT_FOUND" in err_str):
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        exhausted_count += 1
                    break
                raise api_err

    # 모든 모델이 할당량 소진 → 플래그 설정
    if exhausted_count >= len(_MODEL_FALLBACK):
        _QUOTA_EXHAUSTED = True
    raise last_err


def generate_daily_briefing():
    """
    Google Search Grounding을 사용해 오늘 주도 섹터 브리핑을 생성합니다.
    """
    prompt = """
    당신은 월스트리트 최고의 단타 트레이딩 전문가입니다.
    지금 즉시 구글 검색을 통해 오늘 미국 주식 시장에서 가장 자금이 많이 쏠리고 강력하게 급등하고 있는 '주도 섹터(테마)' 3가지를 정확하게 분석해주세요.

    반드시 아래 JSON 형식으로만 응답해야 하며, 어떠한 주석(//)이나 부가 설명도 하지 마세요.
    {
      "sectors": [
        {
          "keyword": "섹터명 (예: 반도체, 비트코인 등)",
          "is_main": true 또는 false,
          "reason": "해당 섹터가 현재 왜 급등하고 있는지 구글 검색된 최신 뉴스를 바탕으로 심도 있게 분석",
          "reference_news_title": "관련된 실제 최신 뉴스 헤드라인 (구글 검색 결과 기반)",
          "reference_news_url": "해당 뉴스의 실제 원문 URL 링크",
          "related_stocks": [
            {"name_kr": "종목명(한국어)", "ticker": "티커기호"}
          ]
        }
      ]
    }
    """
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.7)
        text = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}


def generate_mindmap_data():
    """
    최신 뉴스를 바탕으로 급등/급락 인과관계 마인드맵(Mermaid 문법)을 생성합니다.
    """
    news_text = get_market_news("general")
    prompt = f'''
    다음 최신 뉴스를 바탕으로 미국 증권 시장의 '실시간 급등/급락 테마 마인드맵'을 작성해주세요.
    반드시 Mermaid.js의 graph TD 문법으로만 응답하세요. (마크다운 백틱이나 다른 설명 절대 제외)
    핵심 시장 이슈가 어떤 섹터와 종목에 영향을 만들어 내는지 원인-결과 형태로 연결해야 합니다.

    뉴스 데이터:
    {news_text}

    예시:
    graph TD
      A[AI 반도체 수요 급증] -->|수혜| B(엔비디아 급등)
      A -->|수혜| C(TSMC 상승)
      D[금리 인하 우려] -->|악재| E(비트코인 하락)
    '''
    try:
        response = _call_gemini(prompt, use_search=False, temperature=0.5)
        code = response.text.replace('```mermaid', '').replace('```', '').strip()
        if not code.startswith('graph'):
            code = 'graph TD\n' + code
        return code
    except Exception as e:
        return f"graph TD\n  A[\"분석 시스템\"] --> B[\"{str(e)[:30]}\"]"


def generate_stock_report(ticker, current_price, change_pct):
    """
    선택한 주식의 세력 수급 등급 및 타점을 분석하여 JSON 객체로 반환합니다.
    """
    prompt = f"""
    당신은 월스트리트 최고의 단타 전문 AI 트레이더입니다.
    현재 {ticker}의 주가는 ${current_price} ({change_pct}%) 입니다.

    [요청 사항]
    반드시 아래 JSON 형식으로만 응답하세요. 마크다운이나 다른 텍스트는 절대 포함하지 마세요.
    {{
      "rating": "반드시 다음 중 하나로 정확히 선택: 매우 강력 추천, 추천, 중간추천, 비추천, 매우 비추천",
      "buy_target": "매수가 (구체적인 숫자나 범위)",
      "sell_target": "목표가 (구체적인 숫자)",
      "stop_loss": "손절가 (구체적인 숫자)",
      "analysis": "해당 판단을 정당화하는 구체적인 기술적 분석 근거 (상세한 마크다운 텍스트)"
    }}
    """
    try:
        response = _call_gemini(prompt, use_search=False, temperature=0.7)
        text = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        return {
            "rating": "분석 오류",
            "buy_target": "-",
            "sell_target": "-",
            "stop_loss": "-",
            "analysis": f"AI 분석 중 오류가 발생했습니다: {str(e)}"
        }


def discover_hot_day_trading_stock(context=""):
    """
    Google Search Grounding으로 실시간 마켓을 검색해 오늘 가장 유망한 단타 종목 1개를 발굴합니다.
    """
    prompt = f"""
    당신은 가상의 주식 트레이딩 교육 전문가입니다. 본 분석은 실제 투자 권유가 아니라 교육적 목적으로만 사용합니다.
    지금 즉시 구글 검색 Top gainers, Unusual volume, premarket movers 등을 활용하여 오늘 미국 주식 시장에서 '가장 강한 세력 수급(거래량 급증)'이 들어온 가장 유망한 단타용 종목 딱 1개만 발굴하세요.

    [오늘의 주도 섹터(테마) 참고 자료]:
    {context}
    (위 참고 자료가 있다면 해당 주도 섹터에 해당 종목 중 세력이 진입한 종목을 찾고, 없다면 구글 검색으로 직접 찾으세요.)

    !! [유망 종목 선정 기준 - 반드시 지킬 것] !!
    1. **파동 초입(Breakout) 종목 타겟팅:** 이미 하루에 20~30% 올라서 고점인 종목에 늦게 들어가는 것은 위험 행위입니다.
       **실제 급등 뉴스 재료가 있고, 주요 이동평균선을 상향 돌파하며 '거래량이 급격히 늘기 시작한 초입'**에 있는 종목을 발굴하세요.
    2. **중소형주 우선 선택:** 시가총액이 작은 종목은 오늘 실질적인 재료와 수급으로 5% 이상의 변동성이 기대되면 추천해도 좋습니다.
    3. **이익 목표:** 하루에 최소 **5% ~ 10%의 변동성(이익 구간)**을 노릴 수 있는 잠재력을 갖추어야 합니다.
    4. **세력 수급 파악:** 해당 종목의 세력(기관/고래) 자금이 '지금 막 들어오기 시작하는지', 차트와 뉴스를 분석하세요.

    !! [타점 산정 기준] !!
    종목을 선정했다면 반드시 구글 검색을 통해 해당 종목의 **'오늘 현재 실시간 주가(Current Price)'**를 파악하세요.
    현재가를 기준으로 하루 5~10% 이익을 노릴 수 있는 실질적인 진입가(Buy Target)와 목표가(Sell Target), 그리고 칼같은 손절가(Stop Loss)를 산정하세요.

    반드시 아래 JSON 형식으로만 응답하세요.
    {{
      "ticker": "티커 (예: SOUN, SMCI, PLTR 등 중소형 변동성 주식)",
      "name_kr": "종목명",
      "buy_target": "현재가 부근의 실질적 매수가",
      "sell_target": "매수가 대비 5~10% 이익 구간의 목표가",
      "stop_loss": "매수가 대비 -2~3% 구간의 칼같은 손절가",
      "reasoning": "선정 이유: 1) 세력 수급(거래량 급증) 근거, 2) 차트/모멘텀 분석, 3) 관련 재료 (마크다운 포맷으로 주요 포인트이 있게 상세하게 작성)"
    }}
    """
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.8)
        text = response.text
        if not text:
            return {
                "ticker": "N/A",
                "name_kr": "데이터 차단",
                "reasoning": "AI가 해당 종목의 급등 이유가 안전 정책에 위배되거나, 과도한 투자 권유로 판단하여 응답을 거부했습니다. 다시 시도해주세요.",
                "buy_target": "-", "sell_target": "-", "stop_loss": "-"
            }
        text = re.sub(r'```(?:json)?', '', text).strip()
        start = text.find('{')
        if start == -1:
            raise ValueError("JSON 객체를 찾을 수 없습니다")
        result, _ = json.JSONDecoder().raw_decode(text, start)
        return result
    except Exception as e:
        return {
            "ticker": "N/A",
            "name_kr": "오류",
            "reasoning": f"종목 발굴 중 오류가 발생했습니다: {e}",
            "buy_target": "-", "sell_target": "-", "stop_loss": "-"
        }


def _compute_prebreakout_signals(volume_rank: list, change_rank: list) -> tuple:
    """
    거래량/등락률 랭킹 데이터에서 급등 직전 후보군을 추출하고,
    상위 후보에 대해 분봉 기반 기술적 시그널을 계산합니다.
    반환: (prebreakout_with_signals, already_done)
    """
    from data_kr import get_kr_prebreakout_signal

    prebreakout  = []
    already_done = []
    seen = set()

    def _chg(s):
        return float(s.get("등락률(%)", 0) or 0)

    for s in (volume_rank or []):
        code = str(s.get("종목코드", ""))
        if not code or code in seen:
            continue
        seen.add(code)
        if _chg(s) > 8:
            already_done.append(s)
        elif _chg(s) >= -2:
            prebreakout.append(s)

    for s in (change_rank or []):
        code = str(s.get("종목코드", ""))
        if not code or code in seen:
            continue
        seen.add(code)
        if _chg(s) > 8:
            already_done.append(s)
        elif 1 <= _chg(s) <= 8:
            prebreakout.append(s)

    # 상위 6종목에 분봉 시그널 계산 (API 과호출 방지)
    enriched = []
    for s in prebreakout[:6]:
        code = str(s.get("종목코드", ""))
        try:
            sig = get_kr_prebreakout_signal(code)
        except Exception:
            sig = {"signal_score": 0, "signal_label": "-", "vol_accel": 0}
        enriched.append({**s, "_signal": sig})

    # 시그널 점수 높은 순 정렬
    enriched.sort(key=lambda x: x["_signal"].get("signal_score", 0), reverse=True)
    # 시그널 미계산 종목 뒤에 붙임
    enriched += prebreakout[6:]

    return enriched, already_done


def generate_realtime_picks(market_data: dict, volume_rank: list, change_rank: list) -> dict:
    """
    스캘핑 종목 발굴 — 과거 급등 직전 패턴을 기준으로 현재 진입 가능 종목을 탐지합니다.

    동작 방식:
    1. 거래량 랭킹 + 등락률 랭킹에서 이미 급등한 종목(>8%) 제거
    2. 남은 후보군의 5분봉 데이터로 기술적 시그널 계산
       (거래량가속도, 박스권돌파, 연속양봉 등)
    3. 시그널 점수가 높은 순으로 정렬하여 AI에 전달
    4. AI는 구글 검색으로 재료·수급을 확인 후 최종 3종목 선정
    """
    kospi  = market_data.get("KOSPI",  {})
    kosdaq = market_data.get("KOSDAQ", {})

    prebreakout, already_done = _compute_prebreakout_signals(volume_rank, change_rank)

    def _chg(s):
        return float(s.get("등락률(%)", 0) or 0)

    def _fmt_candidate(s):
        chg   = _chg(s)
        vol   = s.get("거래량", "")
        price = s.get("현재가", "")
        vol   = f"{vol:,}주" if isinstance(vol, int) else str(vol)
        price = f"₩{price:,}" if isinstance(price, int) else str(price)
        mkt   = f"[{s['시장']}]" if "시장" in s else ""
        sig   = s.get("_signal", {})
        score = sig.get("signal_score", "-")
        label = sig.get("signal_label", "")
        accel = sig.get("vol_accel", 0)
        accel_str = f"거래량가속 {accel:.1f}x" if accel > 0 else ""
        signal_str = f"  ▶ 패턴점수:{score}/5 | {label}" if label and label != "-" else ""
        return (
            f"- {s.get('종목명','')} ({s.get('종목코드','')}) {mkt} "
            f"등락률 {chg:+.2f}%, 현재가 {price}, 거래량 {vol}"
            + (f"\n{signal_str}" if signal_str else "")
        )

    pb_lines  = [_fmt_candidate(s) for s in prebreakout[:8]] or ["- 데이터 없음"]
    sur_lines = [
        f"- {s.get('종목명','')} ({s.get('종목코드','')}): {_chg(s):+.1f}% (진입 금지)"
        for s in already_done[:6]
    ]

    prompt = f"""당신은 10년 경력의 한국 주식시장 스캘핑·단타 트레이더입니다.
지금 즉시 구글 검색으로 오늘의 뉴스·공시·외국인/기관 수급 흐름을 파악하세요.

[현재 시장]
KOSPI : {kospi.get('index',0):,.2f}  ({kospi.get('change_pct',0):+.2f}%)
KOSDAQ: {kosdaq.get('index',0):,.2f}  ({kosdaq.get('change_pct',0):+.2f}%)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 [실시간 측정된 급등 직전 시그널 후보군]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
(패턴점수 높을수록 급등 직전 상태. 등락률 8% 미만 = 아직 진입 가능)
{chr(10).join(pb_lines)}

{"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" if sur_lines else ""}
{"❌ [이미 급등 완료 — 진입 불가 목록]" if sur_lines else ""}
{chr(10).join(sur_lines)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 [급등 직전 종목의 실증적 패턴 사전] ← 이 기준으로 판단하세요
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶ 당일 수분~수십분 내 급등 패턴:
  1. 거래량 가속 돌파 (Volume Acceleration Breakout)
     - 최근 15~30분 거래량이 직전 동일 시간 대비 3배 이상 갑자기 터짐
     - 주가는 아직 1~5% 상승에 그쳤지만 거래량이 먼저 급증 = 세력 진입 초기
     - 실제 패턴: 거래량 폭발 → 주가 가속 급등 (수분~10분 시차)

  2. 박스권 돌파 + 거래량 (Consolidation Breakout)
     - 수십분~수시간 좁은 박스권에서 횡보하다가 상단 저항선 돌파
     - 돌파 시 거래량이 박스권 내 평균의 2배 이상 = 세력이 저항을 뚫는 것
     - 돌파 직후 1봉이 핵심 진입 타이밍 (추격 금지)

  3. 눌림목 반등 + 거래량 확인 (Pullback with Volume Confirmation)
     - 급등 후 자연스런 눌림목(2~5% 조정) → 지지선에서 반등
     - 반등 시 거래량이 눌림목 구간보다 많으면 재진입 기회
     - 스캘핑: 지지선 +0.3~0.5% 위에서 매수

  4. 5분봉 연속 양봉 + 거래량 증가 (Consecutive Bullish Candles)
     - 3봉 이상 연속 양봉이면서 각 봉의 거래량이 이전 봉보다 증가
     - 매도 압력 없이 매수세 지속 = 추가 상승 가능성 높음
     - 4번째 봉 시작 시 진입하면 리스크/리워드 유리

  5. VWAP 돌파 + 재테스트 성공 (VWAP Breakout & Retest)
     - 장중 VWAP(당일 평균 가중치 가격) 위로 돌파 후 눌려서 VWAP 재테스트
     - VWAP이 지지로 작동하면서 반등 = 기관 매수 우위
     - 매수: VWAP 재테스트 성공 확인 후

▶ 1~2일 후 급등 패턴:
  1. 장 마감 전 거래량 폭발 (End-of-Day Volume Spike)
     - 오후 2:30~3:20 사이 거래량이 전일 같은 시간대의 3배 이상
     - 세력이 내일 상승을 위한 물량 매집 중 = 다음날 갭상승 또는 장 초반 급등
     - 이 패턴은 당일보다 다음날 오전 9:00~9:30 사이 진입이 유리

  2. 거래량 점진적 증가 + 주가 횡보 (Accumulation Pattern)
     - 3~5일간 거래량이 조금씩 늘면서 주가가 좁은 범위에서 횡보
     - "바닥 다지기" = 세력 매집 완료 단계, 곧 급등 가능
     - 횡보 범위 상단 돌파 시 진입

  3. 뉴스/공시 발생 + 초기 반응 미흡 (Catalyst Lag Effect)
     - 긍정적 뉴스나 공시가 나왔는데 주가가 5% 미만 상승에 그침
     - 시장이 아직 뉴스를 소화하지 못한 상태 = 다음날 추가 상승 가능
     - 조건: 뉴스의 임팩트가 실질적(실적 개선, 수주, M&A 등)이어야 함

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[선정 기준 — 반드시 준수]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ 절대 금지: 현재 등락률 10% 이상 종목 (이미 급등 완료, 진입 불가)
✅ 필수 조건:
   · 위 패턴 사전 중 최소 1개 이상 해당
   · 구글 검색으로 오늘 실제 재료(뉴스/공시/테마) 확인 필수
   · 현재 등락률 0%~8% 사이 종목 우선
   · 후보 목록에 없어도 구글 검색에서 패턴 일치 종목 발굴 가능

🎯 타점 산정 (구글 검색으로 현재가 확인 후):
   · 매수 타점: 패턴별 최적 진입가 (위 패턴 기준 적용)
   · 목표가: 매수가 대비 +3%~+8%
   · 손절가: 매수가 대비 -2% (칼손절)

반드시 아래 JSON만 반환 (백틱·설명 없이):
{{
  "market_condition": "상승장 또는 하락장 또는 혼조세",
  "market_comment": "오늘 시장 한 문장 요약",
  "picks": [
    {{
      "rank": 1,
      "code": "종목코드 6자리",
      "name": "종목명",
      "theme": "핵심 테마 1~2개",
      "pattern": "해당하는 급등 직전 패턴명 (예: 거래량가속돌파, 박스권돌파, 눌림목반등 등)",
      "reason": "패턴 근거 + 오늘 재료 + 진입 가능한 이유 (3줄 이내)",
      "current_price": 현재가_숫자,
      "change_pct": 현재_등락률_숫자,
      "entry": 매수타점_숫자,
      "target": 목표가_숫자,
      "stop": 손절가_숫자,
      "urgency": "즉시진입 또는 눌림목대기 또는 내일장초반",
      "horizon": "당일스캘핑 또는 1~2일스윙"
    }}
  ]
}}

⚠️ 자가검증: change_pct ≥ 10%인 종목이 있으면 반드시 교체하세요."""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.35)
        text = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        return {"error": str(e), "picks": []}


def generate_kr_stock_report(stock_code: str, name: str, price_data: dict, investor_data: list):
    """국내 주식 AI 수급 분석 및 단타 타점 리포트"""
    investor_summary = ""
    if investor_data:
        latest = investor_data[0]
        investor_summary = f"""
최근 수급 동향 ({latest['날짜']}):
- 외국인 순매수: {latest['외국인']:+,}주
- 기관 순매수: {latest['기관']:+,}주
- 개인 순매수: {latest['개인']:+,}주"""

    prompt = f"""
당신은 한국 주식시장 전문 단타 트레이더이자 세력 추적 전문가입니다.

[종목 정보]
종목명: {name} ({stock_code})
현재가: {price_data['price']:,}원 ({price_data['change_pct']:+.2f}%)
거래량: {price_data['volume']:,}주 / 거래대금: {price_data['amount'] // 100000000:,}억원
시가: {price_data['open']:,}원 | 고가: {price_data['high']:,}원 | 저가: {price_data['low']:,}원
52주 최고: {price_data['w52_high']:,}원 | 52주 최저: {price_data['w52_low']:,}원
PER: {price_data['per']} | PBR: {price_data['pbr']}
{investor_summary}

위 데이터와 구글 검색을 통한 최신 뉴스를 종합하여 반드시 아래 JSON으로만 응답하세요.
{{
  "rating": "매우 강력 추천, 추천, 중간추천, 비추천, 매우 비추천 중 하나",
  "buy_target": "매수 타점 (원 단위, 예: 72,500)",
  "sell_target": "목표가 (원 단위, 예: 78,000)",
  "stop_loss": "손절가 (원 단위, 예: 70,000)",
  "세력분석": "외국인/기관 수급 흐름의 의미를 2~3문장으로 분석",
  "analysis": "종합 단타 전략 (최신 뉴스, 차트 패턴, 진입 근거 등을 마크다운으로 상세 작성)"
}}
"""
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.7)
        text = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        return {
            "rating": "분석 오류",
            "buy_target": "-", "sell_target": "-", "stop_loss": "-",
            "세력분석": "-",
            "analysis": f"AI 분석 중 오류가 발생했습니다: {str(e)}"
        }


@st.cache_data(ttl=600)
def generate_dynamic_themes():
    """
    미국 주식 시장 전체를 스캔하여 현재 가장 핫한 테마 5개를 분류하고
    각 테마의 대장주, 관련주, 상관관계 설명을 JSON 형태로 반환합니다.
    (10분 단위 캐싱으로 API 과호출 방지)
    """
    prompt = """
    당신은 월스트리트의 저명한 섹터 애널리스트입니다.
    지금 바로 구글 검색을 통해 오늘 미국 주식 시장을 이끌고 있는 '가장 주목받고 뜨거운 테마(섹터)' 5가지를 완벽하게 분류해주세요.
    단순히 '반도체', '바이오' 같은 1차원적인 분류가 아니라, 'AI 데이터센터 전력 수급', 'GLP-1 비만치료제', '전력 인프라 및 그리드' 처럼
    지금 돈이 쏠리는 날카롭고 뾰족한 테마명이어야 합니다.

    각 테마에 반드시 아래를 포함하세요.
    1. 대장주 (Leader Stock): 해당 테마를 가장 강력하게 이끌고 있는 1개 종목 딱 1개
    2. 밸류체인 설명 (Correlation): 왜 이 테마가 뜨고, 아래 관련주들이 대장주와 구체적으로 어떤 밸류체인/산업 연관성을 가지는지 2~3문장으로 요약
    3. 관련주 (Related Stocks): 대장주를 따라가는 2번, 3번 주식이나 밸류체인에 해당하는 중소형주 3~5개

    반드시 아래 JSON 배열 형식으로만 응답하세요. (마크다운 백틱 제외)
    {
      "themes": [
        {
          "theme_name": "날카로운 테마명 (예: AI 데이터센터 전력소비)",
          "leader_stock": {"name_kr": "버티브 홀딩스", "ticker": "VRT"},
          "correlation": "AI 데이터센터 전력 충격으로 전력 수요가 폭발적으로 늘어남에 따라, 냉각 및 전력 인프라를 전문 공급하는 VRT가 대장주로 상승 중이며 변압기 및 변전기 관련주들이 강한 동조화 커플링을 보이고 있습니다.",
          "related_stocks": [
            {"name_kr": "이튼", "ticker": "ETN"},
            {"name_kr": "퀀타 서비스", "ticker": "PWR"},
            {"name_kr": "슈나이더 일렉트릭", "ticker": "SBGSY"}
          ]
        }
      ]
    }
    """
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.7)
        text = response.text
        if not text:
            return {"themes": []}
        text = re.sub(r'```(?:json)?', '', text).strip()
        start = text.find('{')
        if start == -1:
            raise ValueError("JSON 객체를 찾을 수 없습니다")
        result, _ = json.JSONDecoder().raw_decode(text, start)
        return result
    except Exception as e:
        return {"error": str(e), "themes": []}


@st.cache_data(ttl=3600)  # 1시간 캐싱 (할당량 절약)
def analyze_kr_hot_sectors() -> dict:
    """
    Gemini + Google Search로 오늘 증권사 리포트·금융 뉴스를 분석하여
    핫 섹터를 선별하고 sectors_kr.py DB와 매핑합니다.
    실시간 급등 종목(KIS API)을 프롬프트에 주입하여 정확도를 높입니다.
    """
    from sectors_kr import KR_SECTOR_MAP
    from data_kr import get_kr_change_ranking

    # sectors_kr.py 전체 섹터명을 AI 키워드 기준으로 사용
    known_sectors = list(KR_SECTOR_MAP.keys())
    sectors_str   = "\n".join(f"- {s}" for s in known_sectors)

    # 실시간 급등 종목 수집 (KOSPI + KOSDAQ 상위 10개씩)
    gainers_str = ""
    try:
        kospi_gainers  = get_kr_change_ranking("J")[:10]
        kosdaq_gainers = get_kr_change_ranking("Q")[:10]
        all_gainers    = kospi_gainers + kosdaq_gainers
        if all_gainers:
            lines = [f"- {g['종목명']}({g['종목코드']}) {g['등락률(%)']:+.1f}% [{g['시장']}]"
                     for g in all_gainers]
            gainers_str = "\n[오늘 실시간 급등 종목 (KIS API 현재 데이터)]:\n" + "\n".join(lines) + "\n"
    except Exception:
        pass

    prompt = f"""당신은 한국 주식시장 전문 섹터 애널리스트입니다.
지금 즉시 구글 검색으로 오늘(한국 기준) 증권사 리포트, 금융 뉴스, 공시에서 주목받는 테마를 분석하세요.

[등록된 섹터 DB (keyword는 아래 이름과 정확히 일치시킬 것)]:
{sectors_str}
{gainers_str}
[지시사항]:
1. 위 DB에서 오늘 가장 뜨거운 섹터 5~7개를 선택하세요. keyword는 위 섹터명과 정확히 일치해야 합니다.
2. DB에 없어도 오늘 뉴스에서 새롭게 부각되는 테마가 있으면 신규 keyword로 추가하세요 (예: 양자컴퓨터·암호, 우주·항공우주).
3. 실시간 급등 종목 데이터가 있으면 해당 종목이 속한 섹터의 hot_codes에 반영하세요.
4. hot_codes: 이 섹터에서 오늘 가장 주목받는 종목코드 최대 10개 (KR 6자리).
5. new_stocks: DB에 없지만 오늘 뉴스로 주목받는 신규 종목 (신규 섹터일 때 특히 중요).
6. dynamic_subsectors: 이 섹터 안에서 오늘 뉴스·수급으로 새롭게 부각되는 세부 테마 최대 2개.
   예) '통신' 섹터에서 '광통신'이 급부상, 'AI·로봇' 섹터에서 '온디바이스AI'가 급부상하는 경우.
   세부테마가 없으면 빈 배열 []로 두세요.

반드시 아래 JSON으로만 응답하세요. 주석 없이:
{{
  "market": "KR",
  "sectors": [
    {{
      "keyword": "섹터명 (DB에 있으면 그대로, 없으면 신규명)",
      "hot_score": 1~10,
      "reason": "오늘 이 섹터가 주목받는 이유 (뉴스 기반, 2문장)",
      "news_title": "관련 오늘 뉴스 제목",
      "hot_codes": ["005930", "000660"],
      "new_stocks": [
        {{"name": "종목명", "code": "6자리코드", "suffix": ".KS또는.KQ", "reason": "편입 이유"}}
      ],
      "dynamic_subsectors": [
        {{
          "name": "세부테마명 (예: 광통신, 온디바이스AI)",
          "reason": "오늘 이 세부테마가 새롭게 부각되는 이유 1문장",
          "hot_codes": ["종목코드1", "종목코드2"],
          "new_stocks": [
            {{"name": "종목명", "code": "6자리코드", "suffix": ".KS또는.KQ", "reason": "편입 이유"}}
          ]
        }}
      ]
    }}
  ]
}}"""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.5)
        text  = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        err_str = str(e)
        if "QUOTA" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            return _quota_error_result("analyze_kr_hot_sectors")
        return {"error": f"AI 분석 오류: {type(e).__name__}"}


def _quota_error_result(fn_name: str) -> dict:
    """할당량 초과 시 통일된 에러 딕셔너리 반환."""
    return {
        "error": "QUOTA",
        "message": "오늘의 Gemini API 무료 할당량이 소진되었습니다.\n내일 자정(KST) 자동 초기화되며, Google AI Studio에서 유료 전환 시 즉시 해제됩니다.",
    }


@st.cache_data(ttl=1800)  # 30분 캐싱 (할당량 절약)
def analyze_today_market() -> dict:
    """
    오늘 급등 종목들을 AI + Google Search로 분석하여
    종목별 급등 이유와 오늘의 주도 테마를 반환합니다.
    """
    from data_kr import get_kr_change_ranking

    try:
        kospi_g  = get_kr_change_ranking("J")[:10]
        kosdaq_g = get_kr_change_ranking("Q")[:10]
        all_g    = kospi_g + kosdaq_g
    except Exception:
        all_g = []

    if not all_g:
        return {"error": "급등 종목 데이터 없음 (장 마감 또는 API 오류)"}

    gainers_text = "\n".join(
        f"- {g['종목명']}({g['종목코드']}) {g.get('등락률(%)', 0):+.1f}% [{g.get('시장', '')}]"
        for g in all_g
    )

    prompt = f"""당신은 한국 주식시장 전문 애널리스트입니다.
지금 즉시 구글 검색을 통해 아래 오늘의 급등 종목들의 상승 이유를 분석하세요.

[오늘 급등 종목]:
{gainers_text}

[요청 사항]:
1. 각 종목이 오늘 왜 급등하는지 뉴스·공시·테마 기반으로 1~2문장 설명
2. 오늘 시장 전체의 주도 테마 3가지
3. 가장 강한 테마 1개와 그 이유

반드시 아래 JSON으로만 응답하세요. 주석 없이:
{{
  "market_summary": "오늘 시장 전체 흐름 2~3문장 핵심 요약",
  "leading_themes": ["테마1", "테마2", "테마3"],
  "top_theme": "오늘 가장 강한 테마명",
  "top_theme_reason": "이 테마가 오늘 주도하는 이유 2문장",
  "stocks": [
    {{
      "code": "종목코드6자리",
      "name": "종목명",
      "change_pct": 등락률숫자,
      "market": "KOSPI 또는 KOSDAQ",
      "theme": "속한 테마 (예: 방산, 광통신, AI반도체)",
      "reason": "급등 이유 1~2문장 (뉴스·공시 기반 구체적으로)"
    }}
  ]
}}"""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.4)
        text  = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        if "QUOTA" in str(e) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return _quota_error_result("analyze_today_market")
        return {"error": str(e)}


@st.cache_data(ttl=3600)
def analyze_market_pattern(keyword: str) -> dict:
    """특정 섹터/테마의 역사적 경제 패턴을 분석하고 미래를 예측합니다. (1시간 캐싱)"""
    prompt = f"""당신은 한국 주식시장 전문 섹터 애널리스트이자 역사적 패턴 분석 전문가입니다.
지금 즉시 구글 검색으로 '{keyword}' 섹터/테마에 대한 역사적 주가 패턴과 현재 상황을 분석하세요.

[분석 항목]:
1. 과거에 유사한 이슈/사건이 발생했을 때 이 섹터가 어떻게 움직였는지 (최대 3건의 역사적 사례)
2. 현재 상황과 과거 패턴의 유사점/차이점
3. 과거 패턴 기반 향후 3~6개월 전망

반드시 아래 JSON으로만 응답하세요. 주석 없이:
{{
  "keyword": "{keyword}",
  "historical_patterns": [
    {{
      "period": "시기 (예: 2020년 코로나 이후)",
      "trigger": "촉발 요인 (1문장)",
      "what_happened": "해당 섹터 주가 반응 및 주요 종목 움직임 (1~2문장)",
      "duration": "지속 기간 (예: 약 6개월)",
      "outcome": "최종 결과 (1문장)"
    }}
  ],
  "current_similarity": "현재 상황과 과거 패턴의 유사도 분석 (2~3문장)",
  "prediction": "과거 패턴 기반 향후 3~6개월 전망 (2~3문장, 가능하면 수치 포함)",
  "risk_factors": "주요 리스크 요인 (1~2문장)",
  "key_stocks_to_watch": ["주목할 국내 종목명1", "종목명2", "종목명3"]
}}"""
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.5)
        text = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        return {"keyword": keyword, "error": str(e)}


@st.cache_data(ttl=300)
def generate_related_stocks(ticker: str, sector: str = "") -> list:
    """특정 종목의 동조화 관련주를 AI가 발굴합니다."""
    sector_str = f" ({sector} 섹터)" if sector else ""
    prompt = f"""미국 주식 {ticker}{sector_str}의 동조화 관련주 4개를 발굴해주세요.
구글 검색을 통해 현재 {ticker}와 가장 강한 상관관계를 가진 종목을 찾아주세요.
아래 JSON 배열만 반환하세요. (설명 없이, 마크다운 백틱 제외)
[
  {{"ticker": "티커심볼", "name": "한국어 종목명", "reason": "연관 이유 한 줄"}},
  ...
]"""
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.5)
        text = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('[')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result if isinstance(result, list) else []
        return []
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# US STOCK — AI 타점 보드 / 시장분석 / 핫섹터 (국내 버전의 US 미러)
# ══════════════════════════════════════════════════════════════════════════════

def _compute_us_prebreakout_signals(volume_rank: list, change_rank: list) -> tuple:
    """US 거래량/등락률 랭킹에서 급등 직전 후보를 추출하고 분봉 신호를 계산합니다."""
    from data_kr import get_us_prebreakout_signal

    prebreakout, already_done, seen = [], [], set()

    def _chg(s):
        return float(s.get("등락률(%)", 0) or 0)

    for s in (volume_rank or []):
        t = str(s.get("티커", ""))
        if not t or t in seen:
            continue
        seen.add(t)
        if _chg(s) > 12:
            already_done.append(s)
        elif _chg(s) >= -2:
            prebreakout.append(s)

    for s in (change_rank or []):
        t = str(s.get("티커", ""))
        if not t or t in seen:
            continue
        seen.add(t)
        if _chg(s) > 12:
            already_done.append(s)
        elif 1 <= _chg(s) <= 12:
            prebreakout.append(s)

    enriched = []
    for s in prebreakout[:6]:
        t = str(s.get("티커", ""))
        try:
            sig = get_us_prebreakout_signal(t)
        except Exception:
            sig = {"signal_score": 0, "signal_label": "-", "vol_accel": 0}
        enriched.append({**s, "_signal": sig})

    enriched.sort(key=lambda x: x["_signal"].get("signal_score", 0), reverse=True)
    enriched += prebreakout[6:]
    return enriched, already_done


def generate_us_realtime_picks(market_data: dict, volume_rank: list, change_rank: list) -> dict:
    """
    US 스캘핑 종목 발굴 — 급등 직전 패턴 기준으로 진입 가능 종목 3개 추천.
    generate_realtime_picks()의 US 버전.
    """
    sp500  = market_data.get("S&P500",  {})
    nasdaq = market_data.get("NASDAQ",  {})
    dow    = market_data.get("DOW",     {})

    prebreakout, already_done = _compute_us_prebreakout_signals(volume_rank, change_rank)

    def _chg(s):
        return float(s.get("등락률(%)", 0) or 0)

    def _fmt(s):
        chg   = _chg(s)
        vol   = s.get("거래량", 0)
        price = s.get("현재가($)", 0)
        sig   = s.get("_signal", {})
        score = sig.get("signal_score", "-")
        label = sig.get("signal_label", "")
        accel = sig.get("vol_accel", 0)
        signal_str = f"  ▶ 패턴점수:{score}/5 | {label}" if label and label != "-" else ""
        return (
            f"- {s.get('티커','')}  등락률 {chg:+.2f}%,  현재가 ${price:,.2f},  "
            f"거래량 {vol:,}"
            + (f"\n{signal_str}" if signal_str else "")
        )

    pb_lines  = [_fmt(s) for s in prebreakout[:8]]  or ["- 데이터 없음"]
    sur_lines = [
        f"- {s.get('티커','')}: {_chg(s):+.1f}% (급등 완료, 진입 불가)"
        for s in already_done[:5]
    ]

    prompt = f"""당신은 10년 경력의 미국 주식시장 스캘핑·단타 트레이더입니다.
지금 즉시 구글 검색으로 오늘의 뉴스·실적·SEC 공시·옵션 플로우를 파악하세요.

[현재 시장]
S&P500 : {sp500.get('price',0):,.2f}  ({sp500.get('change_pct',0):+.2f}%)
NASDAQ : {nasdaq.get('price',0):,.2f}  ({nasdaq.get('change_pct',0):+.2f}%)
DOW    : {dow.get('price',0):,.2f}  ({dow.get('change_pct',0):+.2f}%)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 [실시간 측정된 급등 직전 시그널 후보군]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
(패턴점수 높을수록 급등 직전. 등락률 12% 미만 = 아직 진입 가능)
{chr(10).join(pb_lines)}

{"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" if sur_lines else ""}
{"❌ [이미 급등 완료 — 진입 불가]" if sur_lines else ""}
{chr(10).join(sur_lines)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 [급등 직전 패턴 사전 — US 버전]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
▶ 당일 스캘핑 패턴:
  1. 거래량 가속 돌파 — 평균 대비 3x 거래량 + 주가 아직 3%↓
  2. 박스권 돌파 + 거래량 확인 — 하루 내 박스 상단 돌파 후 리테스트
  3. VWAP 돌파 & 재테스트 — VWAP 위로 넘은 후 지지 확인
  4. 연속 양봉 + 거래량 증가 — 3봉↑ 연속 양봉, 각 봉 거래량 증가
  5. 프리마켓 갭업 + 첫 5분봉 확인 — 갭업 후 첫 5분봉 종가 > 시가

▶ 1~2일 스윙 패턴:
  1. 실적 서프라이즈 + 초기 반응 미흡 — EPS 비트 but 2% 미만 반응
  2. 섹터 로테이션 선행 종목 — 지수 약세에도 버티다가 급등 예고
  3. 옵션 대량 콜매수 확인 — 비정상적인 콜 옵션 플로우 감지

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[선정 기준]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ 절대 금지: 등락률 12% 이상 종목 (추격 불가)
✅ 필수 조건:
   · 위 패턴 최소 1개 이상 해당
   · 구글 검색으로 오늘 실제 재료(뉴스/실적/SEC공시/옵션플로우) 확인
   · 후보 목록 외 종목도 검색으로 발굴 가능
🎯 타점 산정 ($달러 단위):
   · 매수 타점: 패턴별 최적 진입가
   · 목표가: 매수가 대비 +4%~+10%
   · 손절가: 매수가 대비 -2%

반드시 아래 JSON만 반환 (백틱·설명 없이):
{{
  "market_condition": "상승장 또는 하락장 또는 혼조세",
  "market_comment": "오늘 US 시장 한 문장 요약",
  "picks": [
    {{
      "rank": 1,
      "ticker": "티커심볼",
      "name": "영문 종목명",
      "theme": "핵심 테마 1~2개",
      "pattern": "해당 급등 직전 패턴명",
      "reason": "패턴 근거 + 오늘 재료 + 진입 가능한 이유 (3줄 이내)",
      "current_price": 현재가_달러_숫자,
      "change_pct": 현재_등락률_숫자,
      "entry": 매수타점_달러_숫자,
      "target": 목표가_달러_숫자,
      "stop": 손절가_달러_숫자,
      "urgency": "즉시진입 또는 눌림목대기 또는 내일장초반",
      "horizon": "당일스캘핑 또는 1~2일스윙"
    }}
  ]
}}

⚠️ 자가검증: change_pct ≥ 12%인 종목이 있으면 반드시 교체하세요."""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.35)
        text = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        return {"error": str(e), "picks": []}


@st.cache_data(ttl=1800)
def analyze_us_today_market() -> dict:
    """오늘 US 급등 종목 + 주도 테마 AI 분석 (analyze_today_market의 US 버전)"""
    from data_kr import get_us_change_ranking
    try:
        gainers = [s for s in (get_us_change_ranking() or []) if s.get("등락률(%)", 0) > 0][:15]
    except Exception:
        gainers = []

    if not gainers:
        return {"error": "급등 종목 데이터 없음 (장 마감 또는 API 오류)"}

    gainers_text = "\n".join(
        f"- {g['티커']}  {g.get('등락률(%)', 0):+.1f}%  ${g.get('현재가($)', 0):,.2f}"
        for g in gainers
    )

    prompt = f"""당신은 미국 주식시장 전문 애널리스트입니다.
지금 즉시 구글 검색으로 아래 오늘의 US 급등 종목들의 상승 이유를 분석하세요.

[오늘 급등 종목]:
{gainers_text}

반드시 아래 JSON으로만 응답하세요. 주석 없이:
{{
  "market_summary": "오늘 US 시장 전체 흐름 2~3문장 핵심 요약",
  "leading_themes": ["테마1", "테마2", "테마3"],
  "top_theme": "오늘 가장 강한 테마명",
  "top_theme_reason": "이 테마가 오늘 주도하는 이유 2문장",
  "stocks": [
    {{
      "ticker": "티커심볼",
      "name": "종목명",
      "change_pct": 등락률숫자,
      "theme": "속한 테마",
      "reason": "급등 이유 1~2문장 (뉴스·실적·SEC공시 기반)"
    }}
  ]
}}"""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.4)
        text  = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        if "QUOTA" in str(e) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return _quota_error_result("analyze_us_today_market")
        return {"error": str(e)}


@st.cache_data(ttl=3600)
def analyze_us_hot_sectors() -> dict:
    """오늘 US 핫 섹터 AI 분석 (analyze_kr_hot_sectors의 US 버전)"""
    from sectors_us import US_SECTOR_MAP
    from data_kr import get_us_change_ranking

    known_sectors = list(US_SECTOR_MAP.keys())
    sectors_str   = "\n".join(f"- {s}" for s in known_sectors)

    gainers_str = ""
    try:
        gainers = [s for s in (get_us_change_ranking() or []) if s.get("등락률(%)", 0) > 0][:10]
        if gainers:
            lines = [f"- {g['티커']} {g.get('등락률(%)', 0):+.1f}%" for g in gainers]
            gainers_str = "\n[오늘 US 실시간 급등 종목]:\n" + "\n".join(lines) + "\n"
    except Exception:
        pass

    prompt = f"""당신은 미국 주식시장 전문 섹터 애널리스트입니다.
지금 즉시 구글 검색으로 오늘 US 증권가에서 주목받는 테마를 분석하세요.

[등록된 US 섹터 DB]:
{sectors_str}
{gainers_str}
[지시사항]:
1. 위 DB에서 오늘 가장 뜨거운 섹터 5~7개를 선택하세요. keyword는 위 섹터명과 정확히 일치.
2. DB에 없는 신규 테마도 추가 가능 (예: 핵에너지, 국방AI, 자율주행).
3. hot_tickers: 이 섹터에서 오늘 가장 주목받는 티커 최대 10개.
4. dynamic_subsectors: 오늘 뉴스로 새롭게 부각되는 세부테마 최대 2개.

반드시 아래 JSON으로만 응답하세요:
{{
  "market": "US",
  "sectors": [
    {{
      "keyword": "섹터명",
      "hot_score": 1~10,
      "reason": "오늘 이 섹터가 주목받는 이유 2문장",
      "news_title": "관련 뉴스 제목",
      "hot_tickers": ["NVDA", "AMD"],
      "dynamic_subsectors": [
        {{
          "name": "세부테마명",
          "reason": "부각 이유 1문장",
          "hot_tickers": ["티커1", "티커2"]
        }}
      ]
    }}
  ]
}}"""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.5)
        text  = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        if "QUOTA" in str(e) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return _quota_error_result("analyze_us_hot_sectors")
        return {"error": f"AI 분석 오류: {type(e).__name__}"}
