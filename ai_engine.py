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


# 모델 폴백 순서 (분석 품질을 위해 Pro 모델을 최상단에 배치)
_MODEL_FALLBACK = [
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

# 할당량 소진 여부 (세션 중 반복 호출 방지)
_QUOTA_EXHAUSTED = False

# API 호출 타임아웃 (초)
_API_TIMEOUT_SEC = 90


def _clean_ai_json(raw: str) -> str:
    """AI 응답 텍스트에서 JSON을 추출 가능한 형태로 정제합니다."""
    # BOM 제거
    text = raw.lstrip('﻿').strip()
    # 백틱 코드블록 제거
    text = re.sub(r'```(?:json)?', '', text).strip()
    # /* ... */ 블록 주석 제거
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # // 한줄 주석 제거
    text = re.sub(r'//[^\n"]*', '', text)
    # bare ellipsis placeholder: "key": ... → "key": null
    text = re.sub(r':\s*\.\.\.', ': null', text)
    # trailing comma 제거: ,} 또는 ,]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def _friendly_error(e: Exception) -> str:
    """Exception을 사용자 친화적 한국어 메시지로 변환합니다."""
    err = str(e)
    if "API_TIMEOUT" in err:
        return "AI 응답 시간이 초과됐습니다. 잠시 후 다시 시도해주세요."
    if "QUOTA_EXHAUSTED" in err or "429" in err or "RESOURCE_EXHAUSTED" in err:
        return "오늘 AI 사용량이 초과됐습니다. 내일 자정 이후 다시 시도해주세요."
    if "503" in err or "UNAVAILABLE" in err:
        return "AI 서버가 일시적으로 과부하 상태입니다. 잠시 후 다시 시도해주세요."
    if "empty_response" in err or (isinstance(e, AttributeError) and "text" in err):
        return "AI로부터 응답을 받지 못했습니다. 잠시 후 다시 시도해주세요."
    if isinstance(e, (json.JSONDecodeError, ValueError)):
        return "AI 응답 형식 오류입니다. 잠시 후 다시 시도해주세요."
    return "AI 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."


def _repair_truncated_json(fragment: str):
    """잘린 JSON 복구 시도. 성공 시 parsed 결과, 실패 시 None."""
    s = fragment.rstrip()
    s = re.sub(r',\s*$', '', s)
    s = re.sub(r',?\s*"[^"\\]*(?:\\.[^"\\]*)?\s*:\s*$', '', s)  # 불완전 key:
    s = re.sub(r',?\s*"[^"\\]*$', '', s)                          # 불완전 문자열
    s = re.sub(r',\s*$', '', s)

    depth_brace = s.count('{') - s.count('}')
    depth_bracket = s.count('[') - s.count(']')
    if depth_brace < 0 or depth_bracket < 0:
        return None

    repaired = s + ']' * depth_bracket + '}' * depth_brace
    try:
        return json.loads(repaired)
    except Exception:
        return None


def _parse_json_response(response) -> dict:
    """API 응답에서 JSON 추출 (빈 응답·잘린 JSON 자동 복구). 실패 시 ValueError."""
    if response is None:
        raise ValueError("empty_response")
    raw = getattr(response, 'text', None) or ""
    if not raw.strip():
        raise ValueError("empty_response")

    text = _clean_ai_json(raw)

    for start_char in ('{', '['):
        idx = text.find(start_char)
        if idx == -1:
            continue
        try:
            result, _ = json.JSONDecoder().raw_decode(text, idx)
            return result
        except json.JSONDecodeError:
            repaired = _repair_truncated_json(text[idx:])
            if repaired is not None:
                return repaired

    try:
        return json.loads(text)
    except Exception:
        raise ValueError("no_json_found")


def _call_gemini(prompt, use_search=False, temperature=0.7, response_mime_type=None, timeout_sec=None):
    """Gemini API 호출 공통 헬퍼 (모델 폴백 + 재시도 + 타임아웃)."""
    import concurrent.futures
    _timeout = timeout_sec if timeout_sec else _API_TIMEOUT_SEC
    global _QUOTA_EXHAUSTED

    if _QUOTA_EXHAUSTED:
        raise Exception("QUOTA_EXHAUSTED: 오늘의 Gemini API 무료 할당량이 소진되었습니다. 내일 자정(한국 기준) 초기화됩니다.")

    api_key = st.secrets["gemini"]["api_key"]
    client = genai.Client(api_key=api_key)

    config_kwargs = {"temperature": temperature}
    if use_search:
        config_kwargs["tools"] = [{"google_search": {}}]
    elif response_mime_type:
        config_kwargs["response_mime_type"] = response_mime_type

    config = types.GenerateContentConfig(**config_kwargs)

    def _do_call(mdl, cfg):
        return client.models.generate_content(model=mdl, contents=prompt, config=cfg)

    last_err = None
    for model in _MODEL_FALLBACK:
        for attempt in range(2):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(_do_call, model, config)
                    try:
                        response = future.result(timeout=_timeout)
                    except concurrent.futures.TimeoutError:
                        raise Exception(f"API_TIMEOUT: AI 응답 대기 시간({_timeout}초)을 초과했습니다. 잠시 후 다시 시도해주세요.")

                _QUOTA_EXHAUSTED = False
                return response

            except Exception as api_err:
                err_str = str(api_err)
                last_err = api_err

                # 타임아웃 — 즉시 중단 (재시도 무의미)
                if "API_TIMEOUT" in err_str:
                    raise api_err

                # 할당량 초과 — 즉시 중단
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    _QUOTA_EXHAUSTED = True
                    raise api_err

                # 서버 일시 오류 — 1회 재시도 후 다음 모델로
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    if attempt == 0:
                        time.sleep(3)
                        continue
                    break

                # 모델 없음 — 다음 모델로
                if "404" in err_str or "NOT_FOUND" in err_str:
                    print(f"[AI] 모델 {model} 사용 불가 (404), 다음 모델로 폴백. 에러: {err_str[:120]}")
                    break

                # Google Search 권한 오류 (403) → 검색 없이 재시도
                if "403" in err_str and use_search:
                    config_no_search = types.GenerateContentConfig(temperature=temperature)
                    if response_mime_type:
                        config_no_search.response_mime_type = response_mime_type
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                            future = ex.submit(_do_call, model, config_no_search)
                            response = future.result(timeout=_timeout)
                        return response
                    except Exception as fallback_err:
                        print(f"Fallback without search also failed: {fallback_err}")
                        break

                raise api_err

    raise last_err


def generate_daily_briefing():
    """
    Google Search Grounding을 사용해 오늘 주도 섹터 브리핑을 생성합니다.
    """
    prompt = """
    당신은 월스트리트 최고의 단타 트레이딩 전문가입니다.
    지금 즉시 구글 검색을 통해 오늘 미국 주식 시장에서 가장 자금이 많이 쏠리고 강력하게 급등하고 있는 '주도 섹터(테마)' 3가지를 정확하게 분석해주세요.

    ⚠️ [종목 신뢰성 원칙] related_stocks에 포함하는 모든 종목은 NYSE/NASDAQ에 실제 상장된 심볼인지 구글 검색으로 반드시 확인하세요. 확인되지 않는 심볼은 절대 포함하지 마세요.

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
        return _parse_json_response(response)
    except Exception as e:
        return {"error": _friendly_error(e), "sectors": []}


def generate_market_scenarios() -> dict:
    """오늘의 주요 이슈별 시나리오 — 비트코인 포함 전 영역, 단타/장타 전략 분리."""
    prompt = (
        "당신은 월스트리트 20년 경력의 매크로 전략가이자 퀀트 트레이더입니다.\n"
        "구글 검색으로 오늘 글로벌 금융시장(주식·암호화폐 포함)에 가장 큰 영향을 줄 수 있는\n"
        "주요 이슈를 최대 6개까지 파악하세요. 실제로 중요한 이슈만 포함하고, 억지로 채우지 마세요. 반드시 비트코인·암호화폐 관련 이슈 1개를 포함하세요.\n"
        "이슈는 시장 파급력이 큰 순서대로 정렬하세요 (issue_no 1이 가장 중요).\n"
        "(예: 미·중 무역협상, 반도체, 전쟁·지정학, 연준 금리, 유가, 비트코인 법안/ETF, SpaceX 등)\n\n"
        "각 이슈별로 2가지 시나리오(A: 낙관, B: 비관)를 작성하세요.\n"
        "PER/밸류에이션 관점을 반드시 포함하고, 단타전략과 장타전략을 구분해서 작성하세요.\n\n"
        "⚠️ [종목 신뢰성 원칙 — 최우선 적용]\n"
        "rising_stocks, falling_stocks, theme_stocks에 포함하는 모든 종목은 구글 검색으로 반드시 검증하세요:\n"
        "① 국내 종목: 해당 6자리 코드가 실제 KRX(KOSPI/KOSDAQ) 상장 종목코드인지 확인\n"
        "② 미국 종목: 해당 심볼이 NYSE/NASDAQ에 실제 상장된 심볼인지 확인\n"
        "확인되지 않는 종목은 절대 포함하지 마세요. 거래정지·상장폐지 절차 중인 종목도 제외하세요.\n\n"
        "【종목 선정 규칙】\n"
        "- rising_stocks/falling_stocks: 해당 이슈에 실제로 영향받는 국내(KOSPI/KOSDAQ) 및 미국 종목. 억지로 넣을 필요는 없습니다.\n"
        "- 국내 종목 ticker는 KOSPI/KOSDAQ 6자리 숫자 코드(예: 삼성전자=005930, SK하이닉스=000660, 카카오=035720)를 사용하세요.\n"
        "- 미국 종목 ticker는 NYSE/NASDAQ 심볼(예: NVDA, TSLA, AAPL)을 사용하세요.\n"
        "- 불가피하게 불확실한 종목을 포함할 경우 reason 필드에 '⚠️ 코드 직접 확인 필요' 문구를 포함하세요.\n\n"
        "【테마 연동주 선정 규칙 — theme_stocks】\n"
        "theme_stocks는 rising_stocks가 오를 때 '테마 심리'로 함께 급등하는 주변 관련주 섹션입니다.\n"
        "핵심 목적: 대형주(삼성전자·SK하이닉스·현대차 등 시총 10조↑)는 이미 rising_stocks에 있으므로 theme_stocks에는 절대 포함하지 마세요.\n"
        "✅ 선정 기준 — 단타·스윙에 유리한 중소형 KOSDAQ/KOSPI 종목 위주:\n"
        "- 직접관련주(2~3개): 대장주 이슈에 사업 구조상 직접 연동되는 중소형주. 시총 1조 미만 코스닥 종목 우선.\n"
        "- 간접테마주(1~3개): 과거 동일 이슈 때 시장 심리로 함께 급등한 이력이 있는 중소형 테마주. 역사적 패턴 근거 필수.\n"
        "- ⚠️ rising_stocks·falling_stocks에 이미 있는 종목은 제외하세요.\n"
        "- ⚠️ 삼성전자(005930)·SK하이닉스(000660)·현대차(005380)·LG에너지솔루션(373220) 등 시총 10조↑ 대형주는 제외.\n"
        "- 총 3~5개. 단타·스윙 관점에서 하루 5~15% 급등 가능성이 있는 종목 위주로 선정하세요.\n"
        "- 국내(KOSPI/KOSDAQ) 종목만.\n\n"
        "반드시 아래 JSON 형식으로만 응답하세요 (마크다운 백틱, 주석 절대 금지):\n\n"
        "{\n"
        '  "issues": [\n'
        "    {\n"
        '      "issue_no": 1,\n'
        '      "title": "이슈 제목",\n'
        '      "summary": "현황 요약 (1~2문장)",\n'
        '      "urgency": "긴급/보통/장기",\n'
        '      "category": "주식/암호화폐/매크로/지정학",\n'
        '      "scenarios": [\n'
        "        {\n"
        '          "label": "A",\n'
        '          "title": "시나리오 제목",\n'
        '          "probability": "높음/보통/낮음",\n'
        '          "probability_pct": 확률(정수),\n'
        '          "market_direction": "강세/약세/혼조",\n'
        '          "trigger": "현실화 조건 (1문장)",\n'
        '          "economic_analysis": "경제적 영향. PER/밸류에이션 관점 포함 (2~3문장)",\n'
        '          "rising_stocks": [\n'
        '            {"name": "종목명", "ticker": "국내=6자리숫자코드/미국=심볼", "reason": "이유", "valuation_note": "PER 코멘트", "signal": "매우 강력 추천/추천/중간추천/비추천/매우 비추천", "signal_reason": "현재 매수 관점 한 줄 요약"}\n'
        "          ],\n"
        '          "falling_stocks": [\n'
        '            {"name": "종목명", "ticker": "국내=6자리숫자코드/미국=심볼", "reason": "이유", "valuation_note": "PER 코멘트", "signal": "매우 강력 추천/추천/중간추천/비추천/매우 비추천", "signal_reason": "현재 매수 관점 한 줄 요약"}\n'
        "          ],\n"
        '          "theme_stocks": [\n'
        '            {"name": "종목명", "ticker": "KOSPI/KOSDAQ 6자리숫자코드", "type": "직접관련주 또는 간접테마주", "historical_pattern": "과거 유사 이슈 때 이 종목이 어떻게 움직였는지 (1문장)", "reason": "이번에 연동 상승이 예상되는 이유 + 시총 규모 간략 언급", "signal": "매우 강력 추천/추천/중간추천/비추천/매우 비추천", "signal_reason": "현재 매수 관점 한 줄 요약"}\n'
        "          ],\n"
        '          "short_strategy": "단타 전략: 진입 타이밍·청산 조건 (1~2문장)",\n'
        '          "long_strategy": "장타 전략: 포지션 방향·보유 기간 (1~2문장)"\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}"
    )
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.6, timeout_sec=120)
        return _parse_json_response(response)
    except Exception as e:
        return {"error": _friendly_error(e), "issues": []}


def generate_scenario_detail(issue_title: str, scenario_title: str, economic_analysis: str,
                              rising: list, falling: list) -> dict:
    """특정 시나리오의 상세 심층 분석을 생성합니다."""
    rising_txt = ", ".join(f"{s.get('name','?')}({s.get('ticker','?')})" for s in rising)
    falling_txt = ", ".join(f"{s.get('name','?')}({s.get('ticker','?')})" for s in falling)
    prompt = (
        f"당신은 월스트리트 20년 경력의 매크로 전략가이자 퀀트 트레이더입니다.\n"
        f"아래 시나리오에 대한 심층 상세 분석을 제공하세요.\n\n"
        f"## 이슈: {issue_title}\n"
        f"## 시나리오: {scenario_title}\n"
        f"## 기본 분석: {economic_analysis}\n"
        f"## 상승 후보: {rising_txt}\n"
        f"## 하락 후보: {falling_txt}\n\n"
        "⚠️ [가격 신뢰성 원칙] short_detail.stocks의 entry_point, target, stop은 구글 검색으로 각 종목의 실제 현재가를 확인한 뒤, "
        "그 가격에 기반한 합리적인 수준으로 설정하세요. 현재가와 동떨어진(±50% 이상 차이나는) 가격은 절대 제시하지 마세요.\n\n"
        "구글 검색을 통해 최신 정보를 보강하고 아래 JSON 형식으로만 응답하세요 (백틱, 주석 금지):\n\n"
        "{\n"
        '  "deep_analysis": "심층 경제·시장 분석 (4~5문장, PER·금리·수급·섹터 로테이션 포함)",\n'
        '  "historical_precedent": "유사한 역사적 사례와 당시 시장 반응 (2~3문장)",\n'
        '  "key_risks": ["주요 리스크 1", "주요 리스크 2", "주요 리스크 3"],\n'
        '  "short_detail": {\n'
        '    "entry": "단타 진입 조건·가격대",\n'
        '    "exit": "청산 조건·목표가·손절선",\n'
        '    "timing": "최적 진입 타이밍 (장 초반/중반/후반)",\n'
        '    "stocks": [\n'
        '      {"name": "종목명", "ticker": "티커", "entry_point": "진입가 기준 (구글 검색 실제가 기반)", "target": "목표가", "stop": "손절가", "note": "추가 코멘트"}\n'
        "    ]\n"
        "  },\n"
        '  "long_detail": {\n'
        '    "thesis": "장타 투자 근거 (2~3문장)",\n'
        '    "hold_period": "예상 보유 기간",\n'
        '    "position_sizing": "포지션 비중 권고 (예: 포트폴리오의 X%)  ",\n'
        '    "stocks": [\n'
        '      {"name": "종목명", "ticker": "티커", "reason": "장기 보유 이유", "catalyst": "주요 촉매 이벤트"}\n'
        "    ]\n"
        "  }\n"
        "}"
    )
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.5, timeout_sec=120)
        res = _parse_json_response(response)
        # [Python Override - 실시간 현재가 기반 단타 타점 교정]
        try:
            from data import get_us_stock_data
            stocks = res.get("short_detail", {}).get("stocks", [])
            if stocks:
                tickers = [s.get("ticker", "") for s in stocks if s.get("ticker")]
                if tickers:
                    df_prices = get_us_stock_data(tickers)
                    price_map = {}
                    if not df_prices.empty:
                        for _, row in df_prices.iterrows():
                            price_map[row["심볼"]] = float(row["현재가($)"])
                    for s in stocks:
                        cp = price_map.get(s.get("ticker", ""), 0)
                        if cp > 0:
                            s["entry_point"] = f"${cp:.2f} (현재가)"
                            s["target"] = f"${cp * 1.06:.2f} (+6%)"
                            s["stop"] = f"${cp * 0.98:.2f} (-2%)"
                        else:
                            s["entry_point"] = "시세 조회 실패"
                            s["target"] = "시세 조회 실패"
                            s["stop"] = "시세 조회 실패"
        except Exception:
            pass
        return res
    except Exception as e:
        return {"error": _friendly_error(e)}


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


@st.cache_data(ttl=300)
def analyze_sell_timing(ticker: str, name: str, avg_price: float, current_price: float, market: str = "KR") -> dict:
    """평단가 기준 AI 매도 타이밍 분석. 결과를 5분간 캐싱."""
    pnl_pct = (current_price - avg_price) / avg_price * 100 if avg_price > 0 else 0
    sign = "+" if pnl_pct >= 0 else ""
    if market == "KR":
        avg_str = f"{int(avg_price):,}원"
        cp_str  = f"{int(current_price):,}원"
    else:
        avg_str = f"${avg_price:.2f}"
        cp_str  = f"${current_price:.2f}"

    prompt = f"""당신은 개인 투자자의 실전 포트폴리오를 관리하는 전문 트레이딩 어드바이저입니다.

[보유 종목 현황]
종목: {name} ({ticker})
평단가: {avg_str}
현재가: {cp_str}
현재 수익률: {sign}{pnl_pct:.2f}%

구글 검색으로 {name}({ticker})의 최신 뉴스, 차트 흐름, 수급 동향, 거시경제 변수를 파악하세요.
위 투자자가 보유 중인 포지션 기준으로, 지금 매도하는 것이 좋은지, 기다려야 하는지, 타이밍을 어떻게 잡아야 하는지 분석하세요.

반드시 아래 JSON 형식으로만 응답하세요 (마크다운 백틱 없이):
{{
  "verdict": "즉시 매도 | 분할 매도 | 보유 유지 | 추가 매수 고려",
  "timing": "구체적인 매도 타이밍 — 오늘 장 마감 전 / 다음 저항선 도달 시 / 실적 발표 전 등 구체 조건",
  "reason": "판단 근거 — 현재 수익률 상황, 차트 기술적 위치, 최신 뉴스·이슈, 수급 흐름을 종합 (마크다운 불릿 3~4줄)",
  "target_exit": "권장 매도 목표가 또는 청산 트리거 조건 (구체적 가격 또는 이벤트)",
  "risk": "보유 지속 시 주의해야 할 핵심 리스크 1~2문장"
}}"""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.4)
        return _parse_json_response(response)
    except Exception as e:
        if "QUOTA" in str(e) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return {"error": "API 할당량 초과 — 잠시 후 다시 시도하세요."}
        return {"error": _friendly_error(e)}


def generate_stock_report(ticker, current_price, change_pct):
    """
    선택한 주식의 세력 수급 등급 및 타점을 분석하여 JSON 객체로 반환합니다.
    """
    prompt = f"""
당신은 월스트리트 전문 애널리스트입니다.
현재 {ticker}의 주가는 ${current_price} ({change_pct}%)입니다.

[분석 원칙 — 데이터 기반 객관적 판단]
상승·하락 어느 쪽으로도 편향하지 마세요.
실적, 수급, 기술적 지표, 역사적 흐름, 매크로 데이터를 종합해 사실에 근거한 전망을 제시하세요.
데이터가 상승을 지지하면 상승을, 하락을 지지하면 하락을 솔직하게 제시하세요.
근거 없는 낙관도, 근거 없는 비관도 금지. 수치와 사실로만 서술하세요.

⚠️ [최우선 검증 단계] 분석 전 반드시 구글 검색으로 티커 '{ticker}'가 실제 NYSE/NASDAQ/AMEX 상장 회사인지 확인하세요.
- 검색어: "{ticker} stock company name NYSE NASDAQ"
- 확인한 실제 회사명을 'verified_name'에 기재하세요.
- 확인한 회사가 분석 맥락과 다르거나 확인 불가 시 'ticker_mismatch': true 설정.

구글 검색으로 최신 뉴스·실적·SEC 공시·옵션 플로우를 파악한 뒤 반드시 아래 JSON 형식으로만 응답하세요:
{{
  "verified_name": "구글 검색으로 확인한 티커 {ticker}의 실제 회사명",
  "ticker_mismatch": false,

  "rating": "단기 트레이딩 등급 (매우 강력 추천 / 추천 / 중간추천 / 비추천 / 매우 비추천)",

  "key_issues": "현재 이 종목에 영향을 주는 핵심 이슈·변수 2~3가지 (마크다운 불릿. 긍정·부정 모두 포함, 실적·수급·매크로 등 구체적 수치와 함께)",

  "short_term_view_pct": "근 시일(1~4주) 예상 주가 변동률 — 데이터 근거로 객관 판단 (예: +5~+8% 또는 -6~-10%)",
  "short_term_view_price": "단기 예상 도달 가격대 (달러 단위)",
  "short_term_view_reason": "이 전망의 구체적 근거 — 실적, 수급 흐름, 기술적 지지·저항 등 수치 포함 (2~3문장)",

  "buy_target": "매수 적정 구간 가이드라인 (rating이 추천/매우 강력 추천이면 시스템이 현재가 ±1%로 자동 교정, 그 외 등급이면 '관망'으로 대체됨)",
  "sell_target": "단기 목표가 가이드라인 (추천/매우 강력 추천이면 시스템이 +6%로 자동 교정)",
  "stop_loss": "손절가 가이드라인 (추천/매우 강력 추천이면 시스템이 -2%로 자동 교정)",

  "mid_term_view_pct": "중기(1~3개월) 예상 변동률 — % 기호 없이 순수 숫자만 (예: 8.5 또는 -6.0)",
  "mid_term_view_price": "중기 예상 가격대 (달러 단위, 시스템이 mid_term_view_pct로 자동 계산)",
  "mid_term_view_condition": "이 중기 전망의 핵심 변수 또는 catalyst (상승·하락 모두 가능, 구체적인 이벤트·조건)",

  "analysis": "종합 단타 전략 (최신 뉴스, 차트 패턴, 진입 근거 등 마크다운 상세)",
  "historical_pattern_analysis": "유사 과거 패턴(프랙탈) 1~2개, 당시 결과 비교 (마크다운)",

  "long_term_rating": "중장기 등급 (적극 매수 / 분할 매수 / 관망 / 비중 축소 / 전량 매도)",
  "long_term_period": "권장 투자 기간",
  "long_term_target": "중장기 목표가 가이드라인 (달러 단위, 시스템이 long_term_target_pct로 자동 계산)",
  "long_term_target_pct": "중장기 예상 수익/손실률 — % 기호 없이 순수 숫자만 (예: 25.0 또는 -10.0)",
  "long_term_analysis": "매크로 사이클·펀더멘털 중장기 분석 (마크다운 상세)"
}}

!! [수치 산정 주의] 타점(buy/sell/stop) 및 중장기 목표가는 시스템이 실시간 현재가 기반으로 강제 덮어쓰기(Override) 하므로, AI는 논리적 근거 확보에 집중하세요.

!! [딥링크] 종목 언급 시 반드시 '종목명(티커)' 형식: Apple(AAPL), NVIDIA(NVDA) 등
"""
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.7)
        res = _parse_json_response(response)

        # [Python Override - Conditional & No-Fallback]
        try:
            cp = float(current_price)
            rating = str(res.get("rating", ""))

            # 조건부 단기 타점: 추천/매우 강력 추천일 때만 계산
            if rating in ("추천", "매우 강력 추천"):
                res["buy_target"] = f"${cp:.2f} ~ ${cp * 1.01:.2f}"
                res["sell_target"] = f"${cp * 1.06:.2f} (+6%)"
                res["stop_loss"]   = f"${cp * 0.98:.2f} (-2%)"
            else:
                res["buy_target"] = "관망 (진입 타점 없음)"
                res["sell_target"] = "단타 진입 불가"
                res["stop_loss"]   = "단타 진입 불가"

            # 노-폴백 중기 목표가: AI 수익률 숫자 → 실제 가격 환산
            try:
                mid_pct = float(str(res.get("mid_term_view_pct", "")).strip().replace("%", "").replace("+", ""))
                sign = "+" if mid_pct >= 0 else ""
                res["mid_term_view_price"] = f"${cp * (1 + mid_pct / 100):.2f} ({sign}{mid_pct:.1f}%)"
            except Exception:
                res["mid_term_view_price"] = "AI 수익률 산정 불가 (재분석 요망)"

            # 노-폴백 장기 목표가
            try:
                lt_pct = float(str(res.get("long_term_target_pct", "")).strip().replace("%", "").replace("+", ""))
                sign = "+" if lt_pct >= 0 else ""
                res["long_term_target"] = f"${cp * (1 + lt_pct / 100):.2f} ({sign}{lt_pct:.1f}%)"
            except Exception:
                res["long_term_target"] = "AI 수익률 산정 불가 (재분석 요망)"

        except Exception:
            pass

        return res
    except Exception as e:
        msg = _friendly_error(e)
        return {
            "rating": "분석 오류",
            "buy_target": "-", "sell_target": "-", "stop_loss": "-",
            "analysis": msg
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

    ⚠️ [필수 검증] 발굴한 종목의 티커가 실제로 NYSE/NASDAQ에 상장되어 오늘 거래 중인지 구글 검색으로 반드시 확인하세요.
    - 검색어: "[티커] stock price today NYSE NASDAQ"
    - 확인된 실제 회사명을 'verified_name'에 기재하세요.
    - 오늘 실제로 거래 중임이 확인되면 'ticker_verified': true, 확인 불가 시 'ticker_verified': false.

    반드시 아래 JSON 형식으로만 응답하세요.
    {{
      "ticker": "티커 (예: SOUN, SMCI, PLTR 등 중소형 변동성 주식)",
      "verified_name": "구글 검색으로 확인한 실제 회사명",
      "ticker_verified": true,
      "name_kr": "종목명",
      "buy_target": "매수 적정 구간 가이드라인 (시스템이 현재가 기준 ±1% 자동 교정 예정)",
      "sell_target": "목표가 가이드라인 (시스템이 +6% 자동 교정 예정)",
      "stop_loss": "손절가 가이드라인 (시스템이 -2% 자동 교정 예정)",
      "reasoning": "선정 이유: 1) 세력 수급(거래량 급증) 근거, 2) 차트/모멘텀 분석, 3) 관련 재료 (마크다운 포맷으로 주요 포인트이 있게 상세하게 작성)"
    }}

    ⚠️ [수치 산정 주의] 최종 타점은 시스템이 실시간 현재가를 재조회하여 강제 덮어쓰기 하므로, AI는 최적의 종목 발굴 논리에만 집중하세요.
    """
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.8)
        res = _parse_json_response(response)

        # [Python Override - Hallucination Prevention]
        ticker = res.get("ticker")
        if ticker:
            from data import get_us_stock_data
            try:
                # 실시간 시세 재조회하여 타점 강제 덮어쓰기
                price_data = get_us_stock_data([ticker])
                if price_data and ticker in price_data:
                    cp = float(price_data[ticker]['price'])
                    res["buy_target"] = f"${cp * 0.99:.2f} ~ ${cp * 1.01:.2f} 이하"
                    res["sell_target"] = f"${cp * 1.06:.2f} (+6%)"
                    res["stop_loss"] = f"${cp * 0.98:.2f} (-2%)"
                else:
                    res["buy_target"] = "시세 조회 실패 (수동 확인 권장)"
                    res["sell_target"] = "시세 조회 실패"
                    res["stop_loss"] = "시세 조회 실패"
            except Exception:
                res["buy_target"] = "시세 조회 중 오류"

        return res
    except Exception as e:
        return {
            "ticker": "N/A",
            "name_kr": "오류",
            "reasoning": _friendly_error(e),
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


def generate_realtime_picks(
    market_data: dict,
    volume_rank: list,
    change_rank: list,
    hot_sectors: list = None,
    investor_rank: list = None,
) -> dict:
    """
    테마·수급·기술적 시그널을 종합한 AI 종목 발굴.

    동작 방식:
    1. 거래량 랭킹 + 등락률 랭킹에서 이미 급등한 종목(>8%) 제거
    2. 남은 후보군의 5분봉 데이터로 기술적 시그널 계산
    3. 오늘의 핫 섹터·대장주 컨텍스트와 교차 분석
    4. AI가 구글 검색으로 재료·수급·테마 흐름 확인 후 최종 3종목 선정
       → 각 종목마다 테마 내 포지션, 섹터 단계, 대장주 정보 포함
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

    # ── 핫 섹터 컨텍스트 구성 ──────────────────────────────────────────────
    hot_sector_block = ""
    if hot_sectors:
        lines = []
        for hs in hot_sectors[:6]:
            kw    = hs.get("keyword", "")
            score = hs.get("hot_score", 0)
            reason= hs.get("reason", "")
            news  = hs.get("news_title", "")
            codes  = ", ".join(hs.get("hot_codes", [])[:5])
            stage  = hs.get("sector_stage", "")
            leader = hs.get("leader_name", "")
            lines.append(
                f"  [{kw}] 점수:{score}/10  단계:{stage if stage else '?'}"
                + (f"  대장주:{leader}" if leader else "")
                + f"\n    이유: {reason}"
                + (f"\n    뉴스: {news}" if news else "")
                + (f"\n    핵심코드: {codes}" if codes else "")
            )
        hot_sector_block = (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔥 [오늘의 핫 섹터 현황 — 테마 연동 기준으로 종목 선정]\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(lines)
            + "\n\n"
            "→ 위 핫 섹터의 추종주 중 아직 덜 오른 종목도 우선 후보로 고려하세요.\n"
            "→ 대장주가 확인된 경우, 추종주의 테마 포지션(선도추종주/후발추종주)을 파악하세요.\n"
        )

    # ── 외국인·기관 순매수 상위 ──────────────────────────────────────────
    investor_block = ""
    if investor_rank:
        inv_lines = [
            f"  - {iv.get('종목명','')}({iv.get('종목코드','')})  "
            f"외국인:{iv.get('외국인순매수',0):+,}주  기관:{iv.get('기관순매수',0):+,}주"
            for iv in investor_rank[:8]
        ]
        if inv_lines:
            investor_block = (
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💰 [오늘 외국인·기관 순매수 상위 종목]\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                + "\n".join(inv_lines)
                + "\n→ 수급이 강한 종목은 기술적 시그널이 약해도 우선 고려하세요.\n"
            )

    # ── 최신 찌라시/뉴스 컨텍스트 구성 (The Link Fetcher) ───────────────────
    news_block = ""
    try:
        from news_fetcher import get_latest_market_news
        kr_news = get_latest_market_news(market="KR", limit=3)
        if kr_news:
            n_lines = [f"- 헤드라인: {n['headline']}\n  본문 요약: {n['body']}" for n in kr_news]
            news_block = (
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "📰 [실시간 텔레그램 뉴스 및 찌라시 (The Link Fetcher)]\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                + "\n\n".join(n_lines)
                + "\n→ 최신 재료 파악 시 위 뉴스를 우선적으로 참고하여 테마/급등 원인을 분석하세요.\n"
            )
    except Exception:
        pass

    prompt = f"""당신은 10년 경력의 한국 주식시장 스캘핑·단타 트레이더이자 테마·세력 추적 전문가입니다.
지금 즉시 구글 검색으로 오늘의 뉴스·공시·외국인/기관 수급 흐름, 테마 흐름을 파악하세요.

[현재 시장]
KOSPI : {kospi.get('index',0):,.2f}  ({kospi.get('change_pct',0):+.2f}%)
KOSDAQ: {kosdaq.get('index',0):,.2f}  ({kosdaq.get('change_pct',0):+.2f}%)
{hot_sector_block}{investor_block}{news_block}
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
   · 위 패턴 사전 중 최소 1개 이상 해당, 또는 수급·테마 흐름이 강력한 종목
   · 구글 검색으로 오늘 실제 재료(뉴스/공시/테마/수급) 확인 필수
   · 현재 등락률 0%~8% 사이 종목 우선
   · 후보 목록에 없어도 구글 검색에서 패턴 일치 종목 발굴 가능
   · 핫 섹터가 있으면 해당 섹터의 추종주 중 아직 덜 움직인 종목도 우선 고려

🔍 테마 연동 분석 (각 픽에 대해 반드시 수행):
   · 이 종목이 속한 섹터/테마에서 오늘 대장주가 누구인지 확인
   · 대장주 대비 이 종목의 위치 파악 (이미 같이 올랐나, 아직 후행하나)
   · 섹터 단계 판단 (초기 형성/확산/과열/냉각)
   · 세력(외국인·기관)의 현재 유입/이탈 방향 확인
   · 역사적으로 이 패턴에서 이 종목 또는 유사 종목이 어떻게 움직였는지 참조

🎯 타점 산정 (구글 검색으로 현재가 확인 후):
   · 매수 타점: 패턴별 최적 진입가 (위 패턴 기준 + 테마 연동 고려)
   · 목표가: 매수가 대비 +3%~+8% (테마 확산 중이면 +10%까지 설정 가능)
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
      "from_search": false,
      "theme": "핵심 테마 1~2개 (섹터명 기준)",
      "pattern": "해당하는 급등 직전 패턴명 (예: 거래량가속돌파, 박스권돌파, 눌림목반등, 테마추종 등)",
      "reason": "패턴 근거 + 오늘 재료 + 테마 연동 이유 + 진입 근거 (3~4줄)",
      "current_price": 현재가_숫자,
      "change_pct": 현재_등락률_숫자,
      "entry": 매수타점_숫자,
      "entry_limit": 추격매수_금지선_숫자_이_가격_이상_진입_불가,
      "target": 목표가_숫자,
      "stop": 손절가_숫자,
      "urgency": "즉시진입 또는 눌림목대기 또는 내일장초반",
      "horizon": "당일스캘핑 또는 1~2일스윙",
      "position": "대장주 또는 선도추종주 또는 후발추종주",
      "theme_stage": "초기 형성 또는 확산 또는 과열 또는 냉각",
      "leader_name": "이 테마의 오늘 대장주 종목명",
      "supply_signal": "세력 강하게 유입 또는 기관 매집 또는 외국인 매집 또는 관망 또는 이탈",
      "theme_linkage": "대장주와의 연동 설명 + 이 종목이 왜 다음 타자인지 1~2문장"
    }}
  ]
}}

⚠️ 자가검증 (반드시 수행):
① change_pct ≥ 10%인 종목이 있으면 교체하세요.
② 위 '급등 직전 시그널 후보군' 목록에 없는 종목을 선택했다면 해당 픽의 'from_search': true로 설정하고 reason에 구글 검색 근거를 명시하세요.
③ code가 실제 KRX 6자리 코드인지 확인하세요 (숫자 6자리 형식)."""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.35)
        return _parse_json_response(response)
    except Exception as e:
        return {"error": _friendly_error(e), "picks": []}


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
당신은 한국 주식시장 전문 애널리스트입니다.

[분석 원칙 — 데이터 기반 객관적 판단]
상승·하락 어느 쪽으로도 편향하지 마세요.
실적, 수급, 기술적 지표, 역사적 흐름, 섹터 동향을 종합해 사실에 근거한 전망을 제시하세요.
데이터가 상승을 지지하면 상승을, 하락을 지지하면 하락을 솔직하게 제시하세요.
근거 없는 낙관도, 근거 없는 비관도 금지. 수치와 사실로만 서술하세요.

[종목 정보]
종목명: {name} ({stock_code})
현재가: {price_data['price']:,}원 ({price_data['change_pct']:+.2f}%)
시가총액: {price_data.get('market_cap', '-')}
거래량: {price_data['volume']:,}주 / 거래대금: {price_data['amount'] // 100000000:,}억원
시가: {price_data['open']:,}원 | 고가: {price_data['high']:,}원 | 저가: {price_data['low']:,}원
52주 최고: {price_data['w52_high']:,}원 | 52주 최저: {price_data['w52_low']:,}원
PER: {price_data['per']} | PBR: {price_data['pbr']}
{investor_summary}

⚠️ [최우선 검증 단계] 분석 시작 전 반드시 구글 검색으로 KRX 종목코드 '{stock_code}'의 실제 종목명을 확인하세요.
- 검색어: "KRX {stock_code} 종목명" 또는 "{stock_code} 주식 종목"
- 검색 결과에서 확인한 실제 종목명을 'verified_name' 필드에 기재하세요.
- 확인된 실제 종목명이 '{name}'과 다를 경우: 'ticker_mismatch'를 true로 설정하고, 실제 종목명({stock_code}) 기준으로만 분석하세요. '{name}' 정보를 혼용하지 마세요.
- 일치할 경우: 'ticker_mismatch'를 false로 설정하고 정상 분석을 진행하세요.

구글 검색으로 최신 뉴스·실적·공시·섹터 동향을 파악한 뒤 반드시 아래 JSON으로만 응답하세요.
{{
  "verified_name": "구글 검색으로 확인한 종목코드 {stock_code}의 실제 종목명",
  "ticker_mismatch": false,

  "rating": "단기 트레이딩 등급 (매우 강력 추천 / 추천 / 중간추천 / 비추천 / 매우 비추천)",

  "key_issues": "현재 이 종목에 영향을 주는 핵심 이슈·변수 2~3가지 (마크다운 불릿. 긍정·부정 모두 포함, 실적·수급·섹터·매크로 등 구체적 수치와 함께)",

  "short_term_view_pct": "근 시일(1~4주) 예상 주가 변동률 — 데이터 근거로 객관 판단 (예: +5~+8% 또는 -6~-10%)",
  "short_term_view_price": "단기 예상 도달 가격대 (원 단위)",
  "short_term_view_reason": "이 전망의 구체적 근거 — 이슈, 수급 흐름, 기술적 지지·저항, 실적 등 수치 포함 (2~3문장)",

  "buy_target": "매수 적정 구간 가이드라인 (rating이 추천/매우 강력 추천이면 시스템이 현재가 ±1%로 자동 교정, 그 외 등급이면 '관망'으로 대체됨)",
  "sell_target": "단기 목표가 가이드라인 (추천/매우 강력 추천이면 시스템이 +6%로 자동 교정)",
  "stop_loss": "손절가 가이드라인 (추천/매우 강력 추천이면 시스템이 -2%로 자동 교정)",

  "mid_term_view_pct": "중기(1~3개월) 예상 변동률 — % 기호 없이 순수 숫자만 (예: 8.5 또는 -6.0)",
  "mid_term_view_price": "중기 예상 가격대 (원 단위, 시스템이 mid_term_view_pct로 자동 계산)",
  "mid_term_view_condition": "이 중기 전망의 핵심 변수 또는 catalyst (상승·하락 모두 가능, 구체적인 이벤트·조건)",

  "세력분석": "외국인/기관 수급 흐름과 그 의미를 2~3문장으로 분석",
  "analysis": "종합 단타 전략 (최신 뉴스, 차트 패턴, 진입 근거 등 마크다운 상세)",
  "historical_pattern_analysis": "현재 주가 흐름·수급·섹터와 유사했던 과거 패턴(프랙탈) 1~2개, 당시 결과 비교 (마크다운)",

  "long_term_rating": "중장기 등급 (적극 매수 / 분할 매수 / 관망 / 비중 축소 / 전량 매도)",
  "long_term_period": "권장 투자 기간",
  "long_term_target": "중장기 목표가 가이드라인 (원 단위, 시스템이 long_term_target_pct로 자동 계산)",
  "long_term_target_pct": "중장기 예상 수익/손실률 — % 기호 없이 순수 숫자만 (예: 25.0 또는 -10.0)",
  "long_term_analysis": "거시경제 사이클·펀더멘털 기반 중장기 분석 (마크다운 상세)"
}}

!! [수치 산정 주의] 모든 가격 타점은 시스템이 실시간 현재가 기반으로 강제 덮어쓰기 하므로, AI는 수치 계산보다 분석 논리에 집중하세요.

!! [딥링크] 종목 언급 시 반드시 '종목명(6자리코드)' 형식: 삼성전자(005930), SK하이닉스(000660) 등
"""
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.7)
        res = _parse_json_response(response)

        # [Python Override - Conditional & No-Fallback]
        try:
            cp = float(price_data['price'])
            rating = str(res.get("rating", ""))
            if rating in ("추천", "매우 강력 추천"):
                res["buy_target"] = f"{int(cp * 0.99):,}원 ~ {int(cp * 1.01):,}원"
                res["sell_target"] = f"{int(cp * 1.06):,}원 (+6%)"
                res["stop_loss"] = f"{int(cp * 0.98):,}원 (-2%)"
            else:
                res["buy_target"] = "관망 (진입 타점 없음)"
                res["sell_target"] = "단타 진입 불가"
                res["stop_loss"] = "단타 진입 불가"
            try:
                mid_pct = float(str(res.get("mid_term_view_pct", "")).strip().replace("%", "").replace("+", ""))
                sign = "+" if mid_pct >= 0 else ""
                res["mid_term_view_price"] = f"{int(cp * (1 + mid_pct / 100)):,}원 ({sign}{mid_pct:.1f}%)"
            except Exception:
                res["mid_term_view_price"] = "AI 수익률 산정 불가 (재분석 요망)"
            try:
                lt_pct = float(str(res.get("long_term_target_pct", "")).strip().replace("%", "").replace("+", ""))
                sign = "+" if lt_pct >= 0 else ""
                res["long_term_target"] = f"{int(cp * (1 + lt_pct / 100)):,}원 ({sign}{lt_pct:.1f}%)"
            except Exception:
                res["long_term_target"] = "AI 수익률 산정 불가 (재분석 요망)"
        except Exception:
            pass

        return res
    except Exception as e:
        msg = _friendly_error(e)
        return {
            "rating": "분석 오류",
            "buy_target": "-", "sell_target": "-", "stop_loss": "-",
            "세력분석": "-",
            "analysis": msg
        }


def analyze_box_pattern(ticker: str, name: str, price_data: dict, market: str = "KR"):
    """
    퀀트+AI 하이브리드: Python이 실제 차트 데이터로 지지/저항선을 계산하고,
    AI는 그 수치를 근거로 돌파 가능성과 수급 동향만 뉴스 기반으로 분석합니다.
    """
    cp = float(price_data.get("price", 0))
    currency = "원" if market == "KR" else "달러"

    # ── Step 1: Python 정량 계산 (최근 20거래일 고가/저가) ─────────────────
    support_price = cp * 0.95   # 데이터 조회 실패 시 폴백
    resistance_price = cp * 1.05
    _data_source = "폴백(±5%)"
    try:
        from data_kr import get_kr_daily_chart, get_us_daily_chart
        df_chart = get_kr_daily_chart(ticker, period="3mo") if market == "KR" \
                   else get_us_daily_chart(ticker, period="3mo")
        if not df_chart.empty and len(df_chart) >= 5:
            recent = df_chart.tail(20)
            support_price = float(recent["low"].min())
            resistance_price = float(recent["high"].max())
            _data_source = f"실제 차트 {len(recent)}거래일"
    except Exception:
        pass

    # ── Step 2: 포맷 문자열 생성 ──────────────────────────────────────────
    if market == "KR":
        sup_str = f"{int(support_price):,}원"
        res_str = f"{int(resistance_price):,}원"
        cp_str  = f"{int(cp):,}원"
    else:
        sup_str = f"${support_price:.2f}"
        res_str = f"${resistance_price:.2f}"
        cp_str  = f"${cp:.2f}"

    # ── Step 3: AI 프롬프트에 정량값 주입 ─────────────────────────────────
    prompt = f"""당신은 15년 경력의 기술적 분석 및 세력 수급 추적 전문가입니다.

[퀀트 알고리즘 계산 결과 — 최근 20거래일 실제 OHLC 데이터 기반]
종목: {name} ({ticker})
현재가: {cp_str}
1차 지지선 (20일 최저가): {sup_str}  ← 이 수치를 그대로 사용할 것
1차 저항선 (20일 최고가): {res_str}  ← 이 수치를 그대로 사용할 것
데이터 출처: {_data_source}

⚠️ [중요] support_line과 resistance_line은 위 계산값을 그대로 답하세요. 임의로 변경하거나 다른 수치를 추측하지 마세요.

구글 검색으로 최신 뉴스·수급·공시를 파악해 아래 분석을 완성하세요.
반드시 아래 JSON 형식으로만 응답하세요 (마크다운 백틱 없이):
{{
  "support_line": "{sup_str}",
  "resistance_line": "{res_str}",
  "breakout_probability": "저항선 돌파 확률 (예: 65%) — 뉴스·수급 근거 기반",
  "box_analysis": "현재 박스권 형성 배경과 돌파/이탈 가능성 기술적 분석 (3~4문장, 뉴스 및 수급 데이터 포함)",
  "supply_demand_analysis": "외국인·기관·세력 수급 동향 및 매집/분산 여부 (3~4문장)",
  "action_plan": "현재 자리 대응 전략 — 매수 타이밍, 저항 돌파 후 전략, 손절 기준 포함"
}}"""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.5)
        res = _parse_json_response(response)
        # [Python Override - 정량 계산값으로 강제 덮어쓰기]
        res["support_line"] = sup_str
        res["resistance_line"] = res_str
        return res
    except Exception as e:
        return {
            "support_line": sup_str,
            "resistance_line": res_str,
            "breakout_probability": "-",
            "box_analysis": _friendly_error(e),
            "supply_demand_analysis": "-",
            "action_plan": "-",
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
    4. 분석 시 종목 언급은 반드시 '종목명(티커)' 형식을 사용하세요.
    5. 답변은 반드시 한국어로 작성하세요.

    ⚠️ [종목 신뢰성 원칙] leader_stock과 related_stocks의 모든 티커가 NYSE/NASDAQ에 실제 상장된 심볼인지 구글 검색으로 반드시 확인하세요.
    존재하지 않거나 확인되지 않는 심볼은 절대 사용하지 마세요.

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
        return _parse_json_response(response)
    except Exception as e:
        return {"error": _friendly_error(e), "themes": []}


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
4. hot_codes: 이 섹터에서 오늘 가장 주목받는 종목코드 최대 10개 (KR 6자리). ⚠️ 반드시 구글 검색으로 각 코드가 실제 KRX 상장 종목 코드인지 확인하고, 확인되지 않은 코드는 제외하세요.
5. new_stocks: DB에 없지만 오늘 뉴스로 주목받는 신규 종목 (신규 섹터일 때 특히 중요). ⚠️ code와 name이 실제로 일치하는지 구글 검색으로 확인 후 기재하세요.
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
        return _parse_json_response(response)
    except Exception as e:
        err_str = str(e)
        if "QUOTA" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            return _quota_error_result("analyze_kr_hot_sectors")
        return {"error": _friendly_error(e)}


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
        return _parse_json_response(response)
    except Exception as e:
        if "QUOTA" in str(e) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return _quota_error_result("analyze_today_market")
        return {"error": _friendly_error(e)}


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
        return _parse_json_response(response)
    except Exception as e:
        return {"keyword": keyword, "error": _friendly_error(e)}


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
        result = _parse_json_response(response)
        return result if isinstance(result, list) else []
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

    # ── 최신 찌라시/뉴스 컨텍스트 구성 (The Link Fetcher) ───────────────────
    news_block = ""
    try:
        from news_fetcher import get_latest_market_news
        us_news = get_latest_market_news(market="US", limit=3)
        if us_news:
            n_lines = [f"- Headline: {n['headline']}\n  Body: {n['body']}" for n in us_news]
            news_block = (
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "📰 [Real-time Telegram News & Rumors (The Link Fetcher)]\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                + "\n\n".join(n_lines)
                + "\n→ 최신 재료 파악 시 위 뉴스를 우선적으로 참고하여 상승/급락 원인을 분석하세요.\n"
            )
    except Exception:
        pass

    prompt = f"""당신은 10년 경력의 미국 주식시장 스캘핑·단타 트레이더입니다.
지금 즉시 구글 검색으로 오늘의 뉴스·실적·SEC 공시·옵션 플로우를 파악하세요.

[현재 시장]
S&P500 : {sp500.get('price',0):,.2f}  ({sp500.get('change_pct',0):+.2f}%)
NASDAQ : {nasdaq.get('price',0):,.2f}  ({nasdaq.get('change_pct',0):+.2f}%)
DOW    : {dow.get('price',0):,.2f}  ({dow.get('change_pct',0):+.2f}%)
{news_block}
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
      "from_search": false,
      "theme": "핵심 테마 1~2개",
      "pattern": "해당 급등 직전 패턴명",
      "reason": "패턴 근거 + 오늘 재료 + 진입 가능한 이유 (3줄 이내)",
      "current_price": 현재가_달러_숫자,
      "change_pct": 현재_등락률_숫자,
      "entry": 매수타점_달러_숫자,
      "entry_limit": 추격매수_금지선_달러_숫자_이_가격_이상_진입_불가,
      "target": 목표가_달러_숫자,
      "stop": 손절가_달러_숫자,
      "urgency": "즉시진입 또는 눌림목대기 또는 내일장초반",
      "horizon": "당일스캘핑 또는 1~2일스윙"
    }}
  ]
}}

⚠️ 자가검증 (반드시 수행):
① change_pct ≥ 12%인 종목은 교체하세요.
② 위 '급등 직전 시그널 후보군' 목록에 없는 종목을 선택했다면 해당 픽의 'from_search': true로 설정하고 reason에 구글 검색 근거를 명시하세요.
③ ticker가 실제 NYSE/NASDAQ 상장 심볼인지 확인하세요."""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.35)
        return _parse_json_response(response)
    except Exception as e:
        return {"error": _friendly_error(e), "picks": []}


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
        return _parse_json_response(response)
    except Exception as e:
        if "QUOTA" in str(e) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return _quota_error_result("analyze_us_today_market")
        return {"error": _friendly_error(e)}


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
        return _parse_json_response(response)
    except Exception as e:
        if "QUOTA" in str(e) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return _quota_error_result("analyze_us_hot_sectors")
        return {"error": _friendly_error(e)}


def analyze_sector_theme_linkage(sector_name: str, stocks_with_data: list) -> dict:
    """섹터 테마 연동 종합 분석.

    대장주 식별 → 추종주 순서 → 수급/세력 동향 → 현재 단계 → 역사적 패턴 → 매매 전략

    Args:
        sector_name: 섹터명 (예: "반도체", "방산")
        stocks_with_data: [{name, code, price, change_pct, volume}]

    Returns: dict with keys:
        leader_name, leader_code, leader_reason,
        chain_explanation, supply_signal, supply_detail,
        sector_stage, stage_reason,
        followers:[{name, code, reason, timing}],
        historical_pattern, leader_strategy, follower_strategy, risk_factors
    """
    if not stocks_with_data:
        return {"error": "종목 데이터 없음"}

    sorted_stk = sorted(stocks_with_data, key=lambda x: x.get("change_pct", 0), reverse=True)
    stock_lines = "\n".join([
        f"- {s['name']} (코드:{s.get('code','?')})  등락률:{s.get('change_pct',0):+.2f}%  "
        f"현재가:{s.get('price',0):,}원  거래량:{s.get('volume',0):,}주"
        for s in sorted_stk[:20]
    ])

    prompt = f"""당신은 한국 주식시장 세력·테마 전문가입니다.
오늘 [{sector_name}] 섹터의 테마 연동 흐름을 완전 분석해주세요.

[오늘 [{sector_name}] 섹터 종목 현황 — 등락률 내림차순]
{stock_lines}

구글 검색으로 오늘 이 섹터와 관련된 뉴스·공시·수급·외국인/기관 동향을 반드시 확인하고 아래를 분석하세요.

⚠️ [코드 신뢰성 원칙] leader_code와 followers의 code는 위에 제공된 [오늘 섹터 종목 현황] 목록에 있는 코드만 사용하세요.
목록에 없는 코드를 임의로 생성하거나 추측하지 마세요.

1. 대장주: 오늘 이 테마를 이끄는 종목 1개, 이유 (시가총액·모멘텀·뉴스 종합)
2. 밸류체인: 대장주와 추종주들이 왜 같이 오르는지 산업 연결고리 설명
3. 수급·세력: 외국인/기관/큰손의 현재 유입 또는 이탈 신호와 의미
4. 섹터 단계: 지금 이 테마가 [초기 형성 / 확산 / 과열 / 냉각] 중 어느 단계이고 이유
5. 추종주 순서: 대장주 다음에 오를 가능성 높은 종목들을 순위별로 이유와 예상 타이밍 포함
6. 역사적 패턴: 과거 이 섹터 또는 유사 테마가 같은 단계에서 어떻게 전개됐는지
7. 매매 전략: 대장주 접근법 vs 추종주 접근법 각각
8. 리스크: 이 테마가 꺾일 수 있는 핵심 요인

아래 JSON으로만 응답 (설명 없이):
{{
  "leader_name": "대장주 종목명",
  "leader_code": "종목코드 6자리",
  "leader_reason": "대장주인 이유 2~3문장",
  "chain_explanation": "밸류체인·연동 설명 3~4문장",
  "supply_signal": "세력 강하게 유입 | 기관 매집 | 외국인 매집 | 세력 이탈 | 관망",
  "supply_detail": "수급 세부 설명 2~3문장",
  "sector_stage": "초기 형성 | 확산 | 과열 | 냉각",
  "stage_reason": "단계 판단 이유 1~2문장",
  "followers": [
    {{"name": "종목명", "code": "6자리코드", "reason": "추종 이유", "timing": "즉시/1~3일/3일이후"}}
  ],
  "historical_pattern": "역사적 유사 패턴 2~3문장",
  "leader_strategy": "대장주 매매 전략 2문장",
  "follower_strategy": "추종주 매매 전략 2문장",
  "risk_factors": "리스크 요인 1~2문장"
}}"""

    try:
        resp = _call_gemini(prompt, use_search=True, temperature=0.3)
        return _parse_json_response(resp)
    except Exception as e:
        if "QUOTA" in str(e) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return _quota_error_result("analyze_sector_theme_linkage")
        return {"error": _friendly_error(e)}


def analyze_stock_theme_position(
    code: str,
    name: str,
    price_data: dict,
    investor_data: list,
    sector_name: str,
    sector_stocks: list,
) -> dict:
    """개별 종목의 테마 내 포지션 + 수급·세력·차트·역사 종합 분석.

    Args:
        code, name: 종목 코드·이름
        price_data: {price, change_pct, volume, open, high, low, w52_high, w52_low, per, pbr, amount}
        investor_data: [{날짜, 외국인, 기관, 개인}] 최신순
        sector_name: 속한 섹터명
        sector_stocks: [{name, code, price, change_pct}] 섹터 전체 종목

    Returns: dict with position, leader_name, supply_analysis, chart_pattern, etc.
    """
    chg    = price_data.get("change_pct", 0)
    price  = price_data.get("price", 0)
    volume = price_data.get("volume", 0)

    # 섹터 내 순위
    srt = sorted(sector_stocks, key=lambda x: x.get("change_pct", 0), reverse=True)
    rank = next((i + 1 for i, s in enumerate(srt) if s.get("code") == code), "?")
    sector_top = "\n".join([
        f"  {i+1}위. {s['name']} ({s.get('code','')})  {s.get('change_pct',0):+.2f}%"
        for i, s in enumerate(srt[:8])
    ])

    # 수급 요약
    inv_lines = ""
    if investor_data:
        for row in investor_data[:5]:
            inv_lines += (
                f"  {row.get('날짜','')}: "
                f"외국인 {row.get('외국인',0):+,}주  기관 {row.get('기관',0):+,}주  "
                f"개인 {row.get('개인',0):+,}주\n"
            )

    prompt = f"""당신은 한국 주식시장 세력 추적·테마 분석 전문가입니다.
[{name} ({code})]를 [{sector_name}] 테마 관점에서 완전 분석해주세요.

[종목 현황]
현재가: {price:,}원  등락률: {chg:+.2f}%  거래량: {volume:,}주
시가: {price_data.get('open',0):,}  고가: {price_data.get('high',0):,}  저가: {price_data.get('low',0):,}
52주 최고: {price_data.get('w52_high',0):,}  52주 최저: {price_data.get('w52_low',0):,}
PER: {price_data.get('per','-')}  PBR: {price_data.get('pbr','-')}

[{sector_name} 섹터 내 순위 (오늘 등락률 기준)]
이 종목 현재 {rank}위
{sector_top}

[최근 수급 (기관/외국인/개인 순매수량)]
{inv_lines if inv_lines else "  데이터 없음"}

구글 검색으로 오늘 이 종목·섹터 관련 뉴스·공시·수급 흐름을 반드시 확인하고 분석하세요.

분석 항목:
1. 테마 내 포지션: 대장주/선도추종주/후발추종주/소외주 판별 및 이유
2. 세력 분석: 외국인·기관·큰손의 매매 패턴, 의도, 누적 방향
3. 차트 패턴: 현재 기술적 패턴 (돌파/눌림목/과매수/축적/매집 등)
4. 모멘텀 단계: 상승 초기/중반/과열/하락 전환 등 현재 위치
5. 대장주와의 연동: 이 섹터 대장주와 이 종목의 연동성, 후행 여부
6. 역사적 패턴: 이 종목 또는 이 테마 과거 유사 상황에서의 전개 방식
7. 매매 전략: 지금 들어가야 하는가, 최적 타이밍, 목표·손절

아래 JSON으로만 응답:
{{
  "position": "대장주 | 선도추종주 | 후발추종주 | 소외주",
  "position_reason": "포지션 판단 이유 2문장",
  "leader_name": "이 섹터 오늘의 대장주 이름",
  "leader_correlation": "대장주와 연동 관계·후행 여부 설명 2문장",
  "supply_analysis": "수급·세력 분석 3~4문장 (기관/외국인 동향 포함)",
  "force_direction": "강하게 유입 | 분산 매집 | 관망 | 이탈 | 혼조",
  "chart_pattern": "현재 차트 패턴 명칭과 설명",
  "momentum_stage": "돌파 직전 | 상승 초기 | 상승 중반 | 과열 구간 | 조정 중 | 하락 전환 | 바닥 다지기",
  "historical_pattern": "역사적 유사 흐름과 결과 2~3문장",
  "entry_timing": "즉시 진입 | 눌림목 대기 | 돌파 확인 후 | 관망 권고",
  "entry_reason": "진입 타이밍 판단 이유 2문장",
  "buy_target": "매수 타점 (예: 72,500원)",
  "sell_target": "목표가 (예: 78,000원)",
  "stop_loss": "손절가 (예: 70,000원)",
  "risk_factors": "주의사항 1~2문장"
}}"""

    try:
        resp = _call_gemini(prompt, use_search=True, temperature=0.3)
        res = _parse_json_response(resp)
        # [Python Override - 진입 타이밍 조건부]
        try:
            cp = float(price_data.get("price", 0))
            entry_timing = str(res.get("entry_timing", ""))
            _positive = ("즉시 진입", "눌림목 대기", "돌파 확인 후")
            if cp > 0 and any(t in entry_timing for t in _positive):
                res["buy_target"] = f"{int(cp * 0.99):,}원 ~ {int(cp * 1.01):,}원"
                res["sell_target"] = f"{int(cp * 1.06):,}원 (+6%)"
                res["stop_loss"] = f"{int(cp * 0.98):,}원 (-2%)"
            else:
                res["buy_target"] = "관망 (진입 타점 없음)"
                res["sell_target"] = "단타 진입 불가"
                res["stop_loss"] = "단타 진입 불가"
        except Exception:
            pass
        return res
    except Exception as e:
        if "QUOTA" in str(e) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return _quota_error_result("analyze_stock_theme_position")
        return {"error": _friendly_error(e)}


def fetch_rss_news(max_items_per_feed=5):
    """
    주요 언론사 RSS 피드를 통해 최신 경제/매크로 뉴스를 수집합니다.
    """
    try:
        import feedparser
    except ImportError:
        return "feedparser 라이브러리가 설치되지 않았습니다."

    rss_urls = [
        "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml", # WSJ Business
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", # CNBC Finance
        "https://www.mk.co.kr/rss/30100041/", # 매일경제 증권
        "https://www.hankyung.com/feed/finance" # 한국경제 증권
    ]
    
    all_news = []
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items_per_feed]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                # HTML 태그 제거
                summary = re.sub('<[^<]+>', '', summary)
                all_news.append(f"Title: {title}\nSummary: {summary[:200]}")
        except Exception:
            continue
            
    if not all_news:
        return "최신 뉴스를 가져오지 못했습니다."
        
    return "\n\n".join(all_news)


def generate_macro_phase_analysis():
    """
    최신 글로벌/국내 매크로 뉴스를 RAG 방식으로 분석하여
    현재 시장의 Phase와 수혜 섹터를 JSON 형태로 반환합니다.
    """
    news_text = fetch_rss_news()
    
    prompt = f"""
    당신은 월스트리트의 수석 매크로 전략가입니다.
    다음은 방금 RSS 피드를 통해 수집된 전 세계 및 국내 최신 경제/금융 뉴스입니다.
    
    [최신 경제 뉴스 (RAG Context)]
    {news_text}
    
    위 최신 뉴스를 바탕으로 중장기적인 매크로 투자 사이클과 전 섹터의 자금 이동을 분석해주세요.
    반드시 아래 JSON 형식으로만 응답해야 하며, 어떠한 부가 설명도 하지 마세요.
    
    {{
      "macro_phase": "현재 시장 매크로 사이클 진단 (예: AI 인프라 설비투자 급증기)",
      "key_insight": "최신 수집 데이터 기반 핵심 시사점 3줄 요약",
      "bullish_sectors": ["현재 자금이 쏠리는 수혜 섹터1", "섹터2"],
      "action_point": "구체적인 투자 스탠스 (예: Capex 꺾이기 전까지 전력망/장비주 보유 유지)"
    }}
    """
    try:
        response = _call_gemini(prompt, use_search=False, temperature=0.5)
        return _parse_json_response(response)
    except Exception as e:
        if "QUOTA" in str(e) or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return _quota_error_result("generate_macro_phase_analysis")
        return {"error": _friendly_error(e)}


def analyze_sector_rotation(market_type, raw_market_data):
    """
    실시간 시장 데이터(랭킹, 지수 등)를 바탕으로 현재 상황 진단부터 
    다음 섹터 예측, 추천주(단타/중장기 구분), 진입 타이밍까지 종합 분석합니다.
    """
    prompt = f"""
    당신은 세계 최고의 글로벌 퀀트 전략가이자 실전 트레이딩 전문가입니다.
    제공된 실시간 {market_type} 시장 데이터를 바탕으로 '종합 섹터 순환매 로드맵'을 작성하세요.

    [실시간 시장 데이터]
    {raw_market_data}

    [필수 포함 내용 및 작성 규칙]
    1. 🚀 현재 시장 에너지 진단 및 근거
       - 현재 주도 섹터의 상승 동력과 수급 상태를 분석하세요.
    
    2. 🧭 다음 순환매 이동 경로 예측 (바통 터치)
       - 자금이 다음에 어느 섹터로 이동할지 논리적 근거(매크로, 역사적 패턴)와 함께 예측하세요.

    3. 💎 투자 성향별 TOP 추천 종목 (필수 구분)
       - 예측한 섹터 내 유망 종목을 아래 두 가지 카테고리로 나누어 제시하세요.
       
       A. [⚡ 극단타/단기 전략]
          * 초단기 모멘텀이 강한 종목 (당일 ~ 3일 보유)
          * 현재 주가 및 수급 상태 진단
          * **정확한 진입 타점** (예: 현재가 즉시, OO원 눌림목 대기 등)
          * 기대 수익 및 손절가
       
       B. [📈 중장기 투자 전략]
          * 섹터 순환매의 중심이 될 우량주/주도주 (1개월 ~ 6개월 이상)
          * 산업 내 포지션 및 성장 근거
          * **분할 매수 전략** 및 목표가

    4. 📝 수치 표기 규칙 (중요!)
       - 수익률이나 가격 범위 표기 시 반드시 `20% ~ 30%`와 같이 **물결표(~) 양옆에 공백**을 두세요.
       - 절대 `~~20%~~` 처럼 물결표를 붙여 쓰지 마세요 (취소선 방지).
       - 기대 수익률이 1,000%가 넘는 등의 비현실적인 수치는 지양하고 실전적인 목표치를 제시하세요.

    5. 🔗 딥링크 활성화 규칙 (매우 중요!)
       - 추천 종목이나 관련 종목을 언급할 때는 반드시 '종목명(코드)' 형식을 사용하세요.
       - 국내 주식: 삼성전자(005930), 미국 주식: Apple(AAPL)

    제목: '🚀 [종합] {market_type} 시장 자금 흐름 & 차기 주도주 로드맵'
    형식: 마크다운을 활용하여 가독성 있게 작성하세요.
    """
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.7)
        if hasattr(response, 'text'):
            return response.text
        return str(response)
    except Exception as e:
        return f"분석 중 오류 발생: {e}"


def analyze_trade_history(trades: list, past_lessons: list = None) -> dict:
    """매도 완료된 거래 내역을 AI로 분석하여 성공/실패 패턴과 교훈을 추출합니다."""
    if not trades:
        return {"error": "분석할 거래 내역이 없습니다."}

    trade_lines = []
    for t in trades:
        sym = "₩" if (len(str(t.get("ticker", ""))) == 6 and str(t.get("ticker", "")).isdigit()) else "$"
        trade_lines.append(
            f"- {t.get('sell_date','?')} | {t.get('name','?')}({t.get('ticker','?')}) | "
            f"매수 {sym}{float(t.get('buy_price',0)):,.2f} → 매도 {sym}{float(t.get('sell_price',0)):,.2f} | "
            f"수익률 {float(t.get('profit_pct',0)):+.2f}% | 결과: {t.get('result','?')}"
        )
    trades_text = "\n".join(trade_lines)

    past_context = ""
    if past_lessons:
        lessons_text = "\n".join(f"- {l}" for l in past_lessons[-8:] if l)
        past_context = f"\n\n## 이 트레이더의 과거 누적 교훈 (참고하여 반복 패턴 지적)\n{lessons_text}"

    prompt = f"""당신은 20년 경력의 국내외 단타 트레이딩 전문가이자 퀀트 애널리스트입니다.
아래는 실제 매매 완료된 거래 내역입니다. 각 종목에 대해 심층 분석하여 성공/실패 이유와 패턴을 도출하세요.
과거 교훈이 있다면 반복 실수 여부를 반드시 교훈(lesson)에 포함하세요.

## 거래 내역
{trades_text}{past_context}

구글 검색을 활용하여 각 종목의 매도 시점 전후 뉴스, 섹터 흐름, 세력 수급 동향을 파악하고,
반드시 아래 JSON 형식으로만 응답하세요 (마크다운 백틱, 주석 절대 금지):

{{
  "summary": {{
    "total": {len(trades)},
    "win_count": 승리 건수(정수),
    "loss_count": 패배 건수(정수),
    "win_pattern": "공통적인 성공 패턴 요약 (섹터·타이밍·뉴스·수급 등 2~3문장)",
    "loss_pattern": "공통적인 실패 패턴 요약 (섹터·타이밍·뉴스·수급 등 2~3문장)",
    "key_insights": ["핵심 인사이트1", "핵심 인사이트2", "핵심 인사이트3"],
    "future_strategy": "이 분석을 바탕으로 향후 단타 전략에서 반드시 지켜야 할 원칙 3가지"
  }},
  "trades": [
    {{
      "ticker": "종목코드",
      "name": "종목명",
      "result": "승 또는 패",
      "profit_pct": 수익률(숫자),
      "sector": "섹터/테마 (예: 반도체, AI, 바이오, 2차전지 등)",
      "sector_characteristic": "해당 섹터의 당시 시장 특성 및 트렌드",
      "social_factor": "매매 시점 전후 사회적·뉴스·정치·정책 요인",
      "institutional_factor": "세력·외국인·기관 수급 동향",
      "technical_factor": "기술적 분석 관점 (차트패턴, 거래량, 변동성)",
      "success_reason": "성공 이유 (승인 경우, 패면 빈 문자열)",
      "failure_reason": "실패 이유 (패인 경우, 승이면 빈 문자열)",
      "lesson": "이 종목 매매에서 얻어야 할 핵심 교훈 (1~2문장)"
    }}
  ]
}}"""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.4)
        return _parse_json_response(response)
    except Exception as e:
        return {"error": _friendly_error(e), "summary": {}, "trades": []}


def analyze_trading_patterns(records: list) -> dict:
    """누적된 거래분석DB 기록을 바탕으로 트레이딩 패턴을 종합 분석합니다."""
    if not records:
        return {"error": "분석할 누적 거래 데이터가 없습니다."}

    wins = [r for r in records if str(r.get("결과", "")) == "승"]
    losses = [r for r in records if str(r.get("결과", "")) == "패"]
    total = len(records)
    win_rate = round(len(wins) / total * 100, 1) if total > 0 else 0

    record_lines = []
    for r in records:
        pct = r.get("수익률(%)", 0)
        try:
            pct = float(pct)
        except (ValueError, TypeError):
            pct = 0.0
        record_lines.append(
            f"- {r.get('매도일','')} | {r.get('종목명','')}({r.get('티커','')}) | "
            f"수익률 {pct:+.2f}% | {r.get('결과','')} | "
            f"섹터: {r.get('섹터','')} | 교훈: {r.get('교훈','')}"
        )
    records_text = "\n".join(record_lines)

    json_template = (
        "{\n"
        f'  "total": {total},\n'
        f'  "win_count": {len(wins)},\n'
        f'  "loss_count": {len(losses)},\n'
        f'  "win_rate": {win_rate},\n'
        '  "strong_sectors": ["강한 섹터/테마 1", "섹터2"],\n'
        '  "weak_sectors": ["약한 섹터/테마 1", "섹터2"],\n'
        '  "repeated_mistakes": ["반복 실수 패턴 1", "패턴 2", "패턴 3"],\n'
        '  "success_habits": ["성공 시 공통 습관 1", "습관 2"],\n'
        '  "personality_analysis": "이 트레이더의 매매 심리·성향 분석 (3~4문장)",\n'
        '  "improvement_points": ["개선할 점 1", "개선할 점 2", "개선할 점 3"],\n'
        '  "recommended_strategy": "이 데이터 기반으로 이 트레이더에게 최적화된 단타 전략 (3~5문장)"\n'
        "}"
    )

    prompt = (
        f"당신은 20년 경력의 퀀트 트레이더이자 트레이딩 심리 전문가입니다.\n"
        f"아래는 한 트레이더의 누적 매매 분석 데이터입니다 (총 {total}건, 승 {len(wins)}건, "
        f"패 {len(losses)}건, 승률 {win_rate}%).\n\n"
        f"## 누적 거래 분석 기록\n{records_text}\n\n"
        "이 트레이더의 매매 패턴, 반복 실수, 강점을 종합 분석하여 "
        "반드시 아래 JSON 형식으로만 응답하세요 (마크다운 백틱, 주석 절대 금지):\n\n"
        + json_template
    )

    try:
        response = _call_gemini(prompt, use_search=False, temperature=0.4)
        return _parse_json_response(response)
    except Exception as e:
        return {"error": _friendly_error(e)}

