import asyncio
import logging
from db import load_price_alerts, update_price_alert_status
from telegram_bot import send_price_alert
import api.routers.market_kr as market_kr
import api.routers.market_us as market_us

logger = logging.getLogger(__name__)

async def price_alert_loop():
    """주기적으로 가격 알림을 확인하고 텔레그램으로 발송하는 백그라운드 태스크"""
    logger.info("Price alert background task started.")
    while True:
        try:
            # 1. 활성 알림 로드
            alerts = await asyncio.to_thread(load_price_alerts)
            if not alerts:
                await asyncio.sleep(60)
                continue

            # 2. 시장별로 티커 분리
            kr_tickers = set(a["ticker"] for a in alerts if a["market"] == "국내")
            us_tickers = set(a["ticker"] for a in alerts if a["market"] == "미국")

            current_prices = {}

            # 3. 현재가 조회 (동시 요청 최소화를 위해 하나씩 조회하거나 멀티플렉싱)
            # 여기서는 편의상 하나씩 조회 (api 라우터 재사용)
            for t in kr_tickers:
                try:
                    res = await asyncio.to_thread(market_kr.kr_stock_price, t)
                    if res and res.get("price"):
                        current_prices[t] = res["price"]
                except Exception as e:
                    logger.warning(f"Failed to fetch KR price for {t}: {e}")
                    
            for t in us_tickers:
                try:
                    res = await asyncio.to_thread(market_us.us_stock_detail, t)
                    if res and res.get("price"):
                        current_prices[t] = res["price"]
                except Exception as e:
                    logger.warning(f"Failed to fetch US price for {t}: {e}")

            # 4. 조건 확인 및 발송
            for alert in alerts:
                ticker = alert["ticker"]
                cp = current_prices.get(ticker)
                if cp is None:
                    continue
                
                tp = alert["target_price"]
                alert_type = alert["alert_type"]
                
                triggered = False
                
                # 목표가 도달 (상승 돌파/매수진입/하락돌파 등의 조건 해석)
                if alert_type in ["목표가 도달", "상승돌파", "AI목표가 도달"] and cp >= tp:
                    triggered = True
                elif alert_type in ["손절가 도달", "하락돌파", "매수진입", "AI손절가 도달", "AI매수가 도달"] and cp <= tp:
                    triggered = True

                if triggered:
                    # 알림 소유자의 텔레그램 챗으로 발송 (없으면 전역 기본=관리자)
                    owner = alert.get("owner") or ""
                    chat_id = None
                    if owner:
                        try:
                            from api.auth import get_telegram_chat_id
                            chat_id = await asyncio.to_thread(get_telegram_chat_id, owner) or None
                        except Exception:
                            chat_id = None
                    success = await asyncio.to_thread(
                        send_price_alert,
                        alert["market"], ticker, alert["name"],
                        alert_type, cp, tp, chat_id
                    )

                    if success:
                        # 발송 성공 시 상태 완료 처리 (소유자 스코프)
                        await asyncio.to_thread(
                            update_price_alert_status,
                            ticker, alert_type, "완료", owner or None
                        )
                        logger.info(f"Alert sent to '{owner}' and marked completed for {ticker} ({alert_type})")

        except Exception as e:
            logger.error(f"Error in price alert loop: {e}")
        
        # 1분(60초) 대기
        await asyncio.sleep(60)
