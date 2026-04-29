from google import genai
from google.genai import types
import streamlit as st
import requests
import urllib3

# SSL 경고 무시 (사용자 네트워크 방화벽 이슈 우회)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_market_news(category="general"):
    """
    Yahoo Finance를 사용하여 최신 시장 뉴스를 가져옵니다. (방화벽 우회 목적)
    """
    import yfinance as yf
    try:
        # SPY(S&P 500 ETF)와 QQQ(나스닥 100 ETF) 뉴스를 통해 전반적인 시장 동향 파악
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
            content = item.get('content', item) # yfinance 반환 구조에 따라 유연하게 대처
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
    """
    Google Search Grounding을 활용하여 구글 실시간 검색을 바탕으로 오늘의 주도 섹터 브리핑을 생성합니다.
    """
    prompt = """
    당신은 월스트리트 최고의 단타 트레이딩 전문가입니다. 
    지금 즉시 구글 검색을 통해 오늘 미국 주식 시장에서 가장 자금이 많이 쏠리고 강력하게 급등하고 있는 '주도 섹터(테마)' 3가지를 정확히 분석해주세요.
    
    반드시 다음 JSON 형식으로만 응답해야 하며, 어떠한 주석(//)이나 부가 설명도 넣지 마세요.
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
        api_key = st.secrets["gemini"]["api_key"]
        client = genai.Client(api_key=api_key)
        
        config = types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="application/json",
            tools=[{"google_search": {}}] # 구글 검색 활성화로 정확도 폭발적 상승
        )
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=config
            )
        except Exception as api_err:
            if "503" in str(api_err) or "UNAVAILABLE" in str(api_err):
                response = client.models.generate_content(
                    model='gemini-2.5-flash-lite',
                    contents=prompt,
                    config=config
                )
            else:
                raise api_err
                
        import json
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

def generate_mindmap_data():
    """
    뉴스 데이터를 바탕으로 토스 증권 스타일의 급등/급락 원인 마인드맵(Mermaid 문법)을 생성합니다.
    """
    news_text = get_market_news("general")
    prompt = f'''
    다음 최신 뉴스를 바탕으로 토스 증권 스타일의 '실시간 급등/급락 테마 마인드맵'을 작성해주세요.
    반드시 Mermaid.js의 graph TD 문법만 응답하세요. (마크다운 백틱이나 다른 설명 절대 제외)
    핵심 시장 이슈가 어떤 섹터와 종목의 등락을 만들고 있는지 원인-결과 형태로 연결해야 합니다.
    
    뉴스 데이터:
    {news_text}
    
    예시:
    graph TD
      A[AI 반도체 수요 폭증] -->|수혜| B(엔비디아 급등)
      A -->|수혜| C(TSMC 상승)
      D[금리 인하 우려] -->|악재| E(비트코인 하락)
    '''
    try:
        api_key = st.secrets["gemini"]["api_key"]
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7)
        )
        # 백틱 제거 처리
        code = response.text.replace('```mermaid', '').replace('```', '').strip()
        return code
    except Exception as e:
        return f"graph TD\n  A[오류 발생] --> B[{str(e)}]"

def generate_stock_report(ticker, current_price, change_pct):
    """
    선택된 주식에 대한 세력 수급 및 타점을 분석하여 JSON 객체로 반환합니다.
    """
    import json
    import re
    
    prompt = f"""
    당신은 월스트리트 최고의 단타 전문 AI 트레이더입니다.
    현재 {ticker}의 주가는 ${current_price} ({change_pct}%) 입니다.
    
    [요청 사항]
    반드시 아래의 JSON 형식으로만 응답하세요. 마크다운이나 다른 텍스트는 절대 포함하지 마세요.
    {{
      "rating": "단타 강력 추천", // 다음 중 하나만 정확히 선택: 단타 강력 추천, 추천, 중간추천, 비추천, 절대 비추천
      "buy_target": "매수가 (구체적인 숫자나 범위)",
      "sell_target": "목표가 (구체적인 숫자)",
      "stop_loss": "손절가 (구체적인 숫자)",
      "analysis": "해당 타점을 설정한 구체적인 기술적/심리적 근거 (상세한 마크다운 텍스트)"
    }}
    """
    
    try:
        api_key = st.secrets["gemini"]["api_key"]
        client = genai.Client(api_key=api_key)
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.7)
            )
        except Exception as api_err:
            if "503" in str(api_err) or "UNAVAILABLE" in str(api_err):
                response = client.models.generate_content(
                    model='gemini-2.5-flash-lite',
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.7)
                )
            else:
                raise api_err
                
        text = response.text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
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
    Google Search Grounding을 활용하여 실시간 인터넷 검색으로 현재 가장 뜨거운 단타 종목을 하나 발굴합니다.
    """
    import json
    import re
    
    prompt = f"""
    당신은 가상의 주식 시뮬레이션 및 트레이딩 교육 전문가입니다. 이 분석은 절대 실제 투자 권유가 아니며 교육적 목적으로만 사용됩니다.
    지금 즉시 구글 검색(Top gainers, Unusual volume, premarket movers 등)을 활용하여 오늘 미국 주식 시장에서 '가장 폭발적인 세력 수급(거래량 급증)'이 들어온 가상 단타 시뮬레이션용 종목 딱 1개만 발굴하세요.
    
    [오늘의 주도 섹터(테마) 참고 자료]:
    {context}
    (위 참고 자료가 있다면 해당 주도 섹터에 속한 종목 중 수급이 터진 종목을 찾고, 없다면 구글 검색으로 직접 찾으세요.)
    
    🔥 [단타 종목 선정 절대 규칙 - 반드시 지킬 것] 🔥
    1. **돌파 초입(Breakout) 종목 타겟팅:** 이미 하루에 20~30% 폭등해서 고점인 종목에 뒤늦게 타는 것은 자살 행위입니다. **이제 막 뉴스 호재가 떴거나, 주요 이동평균선/저항선을 돌파하며 '거래량이 막 터지기 시작한 초입'**에 있는 종목을 발굴하세요.
    2. **대형주 및 중소형주 유연한 선택:** 시가총액이 크더라도(NVDA, TSLA 등) 오늘 확실한 호재와 압도적 수급으로 5% 이상의 변동성이 확정적이라면 추천해도 좋습니다. 단, 별다른 호재 없이 무겁기만 한 상황이라면 가볍게 움직일 수 있는 중소형 대장주를 선택하세요.
    3. **수익 목표치:** 하루에 최소 **5% ~ 10%의 변동성(수익 구간)**이 나올 수 있는 폭발력을 지녀야 합니다.
    4. **세력 수급 파악:** 왜 이 종목에 세력(기관/고래) 자금이 '지금 막' 쏠리기 시작했는지, 차트적 맥점과 구글 뉴스를 분석하세요.
    
    🔥 [타점 설정 절대 규칙] 🔥
    단타 종목을 선정했다면, 반드시 구글 검색을 통해 해당 종목의 **'오늘 현재 실시간 주가(Current Price)'**를 파악하세요.
    현재가를 기준으로 하루 5~10% 수익을 낼 수 있는 현실적인 진입가(Buy Target)와 목표가(Sell Target), 그리고 칼같은 손절가(Stop Loss)를 설정하세요.
    
    반드시 아래의 JSON 형식으로만 응답하세요.
    {{
      "ticker": "티커 (예: SOUN, SMCI, PLTR 등 중소형/변동성 주식)",
      "name_kr": "종목명",
      "buy_target": "현재가 부근의 현실적 매수가",
      "sell_target": "매수가 대비 5~10% 수익 구간의 목표가",
      "stop_loss": "매수가 대비 -2~3% 구간의 칼같은 손절가",
      "reasoning": "선정 이유: 1) 세력 수급(거래량 급증) 근거, 2) 차트/모멘텀 분석, 3) 관련 호재 (마크다운 포맷으로 아주 전문적이고 상세하게 작성)"
    }}
    """
    
    try:
        api_key = st.secrets["gemini"]["api_key"]
        client = genai.Client(api_key=api_key)
        
        config = types.GenerateContentConfig(
            temperature=0.8,
            tools=[{"google_search": {}}] # 구글 검색 접지 활성화
        )
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=config
            )
        except Exception as api_err:
            if "503" in str(api_err) or "UNAVAILABLE" in str(api_err):
                response = client.models.generate_content(
                    model='gemini-2.5-flash-lite',
                    contents=prompt,
                    config=config
                )
            else:
                raise api_err
        
        text = response.text
        if not text:
            return {
                "ticker": "N/A",
                "name_kr": "필터링 차단",
                "reasoning": "AI가 해당 종목의 급등 사유가 정책(Safety)에 위배되거나, 과도한 투자 권유로 판단하여 응답을 거부했습니다. 다시 시도해주세요.",
                "buy_target": "-", "sell_target": "-", "stop_loss": "-"
            }
            
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text)
    except Exception as e:
        return {
            "ticker": "N/A",
            "name_kr": "오류",
            "reasoning": f"종목 발굴 중 오류가 발생했습니다: {e}"
        }
