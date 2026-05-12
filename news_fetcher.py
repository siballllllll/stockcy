import requests
from bs4 import BeautifulSoup
import re
import time
import streamlit as st

_TELEGRAM_URLS = {
    "KR": "https://t.me/s/FastStockNews",
    "US": "https://t.me/s/FastStockNewsUSA"
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}

def _fetch_article_body(url: str, timeout: int = 2) -> str:
    """The Link Fetcher: 링크된 기사 원문의 본문을 가볍게 파싱합니다."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return ""
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        # 주로 본문을 담고 있는 p 태그들을 추출하여 결합 (너무 길어지는 것을 방지하기 위해 최대 3000자 제한)
        paragraphs = soup.find_all('p')
        body_text = "\n".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
        
        return body_text[:3000] # 너무 길면 LLM 토큰 낭비 방지
    except Exception:
        # 타임아웃, 봇 차단, 파싱 에러 등은 조용히 무시 (Fallback)
        return ""

@st.cache_data(ttl=120) # 1~2분 주기 캐싱
def get_latest_market_news(market: str = "KR", limit: int = 3) -> list:
    """텔레그램 채널에서 최신 뉴스/찌라시를 가져오고, 기사 원문이 있다면 본문도 함께 스크래핑합니다."""
    url = _TELEGRAM_URLS.get(market.upper(), _TELEGRAM_URLS["KR"])
    
    results = []
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=5)
        if resp.status_code != 200:
            return []
            
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 텔레그램 프리뷰 메시지 블록들
        messages = soup.find_all('div', class_='tgme_widget_message_text')
        
        # 최신 메시지부터 역순으로 탐색
        for msg in reversed(messages):
            if len(results) >= limit:
                break
                
            text_content = msg.get_text(separator="\n", strip=True)
            
            # 텔레그램 메시지 내 a 태그 링크 탐색
            links = msg.find_all('a')
            article_body = ""
            for a in links:
                href = a.get('href', '')
                # 기사 링크로 추정되는 외부 URL (텔레그램 내부 해시태그 등 제외)
                if href.startswith("http") and "t.me" not in href:
                    article_body = _fetch_article_body(href)
                    if article_body:
                        break # 첫 번째 유효한 기사 본문만 가져옴
            
            # 최종 컨텍스트 구성
            combined_news = {
                "headline": text_content,
                "body": article_body if article_body else "본문 스크래핑 불가 (텔레그램 헤드라인 원문 참조)",
                "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            results.append(combined_news)
            
        return results
    except Exception as e:
        print(f"[{market}] News fetcher error: {e}")
        return []
