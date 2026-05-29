from google import genai
from google.genai import types
import streamlit as st
import requests
import os
import urllib3
import json
import re
import time
import threading

# SSL 경고 무시 (방화벽 우회)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 핫 섹터 모듈 레벨 캐시 (Streamlit 락 우회용) ─────────────────────────────
# asyncio.wait_for로 @st.cache_data 함수를 캔슬했을 때 락이 남아
# 다음 요청 스레드가 무기한 대기하는 문제를 방지한다.
_HS_CACHE_LOCK = threading.Lock()
_HS_CACHE_DATA: dict | None = None
_HS_CACHE_TS: float = 0.0
_HS_CACHE_TTL = 3600  # 1시간


def get_hot_sectors_nowait() -> dict | None:
    """캐시된 핫 섹터를 즉시(락 없이) 반환. 캐시 미스·만료 시 None."""
    if _HS_CACHE_DATA and (time.time() - _HS_CACHE_TS) < _HS_CACHE_TTL:
        return _HS_CACHE_DATA
    return None


def _update_hs_cache(result: dict):
    global _HS_CACHE_DATA, _HS_CACHE_TS
    if isinstance(result, dict) and "sectors" in result:
        with _HS_CACHE_LOCK:
            _HS_CACHE_DATA = result
            _HS_CACHE_TS = time.time()


def _fix_kr_stock_names(stocks: list) -> list:
    """AI가 생성한 한국 종목 name을 실제 KRX 코드→이름 맵으로 교정.
    KRX에 없는 코드(AI 허구)는 목록에서 제거."""
    try:
        from data_kr import get_kr_code_to_name_map
        code_map = get_kr_code_to_name_map()
    except Exception:
        return stocks
    remove_idx = []
    for i, s in enumerate(stocks):
        tk = str(s.get("ticker", "")).strip()
        if tk.isdigit() and len(tk) == 6:
            if tk in code_map:
                s["name"] = code_map[tk]   # 이름 교정
            else:
                remove_idx.append(i)        # 실재하지 않는 코드 → 제거
    for i in reversed(remove_idx):
        stocks.pop(i)
    return stocks


def _fix_scenario_names(res: dict) -> dict:
    """시나리오 결과 전체의 한국 종목명 교정."""
    for issue in res.get("issues", [res]):  # issues 리스트 OR 단일 dict
        for sc in issue.get("scenarios", []):
            _fix_kr_stock_names(sc.get("rising_stocks", []))
            _fix_kr_stock_names(sc.get("falling_stocks", []))
            _fix_kr_stock_names(sc.get("theme_stocks", []))
    return res


def _override_targets(res: dict) -> dict:
    """시나리오 종목에 현재가 기반 매수타점/목표가/손절선 덮어쓰기."""
    def _is_kr(tk):
        return str(tk).strip().isdigit() and len(str(tk).strip()) == 6

    # 1. 시나리오 내부의 모든 티커 수집
    tickers = set()
    for issue in res.get("issues", [res]):
        for sc in issue.get("scenarios", []):
            for group in ["rising_stocks", "falling_stocks", "theme_stocks"]:
                for s in sc.get(group, []):
                    tk = str(s.get("ticker", "")).strip()
                    if tk:
                        tickers.add(tk)

    # 2. 티커 분류 및 가격 일괄 조회
    price_map = {}
    if tickers:
        kr_tickers = [tk for tk in tickers if _is_kr(tk)]
        us_tickers = [tk for tk in tickers if not _is_kr(tk)]
        
        # 2.1 미국 주식 배치 조회 (yfinance + KIS API 하이브리드)
        if us_tickers:
            try:
                import yfinance as yf
                data = yf.download(us_tickers, period="2d", interval="1d", progress=False, auto_adjust=True, timeout=1.5)
                if not data.empty:
                    close_df = data["Close"]
                    for tk in us_tickers:
                        try:
                            if len(us_tickers) == 1:
                                closes = close_df.dropna()
                            else:
                                closes = close_df[tk].dropna()
                            if not closes.empty:
                                price_map[tk] = round(float(closes.iloc[-1]), 2)
                        except Exception:
                            pass
            except Exception as e:
                print(f"[Override Targets] US yfinance batch failed: {e}")

            # yfinance 실패했거나 누락된 미국 티커에 대한 KIS API 고속 폴백
            from data_kr import get_us_stock_price_kis
            for tk in us_tickers:
                if tk not in price_map or price_map[tk] <= 0:
                    for exch in ["NASDAQ", "NYSE", "AMEX"]:
                        try:
                            kis_res = get_us_stock_price_kis(tk, exch)
                            if kis_res and kis_res.get("price", 0) > 0:
                                price_map[tk] = float(kis_res["price"])
                                break
                        except Exception:
                            pass

        # 2.2 국내 주식 배치 조회 (KIS API 우선 후 yfinance 폴백)
        if kr_tickers:
            from data_kr import get_kr_stock_price
            missing_kr = []
            for tk in kr_tickers:
                try:
                    d = get_kr_stock_price(tk)
                    price = float((d or {}).get("price", 0) or 0)
                    if price > 0:
                        price_map[tk] = price
                    else:
                        missing_kr.append(tk)
                except Exception:
                    missing_kr.append(tk)
            
            # KIS 조회에 실패한 한국 티커들은 yfinance 배치로 일괄 회수
            if missing_kr:
                try:
                    import yfinance as yf
                    yf_kr_tickers = []
                    for tk in missing_kr:
                        yf_kr_tickers.append(tk + ".KS")
                        yf_kr_tickers.append(tk + ".KQ")
                    
                    data = yf.download(yf_kr_tickers, period="2d", interval="1d", progress=False, auto_adjust=True, timeout=1.5)
                    if not data.empty:
                        close_df = data["Close"]
                        for tk in missing_kr:
                            price = 0.0
                            for suffix in [".KS", ".KQ"]:
                                try:
                                    full_tk = tk + suffix
                                    if len(yf_kr_tickers) == 1:
                                        closes = close_df.dropna()
                                    else:
                                        closes = close_df[full_tk].dropna()
                                    if not closes.empty:
                                        price = float(closes.iloc[-1])
                                        break
                                except Exception:
                                    pass
                            if price > 0:
                                price_map[tk] = price
                except Exception as e:
                    print(f"[Override Targets] KR yfinance batch failed: {e}")

    # 3. O(1) 매핑을 통한 가격 덮어쓰기 및 타점 산정
    def _process_group(stocks: list):
        for s in stocks:
            tk = str(s.get("ticker", "")).strip()
            if not tk:
                continue
            is_kr = _is_kr(tk)
            cp = price_map.get(tk, 0.0)
            rating = str(s.get("signal", ""))
            
            if cp > 0:
                if rating in ("추천", "매우 강력 추천"):
                    try:
                        gain = float(str(s.get("expected_gain_pct", "6.0")).strip().replace("%", "").replace("+", ""))
                    except Exception:
                        gain = 6.0
                    try:
                        loss = float(str(s.get("expected_loss_pct", "-2.0")).strip().replace("%", ""))
                        if loss > 0: loss = -loss
                    except Exception:
                        loss = -2.0

                    if is_kr:
                        s["buy_target"]  = f"{int(cp * 0.97):,}원 ~ {int(cp * 1.00):,}원 (현재가 대비 1~3% 분할 눌림목 매수 대기)"
                        s["sell_target"] = f"{int(cp * (1 + gain / 100)):,}원 (+{gain:.1f}%)"
                        s["stop_loss"]   = f"{int(cp * (1 + loss / 100)):,}원 ({loss:.1f}%)"
                    else:
                        s["buy_target"]  = f"${cp * 0.97:.2f} ~ ${cp * 1.00:.2f} (1~3% 분할 눌림목 매수 대기)"
                        s["sell_target"] = f"${cp * (1 + gain / 100):.2f} (+{gain:.1f}%)"
                        s["stop_loss"]   = f"${cp * (1 + loss / 100):.2f} ({loss:.1f}%)"
                else:
                    s["buy_target"]  = "관망 (진입 타점 없음)"
                    s["sell_target"] = "관망"
                    s["stop_loss"]   = "관망"
            else:
                # 가격 조회 실패
                if rating in ("추천", "매우 강력 추천"):
                    s["buy_target"]  = "시세 조회 중 (잠시 후 새로고침)"
                    s["sell_target"] = "시세 조회 중"
                    s["stop_loss"]   = "시세 조회 중"
                else:
                    s["buy_target"]  = "관망 (진입 타점 없음)"
                    s["sell_target"] = "관망"
                    s["stop_loss"]   = "관망"

    for issue in res.get("issues", [res]):
        for sc in issue.get("scenarios", []):
            _process_group(sc.get("rising_stocks", []))
            _process_group(sc.get("falling_stocks", []))
            _process_group(sc.get("theme_stocks", []))
            
    return res


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
    "gemini-1.5-flash",
]

# 할당량 소진 여부 (세션 중 반복 호출 방지)
_QUOTA_EXHAUSTED = False

# API 호출 타임아웃 (초)
_API_TIMEOUT_SEC = 90


def _strip_hanja(text: str) -> str:
    """AI 출력에서 CJK 한자를 제거합니다. 자주 나오는 析(석), 分(분) 등 포함."""
    # 자주 등장하는 한자 → 한글 치환 (문맥상 분석, 분기 등)
    _MAP = {
        "析": "석",  # 분析 → 분석
        "分": "분",  # 分析 → 분析 (이미 앞에서 처리되어 잔여 제거)
        "報": "보",
        "株": "주",
        "場": "장",
        "高": "고",
        "低": "저",
        "買": "매",
        "賣": "매",
        "益": "익",
        "損": "손",
    }
    for hanja, hangul in _MAP.items():
        text = text.replace(hanja, hangul)
    # 나머지 CJK 통합 한자 전체 제거 (U+4E00~U+9FFF)
    text = re.sub(r'[一-鿿]', '', text)
    return text


def _clean_ai_json(raw: str) -> str:
    """AI 응답 텍스트에서 JSON을 추출 가능한 형태로 정제합니다."""
    # 한자 제거 (먼저 처리)
    text = _strip_hanja(raw)
    # BOM 제거
    text = text.lstrip('﻿').strip()
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

    api_key = os.getenv("GEMINI_API_KEY", "")
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

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
                ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = ex.submit(_do_call, model, config)
                try:
                    response = future.result(timeout=_timeout)
                except concurrent.futures.TimeoutError:
                    ex.shutdown(wait=False)  # 블로킹 없이 즉시 해제
                    raise Exception(f"API_TIMEOUT: AI 응답 대기 시간({_timeout}초)을 초과했습니다. 잠시 후 다시 시도해주세요.")
                ex.shutdown(wait=False)

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

                # 모델 없음 혹은 그라운딩 v1beta 모델 404 오류 → 검색 없이 순수 AI 즉시 재시도
                if ("404" in err_str or "NOT_FOUND" in err_str) and use_search:
                    print(f"[AI] 모델 404 감지 (그라운딩 v1beta 호환성 우려) → 검색 없이 즉시 우회 재시도합니다. 모델: {model}")
                    config_no_search = types.GenerateContentConfig(temperature=temperature)
                    if response_mime_type:
                        config_no_search.response_mime_type = response_mime_type
                    try:
                        ex2 = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                        future2 = ex2.submit(_do_call, model, config_no_search)
                        try:
                            response = future2.result(timeout=_timeout)
                        finally:
                            ex2.shutdown(wait=False)
                        return response
                    except Exception as fallback_err:
                        print(f"Fallback without search for 404 also failed: {fallback_err}")

                # 순수 404 오류이거나 검색이 이미 꺼져있었을 때만 다음 모델로 폴백
                if "404" in err_str or "NOT_FOUND" in err_str:
                    print(f"[AI] 모델 {model} 사용 불가 (404), 다음 모델로 폴백. 에러: {err_str[:120]}")
                    break

                # Google Search 권한 오류 (403) → 검색 없이 재시도
                if "403" in err_str and use_search:
                    config_no_search = types.GenerateContentConfig(temperature=temperature)
                    if response_mime_type:
                        config_no_search.response_mime_type = response_mime_type
                    try:
                        ex2 = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                        future2 = ex2.submit(_do_call, model, config_no_search)
                        try:
                            response = future2.result(timeout=_timeout)
                        finally:
                            ex2.shutdown(wait=False)
                        return response
                    except Exception as fallback_err:
                        print(f"Fallback without search also failed: {fallback_err}")
                        break

                raise api_err

    raise last_err


def _fetch_target_news(query: str, limit: int = 4) -> str:
    """구글 뉴스 RSS를 활용해 특정 키워드에 대한 최신 뉴스 헤드라인과 요약을 초고속(0.5초 이내) 수집합니다."""
    import urllib.parse
    import xml.etree.ElementTree as ET
    import requests
    import re

    if not query or not query.strip():
        return ""

    try:
        # 구글 뉴스 RSS 검색 API 호출 (hl=ko, gl=KR)
        encoded_query = urllib.parse.quote(query.strip())
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        }
        
        # 2.5초 내로 타임아웃 주어 딜레이 최소화
        resp = requests.get(url, headers=headers, timeout=2.5)
        if resp.status_code != 200:
            return ""
            
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        
        news_list = []
        for idx, item in enumerate(items[:limit]):
            title_el = item.find("title")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")
            
            title = title_el.text if title_el is not None else ""
            desc = desc_el.text if desc_el is not None else ""
            pub_date = pub_el.text if pub_el is not None else ""
            
            # HTML 태그 제거 (구글 뉴스 RSS description에는 간혹 html이 섞여 있음)
            desc_clean = re.sub(r'<[^>]*>', '', desc).strip()
            
            # 너무 긴 설명 축소
            if len(desc_clean) > 200:
                desc_clean = desc_clean[:200] + "..."
                
            news_list.append(f"[{idx+1}] {title}\n    - 요약: {desc_clean}\n    - 보도일시: {pub_date}")
            
        if not news_list:
            return "최근 24시간 동안 관련된 특정 뉴스 팩트가 조회되지 않았습니다."
            
        return "\n\n".join(news_list)
        
    except Exception as e:
        print(f"[RAG 뉴스 검색 오류] {e}")
        return ""


def _fetch_target_news_us(query: str, limit: int = 5) -> str:
    """구글 뉴스 RSS를 활용해 미국 주식(영문) 특정 키워드에 대한 최신 뉴스 헤드라인과 요약을 초고속(0.5초 이내) 수집합니다."""
    import urllib.parse
    import xml.etree.ElementTree as ET
    import requests
    import re

    if not query or not query.strip():
        return ""

    try:
        # 구글 뉴스 RSS 미국(영어) 검색 API 호출
        encoded_query = urllib.parse.quote(query.strip())
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en&gl=US&ceid=US:en"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        }
        
        resp = requests.get(url, headers=headers, timeout=2.5)
        if resp.status_code != 200:
            return ""
            
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        
        news_list = []
        for idx, item in enumerate(items[:limit]):
            title_el = item.find("title")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")
            
            title = title_el.text if title_el is not None else ""
            desc = desc_el.text if desc_el is not None else ""
            pub_date = pub_el.text if pub_el is not None else ""
            
            desc_clean = re.sub(r'<[^>]*>', '', desc).strip()
            if len(desc_clean) > 200:
                desc_clean = desc_clean[:200] + "..."
                
            news_list.append(f"[{idx+1}] {title}\n    - Summary: {desc_clean}\n    - Published: {pub_date}")
            
        if not news_list:
            return "No recent target news found for the US market query."
            
        return "\n\n".join(news_list)
        
    except Exception as e:
        print(f"[RAG US 뉴스 검색 오류] {e}")
        return ""


def generate_daily_briefing():
    """
    Google Search Grounding을 사용해 오늘 주도 섹터 브리핑을 생성합니다.
    """
    prompt = """
    당신은 월스트리트 최고의 단타 트레이딩 전문가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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
        "당신은 월스트리트 20년 경력의 매크로 전략가이자 퀀트 트레이더입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.\n"
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
        '            {"name": "종목명", "ticker": "국내=6자리숫자코드/미국=심볼", "reason": "이유", "valuation_note": "PER 코멘트", "signal": "매우 강력 추천/추천/중간추천/비추천/매우 비추천", "signal_reason": "현재 매수 관점 한 줄 요약", "expected_gain_pct": "호재/모멘텀 크기에 따른 합리적 단기 목표 상승률 (% 기호 없이, 예: 8.0)", "expected_loss_pct": "합리적 손절 기준율 (음수, 예: -3.0)"}\n'
        "          ],\n"
        '          "falling_stocks": [\n'
        '            {"name": "종목명", "ticker": "국내=6자리숫자코드/미국=심볼", "reason": "이유", "valuation_note": "PER 코멘트", "signal": "매우 강력 추천/추천/중간추천/비추천/매우 비추천", "signal_reason": "현재 매수 관점 한 줄 요약", "expected_gain_pct": "기대 변동률 (% 기호 없이, 예: -12.0)", "expected_loss_pct": "손절 기준율 (예: 5.0)"}\n'
        "          ],\n"
        '          "theme_stocks": [\n'
        '            {"name": "종목명", "ticker": "KOSPI/KOSDAQ 6자리숫자코드", "type": "직접관련주 또는 간접테마주", "historical_pattern": "과거 유사 이슈 때 이 종목이 어떻게 움직였는지 (1문장)", "reason": "이번에 연동 상승이 예상되는 이유 + 시총 규모 간략 언급", "signal": "매우 강력 추천/추천/중간추천/비추천/매우 비추천", "signal_reason": "현재 매수 관점 한 줄 요약", "expected_gain_pct": "테마 연동 기대 상승률 (% 기호 없이, 예: 12.0)", "expected_loss_pct": "손절 기준율 (음수, 예: -4.0)"}\n'
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
        res = _parse_json_response(response)
        _fix_scenario_names(res)
        _override_targets(res)
        return res
    except Exception as e:
        return {"error": _friendly_error(e), "issues": []}


@st.cache_data(ttl=300)
def analyze_custom_issue(keyword: str) -> dict:
    """사용자 지정 이슈 키워드에 대한 A/B 시나리오 분석 + Python Override."""
    prompt = (
        f"당신은 월스트리트 20년 경력의 매크로 전략가이자 퀀트 트레이더입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.\n"
        f"사용자가 지정한 이슈 키워드: [{keyword}]\n\n"
        "구글 검색으로 이 이슈의 최신 현황을 파악한 후, A(낙관)·B(비관) 두 가지 시나리오를 작성하세요.\n\n"
        "⚠️ [종목 신뢰성 원칙 — 최우선 적용]\n"
        "모든 종목은 구글 검색으로 반드시 검증하세요:\n"
        "- 국내 ticker: KOSPI/KOSDAQ 6자리 숫자 코드 (예: 005930)\n"
        "- 미국 ticker: NYSE/NASDAQ 심볼 (예: NVDA)\n"
        "검증 안 된 종목 절대 금지. 거래정지·폐지 종목도 제외.\n\n"
        "theme_stocks는 단타·스윙에 유리한 국내 중소형주(시총 1조 미만 코스닥 우선) 3~5개.\n"
        "rising_stocks·falling_stocks에 이미 있는 종목, 시총 10조↑ 대형주는 제외.\n\n"
        "반드시 아래 JSON 형식으로만 응답 (백틱·주석 절대 금지):\n\n"
        "{\n"
        '  "title": "이슈 제목",\n'
        '  "summary": "현황 요약 (1~2문장)",\n'
        '  "scenarios": [\n'
        "    {\n"
        '      "label": "A",\n'
        '      "title": "시나리오 제목",\n'
        '      "probability_pct": 60,\n'
        '      "market_direction": "강세/약세/혼조",\n'
        '      "trigger": "현실화 조건 (1문장)",\n'
        '      "economic_analysis": "경제적 영향, PER·금리·수급 포함 (2~3문장)",\n'
        '      "rising_stocks": [\n'
        '        {"name": "종목명", "ticker": "코드", "reason": "이유", "valuation_note": "PER 코멘트", "signal": "매우 강력 추천/추천/중간추천/비추천/매우 비추천", "signal_reason": "현재 매수 관점 한 줄"}\n'
        "      ],\n"
        '      "falling_stocks": [\n'
        '        {"name": "종목명", "ticker": "코드", "reason": "이유", "valuation_note": "", "signal": "매우 강력 추천/추천/중간추천/비추천/매우 비추천", "signal_reason": "한 줄"}\n'
        "      ],\n"
        '      "theme_stocks": [\n'
        '        {"name": "종목명", "ticker": "6자리코드", "type": "직접관련주 또는 간접테마주", "historical_pattern": "과거 유사 이슈 때 움직임 (1문장)", "reason": "이번 연동 이유", "signal": "매우 강력 추천/추천/중간추천/비추천/매우 비추천", "signal_reason": "한 줄"}\n'
        "      ],\n"
        '      "short_strategy": "단타 전략: 진입 타이밍·청산 조건 (1~2문장)",\n'
        '      "long_strategy": "장타 전략: 포지션 방향·보유 기간 (1~2문장)"\n'
        "    },\n"
        "    {\n"
        '      "label": "B",\n'
        '      "title": "시나리오 제목",\n'
        '      "probability_pct": 40,\n'
        '      "market_direction": "강세/약세/혼조",\n'
        '      "trigger": "현실화 조건 (1문장)",\n'
        '      "economic_analysis": "경제적 영향 (2~3문장)",\n'
        '      "rising_stocks": [],\n'
        '      "falling_stocks": [],\n'
        '      "theme_stocks": [],\n'
        '      "short_strategy": "단타 전략",\n'
        '      "long_strategy": "장타 전략"\n'
        "    }\n"
        "  ]\n"
        "}"
    )
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.6, timeout_sec=120)
        res = _parse_json_response(response)

        _fix_scenario_names(res)
        _override_targets(res)
        return res
    except Exception as e:
        return {"error": _friendly_error(e), "title": keyword, "scenarios": []}


def generate_scenario_detail(issue_title: str, scenario_title: str, economic_analysis: str,
                              rising: list, falling: list) -> dict:
    """특정 시나리오의 상세 심층 분석을 생성합니다."""
    import re
    
    # ── [RAG] 이슈에 맞는 최신 뉴스 팩트 동적 수집 ───────────────────────────
    # 시나리오 타이틀에서 수식어(예: "시나리오 A: ") 제거
    sc_clean = re.sub(r'^시나리오\s+[A-Z]:\s*', '', scenario_title)
    search_query = f"{issue_title} {sc_clean}"
    # 특수문자 제거 및 공백 정규화
    search_query = re.sub(r'[\[\](){}:,.]', ' ', search_query)
    # 단어 조인 (너무 길지 않게 최대 3단어로 쿼리 구성)
    keywords = [w for w in search_query.split() if len(w) >= 2]
    final_query = " ".join(keywords[:3])
    
    # 구글 뉴스 RSS 기반으로 4개 수집
    news_txt = _fetch_target_news(final_query, limit=4)
    if not news_txt or "조회되지 않았습니다" in news_txt:
        # Fallback: 개별 키워드가 너무 길어 조회가 안 되었을 때를 대비해 이슈 타이틀 단독으로 재조회
        fallback_query = " ".join([w for w in re.sub(r'[\[\](){}:,.]', ' ', issue_title).split() if len(w) >= 2][:2])
        news_txt = _fetch_target_news(fallback_query, limit=3)
        
    rising_txt = ", ".join(f"{s.get('name','?')}({s.get('ticker','?')})" for s in rising)
    falling_txt = ", ".join(f"{s.get('name','?')}({s.get('ticker','?')})" for s in falling)
    
    prompt = (
        f"당신은 월스트리트 20년 경력의 매크로 전략가이자 퀀트 트레이더입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.\n"
        f"아래 시나리오에 대한 심층 상세 분석을 제공하세요.\n\n"
        f"## 이슈: {issue_title}\n"
        f"## 시나리오: {scenario_title}\n"
        f"## 기본 분석: {economic_analysis}\n"
        f"## 상승 후보: {rising_txt}\n"
        f"## 하락 후보: {falling_txt}\n\n"
        f"## [현재 시나리오 관련 최신 뉴스 팩트 (실시간 RAG)]:\n"
        f"{news_txt}\n\n"
        "⚠️ [가격 신뢰성 원칙] short_detail.stocks의 entry_point, target, stop은 구글 검색으로 각 종목의 실제 현재가를 확인한 뒤, "
        "그 가격에 기반한 합리적인 수준으로 설정하세요. 현재가와 동떨어진(±50% 이상 차이나는) 가격은 절대 제시하지 마세요.\n\n"
        "제공된 실시간 뉴스 팩트 및 최신 정보를 바탕으로 분석하되 아래 JSON 형식으로만 응답하세요 (백틱, 주석 금지):\n\n"
        "{\n"
        '  "deep_analysis": "심층 경제·시장 분석 (4~5문장, PER·금리·수급·섹터 로테이션 포함)",\n'
        '  "historical_precedent": "유사한 역사적 사례와 당시 시장 반응 (2~3문장)",\n'
        '  "key_risks": ["주요 리스크 1", "주요 리스크 2", "주요 리스크 3"],\n'
        '  "short_detail": {\n'
        '    "entry": "단타 진입 조건·가격대",\n'
        '    "exit": "청산 조건·목표가·손절선",\n'
        '    "timing": "최적 진입 타이밍 (장 초반/중반/후반)",\n'
        '    "stocks": [\n'
        '      {"name": "종목명", "ticker": "티커", "entry_point": "진입가 기준", "expected_gain_pct": "해당 종목의 당일 호재 강도·모멘텀에 따른 단기 기대 수익률 (% 기호 없이 정수/실수만, 예: 8.5 또는 15.0)", "expected_loss_pct": "단기 감내 리스크 비율 (음수, 예: -3.0)", "note": "추가 코멘트"}\n'
        "    ]\n"
        "  },\n"
        '  "long_detail": {\n'
        '    "thesis": "장타 투자 근거 (2~3문장)",\n'
        '    "hold_period": "예상 보유 기간",\n'
        '    "position_sizing": "포지션 비중 권고 (예: 포트폴리오의 X%)  ",\n'
        '    "stocks": [\n'
        '      {"name": "종목명", "ticker": "티커", "reason": "장기 보유 이유", "catalyst": "주요 촉매 이벤트", "entry_point": "장기 분할매수 타점", "expected_gain_pct": "해당 종목의 장기 성장성/비즈니스 모델 분석에 따른 중장기 목표 기대 수익률 (% 기호 없이 정수/실수만, 예: 45.0 또는 120.0)", "expected_loss_pct": "장기 투자 감내 리스크 비율 (음수, 예: -15.0)", "hold_period": "권장 보유 기간 (예: 6개월~1년)"}\n'
        "    ]\n"
        "  }\n"
        "}"
    )
    try:
        response = _call_gemini(prompt, use_search=False, temperature=0.5, timeout_sec=45)
        res = _parse_json_response(response)
        # [Python Override - 실시간 현재가 기반 단타 & 장타 타점 교정]
        try:
            short_stocks = res.get("short_detail", {}).get("stocks", [])
            long_stocks = res.get("long_detail", {}).get("stocks", [])
            all_detail_stocks = short_stocks + long_stocks
            
            if all_detail_stocks:
                tickers = [s.get("ticker", "") for s in all_detail_stocks if s.get("ticker")]
                if tickers:
                    price_map = {}
                    us_tickers = [t for t in tickers if not str(t).isdigit()]
                    kr_tickers = [t for t in tickers if str(t).isdigit()]
                    
                    if us_tickers:
                        try:
                            from data import get_us_stock_data
                            df_prices = get_us_stock_data(us_tickers)
                            if not df_prices.empty:
                                for _, row in df_prices.iterrows():
                                    price_map[row["심볼"]] = float(row["현재가($)"])
                        except Exception:
                            pass
                            
                    if kr_tickers:
                        try:
                            from data_kr import get_kr_stock_price
                            for t in kr_tickers:
                                kr_data = get_kr_stock_price(t)
                                if kr_data and kr_data.get("price", 0) > 0:
                                    price_map[t] = float(kr_data["price"])
                        except Exception:
                            pass

                    # 1. 단타 타점 교정 (현재가 기준 AI 예측 기대 수익률/손절률 반영)
                    for s in short_stocks:
                        tk = s.get("ticker", "")
                        cp = price_map.get(tk, 0)
                        if cp > 0:
                            is_kr = str(tk).isdigit()
                            curr_sym = "₩" if is_kr else "$"
                            
                            # AI 예측 단기 목표 수익률 파싱 (Fallback: +6%)
                            try:
                                gain = float(str(s.get("expected_gain_pct", "6.0")).strip().replace("%", "").replace("+", ""))
                            except Exception:
                                gain = 6.0
                            # AI 예측 단기 손절 리스크 파싱 (Fallback: -2%)
                            try:
                                loss = float(str(s.get("expected_loss_pct", "-2.0")).strip().replace("%", ""))
                                if loss > 0: loss = -loss # 양수로 오면 음수로 교정
                            except Exception:
                                loss = -2.0
                            
                            if is_kr:
                                s["entry_point"] = f"{curr_sym}{int(cp * 0.97):,} ~ {curr_sym}{int(cp):,} (현재가 대비 1~3% 분할 눌림목 매수)"
                                s["target"] = f"{curr_sym}{int(cp * (1 + gain / 100)):,} (+{gain:.1f}%)"
                                s["stop"] = f"{curr_sym}{int(cp * (1 + loss / 100)):,} ({loss:.1f}%)"
                            else:
                                s["entry_point"] = f"{curr_sym}{cp * 0.97:.2f} ~ {curr_sym}{cp:.2f} (1~3% 눌림목 매수)"
                                s["target"] = f"{curr_sym}{cp * (1 + gain / 100):.2f} (+{gain:.1f}%)"
                                s["stop"] = f"{curr_sym}{cp * (1 + loss / 100):.2f} ({loss:.1f}%)"
                        else:
                            s["entry_point"] = "시세 조회 실패"
                            s["target"] = "시세 조회 실패"
                            s["stop"] = "시세 조회 실패"

                    # 2. 장타 타점 교정 (현재가 기준 AI 예측 기대 수익률/손절률 반영)
                    for s in long_stocks:
                        tk = s.get("ticker", "")
                        cp = price_map.get(tk, 0)
                        if cp > 0:
                            is_kr = str(tk).isdigit()
                            curr_sym = "₩" if is_kr else "$"
                            
                            # AI 예측 장기 목표 수익률 파싱 (Fallback: +30%)
                            try:
                                gain = float(str(s.get("expected_gain_pct", "30.0")).strip().replace("%", "").replace("+", ""))
                            except Exception:
                                gain = 30.0
                            # AI 예측 장기 손절 리스크 파싱 (Fallback: -15%)
                            try:
                                loss = float(str(s.get("expected_loss_pct", "-15.0")).strip().replace("%", ""))
                                if loss > 0: loss = -loss # 양수로 오면 음수로 교정
                            except Exception:
                                loss = -15.0
                            
                            if is_kr:
                                s["entry_point"] = f"{curr_sym}{int(cp * 0.95):,} ~ {curr_sym}{int(cp * 1.02):,}원"
                                s["target"] = f"{curr_sym}{int(cp * (1 + gain / 100)):,}원 (+{gain:.1f}%)"
                                s["stop"] = f"{curr_sym}{int(cp * (1 + loss / 100)):,}원 ({loss:.1f}%)"
                            else:
                                s["entry_point"] = f"{curr_sym}{cp * 0.95:.2f} ~ {curr_sym}{cp * 1.02:.2f}"
                                s["target"] = f"{curr_sym}{cp * (1 + gain / 100):.2f} (+{gain:.1f}%)"
                                s["stop"] = f"{curr_sym}{cp * (1 + loss / 100):.2f} ({loss:.1f}%)"
                            if not s.get("hold_period"):
                                s["hold_period"] = "6개월 ~ 1년"
                        else:
                            s["entry_point"] = "시세 조회 실패"
                            s["target"] = "시세 조회 실패"
                            s["stop"] = "시세 조회 실패"
                            if not s.get("hold_period"):
                                s["hold_period"] = "-"
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
def analyze_autonomous_trading(ticker: str, name: str, current_price: float, market: str, position: str, avg_price: float) -> dict:
    """AI 자율 매매 에이전트를 위한 매수/매도/홀딩 판단 함수.
    position: "NONE" (미보유) 또는 "HOLDING" (보유중)
    """
    try:
        from db import load_ai_cache, save_ai_cache
        
        # [초정밀 비용 세이브 락] 1차 캐시 확인 (NONE 종목은 4시간, HOLDING 종목은 30분 유효)
        # 가격 버킷: 현재가를 2% 단위로 반올림하여 캐시 키에 포함 → 가격 크게 변동 시 캐시 무효화
        price_bucket = round(current_price / max(current_price * 0.02, 1)) if current_price > 0 else 0
        cache_key = f"auto_trade_{ticker}_{position}_{market}_{price_bucket}"
        cached_res = load_ai_cache(cache_key)
        if cached_res:
            return cached_res
            
        from data_kr import get_kr_stock_price
        from data import get_us_stock_detail
        
        info = ""
        if market == "국내":
            d = get_kr_stock_price(ticker)
            if d:
                info = f"변동률: {d.get('change_pct', 0)}%, 52주최고: {d.get('w52_high', 0)}, 52주최저: {d.get('w52_low', 0)}, 거래량: {d.get('volume', 0)}"
        else:
            d = get_us_stock_detail(ticker)
            if d:
                info = f"변동률: {d.get('change_pct', 0)}%, P/E: {d.get('trailingPE', 'N/A')}, P/B: {d.get('priceToBook', 'N/A')}"
                
        # 쉐도우 연관 리스크 감지 로직
        shadow_warning = ""
        shadow_anchors_map = {
            "041190": "⛓️ 두나무 지분연동 (비트코인 테마) - 두나무 지분 7.2% 보유",
            "003530": "⛓️ 두나무/토스/야놀자 3대 지분 연계 변동주 - 지분 보유",
            "021080": "⛓️ 두나무 지분 간접연동 - 펀드를 통한 간접 지분",
            "006800": "🚀 스페이스X 지분연동 (우주항공 테마) - 스페이스X 1000억대 지분 투자",
            "274090": "🚀 스페이스X 밸류체인 연동 - 원소재 가공 공급",
            "211050": "🚀 위성통신 밸류체인 연계",
            "041020": "🧠 오픈AI (인공지능 테마) - GPT Store 서비스 연동",
            "047560": "🧠 오픈AI (인공지능 테마) - 파트너십 기반 사업",
            "084680": "💳 토스 지분연동 - 토스뱅크 지분 7.5% 보유",
            "053300": "💳 토스 지분연동 - 토스뱅크 주주사",
            "041270": "🏦 케이뱅크 지분연동 - 케이뱅크 지주 주주사",
            "035600": "🏦 케이뱅크 지분연동 - 간편결제 연동 주주사",
            "019550": "✈️ 야놀자 지분연동 - 대규모 펀드 투자",
            "086280": "🤖 현대차 로봇 밸류체인 - 보스턴 다이내믹스 지분 직접 보유",
            "108490": "🤖 현대차 로봇 밸류체인 - 자율주행 로봇 협력 실증",
            "018670": "⚡ 초전도체 간접 연동 (퀀텀에너지 테마) - L&S벤처 지분 연동형",
            "047310": "⚡ 초전도체 간접 연동 (퀀텀에너지 테마) - 지분 연동형",
            "047920": "🧪 HLB 바이오 그룹 순환 테마 - 판권/제조 연계",
            "003520": "🧪 HLB 바이오 그룹 순환 테마 - 계열사 유통 연동",
            "000660": "🔌 엔비디아 AI 가속기 공급망 - HBM3E 핵심 독점 공급",
            "042700": "🔌 엔비디아 AI 가속기 공급망 - TC 본더 장비 독점 납품"
        }
        
        ticker_clean = str(ticker).strip().upper()
        if ticker_clean in shadow_anchors_map:
            shadow_warning = f"\n[★ ⚠️ 쉐도우 자산 연동 감지] 이 종목은 {shadow_anchors_map[ticker_clean]}로 인해 시장에서 급등락하는 대표적 지분연동/간접 수혜 쉐도우 종목입니다. 본업 실적보다 연계 자산(비트코인, 스페이스X, 초전도성 검증 등)의 외생적 요소로 요동치므로, 신중하고 극도로 방어적인 포지션을 결정하세요."

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return {"action": "HOLD", "confidence": 0, "reason": "API Key Error"}
            
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
            
        # 수수료 정보 계산 (AI에게 실질 손익 기준 제시)
        if market == "국내":
            fee_roundtrip_pct = 0.21   # 매수 0.015% + 매도 0.015% + 거래세 0.18%
            min_profit_pct    = 0.35   # 수수료(0.21%) + 기대수익 마진(0.14%) = 최소 0.35% 이상이어야 SELL 고려
        else:
            fee_roundtrip_pct = 0.15   # 매수 0.07% + 매도 0.07% + SEC Fee 0.01%
            min_profit_pct    = 0.25   # 수수료(0.15%) + 기대수익 마진(0.10%) = 최소 0.25% 이상이어야 SELL 고려

        # 현재 실질 손익률 계산 (수수료 공제 후)
        net_pct = 0.0
        if avg_price > 0:
            gross_pct = (current_price - avg_price) / avg_price * 100
            net_pct = gross_pct - fee_roundtrip_pct  # 왕복 수수료 차감
        
        system_instruction = f"""당신은 월스트리트 출신의 냉철한 AI 퀀트 트레이더입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.{shadow_warning}
지금 당신은 [{name} ({ticker})] 종목에 대해 {position} 상태입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
시장: {market}
현재가: {current_price:,} | 평단가: {avg_price:,}
수수료 구조: 왕복 {fee_roundtrip_pct:.2f}% (매수+매도+거래세 합산)
수수료 공제 후 실질 손익률: {net_pct:+.2f}%
추가정보: {info}

[핵심 규칙 - 반드시 준수]
- 당신은 스캘핑(초단타)을 절대 하지 않으며, 하루 1~3회 내외로 극도로 신중하게 매매하는 중단기/스윙 트레이더입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요. 잦은 거래는 잦은 수수료와 슬리피지 손실을 부릅니다.
- SELL은 수수료 공제 후 실질 손익률이 최소 +2.50% 이상(안정적인 스윙 수익실현) 또는 -3.0% 이하(안정적인 스윙 손절)일 때만 고려하세요. (0.3% 내외의 이익으로 조기 청산하는 단타성 매도는 엄격히 금지됩니다.)
- BUY는 1분/5분 차트의 일시적 노이즈에 유혹당하지 말고, 일봉/시간봉 상 확실한 눌림목이나 바닥 다지기가 확인되어 최소 몇 시간에서 며칠간 진득하게 보유할 만한 가치가 있는 강력한 타점에서만 결정하세요. 확신이 없다면 무조건 HOLD하세요.
- 보유 중(HOLDING)일 때, 뚜렷한 추세 이탈이 없고 실질 손익률이 목표 청산 구간(+2.50% 이상 또는 -3.0% 이하)에 도달하지 않았다면 차분하게 추세를 길러가며 보유(HOLD) 상태를 유지하세요.

만약 미보유(NONE) 상태라면, 지금이 매수 적기인지(BUY) 아니면 관망할지(HOLD) 결정하세요.
만약 보유중(HOLDING) 상태라면, 위 스윙 트레이더 핵심 규칙을 완벽히 엄수하여 SELL 또는 HOLD를 결정하세요.

당신의 결정을 반드시 다음 JSON 형식으로만 응답하세요:
{{{{
  "action": "BUY" 또는 "SELL" 또는 "HOLD",
  "confidence": 1에서 100 사이의 확신도 (정수),
  "reason": "결정에 대한 명확한 사유 (1-2문장 이내)"{lp_field}
}}}}
절대 다른 마크다운이나 설명을 덧붙이지 마세요."""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="이 종목에 대해 어떻게 처분해야 할까?",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3,
                response_mime_type="application/json"
            ),
        )
        res_text = response.text.strip()
        if res_text.startswith("```json"):
            res_text = res_text[7:-3]
        result_dict = json.loads(res_text)
        
        # 2차: 캐시 저장 (NONE 은 4시간, HOLDING 은 30분)
        ttl_hours = 4.0 if position == "NONE" else 0.5
        save_ai_cache(cache_key, result_dict, ttl_hours=ttl_hours)
        
        return result_dict
    except Exception as e:
        print(f"analyze_autonomous_trading error: {e}")
        return {"action": "HOLD", "confidence": 0, "reason": "AI Error"}



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

    prompt = f"""당신은 개인 투자자의 실전 포트폴리오를 관리하는 전문 트레이딩 어드바이저입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.

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
    # [RAG 영문 실시간 뉴스 피드 강제 주입]
    news_txt = _fetch_target_news_us(f"{ticker} stock", limit=5)
    if not news_txt or "No recent target" in news_txt:
        news_txt = f"Current Price of {ticker} is ${current_price} ({change_pct}%)."

    prompt = f"""
당신은 월스트리트 전문 애널리스트입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
현재 {ticker}의 주가는 ${current_price} ({change_pct}%)입니다.

[실시간 최신 영문 뉴스 팩트시트 (RAG)]
{news_txt}

[분석 원칙 — 냉철한 리스크 차감 및 낙관 편향(Optimism Bias) 절대 금지]
1. 상승·하락 어느 쪽으로도 편향하지 마십시오. 장밋빛 낙관론은 금융 분석가로서 최악의 과오입니다.
2. 실적, 수급, 밸류에이션(PER/PBR 역사적 상단 도달 여부), 매크로 긴축 환경, 최근 분기 성장 둔화 우려 등의 부정적인 요인(Risk Factors)을 반드시 50% 이상의 강도로 엄격히 차감 반영(Risk Discount)하십시오.
3. 데이터가 상승을 지지하면 상승을 제시하되 반드시 상단 저항 매물대의 현실적 한계를 기재하고, 지표나 실적이 하락을 지지하면 하락 전망을 과감하고 냉정하게 제시하십시오.
4. 근거 없는 낙관이나 희망 사항은 완전 배제하며, 오직 밸류에이션 멀티플과 역사적 프랙탈 데이터 등 수치적 사실에만 기반하여 보수적으로 깎아서 산정하십시오.

⚠️ [최우선 검증 단계] 분석 전 반드시 구글 검색으로 티커 '{ticker}'가 실제 NYSE/NASDAQ/AMEX 상장 회사인지 확인하세요.
- 검색어: "{ticker} stock company name NYSE NASDAQ"
- 확인한 실제 회사명을 'verified_name'에 기재하세요.
- 확인한 회사가 분석 맥락과 다르거나 확인 불가 시 'ticker_mismatch': true 설정.

제공된 실시간 영문 뉴스 팩트 및 최신 정보를 바탕으로 분석하되 반드시 아래 JSON 형식으로만 응답하세요:
{{
  "verified_name": "확인한 티커 {ticker}의 실제 회사명",
  "ticker_mismatch": false,

  "rating": "단기 트레이딩 등급 (매우 강력 추천 / 추천 / 중간추천 / 비추천 / 매우 비추천)",

  "key_issues": "현재 이 종목에 영향을 주는 핵심 이슈·변수 2~3가지 (마크다운 불릿. 긍정·부정 모두 포함, 실적·수급·매크로 등 구체적 수치와 함께)",

  "short_term_view_pct": "근 시일(1~4주) 예상 주가 변동률 — 데이터 근거로 객관 판단 (예: +5~+8% 또는 -6~-10%)",
  "short_term_view_price": "단기 예상 도달 가격대 (달러 단위)",
  "short_term_view_reason": "이 전망의 구체적 근거 — 실적, 수급 흐름, 기술적 지지·저항 등 수치 포함 (2~3문장)",

  "buy_target": "매수 적정 구간 가이드라인 (rating이 추천/매우 강력 추천이면 시스템이 현재가 ±1%로 자동 교정, 그 외 등급이면 '관망'으로 대체됨)",
  "sell_target": "단기 목표가 가이드라인 (추천/매우 강력 추천이면 시스템이 +6%로 자동 교정)",
  "stop_loss": "손절가 가이드라인 (추천/매우 강력 추천이면 시스템이 -2%로 자동 교정)",

  "mid_term_view_pct": "중기(1~3개월) 예상 변동률 — % 기호 없이 순수 숫자만. 관성적 15% 기재 절대 금지. 종목 고유 변동성에 맞춰 과감하게 책정 (예: 우량주는 6.5, 변동성 종목은 25.0 등)",
  "mid_term_view_price": "중기 예상 가격대 (달러 단위, 시스템이 mid_term_view_pct로 자동 계산)",
  "mid_term_view_condition": "이 중기 전망의 핵심 변수 또는 catalyst (상승·하락 모두 가능, 구체적인 이벤트·조건)",

  "analysis": "종합 단타 전략 (최신 뉴스, 차트 패턴, 진입 근거 등 마크다운 상세)",
  "historical_pattern_analysis": "유사 과거 패턴(프랙탈) 1~2개, 당시 결과 비교 (마크다운)",

  "long_term_rating": "중장기 등급 (적극 매수 / 분할 매수 / 관망 / 비중 축소 / 전량 매도)",
  "long_term_period": "권장 투자 기간",
  "long_term_target": "중장기 목표가 가이드라인 (달러 단위, 시스템이 long_term_target_pct로 자동 계산)",
  "long_term_target_pct": "중장기 예상 수익/손실률 — % 기호 없이 순수 숫자만. 관성적 30% 기재 절대 금지. 종목 고유 성장성/펀더멘털에 맞춰 책정 (예: 우량주는 12.0, 급등 성장주는 80.0 등)",
  "long_term_analysis": "매크로 사이클·펀더멘털 중장기 분석 (마크다운 상세)",
  "upside_scenario_pct": "긍정적 모멘텀 작동 시 예상 단기 최대 상승률. 관성적 15% 절대 금지. 호재 강도에 연동 (% 기호 없이 실수/정수 숫자만, 예: 8.5 또는 45.0)",
  "upside_scenario_reason": "긍정 시나리오 현실화 시 진입 방법 및 돌파 타점 대응 전략 (1~2문장)",
  "downside_scenario_pct": "부정적 모멘텀 또는 시장 조정 시 예상 단기 최대 하락률. 관성적 -10% 절대 금지 (음수 % 기호 없이 순수 실수/정수 숫자만, 예: -4.5 또는 -25.0)",
  "downside_scenario_reason": "부정 시나리오 발생 시 저점 눌림목 대기 전략 및 지지선 대응법 (1~2문장)"
}}

!! [수치 산정 주의] 타점(buy/sell/stop) 및 중장기 목표가는 시스템이 실시간 현재가 기반으로 강제 덮어쓰기(Override) 하므로, AI는 논리적 근거 확보에 집중하세요.

!! [평균 편향 금지 지침] AI는 관성적으로 중기 +15% 내외, 장기 +30% 내외를 뱉는 치명적인 버그(Average Bias)가 있습니다. 종목 고유의 변동성(안정 대형주는 +5~12%, 성장주는 +25~60%, 강세 테마주는 +80% 이상)에 맞춰 매우 탄력적이고 개성 있는 수치를 뿜어내십시오.

!! [딥링크] 종목 언급 시 반드시 '종목명(티커)' 형식: Apple(AAPL), NVIDIA(NVDA) 등
"""
    try:
        # RAG 뉴스 정보가 이미 완벽하게 주입되었으므로 딜레이 최소화를 위해 use_search=False로 설정
        response = _call_gemini(prompt, use_search=False, temperature=0.7)
        res = _parse_json_response(response)

        # [Python Override - Conditional & No-Fallback - 동적 하이브리드 타점 적용]
        try:
            cp = float(current_price)
            rating = str(res.get("rating", ""))

            # AI 예측 단기 목표 수익률 파싱 (short_term_view_pct)
            try:
                import re
                raw_pct = str(res.get("short_term_view_pct", "6.0"))
                # 숫자(소수점 포함) 모두 추출
                pct_nums = [float(n) for n in re.findall(r'[-+]?\d*\.\d+|\d+', raw_pct)]
                gain = sum(pct_nums) / len(pct_nums) if pct_nums else 6.0
                if gain <= 0: gain = 6.0 # 음수나 0이 오면 기본값 6.0% 적용
            except Exception:
                gain = 6.0
            
            # AI 예측 손절선 (기대 수익 비율의 1/3 수준으로 합리적 하방 리스크 조절)
            loss = -max(2.0, min(gain * 0.4, 8.0))

            # 조건부 단기 타점: 추천/매우 강력 추천일 때만 계산
            if rating in ("추천", "매우 강력 추천"):
                res["buy_target"] = f"${cp * 0.97:.2f} ~ ${cp:.2f} (1~3% 분할 눌림목 매수)"
                res["sell_target"] = f"${cp * (1 + gain / 100):.2f} (+{gain:.1f}%)"
                res["stop_loss"]   = f"${cp * (1 + loss / 100):.2f} ({loss:.1f}%)"
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

            # ── [추가] 양방향 시나리오별 평행 우주 타점 및 가이드 자동 계산 (USD) ──
            try:
                import re
                raw_up = str(res.get("upside_scenario_pct", "15.0"))
                up_pct = float(re.findall(r'[-+]?\d*\.\d+|\d+', raw_up)[0]) if re.findall(r'[-+]?\d*\.\d+|\d+', raw_up) else 15.0
                if up_pct < 0: up_pct = -up_pct
                res["upside_scenario_price"] = f"${cp * (1 + up_pct / 100):.2f}"
                
                raw_down = str(res.get("downside_scenario_pct", "-10.0"))
                down_pct = float(re.findall(r'[-+]?\d*\.\d+|\d+', raw_down)[0]) if re.findall(r'[-+]?\d*\.\d+|\d+', raw_down) else -10.0
                if down_pct > 0: down_pct = -down_pct
                res["downside_scenario_price"] = f"${cp * (1 + down_pct / 100):.2f}"
            except Exception:
                res["upside_scenario_price"] = "AI 가격 산정 불가"
                res["downside_scenario_price"] = "AI 가격 산정 불가"

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
    당신은 가상의 주식 트레이딩 교육 전문가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요. 본 분석은 실제 투자 권유가 아니라 교육적 목적으로만 사용합니다.
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
            try:
                is_kr = str(ticker).isdigit()
                cp = 0
                if is_kr:
                    from data_kr import get_kr_stock_price
                    kr_data = get_kr_stock_price(ticker)
                    if kr_data and kr_data.get("price", 0) > 0:
                        cp = float(kr_data["price"])
                else:
                    from data import get_us_stock_data
                    df_prices = get_us_stock_data([ticker])
                    if not df_prices.empty:
                        for _, row in df_prices.iterrows():
                            if row["심볼"] == ticker:
                                cp = float(row["현재가($)"])
                
                if cp > 0:
                    curr_sym = "₩" if is_kr else "$"
                    if is_kr:
                        res["buy_target"] = f"{curr_sym}{int(cp * 0.99):,} ~ {curr_sym}{int(cp * 1.01):,} 이하"
                        res["sell_target"] = f"{curr_sym}{int(cp * 1.06):,} (+6%)"
                        res["stop_loss"] = f"{curr_sym}{int(cp * 0.98):,} (-2%)"
                    else:
                        res["buy_target"] = f"{curr_sym}{cp * 0.99:.2f} ~ {curr_sym}{cp * 1.01:.2f} 이하"
                        res["sell_target"] = f"{curr_sym}{cp * 1.06:.2f} (+6%)"
                        res["stop_loss"] = f"{curr_sym}{cp * 0.98:.2f} (-2%)"
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

    # 상위 6종목에 분봉 시그널 계산 — 병렬 호출 (순차 최대 60초 → 병렬 최대 15초)
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as _FutTimeout
    enriched = []
    candidates = prebreakout[:6]
    _FALLBACK_SIG = {"signal_score": 0, "signal_label": "-", "vol_accel": 0}
    _pool = ThreadPoolExecutor(max_workers=6)
    try:
        fut_map = {
            _pool.submit(get_kr_prebreakout_signal, str(s.get("종목코드", ""))): s
            for s in candidates
        }
        try:
            for fut in as_completed(fut_map, timeout=15):
                s = fut_map[fut]
                try:
                    sig = fut.result()
                except Exception:
                    sig = _FALLBACK_SIG
                enriched.append({**s, "_signal": sig})
        except _FutTimeout:
            # 15초 내 완료된 것만 사용, 나머지는 fallback
            done_stocks = {id(fut_map[f]) for f in fut_map if f.done()}
            for s in candidates:
                if id(s) not in done_stocks:
                    enriched.append({**s, "_signal": _FALLBACK_SIG})
    finally:
        _pool.shutdown(wait=False)  # 미완료 스레드를 기다리지 않고 즉시 반환

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

    prompt = f"""당신은 10년 경력의 한국 주식시장 스캘핑·단타 트레이더이자 테마·세력 추적 전문가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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


def generate_kr_stock_report(stock_code: str, name: str, price_data: dict, investor_data: list, pattern_context: str | None = None):
    """국내 주식 AI 수급 분석 및 단타 타점 리포트"""
    investor_summary = ""
    if investor_data:
        latest = investor_data[0]
        investor_summary = f"""
최근 수급 동향 ({latest['날짜']}):
- 외국인 순매수: {latest['외국인']:+,}주
- 기관 순매수: {latest['기관']:+,}주
- 개인 순매수: {latest['개인']:+,}주"""

    cp = price_data.get('price', 0)
    if not cp:
        return {
            "rating": "분석 오류",
            "buy_target": "-", "sell_target": "-", "stop_loss": "-",
            "세력분석": "-",
            "analysis": "가격 데이터를 가져오지 못했습니다. 종목 코드와 네트워크 상태를 확인해주세요."
        }

    pattern_section = ""
    try:
        from db import load_pattern_profile
        profile = load_pattern_profile()
        win_rate    = profile.get("win_rate_pct", 0) if profile else 0
        trade_count = profile.get("total_trades", 0) if profile else 0
        if profile and not pattern_context and win_rate >= 50 and trade_count >= 15:
            ind = _get_trade_indicators(stock_code, "")
            match_score = _score_stock_against_profile(ind, profile)
            rsi_val = ind["daily"].get("rsi")
            vol_r = ind["daily"].get("volume_ratio")
            ma_align = ind["daily"].get("ma_aligned")
            win_rsi = profile.get("win", {}).get("rsi", {})
            pattern_context = (
                f"패턴 매칭 점수: {match_score}점"
                + (f" / RSI: {rsi_val}" if rsi_val is not None else "")
                + (f" / 거래량 비율: {vol_r}배" if vol_r is not None else "")
                + (" / MA 정배열" if ma_align else "")
                + f" | 내 과거 승률: {profile.get('win_rate_pct')}% / 평균수익: {profile.get('avg_profit_pct')}%"
                + (f" / 내 승리 RSI 구간: {win_rsi.get('p25','?')}~{win_rsi.get('p75','?')}" if win_rsi else "")
            )
    except Exception:
        pass

    if pattern_context:
        pattern_section = f"""
[📊 내 매매 패턴 데이터 — 단기 분석에만 반영 (중장기 분석에는 적용하지 마세요)]
{pattern_context}
단기 진입 타당성 판단 시 매칭 점수와 내 승리 패턴 조건 일치 여부를 언급하세요.
중장기 분석(long_term_analysis)에는 이 데이터를 사용하지 마세요.
"""

    prompt = f"""
당신은 한국 주식시장 전문 애널리스트입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
{pattern_section}
[분석 원칙 — 냉철한 리스크 차감 및 낙관 편향(Optimism Bias) 절대 금지]
1. 상승·하락 어느 쪽으로도 편향하지 마십시오. 장밋빛 낙관론은 금융 분석가로서 최악의 과오입니다.
2. 실적, 수급, 밸류에이션(PER/PBR 역사적 고점 여부), 고금리 매크로 부담, 개별 오버행(잠재적 매도 물량) 우려 및 섹터 둔화 등 부정적인 요인(Risk Factors)을 반드시 50% 이상의 강도로 엄격히 차감 반영(Risk Discount)하십시오.
3. 데이터가 상승을 지지하면 상승을 제시하되 반드시 저항 매물대의 한계를 명시하고, 수급 이탈이나 실적 둔화가 관찰되면 하락 전망을 과감하고 냉정하게 제시하십시오.
4. 근거 없는 낙관이나 희망 사항은 완전 배제하며, 오직 객관적 밸류에이션 수치와 수급 데이터에만 기반하여 보수적으로 깎아서 산정하십시오.

[종목 정보]
종목명: {name} ({stock_code})
현재가: {cp:,}원 ({price_data.get('change_pct', 0):+.2f}%)
시가총액: {price_data.get('market_cap', '-')}
거래량: {price_data.get('volume', 0):,}주 / 거래대금: {price_data.get('amount', 0) // 100000000:,}억원
시가: {price_data.get('open', 0):,}원 | 고가: {price_data.get('high', 0):,}원 | 저가: {price_data.get('low', 0):,}원
52주 최고: {price_data.get('w52_high', 0):,}원 | 52주 최저: {price_data.get('w52_low', 0):,}원
PER: {price_data.get('per', '-')} | PBR: {price_data.get('pbr', '-')}
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

  "mid_term_view_pct": "중기(1~3개월) 예상 변동률 — % 기호 없이 순수 숫자만. 관성적 15% 기재 절대 금지. 종목 고유 변동성에 맞춰 과감하게 책정 (예: 우량주는 6.5, 변동성 종목은 25.0 등)",
  "mid_term_view_price": "중기 예상 가격대 (원 단위, 시스템이 mid_term_view_pct로 자동 계산)",
  "mid_term_view_condition": "이 중기 전망의 핵심 변수 또는 catalyst (상승·하락 모두 가능, 구체적인 이벤트·조건)",

  "세력분석": "외국인/기관 수급 흐름과 그 의미를 2~3문장으로 분석",
  "analysis": "종합 단타 전략 (최신 뉴스, 차트 패턴, 진입 근거 등 마크다운 상세)",
  "historical_pattern_analysis": "현재 주가 흐름·수급·섹터와 유사했던 과거 패턴(프랙탈) 1~2개, 당시 결과 비교 (마크다운)",

  "long_term_rating": "중장기 등급 (적극 매수 / 분할 매수 / 관망 / 비중 축소 / 전량 매도)",
  "long_term_period": "권장 투자 기간",
  "long_term_target": "중장기 목표가 가이드라인 (원 단위, 시스템이 long_term_target_pct로 자동 계산)",
  "long_term_target_pct": "중장기 예상 수익/손실률 — % 기호 없이 순수 숫자만. 관성적 30% 기재 절대 금지. 종목 고유 성장성/펀더멘털에 맞춰 책정 (예: 우량주는 12.0, 급등 성장주는 80.0 등)",
  "long_term_analysis": "거시경제 사이클·펀더멘털 기반 중장기 분석 (마크다운 상세)",
  "upside_scenario_pct": "긍정적 모멘텀 작동 시 예상 단기 최대 상승률. 관성적 15% 절대 금지. 호재 강도에 연동 (% 기호 없이 실수/정수 숫자만, 예: 8.5 또는 45.0)",
  "upside_scenario_reason": "긍정 시나리오 현실화 시 진입 방법 및 돌파 타점 대응 전략 (1~2문장)",
  "downside_scenario_pct": "부정적 모멘텀 또는 시장 조정 시 예상 단기 최대 하락률. 관성적 -10% 절대 금지 (음수 % 기호 없이 순수 실수/정수 숫자만, 예: -4.5 또는 -25.0)",
  "downside_scenario_reason": "부정 시나리오 발생 시 저점 눌림목 대기 전략 및 지지선 대응법 (1~2문장)"
}}

!! [수치 산정 주의] 모든 가격 타점은 시스템이 실시간 현재가 기반으로 강제 덮어쓰기 하므로, AI는 수치 계산보다 분석 논리에 집중하세요.

!! [평균 편향 금지 지침] AI는 관성적으로 중기 +15% 내외, 장기 +30% 내외를 뱉는 치명적인 버그(Average Bias)가 있습니다. 종목 고유의 변동성(안정 대형주는 +5~12%, 성장주는 +25~60%, 강세 테마주는 +80% 이상)에 맞춰 매우 탄력적이고 개성 있는 수치를 뿜어내십시오.

!! [딥링크] 종목 언급 시 반드시 '종목명(6자리코드)' 형식: 삼성전자(005930), SK하이닉스(000660) 등
"""
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.7)
        res = _parse_json_response(response)

        # [Python Override - Conditional & No-Fallback - 동적 하이브리드 타점 적용]
        try:
            cp = float(price_data['price'])
            rating = str(res.get("rating", ""))
            
            # AI 예측 단기 목표 수익률 파싱 (short_term_view_pct)
            try:
                import re
                raw_pct = str(res.get("short_term_view_pct", "6.0"))
                # 숫자(소수점 포함) 모두 추출
                pct_nums = [float(n) for n in re.findall(r'[-+]?\d*\.\d+|\d+', raw_pct)]
                gain = sum(pct_nums) / len(pct_nums) if pct_nums else 6.0
                if gain <= 0: gain = 6.0 # 음수나 0이 오면 기본값 6.0% 적용
            except Exception:
                gain = 6.0
            
            # AI 예측 손절선 (기대 수익 비율의 1/3 수준으로 합리적 하방 리스크 조절)
            loss = -max(2.0, min(gain * 0.4, 8.0))

            if rating in ("추천", "매우 강력 추천"):
                res["buy_target"] = f"{int(cp * 0.97):,}원 ~ {int(cp * 1.00):,}원 (현재가 대비 1~3% 분할 눌림목 매수)"
                res["sell_target"] = f"{int(cp * (1 + gain / 100)):,}원 (+{gain:.1f}%)"
                res["stop_loss"] = f"{int(cp * (1 + loss / 100)):,}원 ({loss:.1f}%)"
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
                
            # ── [추가] 양방향 시나리오별 평행 우주 타점 및 가이드 자동 계산 ──
            try:
                import re
                raw_up = str(res.get("upside_scenario_pct", "15.0"))
                up_pct = float(re.findall(r'[-+]?\d*\.\d+|\d+', raw_up)[0]) if re.findall(r'[-+]?\d*\.\d+|\d+', raw_up) else 15.0
                if up_pct < 0: up_pct = -up_pct
                res["upside_scenario_price"] = f"{int(cp * (1 + up_pct / 100)):,}원"
                
                raw_down = str(res.get("downside_scenario_pct", "-10.0"))
                down_pct = float(re.findall(r'[-+]?\d*\.\d+|\d+', raw_down)[0]) if re.findall(r'[-+]?\d*\.\d+|\d+', raw_down) else -10.0
                if down_pct > 0: down_pct = -down_pct
                res["downside_scenario_price"] = f"{int(cp * (1 + down_pct / 100)):,}원"
            except Exception:
                res["upside_scenario_price"] = "AI 가격 산정 불가"
                res["downside_scenario_price"] = "AI 가격 산정 불가"
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
    prompt = f"""당신은 15년 경력의 기술적 분석 및 세력 수급 추적 전문가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.

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
    당신은 월스트리트의 저명한 섹터 애널리스트입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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

    prompt = f"""당신은 한국 주식시장 전문 섹터 애널리스트입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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
        result = _parse_json_response(response)
        _update_hs_cache(result)  # 모듈 레벨 캐시도 갱신
        return result
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

    prompt = f"""당신은 한국 주식시장 전문 애널리스트입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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
    prompt = f"""당신은 한국 주식시장 전문 섹터 애널리스트이자 역사적 패턴 분석 전문가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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

    prompt = f"""당신은 10년 경력의 미국 주식시장 스캘핑·단타 트레이더입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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

    prompt = f"""당신은 미국 주식시장 전문 애널리스트입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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

    prompt = f"""당신은 미국 주식시장 전문 섹터 애널리스트입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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

    prompt = f"""당신은 한국 주식시장 세력·테마 전문가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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

    prompt = f"""당신은 한국 주식시장 세력 추적·테마 분석 전문가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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
    당신은 월스트리트의 수석 매크로 전략가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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
    당신은 세계 최고의 글로벌 퀀트 전략가이자 실전 트레이딩 전문가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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
            return _strip_hanja(response.text)
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

    prompt = f"""당신은 20년 경력의 국내외 단타 트레이딩 전문가이자 퀀트 애널리스트입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
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
        f"당신은 20년 경력의 퀀트 트레이더이자 트레이딩 심리 전문가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.\n"
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


def recommend_entry_price(ticker: str, name: str, market: str, current_price: float, w52_high: float = None, w52_low: float = None) -> dict:
    """미매수 관심종목에 대한 AI 매수가(타점) 추천"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets["gemini"]["api_key"]
        except Exception:
            pass
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
    
    currency = "KRW" if market == "국내" else "USD"
    price_info = f"- 현재가: {current_price} {currency}\n"
    if w52_high and w52_low:
        price_info += f"- 52주 최고/최저: {w52_high} / {w52_low} {currency}\n"
        
    prompt = f"""
당신은 최고의 트레이딩 타점 분석가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
사용자가 아직 매수하지 않고 관심종목으로만 지켜보고 있는 종목에 대해 가장 이상적인 **신규 매수 진입가(Buy Target)**를 추천해주세요.

종목: {name} ({ticker}, {market})
{price_info}

지시사항:
1. 현재가와 52주 변동폭(제공된 경우)을 참고하여, **단기~스윙 관점**에서 가장 리스크 대비 보상 비율(손익비)이 좋은 매수 타점을 제시하세요.
2. 현재가가 이미 충분히 저점이라 당장 매수해도 좋다면 현재가 주변을 제시해도 됩니다.
3. 상승 추세라면 약간의 눌림목(Pullback) 가격을 제시하세요.
4. 반드시 JSON 형식으로만 응답해야 합니다.
5. 응답 JSON 구조:
{{
  "recommended_price": 120.5,
  "reason": "현재가 대비 -3% 수준의 주요 지지선. 단기 과매도를 노리는 눌림목 타점입니다."
}}

오직 JSON만 출력하세요. 마크다운 백틱(```json)도 사용하지 마세요.
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json"
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e), "recommended_price": current_price, "reason": "AI 타점 추천에 실패했습니다. 현재가를 기준으로 분석을 보완합니다."}


def analyze_trade_postmortem(ticker: str, name: str, market: str, buy_price: float, sell_price: float, buy_date: str, sell_date: str, profit_pct: float, owner: str = "USER") -> dict:
    """거래 결과(Postmortem) 분석 리포트 생성"""
    curr = "₩" if market == "국내" else "$"
    result_label = "수익" if profit_pct >= 0 else "손실"
    prompt = (
        f"당신은 월스트리트 출신 탑티어 트레이딩 코치이자 퀀트 분석가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.\n"
        f"다음 거래에 대한 냉철한 사후 분석(Postmortem)을 수행하세요.\n\n"
        f"- 종목: {name} ({ticker})\n"
        f"- 시장: {market}\n"
        f"- 매수가: {curr}{buy_price:,}  매수일: {buy_date}\n"
        f"- 매도가: {curr}{sell_price:,}  매도일: {sell_date}\n"
        f"- 손익률: {profit_pct:.2f}% ({result_label})\n"
        f"- 거래 주체: {'AI 에이전트' if owner == 'AI' else '사용자'}\n\n"
        "위 데이터를 바탕으로 매수/매도 타이밍, 수익/손실 원인, 교훈을 분석하세요.\n"
        "반드시 아래 JSON 형식으로만 응답하세요 (추가 텍스트 없이):\n"
        "{\n"
        '  "evaluation": "종합 평가 (3~4문장. 매수/매도 타이밍의 적절성 평가)",\n'
        '  "cause": "수익 또는 손실의 핵심 원인 (2~3문장. 가격 움직임, 보유 기간, 시장 환경 등)",\n'
        '  "learning_point": "이 거래에서 얻을 수 있는 핵심 교훈 (1~2문장. 향후 거래의 가이드라인)"\n'
        "}"
    )
    try:
        response = _call_gemini(prompt, use_search=False, temperature=0.7, timeout_sec=45)
        res = _parse_json_response(response)
        return res
    except Exception as e:
        return {"evaluation": f"분석 오류: {e}", "cause": "-", "learning_point": "-"}


def analyze_shadow_sector_catalyst(ticker: str, name: str, market: str) -> dict:
    """AI 실시간 쉐도우 섹터 & 찌라시 팩트 체커 엔진 코어.
    구글 실시간 검색(use_search=True)을 가동하여 7일간의 신규 공급계약, 신사업, 루머 진위 및 숨겨진 지분 관계를 교차 체크합니다.
    """
    ticker_str = str(ticker).upper()
    prompt = f"""당신은 기업의 공급계약, 신사업 진출, 대기업 수급 밸류체인, 그리고 **'숨겨진 지분 보유/자회사 투자 관계'**를 초정밀 분석하는 'AI 쉐도우 섹터 판독가'입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
최근 7일 및 과거 뉴스 히스토리를 종합하여 [{name} ({ticker_str})] 종목에 대한 실시간 뉴스, 공급계약 체결 공시, 대형사 거래 개시 소식, 혹은 **'비상장사/글로벌 벤처 지분 투자 현황 및 자회사 연동 테마'**를 구글 검색을 통해 철저하게 수집하고 분석하세요.

[분석 및 검증 지침]
1. **지분 관계 및 간접 투자 동조화 (Hidden Equity Connection) 분석**:
   - 이 종목의 공식 업종(예: 창업투자, 증권, 화학 등)과 완전히 무관하더라도, **특정 비상장사나 글로벌 혁신 기업의 지분/투자금 보유(예: 우리기술투자의 두나무/업비트 지분보유 ➔ 비트코인 가상자산 테마, 미래에셋증권의 스페이스X 지분보유 ➔ 우주항공 테마, 창해에탄올의 자회사 지분보유 등)**로 인해 다른 기초자산이나 글로벌 메가 이슈에 100% 동조되어 요동치는 독특한 "지분연동형 쉐도우 섹터"인지를 철저히 파악하여 도출해 내세요.
2. **팩트 신뢰도 등급 (credibility)**을 아래 기준에 따라 냉철하게 부여하세요:
   - '상' (공식 팩트): 금융감독원 DART 공식 공시(분기보고서 지분 명세서 등) 및 계약 공시 확인 완료, 대기업 공식 발표 보도자료, 메이저 경제 3사(연합, 머니투데이 등)의 지분 인수 및 계약 확정보도 확인 완료.
   - '미확인' (찌라시 주의): 공식 공시나 팩트 체크 보도가 전혀 없는 단순 블로그 속보, 카더라 통신, 지라시성 낚시 기사 및 근거 없는 투자 루머.
3. **동적 쉐도우 섹터명 (shadow_sector)**을 도출하세요:
   - 신규 계약뿐 아니라 지분 보유로 인해 주가가 강력하게 동조화되는 '실시간 쉐도우 섹터'를 한 줄로 간결히 나타내세요.
   - 예: "⛓️ 두나무 지분연동 (비트코인 테마)" 또는 "🚀 스페이스X 지분연동 (우주항공 테마)", "⚡ 2차전지 배터리 팩 케이스 (삼성SDI향 납품)" 등.
   - 만약 유의미한 지분 얽힘이나 신사업/공급 계약 팩트가 없다면, 기존의 업종 대분류명을 그대로 표시하세요.
4. **루머 리스크 및 지분 리스크 가이드라인 (rumor_warning_guide)**을 작성하세요:
   - 지분 연동 종목인 경우: 단순히 지분만 가지고 테마로 엮여 요동치므로, 실제 본업의 실적과 괴리가 클 수 있음을 경고하는 지분투자 특화형 리스크 가이드라인을 적어주세요 (1~2줄).
   - 일반 미확인 찌라시인 경우: 뇌동매매 추격 매수를 경고하는 리스크 가이드 (1~2줄).
   - 공식 팩트가 확실한 경우: "금융감독원 공식 보고서 지분 소유 명세 및 계약서가 정식 확인된 공인된 팩트 구조입니다." 로 기재하세요.

반드시 아래 JSON 형식으로만 응답하세요 (설명 없이 JSON 객체만 반환):
{{
  "shadow_sector": "도출된 쉐도우 섹터명 (15자 내외)",
  "credibility": "상 또는 미확인",
  "catalyst_summary": "최근 발생한 핵심 계약/신사업/지분보유 구조 팩트 요약 (1~2줄)",
  "rumor_warning_guide": "투자자 경고용 리스크 가이드라인 (1~2줄)",
  "partner_company": "연계된 대형 고객사 또는 지분 보유사 이름 (예: 두나무 / 스페이스X / 현대차 등, 없으면 '-')"
}}"""
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.3, timeout_sec=60)
        return _parse_json_response(response)
    except Exception as e:
        print(f"analyze_shadow_sector_catalyst error: {e}")
        return {
            "shadow_sector": "데이터 로드 실패",
            "credibility": "미확인",
            "catalyst_summary": f"RAG 검색 오류: {str(e)[:50]}",
            "rumor_warning_guide": "서버 통신 오류로 인해 팩트 체크가 중단되었습니다. 신중한 접근이 필요합니다.",
            "partner_company": "-"
        }


def discover_shadow_stocks(keyword: str) -> dict:
    """사용자가 입력한 임의의 테마/앵커 키워드(예: 트럼프, 케이뱅크, 컬리 등)에 대해
    실시간 구글 검색을 가동하여 숨겨진 지분 보유사나 간접 수혜주(쉐도우 종목)들을 발굴해냅니다.
    """
    keyword_clean = str(keyword).strip()
    prompt = f"""당신은 기업의 숨겨진 지분 관계, 자회사 지분율, 공급계약 및 비상장사 투자 인프라를 추적하는 '초지능형 쉐도우 섹터 발굴 엔진'입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
최근 7일 및 과거 뉴스 히스토리, 기업 공시를 분석하여 입력 키워드 [{keyword_clean}]와 직간접적으로 연결된 국내(KR) 및 미국(US) 상장 주식들 중 **'보유 지분이나 자회사 투자, 혹은 독점 밸류체인 관계'**로 인해 강력한 주가 동조화를 보이는 대표적인 쉐도우 종목들을 구글 실시간 검색을 통해 최소 2개, 최대 5개 발굴해내세요.

[분석 및 반환 필수 요소]
1. **지분 얽힘 및 투자 관계 (Equity Connection)**: 단순한 테마 엮임이 아닌, 구체적으로 몇 %의 지분을 가지고 있는지, 펀드를 통해 투자했는지, 또는 핵심 자회사인지 등의 구체적 지분 팩트를 제시하세요.
2. **신뢰 등급 (credibility)**: '상' (공식 지분/공시 확인) 또는 '미확인' (시장 루머/찌라시)
3. **종목명 및 티커**: 한/미 종목 모두 가능하며 정확한 종목명과 티커(코드는 6자리 숫자 또는 US 알파벳)를 제시해야 합니다.
4. **리스크 가이드라인**: 지분 희석이나 본업 실적 무관 상승에 대한 뇌동매매 방어 경고 (1줄).

반드시 아래 JSON 형식으로만 응답하세요 (설명 없이 JSON 객체만 반환):
{{
  "anchor_keyword": "{keyword_clean}",
  "discovery_summary": "키워드와 관련된 쉐도우 섹터 구조 총평 (1~2줄)",
  "stocks": [
    {{
      "name": "종목명",
      "ticker": "티커/코드",
      "market": "KR 또는 US",
      "relationship": "지분 보유율 및 구체적 관계 설명 (예: 두나무 지분 7.2% 보유)",
      "credibility": "상 또는 미확인",
      "risk_guide": "뇌동매매 방지 경고 가이드라인 (1줄)"
    }}
  ]
}}"""
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.3, timeout_sec=60)
        return _parse_json_response(response)
    except Exception as e:
        print(f"discover_shadow_stocks error: {e}")
        return {
            "anchor_keyword": keyword_clean,
            "discovery_summary": f"RAG 검색 중 오류가 발생했습니다: {str(e)[:50]}",
            "stocks": []
        }


def analyze_overnight_gap_risk(ticker: str, name: str, market: str) -> dict:
    """시간외 거래 및 밤사이 돌발 공시/뉴스를 AI RAG로 긴급 수집하여,
    익일 시초가 갭상승/갭하락 방향 및 예상 등락률 범위를 판독하고 실전 대응 수칙을 제안합니다.
    """
    ticker_str = str(ticker).upper()
    prompt = f"""당신은 장 마감(정규장 종료) 후 발생하는 공시, 실적 발표, 밤사이 글로벌 메가 뉴스 보도 및 찌라시 촉매제를 정밀 수집하고 분석하는 'AI 시간외 긴급 갭 스캐너'입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
최근 24시간(특히 정규장 종료 직후부터 현재 시각까지) 구글 실시간 검색을 가동하여 [{name} ({ticker_str})] 종목에 유입된 돌발 공시(3자배정 유상증자, 무상증자, CB 발행, 공급 계약 등), 분기/연간 실적 발표, 대기업 연계 뉴스, 혹은 글로벌 기초자산(비트코인, 유가 등) 시세 급변동 요인을 수집하세요.

[분석 및 검증 지침]
1. **익일 시초가 영향 진단 (gap_direction)**:
   - 밤사이 발생한 재료의 임팩트를 냉정히 연산하여 아래 3가지 중 하나로 결정하세요:
     - '갭상승 가능성 높음' (호재 공시, 어닝 서프라이즈, 메가 테마 엮임 등)
     - '갭하락 가능성 높음' (악재 CB 공시, 횡령, 어닝 쇼크, 테마 버블 붕괴 등)
     - '영향 없음 (보합 중립)' (유의미한 신규 호재/악재 공시나 기사가 감지되지 않음)
2. **예상 갭 강도 및 등락 범위 (gap_strength)**:
   - 만약 '갭상승 가능성 높음'인 경우: 예상 상승 폭 범위 제시 (예: "+3.5% ~ +7.0%")
   - 만약 '갭하락 가능성 높음'인 경우: 예상 하락 폭 범위 제시 (예: "-3.0% ~ -6.5%")
   - 영향 없음인 경우: "0.0% ~ +0.5%" 또는 "보합권"으로 표시하세요.
3. **긴급 시간외 이슈 요약 (overnight_issue_summary)**:
   - 최근 24시간 동안 발생하여 내일 아침 갭에 영향을 미치는 핵심 돌발 재료를 1줄로 요약하세요 (예: "3자배정 유상증자 500억 납입 공시 유입", "장 마감 후 어닝 쇼크 실적 공시로 애프터마켓 폭락 중" 등).
   - 아무 이슈가 없다면 "최근 24시간 이내 감지된 돌발 시간외 이슈가 없습니다." 로 기재하세요.
4. **시간외 단일가 및 익일 시초가 대처 행동 강령 (trading_action_guide)**:
   - 투자자가 지금 시간외 단일가 거래(16:00~18:00)나 익일 장 시작 시 뇌동매매를 피하고 손실을 최소화할 수 있는 **구체적인 행동 수칙**을 1~2줄로 지능적으로 제안하세요.
   - 예: "시간외 3자배정 호재이므로 매수를 고려하되, 내일 아침 시초가 +8% 초과 갭상 시 추격 매수를 금지하고 눌림목을 대기하세요."
   - 예: "악재 CB 발행 공시이므로 시간외 단일가에서 즉시 비중 축소(손절매)를 실행하여 리스크를 방어하세요."

반드시 아래 JSON 형식으로만 응답하세요 (설명 없이 JSON 객체만 반환):
{{
  "gap_direction": "갭상승 가능성 높음 또는 갭하락 가능성 높음 또는 영향 없음 (보합 중립)",
  "gap_strength": "예상 갭 등락 폭 (예: +4.0% ~ +8.0%, 없으면 '보합권')",
  "overnight_issue_summary": "최근 24시간 핵심 시간외 이슈 요약 (1줄)",
  "trading_action_guide": "시간외 단일가 및 시초가 대응 행동 수칙 (1~2줄)"
}}"""
    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.3, timeout_sec=60)
        return _parse_json_response(response)
    except Exception as e:
        print(f"analyze_overnight_gap_risk error: {e}")
        return {
            "gap_direction": "영향 없음 (보합 중립)",
            "gap_strength": "보합권",
            "overnight_issue_summary": f"RAG 갭 스캔 오류: {str(e)[:50]}",
            "trading_action_guide": "장 마감 후 돌발 공시나 뉴스가 감지되지 않았습니다. 차분한 상시 모니터링을 유지하세요."
        }


# ── 리딩방 패턴 분석 ──────────────────────────────────────────────────────────

def _get_trade_indicators(ticker: str, buy_date_str: str) -> dict:
    """단일 거래의 기술적 지표를 yfinance로 수집합니다."""
    import yfinance as yf
    from datetime import datetime

    is_kr = str(ticker).strip().isdigit()
    yf_ticker = f"{ticker}.KS" if is_kr else ticker.upper()

    result: dict = {"ticker": ticker, "buy_date": buy_date_str, "daily": {}, "minute": {}}

    # buy_date 파싱
    buy_dt = None
    if buy_date_str and str(buy_date_str).strip():
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"]:
            try:
                buy_dt = datetime.strptime(str(buy_date_str).strip(), fmt)
                break
            except ValueError:
                continue

    # ── 일봉 지표 ──────────────────────────────────────────────────────────
    try:
        stock = yf.Ticker(yf_ticker)
        hist = stock.history(period="1y", interval="1d")
        if not hist.empty and len(hist) >= 20:
            closes  = hist["Close"].values
            volumes = hist["Volume"].values
            opens   = hist["Open"].values

            # RSI(14) — 단순 Wilder 방식
            deltas = [float(closes[i]) - float(closes[i - 1]) for i in range(1, len(closes))]
            gains  = [d if d > 0 else 0.0 for d in deltas]
            losses = [-d if d < 0 else 0.0 for d in deltas]
            avg_g  = sum(gains[-14:]) / 14
            avg_l  = sum(losses[-14:]) / 14
            rsi    = 100 - (100 / (1 + avg_g / avg_l)) if avg_l > 0 else 100.0

            vol_20_avg = sum(float(v) for v in volumes[-20:]) / 20
            vol_ratio  = float(volumes[-1]) / vol_20_avg if vol_20_avg > 0 else 1.0

            n52 = min(len(hist), 252)
            high_52w = float(max(hist["High"].values[-n52:]))
            low_52w  = float(min(hist["Low"].values[-n52:]))
            current  = float(closes[-1])
            pos_52w  = (current - low_52w) / (high_52w - low_52w) * 100 if high_52w > low_52w else 50.0

            ma5  = sum(float(c) for c in closes[-5:]) / 5
            ma20 = sum(float(c) for c in closes[-20:]) / 20
            ma60 = sum(float(c) for c in closes[-60:]) / 60 if len(closes) >= 60 else ma20
            ma_aligned = bool(current > ma5 > ma20 > ma60)

            prev_close = float(closes[-2]) if len(closes) >= 2 else current
            gap_pct    = (float(opens[-1]) - prev_close) / prev_close * 100

            result["daily"] = {
                "rsi":          round(rsi, 1),
                "volume_ratio": round(vol_ratio, 2),
                "pos_52w_pct":  round(pos_52w, 1),
                "ma_aligned":   ma_aligned,
                "gap_pct":      round(gap_pct, 2),
            }
    except Exception as e:
        result["daily"]["error"] = str(e)[:80]

    # ── 5분봉 지표 (매수일이 60일 이내일 때만) ─────────────────────────────
    try:
        if buy_dt and (datetime.now() - buy_dt).days <= 58:
            stock5 = yf.Ticker(yf_ticker)
            hist5  = stock5.history(period="60d", interval="5m")
            if not hist5.empty:
                buy_date_only = buy_dt.strftime("%Y-%m-%d")
                day_bars = hist5[hist5.index.strftime("%Y-%m-%d") == buy_date_only]
                if not day_bars.empty:
                    h = buy_dt.hour
                    time_class = (
                        "장초반(~10시)"      if h < 10 else
                        "오전(10~12시)"      if h < 12 else
                        "오후초반(12~14시)"  if h < 14 else
                        "오후후반(14시~)"
                    )

                    day_avg_vol = float(day_bars["Volume"].mean()) or 1.0
                    vol_at_buy  = 1.0
                    if buy_dt.hour > 0:
                        best_idx, min_diff = None, float("inf")
                        for idx in day_bars.index:
                            idt = idx.to_pydatetime().replace(tzinfo=None)
                            diff = abs((idt - buy_dt).total_seconds())
                            if diff < min_diff:
                                min_diff, best_idx = diff, idx
                        if best_idx is not None:
                            vol_at_buy = round(float(day_bars.loc[best_idx, "Volume"]) / day_avg_vol, 2)

                    bars_up_to = hist5[hist5.index.strftime("%Y-%m-%d") <= buy_date_only]
                    prev3_bullish = False
                    if len(bars_up_to) >= 3:
                        last3 = bars_up_to.iloc[-3:]
                        prev3_bullish = bool(all(
                            float(last3.iloc[i]["Close"]) > float(last3.iloc[i]["Open"])
                            for i in range(3)
                        ))

                    result["minute"] = {
                        "time_class":      time_class,
                        "vol_at_buy_ratio": vol_at_buy,
                        "prev3_bullish":   prev3_bullish,
                    }
    except Exception as e:
        result["minute"]["error"] = str(e)[:80]

    return result


def analyze_leading_room_patterns() -> dict:
    """리딩방 출처 거래 전체의 기술적 패턴을 집계하고 Gemini로 해석합니다."""
    from db import get_db_conn

    # 리딩방 거래 로드
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT ticker, name, buy_price, sell_price, profit, profit_pct,
                      result, buy_date, sell_date, trade_type
               FROM trade_history
               WHERE UPPER(owner) = 'USER'
                 AND LOWER(COALESCE(trade_source,'')) LIKE '%리딩방%'
               ORDER BY sell_date DESC"""
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
    except Exception as e:
        return {"error": f"DB 오류: {e}"}

    if not rows:
        return {"error": "리딩방 출처 거래 내역이 없습니다."}

    total     = len(rows)
    wins      = sum(1 for r in rows if float(r.get("profit", 0) or 0) > 0)
    win_rate  = wins / total * 100
    avg_pct   = sum(float(r.get("profit_pct", 0) or 0) for r in rows) / total

    # 지표 수집
    indicators = []
    for r in rows:
        ind = _get_trade_indicators(
            str(r.get("ticker", "")).strip(),
            str(r.get("buy_date", "")).strip(),
        )
        ind["name"]       = r.get("name", "")
        ind["profit_pct"] = float(r.get("profit_pct", 0) or 0)
        ind["result"]     = r.get("result", "")
        indicators.append(ind)

    def _avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else None

    rsi_vals  = [ind["daily"]["rsi"]          for ind in indicators if "rsi"          in ind["daily"]]
    vol_vals  = [ind["daily"]["volume_ratio"]  for ind in indicators if "volume_ratio" in ind["daily"]]
    pos_vals  = [ind["daily"]["pos_52w_pct"]   for ind in indicators if "pos_52w_pct"  in ind["daily"]]
    gap_vals  = [ind["daily"]["gap_pct"]       for ind in indicators if "gap_pct"      in ind["daily"]]
    ma_cnt    = sum(1 for ind in indicators if ind["daily"].get("ma_aligned"))
    time_dist: dict = {}
    for ind in indicators:
        tc = ind["minute"].get("time_class")
        if tc:
            time_dist[tc] = time_dist.get(tc, 0) + 1
    minute_cnt    = sum(1 for ind in indicators if ind["minute"].get("time_class"))
    prev3_cnt     = sum(1 for ind in indicators if ind["minute"].get("prev3_bullish"))

    agg = {
        "total_trades":          total,
        "win_rate_pct":          round(win_rate, 1),
        "avg_profit_pct":        round(avg_pct, 2),
        "avg_rsi_at_entry":      _avg(rsi_vals),
        "avg_volume_ratio":      _avg(vol_vals),
        "avg_52w_position_pct":  _avg(pos_vals),
        "ma_aligned_rate_pct":   round(ma_cnt / total * 100, 1),
        "avg_gap_pct":           _avg(gap_vals),
        "time_distribution":     time_dist,
        "minute_data_count":     minute_cnt,
        "prev3_bullish_rate_pct": round(prev3_cnt / minute_cnt * 100, 1) if minute_cnt > 0 else None,
    }

    # Gemini 분석 프롬프트
    detail_lines = "\n".join(
        f"- {ind.get('name','')}({ind['ticker']}): "
        f"RSI={ind['daily'].get('rsi','N/A')}, "
        f"거래량비율={ind['daily'].get('volume_ratio','N/A')}, "
        f"52주위치={ind['daily'].get('pos_52w_pct','N/A')}%, "
        f"MA정배열={'O' if ind['daily'].get('ma_aligned') else 'X'}, "
        f"갭={ind['daily'].get('gap_pct','N/A')}%, "
        f"매수시간대={ind['minute'].get('time_class','N/A')}, "
        f"이전3봉양봉={'O' if ind['minute'].get('prev3_bullish') else 'X'}, "
        f"수익률={ind['profit_pct']}%"
        for ind in indicators
    )

    prompt = f"""당신은 주식 매매 패턴 분석 전문가입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
아래는 한 투자자의 '리딩방' 출처 실매매 내역과 각 거래 시점의 기술적 지표입니다.

=== 집계 통계 ===
- 총 거래: {total}건 (분봉 데이터 활용 가능: {minute_cnt}건)
- 승률: {win_rate:.1f}%
- 평균 수익률: {avg_pct:.2f}%
- 평균 RSI(14) 매수 시점: {agg['avg_rsi_at_entry']}
- 평균 거래량비율 (20일 평균 대비): {agg['avg_volume_ratio']}배
- 평균 52주 위치: {agg['avg_52w_position_pct']}%
- MA 정배열(5>20>60) 비율: {agg['ma_aligned_rate_pct']}%
- 평균 당일 갭(%): {agg['avg_gap_pct']}%
- 매수 시간대 분포: {time_dist}
- 이전 3봉 양봉 비율: {agg['prev3_bullish_rate_pct']}%

=== 개별 거래 ===
{detail_lines}

위 데이터를 분석해 다음 5가지를 작성해주세요:

1. **매수 패턴 특징**: RSI 구간·거래량·시간대·MA 배열 등 반복 패턴
2. **승패 가르는 핵심 요인**: 수익/손실 거래의 구체적 차이
3. **종목 선정 특징**: 52주 위치·거래량·섹터 경향
4. **개선 권고사항**: 더 높은 승률을 위해 조정할 매수 조건
5. **리스크 경고**: 현재 패턴의 주요 위험 요소

투자자가 실제로 활용할 수 있는 구체적 인사이트로 작성해주세요."""

    try:
        response = _call_gemini(prompt, use_search=False, temperature=0.5, timeout_sec=90)
        narrative = _strip_hanja(response.text if hasattr(response, "text") else str(response))
    except Exception as e:
        narrative = f"AI 분석 오류: {str(e)}"

    return {
        "agg_stats": agg,
        "ai_narrative": narrative,
        "trades_summary": [
            {
                "ticker":     ind["ticker"],
                "name":       ind.get("name", ""),
                "profit_pct": ind["profit_pct"],
                "rsi":        ind["daily"].get("rsi"),
                "time_class": ind["minute"].get("time_class"),
            }
            for ind in indicators
        ],
    }


# ── 패턴 프로파일 빌드 & 저장 ────────────────────────────────────────────────

def build_pattern_profile(source: str = 'all') -> dict:
    """패턴 프로파일 빌드 및 DB 저장.
    source:
      'all'      — 전체 USER·AI_AGENT 거래 (v1 + v2 저장)
      'personal' — 리딩방 제외 개인 거래만 (v2 저장)
      'leading'  — 리딩방 거래만 (v2 저장)
    가중치: 기본 1배, 최근 30일 2배, 리딩방+screener_matched 추가 2배
    """
    from db import get_db_conn, save_pattern_profile, save_pattern_profile_v2
    from datetime import datetime, timedelta

    if source == 'personal':
        where = "WHERE UPPER(owner) IN ('USER','AI_AGENT') AND LOWER(COALESCE(trade_source,'')) NOT LIKE '%리딩방%'"
    elif source == 'leading':
        where = "WHERE UPPER(owner)='USER' AND LOWER(COALESCE(trade_source,'')) LIKE '%리딩방%'"
    else:
        where = "WHERE UPPER(owner) IN ('USER','AI_AGENT')"

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        f"""SELECT ticker, name, buy_price, sell_price, profit, profit_pct,
                  result, buy_date, sell_date, trade_source, owner,
                  COALESCE(screener_matched, 0) AS screener_matched
           FROM trade_history
           {where}
           ORDER BY sell_date DESC"""
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not rows:
        return {"error": "거래 기록 없음"}

    now = datetime.now()
    cutoff_recent = now - timedelta(days=30)

    # 각 거래에 지표 수집 (수익 거래 위주로 패턴 추출)
    win_indicators = []
    loss_indicators = []

    for r in rows:
        profit = float(r.get("profit", 0) or 0)
        ticker = str(r.get("ticker", "")).strip()
        buy_date = str(r.get("buy_date", "")).strip()
        if not ticker:
            continue

        ind = _get_trade_indicators(ticker, buy_date)

        sell_date_str = str(r.get("sell_date", ""))[:10]
        try:
            sell_dt = datetime.strptime(sell_date_str, "%Y-%m-%d")
            recency_bonus = 1 if sell_dt >= cutoff_recent else 0
        except Exception:
            recency_bonus = 0

        # 리딩방 + screener_matched: 스크리너 확인 신호로 2배 부스트
        is_screener_confirmed = (
            "리딩방" in str(r.get("trade_source", ""))
            and int(r.get("screener_matched", 0) or 0) == 1
        )
        weight = (1 + recency_bonus) * (2 if is_screener_confirmed else 1)

        for _ in range(weight):
            if profit > 0:
                win_indicators.append(ind)
            else:
                loss_indicators.append(ind)

    total = len(rows)
    win_count = sum(1 for r in rows if float(r.get("profit", 0) or 0) > 0)

    def _extract_range(indicators, key, sub="daily"):
        vals = [ind[sub].get(key) for ind in indicators if ind[sub].get(key) is not None]
        if not vals:
            return None
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        return {
            "min":    round(vals_sorted[0], 1),
            "max":    round(vals_sorted[-1], 1),
            "avg":    round(sum(vals_sorted) / n, 1),
            "p25":    round(vals_sorted[int(n * 0.25)], 1),
            "p75":    round(vals_sorted[int(n * 0.75)], 1),
        }

    # 승리 거래 패턴 지표
    win_rsi         = _extract_range(win_indicators, "rsi")
    win_vol_ratio   = _extract_range(win_indicators, "volume_ratio")
    win_pos_52w     = _extract_range(win_indicators, "pos_52w_pct")
    win_gap         = _extract_range(win_indicators, "gap_pct")
    win_ma_rate     = (sum(1 for ind in win_indicators if ind["daily"].get("ma_aligned")) / len(win_indicators) * 100) if win_indicators else 0

    win_time_dist: dict = {}
    for ind in win_indicators:
        tc = ind["minute"].get("time_class")
        if tc:
            win_time_dist[tc] = win_time_dist.get(tc, 0) + 1

    # 손실 거래 패턴 (반대로 피해야 할 조건 파악용)
    loss_rsi        = _extract_range(loss_indicators, "rsi")
    loss_vol_ratio  = _extract_range(loss_indicators, "volume_ratio")

    profile = {
        "total_trades":    total,
        "win_count":       win_count,
        "win_rate_pct":    round(win_count / total * 100, 1) if total else 0,
        "avg_profit_pct":  round(sum(float(r.get("profit_pct", 0) or 0) for r in rows) / total, 2) if total else 0,
        # 승리 패턴 지표
        "win": {
            "rsi":          win_rsi,
            "volume_ratio": win_vol_ratio,
            "pos_52w_pct":  win_pos_52w,
            "gap_pct":      win_gap,
            "ma_aligned_rate_pct": round(win_ma_rate, 1),
            "time_dist":    win_time_dist,
        },
        # 손실 패턴 (피해야 할 조건)
        "loss": {
            "rsi":          loss_rsi,
            "volume_ratio": loss_vol_ratio,
        },
        "data_sources": list(set(str(r.get("trade_source", "")) for r in rows)),
    }

    if source == 'all':
        save_pattern_profile(profile, total)
    save_pattern_profile_v2(profile, total, source)
    return profile


def _score_stock_against_profile(ind: dict, profile: dict) -> float:
    """종목 지표를 패턴 프로파일과 비교해 net 점수 반환 (0~100).

    - 승리 패턴과의 유사도에서 손실 패턴 페널티를 차감
    - 승률이 낮을수록 점수를 중립(50)으로 수렴시켜 과신 방지
    """
    if not profile or "win" not in profile:
        return 50.0

    win_rate    = profile.get("win_rate_pct", 50)
    trade_count = profile.get("total_trades", 0)

    # 데이터 부족 또는 승률 극히 낮으면 중립 반환
    if trade_count < 10 or win_rate < 30:
        return 50.0

    # 신뢰도 계수: 승률 30% → 0, 70% 이상 → 1.0 으로 선형 보간
    reliability = min(1.0, max(0.0, (win_rate - 30) / 40))

    def _range_score(val, rng):
        """해당 지표가 범위 내에 얼마나 부합하는지 0~100 반환"""
        if val is None or rng is None:
            return None
        p25, p75 = rng.get("p25"), rng.get("p75")
        avg = rng.get("avg")
        if p25 is None or p75 is None:
            return None
        span = (p75 - p25) or 1.0
        if p25 <= val <= p75:
            return 100.0
        elif avg is not None:
            dist = abs(val - avg)
            return max(0.0, 100.0 - (dist / span) * 80)
        return 0.0

    win  = profile["win"]
    loss = profile.get("loss", {})

    # ── 승리 패턴 점수 ──────────────────────────────────────────
    win_parts, win_weights = [], []

    s = _range_score(ind["daily"].get("rsi"),          win.get("rsi"))
    if s is not None: win_parts.append(s); win_weights.append(30)

    s = _range_score(ind["daily"].get("volume_ratio"), win.get("volume_ratio"))
    if s is not None: win_parts.append(s); win_weights.append(25)

    s = _range_score(ind["daily"].get("pos_52w_pct"),  win.get("pos_52w_pct"))
    if s is not None: win_parts.append(s); win_weights.append(20)

    s = _range_score(ind["daily"].get("gap_pct"),      win.get("gap_pct"))
    if s is not None: win_parts.append(s); win_weights.append(10)

    ma_win_rate = win.get("ma_aligned_rate_pct", 50) / 100
    ma_score    = (ma_win_rate * 100) if ind["daily"].get("ma_aligned") else ((1 - ma_win_rate) * 30)
    win_parts.append(ma_score); win_weights.append(15)

    total_w   = sum(win_weights)
    raw_win   = sum(s * w for s, w in zip(win_parts, win_weights)) / total_w if total_w else 50.0

    # ── 손실 패턴 페널티 ────────────────────────────────────────
    loss_parts, loss_weights = [], []

    s = _range_score(ind["daily"].get("rsi"),          loss.get("rsi"))
    if s is not None: loss_parts.append(s); loss_weights.append(30)

    s = _range_score(ind["daily"].get("volume_ratio"), loss.get("volume_ratio"))
    if s is not None: loss_parts.append(s); loss_weights.append(25)

    loss_total_w = sum(loss_weights)
    loss_score   = sum(s * w for s, w in zip(loss_parts, loss_weights)) / loss_total_w if loss_total_w else 0.0

    # 손실 패턴 유사도가 높을수록 최대 25점 차감
    penalty = loss_score * 0.25

    # ── 최종 점수 ───────────────────────────────────────────────
    # 승률이 낮으면 중립(50)으로 수렴 — 신뢰 없는 프로필이 결과를 왜곡하지 않도록
    net = raw_win - penalty
    final = 50 + (net - 50) * reliability

    return round(max(0.0, min(100.0, final)), 1)


def screen_by_my_pattern() -> dict:
    """오늘 거래량·등락률 상위 종목 중 패턴 프로파일(개인+리딩방 교집합)에 가장 가까운 종목을 추천합니다."""
    import requests as req_lib
    from db import load_pattern_profile, load_pattern_profile_v2

    # 1. 프로파일 로드 — v2(개인/리딩방 분리) 우선, 없으면 v1 폴백
    personal_profile = load_pattern_profile_v2('personal')
    leading_profile  = load_pattern_profile_v2('leading')
    dual_mode = (
        personal_profile and personal_profile.get('total_trades', 0) >= 5 and
        leading_profile  and leading_profile.get('total_trades', 0) >= 5
    )

    profile = load_pattern_profile()
    if not profile:
        profile = build_pattern_profile('all')
        if "error" in profile:
            return {"error": profile["error"]}

    # 1-b. 프로필 신뢰도 검증
    win_rate    = profile.get("win_rate_pct", 0)
    trade_count = profile.get("total_trades", 0)

    if trade_count < 15:
        return {
            "error": f"거래 데이터 부족 ({trade_count}건). 최소 15건 이상의 완료된 거래가 있어야 패턴이 의미 있게 작동합니다.",
            "profile_warning": "data_insufficient",
        }
    if win_rate < 40:
        return {
            "error": (
                f"패턴 프로필 신뢰도 낮음 (승률 {win_rate}%). "
                "승률이 40% 미만이면 스크리너가 오히려 손실 패턴을 반복 추천할 수 있습니다. "
                "거래 전략을 먼저 점검해보세요."
            ),
            "profile_warning": "low_win_rate",
            "win_rate": win_rate,
            "total_trades": trade_count,
        }

    # 40~50%: 경고 포함해서 계속 진행
    reliability_warning = None
    if win_rate < 50:
        reliability_warning = f"승률 {win_rate}% — 참고용으로만 활용하세요 (손실 패턴 페널티 적용 중)"

    # 2. 오늘 거래량·등락률 상위 종목 수집
    candidates: dict[str, dict] = {}

    BASE = "http://127.0.0.1:8000"
    def _extract_code(item: dict) -> str:
        raw = item.get("종목코드") or item.get("code") or item.get("ticker") or ""
        return str(raw).strip().zfill(6)

    def _extract_name(item: dict) -> str:
        return str(item.get("종목명") or item.get("name") or "")

    try:
        vol_r = req_lib.get(f"{BASE}/api/kr/volume-ranking?market=ALL", timeout=10,
                            headers={"ngrok-skip-browser-warning": "69420"})
        for item in (vol_r.json() if vol_r.ok else []):
            code = _extract_code(item)
            if code and code != "000000":
                candidates[code] = {"code": code, "name": _extract_name(item), "signal": "volume"}
    except Exception as e:
        print(f"[screener] volume-ranking 오류: {e}")

    try:
        chg_r = req_lib.get(f"{BASE}/api/kr/change-ranking?market=ALL&direction=up", timeout=10,
                            headers={"ngrok-skip-browser-warning": "69420"})
        for item in (chg_r.json() if chg_r.ok else []):
            code = _extract_code(item)
            if code and code != "000000":
                if code in candidates:
                    candidates[code]["signal"] = "both"
                else:
                    candidates[code] = {"code": code, "name": _extract_name(item), "signal": "change"}
    except Exception as e:
        print(f"[screener] change-ranking 오류: {e}")

    if not candidates:
        return {"error": "시장 데이터를 가져오지 못했습니다. 백엔드 서버가 실행 중인지 확인해주세요."}

    # 3. 각 종목 지표 수집 + 패턴 매칭 점수 계산
    scored: list[dict] = []
    for code, meta in list(candidates.items())[:50]:   # 최대 50개로 제한
        ind = _get_trade_indicators(code, "")           # buy_date 없이 일봉만
        if dual_mode:
            p_score = _score_stock_against_profile(ind, personal_profile)
            l_score = _score_stock_against_profile(ind, leading_profile)
            match_score = round((p_score * l_score) ** 0.5, 1)  # 기하평균: 둘 다 높아야 높은 점수
        else:
            p_score = None
            l_score = None
            match_score = _score_stock_against_profile(ind, profile)
        if meta.get("signal") == "both":
            match_score = min(100, match_score + 8)
        scored.append({
            "code":           code,
            "name":           meta["name"],
            "signal":         meta["signal"],
            "match_score":    match_score,
            "personal_score": p_score,
            "leading_score":  l_score,
            "rsi":            ind["daily"].get("rsi"),
            "vol_ratio":      ind["daily"].get("volume_ratio"),
            "pos_52w":        ind["daily"].get("pos_52w_pct"),
            "ma_aligned":     ind["daily"].get("ma_aligned"),
            "gap_pct":        ind["daily"].get("gap_pct"),
        })

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    top = scored[:8]

    if not top:
        return {"error": "매칭 종목 없음"}

    # 4. Gemini 최종 판단
    if dual_mode:
        profile_summary = (
            f"[개인 패턴] 승률 {personal_profile.get('win_rate_pct')}% / 평균수익률 {personal_profile.get('avg_profit_pct')}% / "
            f"RSI {personal_profile['win'].get('rsi',{}).get('p25','?')}~{personal_profile['win'].get('rsi',{}).get('p75','?')}\n"
            f"[리딩방 패턴] 승률 {leading_profile.get('win_rate_pct')}% / 평균수익률 {leading_profile.get('avg_profit_pct')}% / "
            f"RSI {leading_profile['win'].get('rsi',{}).get('p25','?')}~{leading_profile['win'].get('rsi',{}).get('p75','?')}\n"
            f"[교집합 스코어] 개인×리딩방 기하평균으로 계산 — 양쪽 모두 높아야 높은 점수"
        )
    else:
        profile_summary = (
            f"승률 {profile.get('win_rate_pct')}% / "
            f"평균수익률 {profile.get('avg_profit_pct')}% / "
            f"성공 RSI 구간 {profile['win'].get('rsi', {}).get('p25','?')}~{profile['win'].get('rsi', {}).get('p75','?')} / "
            f"거래량비율 {profile['win'].get('volume_ratio', {}).get('p25','?')}~{profile['win'].get('volume_ratio', {}).get('p75','?')}배 / "
            f"MA정배열 비율 {profile['win'].get('ma_aligned_rate_pct','?')}%"
        )
    candidates_text = "\n".join(
        f"- {s['name']}({s['code']}): 매칭점수={s['match_score']}, RSI={s['rsi']}, "
        f"거래량비율={s['vol_ratio']}배, 52주위치={s['pos_52w']}%, "
        f"MA정배열={'O' if s['ma_aligned'] else 'X'}, 갭={s['gap_pct']}%, 신호={s['signal']}"
        for s in top
    )

    prompt = f"""당신은 퀀트 트레이딩 AI입니다.\n절대로 한자(漢字)를 사용하지 마세요. 모든 출력은 한글과 영문만 사용하세요.
아래는 한 투자자의 과거 성공 매매 패턴 요약과 오늘 시장에서 그 패턴에 가장 근접한 후보 종목들입니다.

=== 나의 성공 패턴 프로파일 ===
{profile_summary}

=== 오늘 패턴 매칭 후보 종목 (매칭점수 높은 순) ===
{candidates_text}

위 데이터를 바탕으로:
1. 지금 당장 진입을 고려할 TOP 3 종목을 선정하고 이유를 설명하세요 (매칭점수 + 오늘의 모멘텀 + 차트 신호 종합)
2. 각 종목의 예상 단기 진입 가격대와 손절 기준을 제시하세요
3. 주의해야 할 리스크 1가지씩 언급하세요

단기 모멘텀 트레이딩 관점에서 구체적이고 실전적으로 답해주세요."""

    try:
        response = _call_gemini(prompt, use_search=True, temperature=0.4, timeout_sec=60)
        narrative = _strip_hanja(response.text if hasattr(response, "text") else str(response))
    except Exception as e:
        narrative = f"AI 분석 오류: {str(e)}"

    return {
        "profile_summary": {
            "win_rate_pct":      profile.get("win_rate_pct"),
            "avg_profit_pct":    profile.get("avg_profit_pct"),
            "total_trades":      profile.get("total_trades"),
            "updated_time":      profile.get("_updated_time"),
            "reliability_warning": reliability_warning,
            "dual_mode":         dual_mode,
            "personal_trades":   personal_profile.get("total_trades") if dual_mode else None,
            "leading_trades":    leading_profile.get("total_trades") if dual_mode else None,
        },
        "top_picks":    top[:5],
        "ai_narrative": narrative,
    }


# ── ② 수급 이동 시퀀스 패턴 빌드 ─────────────────────────────────────────────

def build_supply_flow_patterns() -> dict:
    """리딩방 거래 시퀀스에서 A→B 수급 이동 패턴을 추출하고 DB에 저장합니다."""
    from db import get_db_conn, save_supply_flow_patterns
    from datetime import datetime, timedelta

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT ticker, name, buy_date, sell_date
           FROM trade_history
           WHERE LOWER(COALESCE(trade_source,'')) LIKE '%리딩방%'
             AND buy_date != '' AND sell_date != ''
           ORDER BY sell_date ASC"""
    )
    trades = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if len(trades) < 3:
        return {"error": "리딩방 거래 데이터 부족 (최소 3건 필요)"}

    patterns: dict = {}
    for i, t1 in enumerate(trades):
        for t2 in trades[i + 1:]:
            if t1["ticker"] == t2["ticker"]:
                continue
            try:
                sell_d = datetime.strptime(str(t1["sell_date"])[:10], "%Y-%m-%d")
                buy_d  = datetime.strptime(str(t2["buy_date"])[:10], "%Y-%m-%d")
                gap = (buy_d - sell_d).days
                if not (0 <= gap <= 7):
                    continue
                key = f"{t1['ticker']}→{t2['ticker']}"
                if key not in patterns:
                    patterns[key] = {
                        "from_ticker": t1["ticker"], "from_name": t1["name"],
                        "to_ticker":   t2["ticker"], "to_name":   t2["name"],
                        "count": 0, "days_list": [], "last_observed": ""
                    }
                patterns[key]["count"] += 1
                patterns[key]["days_list"].append(gap)
                patterns[key]["last_observed"] = str(t1["sell_date"])[:10]
            except Exception:
                continue

    result = [
        {**{k: v for k, v in p.items() if k != "days_list"},
         "avg_days": round(sum(p["days_list"]) / len(p["days_list"]), 1)}
        for p in patterns.values() if p["count"] >= 1
    ]
    result.sort(key=lambda x: x["count"], reverse=True)
    save_supply_flow_patterns(result)
    return {"patterns": result, "total": len(result)}


# ── ③ 실시간 수급 이동 감지 ──────────────────────────────────────────────────

def detect_realtime_supply_rotation() -> dict:
    """오늘의 거래량·등락률 데이터 + 뉴스 + 과거 수급 패턴으로 실시간 수급 이동을 분석합니다."""
    import requests as req_lib
    from db import load_supply_flow_patterns

    BASE = "http://127.0.0.1:8000"
    headers = {"ngrok-skip-browser-warning": "69420"}

    def _safe_get(url):
        try:
            r = req_lib.get(url, timeout=10, headers=headers)
            return r.json() if r.ok else []
        except Exception:
            return []

    vol_up  = _safe_get(f"{BASE}/api/kr/volume-ranking?market=ALL")
    chg_up  = _safe_get(f"{BASE}/api/kr/change-ranking?market=ALL&direction=up")
    chg_dn  = _safe_get(f"{BASE}/api/kr/change-ranking?market=ALL&direction=down")
    sectors = _safe_get(f"{BASE}/api/kr/hot-sectors")

    # 외국인·기관 순매수/순매도 TOP 10 (KOSPI/KOSDAQ 각각)
    try:
        from data_kr import get_kr_frgn_inst_rank
        kospi_buy   = get_kr_frgn_inst_rank("J", top_n=10, sort="buy")  or []
        kospi_sell  = get_kr_frgn_inst_rank("J", top_n=10, sort="sell") or []
        kosdaq_buy  = get_kr_frgn_inst_rank("Q", top_n=10, sort="buy")  or []
        kosdaq_sell = get_kr_frgn_inst_rank("Q", top_n=10, sort="sell") or []
    except Exception as e:
        print(f"[supply rotation] 외국인/기관 데이터 실패: {e}")
        kospi_buy = kospi_sell = kosdaq_buy = kosdaq_sell = []

    known_patterns = load_supply_flow_patterns()

    def _fmt(items, key_name, key_val, n=12):
        lines = []
        for s in items[:n]:
            name = s.get("종목명") or s.get("name","?")
            code = s.get("종목코드") or s.get("code","")
            val  = s.get(key_val, "")
            lines.append(f"- {name}({code}): {key_name} {val}")
        return "\n".join(lines) if lines else "(없음)"

    vol_text    = _fmt(vol_up,  "거래량", "거래량")
    chg_up_text = _fmt(chg_up, "등락률", "등락률")
    chg_dn_text = _fmt(chg_dn, "등락률", "등락률")

    def _fmt_inst(items, n=8):
        lines = []
        for s in items[:n]:
            name = s.get("종목명","?")
            code = s.get("종목코드","")
            frgn = s.get("외국인순매수", 0)
            orgn = s.get("기관순매수", 0)
            total = frgn + orgn
            sign = "+" if total >= 0 else ""
            lines.append(f"- {name}({code}): 외인 {frgn:,}주 / 기관 {orgn:,}주 / 합계 {sign}{total:,}주")
        return "\n".join(lines) if lines else "(데이터 없음)"

    kospi_buy_text   = _fmt_inst(kospi_buy)
    kospi_sell_text  = _fmt_inst(kospi_sell)
    kosdaq_buy_text  = _fmt_inst(kosdaq_buy)
    kosdaq_sell_text = _fmt_inst(kosdaq_sell)

    sector_list = sectors.get("sectors", []) if isinstance(sectors, dict) else []
    hot_text = "\n".join(
        f"- {s.get('sector','?')}: 핫스코어 {s.get('hot_score','?')}"
        for s in sorted(sector_list, key=lambda x: x.get("hot_score",0), reverse=True)[:8]
    ) if sector_list else "(없음)"

    flow_text = ""
    if known_patterns:
        flow_text = "\n=== 과거 리딩방 수급 이동 패턴 ===\n" + "\n".join(
            f"- {p['from_name']}({p['from_ticker']}) → {p['to_name']}({p['to_ticker']}): {p['observed_count']}회 관찰, 평균 {p['avg_days']}일 후"
            for p in known_patterns[:10]
        )

    prompt = f"""당신은 주식 수급 분석 전문가입니다. 절대로 한자를 사용하지 마세요.
오늘의 실시간 시장 데이터와 뉴스를 분석해 수급 이동 흐름을 파악해주세요.
**특히 외국인·기관 순매수/순매도 데이터를 핵심 신호로 활용하세요. 단순 거래량만으로는 단타 개인 자금일 수 있지만, 외인·기관 매수가 동반되면 진짜 주포 진입 신호입니다.**

=== 오늘 거래량 상위 종목 ===
{vol_text}

=== 등락률 상위 (상승) ===
{chg_up_text}

=== 등락률 상위 (하락/소화) ===
{chg_dn_text}

=== [핵심] 외국인·기관 순매수 TOP (KOSPI) ===
{kospi_buy_text}

=== [핵심] 외국인·기관 순매도 TOP (KOSPI) ===
{kospi_sell_text}

=== [핵심] 외국인·기관 순매수 TOP (KOSDAQ) ===
{kosdaq_buy_text}

=== [핵심] 외국인·기관 순매도 TOP (KOSDAQ) ===
{kosdaq_sell_text}

=== 섹터 핫스코어 ===
{hot_text}
{flow_text}

위 데이터와 오늘의 뉴스·이슈를 종합하여 다음 5가지를 분석해주세요:

1. **주포 진입 종목/섹터** — 외인·기관 순매수 TOP 중 진짜 자금 유입 신호가 강한 곳 (단순 거래량 급증 vs 외인·기관 동반 매수 구분)
2. **주포 이탈 종목/섹터** — 외인·기관 순매도 TOP 중 자금 빠지는 곳 (개인 매수만 남은 위험 신호)
3. **수급 이동 시나리오** — 어느 종목/섹터에서 어디로 외인·기관 자금이 옮겨가고 있는지
4. **가짜 수급 vs 진짜 수급** — 거래량은 폭증했지만 외인·기관은 빠지는 종목 (단타 개미 집중) 경고
5. **과거 패턴 매칭** — 과거 수급 이동 패턴 중 오늘 상황과 유사한 사례 언급

실전 투자자가 즉시 활용할 수 있는 구체적인 분석을 해주세요."""

    try:
        response = _call_gemini(prompt, use_search=False, temperature=0.5, timeout_sec=90)
        raw = response.text if hasattr(response, "text") and response.text else str(response)
        narrative = _strip_hanja(raw)
    except Exception as e:
        narrative = f"AI 분석 오류: {str(e)}"

    return {
        "narrative":       narrative,
        "vol_ranking":     vol_up[:12],
        "chg_up":          chg_up[:10],
        "chg_dn":          chg_dn[:10],
        "known_patterns":  known_patterns[:10],
        "frgn_inst": {
            "kospi_buy":   kospi_buy[:8],
            "kospi_sell":  kospi_sell[:8],
            "kosdaq_buy":  kosdaq_buy[:8],
            "kosdaq_sell": kosdaq_sell[:8],
        },
    }

