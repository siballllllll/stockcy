import traceback
import logging

def send_daily_brief_to_telegram(status_callback=None) -> dict:
    """
    유저의 즐겨찾기 종목을 바탕으로 AI 매크로 브리핑을 생성하여 텔레그램으로 전송합니다.
    (UI에서 백그라운드 스레드로 실행됨)
    """
    def _update_status(msg):
        if status_callback:
            status_callback(msg)

    try:
        from db import get_favorites
        _update_status("⭐ 즐겨찾기 포트폴리오 정보를 가져오는 중...")
        favorites = get_favorites()
        if not favorites:
            return {"success": False, "msg": "⭐ 즐겨찾기에 등록된 종목이 없습니다."}

        # 시세 데이터 수집
        portfolio_info = []
        for fav in favorites:
            market = fav.get("market_type", "")
            code = fav.get("ticker", "")
            name = fav.get("name", "")
            
            if market == "국내 주식 🇰🇷":
                try:
                    _update_status(f"📊 국내 주식 시세 수집 중... ({name})")
                    from data_kr import get_kr_stock_price
                    price_data = get_kr_stock_price(code)
                    if price_data:
                        portfolio_info.append(f"- [국내] {name} ({code}): {price_data.get('price', 0):,}원 (등락률: {price_data.get('change_pct', 0)}%)")
                except Exception:
                    pass
            else:
                try:
                    _update_status(f"📈 미국 주식 시세 수집 중... ({name})")
                    from data import get_us_stock_detail
                    us_data = get_us_stock_detail(code)
                    if us_data:
                        portfolio_info.append(f"- [미국] {name} ({code}): ${us_data.get('price', 0):.2f} (등락률: {us_data.get('change_pct', 0)}%)")
                except Exception:
                    pass

        if not portfolio_info:
            return {"success": False, "msg": "종목의 시세 데이터를 가져오지 못했습니다."}

        portfolio_str = "\n".join(portfolio_info)

        # AI 브리핑 프롬프트 생성
        prompt = f"""당신은 세계 최고의 프라이빗 뱅커이자 매크로 분석가입니다.
오늘 하루의 핵심 거시경제 뉴스(매크로 이슈)를 간략히 요약하고, 그 이슈들이 아래의 고객 포트폴리오(즐겨찾기 종목)에 어떤 영향을 미쳤는지, 그리고 내일은 어떻게 대응해야 할지 직관적인 브리핑 리포트를 작성해주세요.

[고객 포트폴리오 현황]
{portfolio_str}

작성 규칙:
1. 텔레그램 메신저로 전송될 것이므로 가독성 좋게 이모지를 적극 활용하세요.
2. 마크다운의 *, _ 등 텔레그램에서 파싱 오류를 낼 수 있는 특수문자 포맷팅은 최대한 자제하고 플레인 텍스트와 이모지로 단락을 구분하세요. (볼드체만 제한적으로 사용)
3. 3가지 섹션으로 나누세요: 
   - 🌎 오늘의 매크로 브리핑
   - 💼 포트폴리오 진단
   - 🎯 내일의 투자 시나리오
"""
        
        # AI 엔진 호출 (구글 검색 활성화하여 최신 뉴스 반영)
        _update_status("🤖 구글 검색으로 최신 거시경제 뉴스를 반영하여 포트폴리오 맞춤 리포트를 작성 중입니다... (가장 오래 걸림)")
        from ai_engine import _call_gemini
        brief_text = _call_gemini(prompt, use_search=True, temperature=0.7)
        if not brief_text or "Error" in brief_text:
            return {"success": False, "msg": "AI 브리핑 생성에 실패했습니다."}

        # 텔레그램 전송
        from telegram_bot import send_message, is_configured
        if not is_configured():
            return {"success": False, "msg": "텔레그램 봇이 설정되지 않았습니다. secrets.toml을 확인해주세요."}
            
        header = "🤖 **[스톡시 Daily 개인화 브리핑]**\n\n"
        final_msg = header + brief_text

        # 텔레그램은 기본적으로 HTML이나 Markdown을 파싱하는데 오류가 잘 나므로 일반 텍스트 전송
        _update_status("💌 작성 완료! 텔레그램으로 브리핑을 발송합니다...")
        sent = send_message(final_msg)
        if sent:
            return {"success": True, "msg": "💌 장 마감 AI 리포트가 텔레그램으로 발송되었습니다!"}
        else:
            return {"success": False, "msg": "텔레그램 발송에 실패했습니다."}

    except Exception as e:
        logging.error(f"daily_brief error: {e}")
        return {"success": False, "msg": f"오류 발생: {e}"}
