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


# 모델 폴백 순서: 무료 티어 쿼터 소진 시 다음 모델로 자동 전환
_MODEL_FALLBACK = [
    "gemini-2.5-flash",       # 최신 flash, Google Search 지원
    "gemini-2.0-flash",       # 안정 flash, Google Search 지원
    "gemini-2.0-flash-lite",  # 경량 폴백, Google Search 지원
]


def _call_gemini(prompt, use_search=False, temperature=0.7, response_mime_type=None):
    """Gemini API 호출 공통 헬퍼 (모델 폴백 + 재시도 포함)."""
    api_key = st.secrets["gemini"]["api_key"]
    client = genai.Client(api_key=api_key)

    config_kwargs = {"temperature": temperature}
    if use_search:
        config_kwargs["tools"] = [{"google_search": {}}]
    if response_mime_type:
        config_kwargs["response_mime_type"] = response_mime_type

    config = types.GenerateContentConfig(**config_kwargs)

    last_err = None
    for model in _MODEL_FALLBACK:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                return response
            except Exception as api_err:
                err_str = str(api_err)
                last_err = api_err
                # 503 / 일시적 오류 → 3초 후 같은 모델 재시도
                if ("503" in err_str or "UNAVAILABLE" in err_str) and attempt == 0:
                    time.sleep(3)
                    continue
                # 429 쿼터 소진 또는 404 모델 미지원 → 다음 모델로 전환
                if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                        or "404" in err_str or "NOT_FOUND" in err_str):
                    break
                # 그 외 오류 → 즉시 raise
                raise api_err
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
        response = _call_gemini(prompt, use_search=True, temperature=0.7, response_mime_type="application/json")
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


@st.cache_data(ttl=1800)  # 30분 캐싱 (성공 결과만 캐시됨)
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
        response = _call_gemini(
            prompt, use_search=True, temperature=0.5,
            response_mime_type="application/json",
        )
        text  = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception:
        raise  # 오류는 캐시하지 않음 — app.py에서 try/except로 처리


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
        response = _call_gemini(
            prompt, use_search=True, temperature=0.5,
            response_mime_type="application/json",
        )
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
