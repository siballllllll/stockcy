from google import genai
from google.genai import types
import streamlit as st
import requests
import urllib3
import json
import re

# SSL 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_market_news(category="general"):
    import yfinance as yf
    try:
        news_items = []
        try:
            spy_news = yf.Ticker("SPY").news
            if spy_news: news_items.extend(spy_news[:5])
            qqq_news = yf.Ticker("QQQ").news
            if qqq_news: news_items.extend(qqq_news[:5])
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
            if 'link' in item: url = item['link']
            elif 'canonicalUrl' in content: url = content['canonicalUrl'].get('url', '')
            elif 'clickThroughUrl' in content: url = content['clickThroughUrl'].get('url', '')
            
            if headline and url:
                extracted_news.append(f"Headline: {headline}\nSummary: {summary}\nURL: {url}")
                
        if not extracted_news:
            return "최신 뉴스 데이터를 파싱할 수 없습니다."
            
        return "\n\n".join(extracted_news)
    except Exception as e:
        return f"뉴스 데이터 로드 실패: {e}"

def generate_daily_briefing():
    prompt = """
    당신은 월스트리트 최고의 단타 트레이딩 전문가입니다. 
    지금 즉시 구글 검색을 통해 오늘 미국 주식 시장에서 가장 자금이 많이 쏠리고 강력하게 급등하고 있는 '주도 섹터(테마)' 3가지를 정확하게 분석해주세요.
    반드시 아래 JSON 형식으로만 응답해야 하며, 어떠한 주석이나 부가 설명도 하지 마세요.
    {
      "sectors": [
        {
          "keyword": "섹터명 (예: 반도체, 비트코인 등)",
          "is_main": true 또는 false,
          "reason": "해당 섹터가 현재 왜 급등하고 있는지 구글 검색된 최신 뉴스를 바탕으로 심도 있게 분석",
          "reference_news_title": "관련된 실제 최신 뉴스 헤드라인",
          "reference_news_url": "해당 뉴스 실제 원문 URL 링크",
          "related_stocks": [
            {"name_kr": "종목명(한국어)", "ticker": "티커기호"}
          ]
        }
      ]
    }
    """
    try:
        api_key = st.secrets["gemini"]["api_key"]
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="application/json",
            tools=[{"google_search": {}}]
        )
        for attempt in range(2):
            try:
                response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt, config=config)
                break
            except Exception as api_err:
                if attempt == 0: continue
                raise api_err
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

def generate_mindmap_data():
    news_text = get_market_news("general")
    prompt = f'''
    다음 최신 뉴스를 바탕으로 토스 증권 스타일의 '실시간 급등/급락 테마 마인드맵'을 작성해주세요.
    반드시 Mermaid.js의 graph TD 문법만 응답하세요.
    뉴스 데이터:
    {news_text}
    graph TD
      A[원인] --> B(결과)
    '''
    try:
        import time
        api_key = st.secrets["gemini"]["api_key"]
        client = genai.Client(api_key=api_key)
        for attempt in range(2):
            try:
                response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt, config=types.GenerateContentConfig(temperature=0.5))
                break
            except Exception as api_err:
                if attempt == 0:
                    time.sleep(3)
                    continue
                raise api_err
        code = response.text.replace('```mermaid', '').replace('```', '').strip()
        if not code.startswith('graph'): code = 'graph TD\n' + code
        return code
    except Exception as e:
        return f"graph TD\n  A[\"분석 시스템\"] --> B[\"{str(e)[:30]}\"]"

def generate_stock_report(ticker, current_price, change_pct):
    prompt = f"현재 {ticker} 주가 ${current_price} ({change_pct}%) 분석 리포트를 JSON으로 작성해."
    try:
        api_key = st.secrets["gemini"]["api_key"]
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt, config=types.GenerateContentConfig(temperature=0.7))
        text = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}

def discover_hot_day_trading_stock(context=""):
    prompt = f"오늘 급등주 발굴해줘. {context}"
    try:
        api_key = st.secrets["gemini"]["api_key"]
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(temperature=0.8, tools=[{"google_search": {}}])
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt, config=config)
        text = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}

@st.cache_data(ttl=600)
def generate_dynamic_themes():
    prompt = "오늘 핫한 테마 5개 JSON으로 알려줘."
    try:
        api_key = st.secrets["gemini"]["api_key"]
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(temperature=0.7, tools=[{"google_search": {}}])
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt, config=config)
        text = re.sub(r'```(?:json)?', '', response.text).strip()
        start = text.find('{')
        if start != -1:
            result, _ = json.JSONDecoder().raw_decode(text, start)
            return result
        return json.loads(text)
    except Exception as e:
        return {"error": str(e), "themes": []}
