import asyncio
import logging
from datetime import datetime
from db import (
    load_favorites,
    load_portfolio_from_gsheet,
    save_portfolio_to_gsheet,
    save_trade_record,
    _get_spreadsheet,
    _get_or_create_worksheet,
    log_agent_scan
)
from ai_engine import analyze_autonomous_trading
from telegram_bot import send_message as send_price_alert

logger = logging.getLogger("ai_agent")
logger.setLevel(logging.INFO)

# AI 모의투자용 소유자 이름
AI_OWNER_NAME = "AI_AGENT"

def _get_usd_krw_rate() -> float:
    """USD/KRW 환율 조회: SQLite 캐시 → KIS API → yfinance(timeout=1.5) 폴백 순서."""
    # 1차: data.py 환율 함수 우선 사용 (SQLite 캐시 내장)
    try:
        from data import get_usdkrw_rate
        rate = get_usdkrw_rate()
        if rate and rate > 0:
            return float(rate)
    except Exception:
        pass
    
    # 2차: yfinance 폴백 (타임아웃 1.5초 강제 지정)
    try:
        import yfinance as yf
        raw = yf.download("USDKRW=X", period="2d", progress=False, timeout=1.5)
        if not raw.empty:
            rate = float(raw["Close"].dropna().iloc[-1])
            if rate > 0:
                return rate
    except Exception:
        pass
    return 1350.0

def _is_market_open(market: str) -> bool:
    """한국장/미국장의 실제 개장 및 영업 시간인지 정밀 판정 (주말, 공휴일 및 대체휴일 철저히 배제)"""
    from datetime import datetime, timedelta, timezone
    
    # UTC 기준 현재 시간
    now_utc = datetime.now(timezone.utc)
    
    # 1. 한국 시간 (KST: UTC + 9)
    now_kst = now_utc + timedelta(hours=9)
    today_kst_str = now_kst.strftime("%Y-%m-%d")
    
    # 주말(토, 일)은 장이 열리지 않음
    if now_kst.weekday() in [5, 6]:
        return False
        
    # 2026년 한국 거래소(KRX) 공식 지정 휴장일 리스트
    kr_holidays = {
        "2026-01-01",  # 신정
        "2026-02-16", "2026-02-17", "2026-02-18",  # 설날 연휴
        "2026-03-01",  # 삼일절
        "2026-03-02",  # 삼일절 대체공휴일
        "2026-05-05",  # 어린이날
        "2026-05-24",  # 석가탄신일
        "2026-05-25",  # 석가탄신일 대체공휴일 (★오늘!)
        "2026-06-06",  # 현충일
        "2026-08-15",  # 광복절
        "2026-08-17",  # 광복절 대체공휴일
        "2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28", # 추석 연휴 및 대체공휴일
        "2026-10-03",  # 개천절
        "2026-10-09",  # 한글날
        "2026-12-25",  # 성탄절
        "2026-12-31"   # 연말 휴장일
    }
    
    # 2. 미국 시간 (NY: 서머타임 판정 적용)
    def is_dst(dt: datetime) -> bool:
        dst_start = datetime(dt.year, 3, 8) + timedelta(days=(6 - datetime(dt.year, 3, 8).weekday()) % 7)
        dst_start = dst_start.replace(hour=2)
        dst_end = datetime(dt.year, 11, 1) + timedelta(days=(6 - datetime(dt.year, 11, 1).weekday()) % 7)
        dst_end = dst_end.replace(hour=2)
        dt_naive = dt.replace(tzinfo=None)
        return dst_start <= dt_naive < dst_end

    ny_offset = -4 if is_dst(now_utc) else -5
    now_ny = now_utc + timedelta(hours=ny_offset)
    today_ny_str = now_ny.strftime("%Y-%m-%d")
    
    # 미국 정규장 평일 주말 체크
    if now_ny.weekday() in [5, 6]:
        return False
        
    # 2026년 미국 공식 주식시장(NYSE/NASDAQ) 휴장일 리스트
    us_holidays = {
        "2026-01-01",  # New Year's Day
        "2026-01-19",  # Martin Luther King Jr. Day
        "2026-02-16",  # Washington's Birthday (Presidents' Day)
        "2026-04-03",  # Good Friday
        "2026-05-25",  # Memorial Day (★오늘!)
        "2026-06-19",  # Juneteenth National Independence Day
        "2026-07-03",  # Independence Day Observed
        "2026-07-04",  # Independence Day
        "2026-09-07",  # Labor Day
        "2026-11-26",  # Thanksgiving Day
        "2026-12-25"   # Christmas Day
    }
    
    if market == "국내":
        if today_kst_str in kr_holidays:
            return False
        # 한국 정규장 시간: 09:00 ~ 15:30
        start_time = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
        end_time = now_kst.replace(hour=15, minute=30, second=0, microsecond=0)
        if not (start_time <= now_kst <= end_time):
            return False
            
        # [2중 보안 락] 실제 대한민국 당일 시세 데이터의 생동성(Freshness) 최종 확인
        try:
            from data_kr import get_kr_minute_chart
            df = get_kr_minute_chart("005930", interval=5)
            if not df.empty:
                last_dt = df["datetime"].iloc[-1]
                if last_dt.date() != now_kst.date():
                    # 마지막 실시간 캔들 데이터의 날짜가 오늘과 다르면 실제 장이 열리지 않은 휴장 상태임
                    return False
        except Exception:
            pass
            
        return True
        
    elif market == "미국":
        if today_ny_str in us_holidays:
            return False
        # 미국 정규장 시간: 현지 시간 09:30 ~ 16:00
        start_time = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
        end_time = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        if not (start_time <= now_ny <= end_time):
            return False
            
        # [2중 보안 락] 실제 미국 당일 시세 데이터의 생동성(Freshness) 최종 확인
        try:
            from data_kr import get_us_minute_chart
            df = get_us_minute_chart("SPY", interval=5)
            if not df.empty:
                last_dt = df["datetime"].iloc[-1]
                if last_dt.date() != now_ny.date():
                    # 마지막 실시간 캔들 데이터의 날짜가 미국 오늘과 다르면 실제 휴장 상태임
                    return False
        except Exception:
            pass
            
        return True
        
    return False

def _get_today_buy_count() -> int:
    """KST 기준 오늘(당일) AI 에이전트가 실제로 실행한 매수(BUY) 성공 건수를 조회합니다."""
    try:
        from db import get_db_conn
        conn = get_db_conn()
        cursor = conn.cursor()
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM ai_scan_logs WHERE SUBSTR(scan_time, 1, 10) = ? AND action = 'BUY' AND reason NOT LIKE '%자금 부족%' AND reason NOT LIKE '%보류%'",
            (today_str,)
        )
        row = cursor.fetchone()
        count = row["cnt"] if row else 0
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Failed to get today's buy count: {e}")
        return 0

async def ai_trading_loop():
    """AI 자율 매매 에이전트 메인 루프 (주기적 실행)"""
    logger.info("🤖 AI Trading Agent Loop Started")
    
    # 30분 주기로 관찰하여 단기 시장 노이즈 배제 (스윙/데이 트레이딩 템포)
    INTERVAL_SECONDS = 1800  
    
    while True:
        try:
            kr_open = _is_market_open("국내")
            us_open = _is_market_open("미국")

            if not kr_open and not us_open:
                logger.info("AI Agent: 모든 시장 휴장 중. 스캔 건너뜀.")
                await asyncio.sleep(INTERVAL_SECONDS)
                continue

            logger.info(f"🔍 AI Agent: 시장 스캔 시작... (국내: {'개장' if kr_open else '휴장'}, 미국: {'개장' if us_open else '휴장'})")

            # 1. 감시 대상 종목 로드 및 동적 시장 주도주 우주(Universe) 결합
            # (사용자 즐겨찾기 + 실시간 국내/미국 거래대금 상위 + 상승률 상위)
            favorites, _ = load_favorites()
            if not favorites:
                favorites = []

            scan_universe = []
            seen_tickers = set()

            # (1) 사용자 즐겨찾기 최우선 추가
            for fav in favorites:
                ticker = fav.get("티커", "")
                if ticker and ticker not in seen_tickers:
                    seen_tickers.add(ticker)
                    scan_universe.append({
                        "티커": ticker,
                        "종목명": fav.get("종목명", ticker),
                        "시장": fav.get("시장", "국내"),
                        "source": "FAVORITE"
                    })

            if kr_open:
                # (2) 국내 실시간 거래대금 상위 5개 추가
                try:
                    from data_kr import get_kr_volume_ranking
                    kr_vols = get_kr_volume_ranking() or []
                    for item in kr_vols[:5]:
                        code = item.get("종목코드", "")
                        if code and code not in seen_tickers:
                            seen_tickers.add(code)
                            scan_universe.append({
                                "티커": code,
                                "종목명": item.get("종목명", code),
                                "시장": "국내",
                                "source": "KR_HOT_VOLUME"
                            })
                except Exception as e:
                    logger.error(f"Failed to fetch KR volume ranking: {e}")

                # (3) 국내 실시간 등락률 상위 5개 추가 (코스피 3개 + 코스닥 3개)
                try:
                    from data_kr import get_kr_change_ranking
                    kr_changes_j = get_kr_change_ranking(market="J") or []
                    kr_changes_q = get_kr_change_ranking(market="Q") or []
                    for item in kr_changes_j[:3] + kr_changes_q[:3]:
                        code = item.get("종목코드", "")
                        if code and code not in seen_tickers:
                            seen_tickers.add(code)
                            scan_universe.append({
                                "티커": code,
                                "종목명": item.get("종목명", code),
                                "시장": "국내",
                                "source": "KR_HOT_CHANGE"
                            })
                except Exception as e:
                    logger.error(f"Failed to fetch KR change ranking: {e}")

            if us_open:
                # (4) 미국 실시간 거래대금 상위 5개 추가
                try:
                    from data_kr import get_us_volume_ranking
                    us_vols = get_us_volume_ranking() or []
                    for item in us_vols[:5]:
                        ticker = item.get("티커", "")
                        if ticker and ticker not in seen_tickers:
                            seen_tickers.add(ticker)
                            scan_universe.append({
                                "티커": ticker,
                                "종목명": ticker,
                                "시장": "미국",
                                "source": "US_HOT_VOLUME"
                            })
                except Exception as e:
                    logger.error(f"Failed to fetch US volume ranking: {e}")

                # (5) 미국 실시간 등락률 상위 5개 추가
                try:
                    from data_kr import get_us_change_ranking
                    us_changes = get_us_change_ranking() or []
                    for item in us_changes[:5]:
                        ticker = item.get("티커", "")
                        if ticker and ticker not in seen_tickers:
                            seen_tickers.add(ticker)
                            scan_universe.append({
                                "티커": ticker,
                                "종목명": ticker,
                                "시장": "미국",
                                "source": "US_HOT_CHANGE"
                            })
                except Exception as e:
                    logger.error(f"Failed to fetch US change ranking: {e}")
            
            if not scan_universe:
                logger.info("AI Agent: 스캔할 감시 대상 종목이 없습니다. 대기...")
                await asyncio.sleep(INTERVAL_SECONDS)
                continue
                
            # 2. AI의 현재 포트폴리오(보유 종목) 조회
            ai_portfolio = load_portfolio_from_gsheet(owner=AI_OWNER_NAME)
            ai_holdings = {p["ticker"]: p for p in ai_portfolio}
            
            # 3. 각 종목 순회하며 AI 판단 요청
            from data_kr import get_kr_stock_price
            from data import get_us_stock_detail
            
            for fav in scan_universe:
                market = fav.get("시장", "국내")
                ticker = fav.get("티커", "")
                name = fav.get("종목명", ticker)
                source_type = fav.get("source", "FAVORITE")
                
                source_korean = {
                    "FAVORITE": "즐겨찾기",
                    "KR_HOT_VOLUME": "국내 거래대금 핫종목",
                    "KR_HOT_CHANGE": "국내 상승률 핫종목",
                    "US_HOT_VOLUME": "미국 거래대금 핫종목",
                    "US_HOT_CHANGE": "미국 상승률 핫종목"
                }.get(source_type, "주도주")
                
                if not ticker: continue
                if not _is_market_open(market):
                    continue
                    
                # 현재가 조회
                current_price = 0
                if market == "국내":
                    kr_data = get_kr_stock_price(ticker)
                    current_price = float((kr_data or {}).get("price", 0))
                else:
                    us_data = get_us_stock_detail(ticker)
                    current_price = float((us_data or {}).get("price", 0))
                    
                if current_price <= 0:
                    continue
                
                # 보유 여부 파악
                holding = ai_holdings.get(ticker)
                position = "HOLDING" if holding else "NONE"
                avg_price = holding["buy_price"] if holding else 0
                
                # AI에게 매수/매도/홀딩 판단 요청
                logger.info(f"AI Agent: {name}({ticker}) 분석 중... (Position: {position})")
                
                # 비동기 I/O 래핑
                decision = await asyncio.to_thread(
                    analyze_autonomous_trading,
                    ticker, name, current_price, market, position, avg_price
                )
                
                if not decision: continue
                
                action = decision.get("action", "HOLD").upper()
                reason = decision.get("reason", "이유 없음")
                confidence = decision.get("confidence", 50)
                
                logger.info(f"AI Agent: {name} -> {action} (신뢰도: {confidence}%)")
                
                # 구글 시트에 고민 일지 실시간 기록
                try:
                    await asyncio.to_thread(
                        log_agent_scan,
                        ticker, name, current_price, position, action, confidence, f"[{source_korean}] {reason}"
                    )
                except Exception as ex:
                    logger.error(f"Failed to save scan log: {ex}")
                
                if action == "BUY" and position == "NONE" and confidence >= 60:
                    # 하루 매수 한도(3회) 검증 (과도한 매매 제한)
                    today_buy_count = _get_today_buy_count()
                    if today_buy_count >= 3:
                        logger.info(f"AI Agent: {name} 매수 제한 - 하루 매수 한도(3회) 초과. (오늘 매수: {today_buy_count}회)")
                        try:
                            await asyncio.to_thread(
                                log_agent_scan,
                                ticker, name, current_price, position, "HOLD", confidence, 
                                f"[{source_korean}] AI는 BUY 결정을 내렸으나 하루 최대 매수 제한(3회) 도달로 신규 매수를 차단합니다. (오늘 매수: {today_buy_count}회)"
                            )
                        except Exception:
                            pass
                        continue

                    # 이미 이번 루프에서 매수한 종목은 스킵 (중복 매수 방지)
                    if ticker in ai_holdings:
                        logger.info(f"AI Agent: {name} 이미 보유중(이번 루프 매수). 중복 매수 스킵.")
                        continue
                    
                    # 1. 예수금 조회 및 검증
                    from db import load_virtual_balances, save_virtual_balance
                    balances = load_virtual_balances()
                    ai_cash = balances.get("AI", 10000000.0)
                    
                    qty = 10  # 국내 10주
                    if market == "미국":
                        qty = 1  # 미국 1주
                    
                    # 매매 대금 및 매수 수수료 계산 (온라인 기본 수수료 적용)
                    base_cost = current_price * qty
                    fee_rate = 0.00015 if market == "국내" else 0.0007  # 국내 0.015%, 미국 0.07%
                    fee = base_cost * fee_rate
                    trade_cost = base_cost + fee
                    
                    if market == "미국":
                        rate = _get_usd_krw_rate()
                        trade_cost = trade_cost * rate
                        fee_krw = fee * rate
                    else:
                        fee_krw = fee
                        
                    if ai_cash < trade_cost:
                        logger.info(f"AI Agent: {name} 매수 자금 부족 (잔고: {ai_cash:,.0f}원, 필요: {trade_cost:,.0f}원). 매매 보류.")
                        try:
                            await asyncio.to_thread(
                                log_agent_scan,
                                ticker, name, current_price, position, "HOLD", confidence, f"[{source_korean}] 자금 부족으로 매수 보류 (필요: {trade_cost:,.0f}원, 잔고: {ai_cash:,.0f}원)"
                            )
                        except Exception:
                            pass
                        continue
                        
                    # 2. 예수금 차감 및 저장
                    new_ai_cash = ai_cash - trade_cost
                    save_virtual_balance("AI", new_ai_cash)
                    
                    # 3. 포트폴리오 반영 + ai_holdings 즉시 동기화 (중복 매수 방지)
                    new_item = {
                        "ticker": ticker,
                        "name": name,
                        "buy_price": current_price,
                        "quantity": qty,
                        "buy_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "rating": f"AI 자동 매수 ({source_korean})"
                    }
                    ai_portfolio.append(new_item)
                    ai_holdings[ticker] = new_item  # 즉시 동기화
                    save_portfolio_to_gsheet(ai_portfolio, owner=AI_OWNER_NAME)
                    
                    # 텔레그램 알림
                    currency = "$" if market == "미국" else "₩"
                    msg = f"[AI 매수 진입] 출처:{source_korean} | 종목:{name}({ticker}) | 매수가:{currency}{current_price:,.0f} | 수량:{qty}주 | 수수료:{fee_krw:,.0f}원 | 잔고:{new_ai_cash:,.0f}원 | 사유:{reason}"
                    send_price_alert(msg)
                    
                elif action == "SELL" and position == "HOLDING" and confidence >= 60:
                    # 최소 4시간 이상 보유 여부 검증 (초단타/스캘핑 강력 방어 가드)
                    buy_date_str = holding.get("buy_date") or holding.get("updated_time")
                    is_holding_time_valid = True
                    holding_hours = 0.0
                    
                    if buy_date_str:
                        try:
                            buy_dt = datetime.strptime(buy_date_str, "%Y-%m-%d %H:%M:%S")
                            elapsed_seconds = (datetime.now() - buy_dt).total_seconds()
                            holding_hours = elapsed_seconds / 3600.0
                            if elapsed_seconds < 14400: # 4시간 미만 (4 * 3600 = 14400)
                                is_holding_time_valid = False
                        except Exception as parse_err:
                            logger.error(f"Failed to parse buy_date '{buy_date_str}': {parse_err}")
                            
                    if not is_holding_time_valid:
                        logger.info(f"AI Agent: {name} 매도 제한 - 최소 보유 시간(4시간) 미달. (현재 보유 시간: {holding_hours:.1f}시간)")
                        try:
                            await asyncio.to_thread(
                                log_agent_scan,
                                ticker, name, current_price, position, "HOLD", confidence, 
                                f"[{source_korean}] AI는 SELL 신호를 보냈으나, 최소 보유 시간(4시간) 미달로 매도를 보류하고 HOLD를 강제 유지합니다. (보유 시간: {holding_hours:.1f}시간)"
                            )
                        except Exception:
                            pass
                        continue

                    # 매도 체결 로직 및 거래세/수수료 공제
                    qty = holding["quantity"]
                    bp = holding["buy_price"]
                    sp = current_price
                    
                    # 수수료 및 거래세율 적용 (국내 0.195% 매도세 포함, 미국 SEC Fee 포함 0.08%)
                    if market == "국내":
                        buy_fee_rate = 0.00015   # 0.015%
                        sell_fee_rate = 0.00195  # 0.015% + 0.18% (거래세)
                    else:
                        buy_fee_rate = 0.0007    # 0.07%
                        sell_fee_rate = 0.0008   # 0.07% + 0.01% (SEC Fee 등)
                        
                    # 실질 투자금(수수료 가산) 및 실질 회수금(수수료/거래세 차감) 계산
                    invested = bp * qty * (1 + buy_fee_rate)
                    returned = sp * qty * (1 - sell_fee_rate)
                    
                    # 실질 정밀 손익 및 수익률 책정 (수수료 제세금 완전 공제)
                    profit = returned - invested
                    profit_pct = (profit / invested * 100) if invested > 0 else 0.0
                    
                    # 1. 예수금 가산 및 저장 (원화 환산 기준)
                    from db import load_virtual_balances, save_virtual_balance
                    balances = load_virtual_balances()
                    ai_cash = balances.get("AI", 10000000.0)
                    
                    trade_revenue = returned
                    if market == "미국":
                        rate = _get_usd_krw_rate()
                        trade_revenue = trade_revenue * rate
                        
                    new_ai_cash = ai_cash + trade_revenue
                    save_virtual_balance("AI", new_ai_cash)
                    
                    # 2. 거래내역(AI) 기록
                    # learning_point: SELL 결정 시 AI가 직접 생성한 교훈 우선 사용, 없으면 reason 사용
                    learning_point = decision.get("learning_point", "").strip() or reason
                    trade_record = {
                        "ticker": ticker,
                        "name": name,
                        "quantity": qty,
                        "buy_price": bp,
                        "sell_price": sp,
                        "profit": profit,
                        "profit_pct": profit_pct,
                        "result": "수익" if profit >= 0 else "손실",
                        "learning_point": learning_point
                    }
                    save_trade_record(trade_record, owner=AI_OWNER_NAME)
                    
                    # 3. 보유종목(AI)에서 삭제 + ai_holdings 즉시 동기화 (매도 후 재매수 방지)
                    ai_portfolio = [p for p in ai_portfolio if p["ticker"] != ticker]
                    ai_holdings.pop(ticker, None)  # 즉시 동기화
                    save_portfolio_to_gsheet(ai_portfolio, owner=AI_OWNER_NAME)
                    
                    # 텔레그램 알림
                    currency = "$" if market == "미국" else "₩"
                    msg = f"[AI 매도 청산] 종목:{name}({ticker}) | 매도가:{currency}{sp:,.0f} | 손익:{profit:+,.0f}원({profit_pct:+.2f}%) | 잔고:{new_ai_cash:,.0f}원 | 사유:{reason}"
                    send_price_alert(msg)
                    
            logger.info(f"AI Agent: 1주기 스캔 완료. {INTERVAL_SECONDS}초 대기...")
            
        except Exception as e:
            logger.error(f"AI Trading Loop Error: {e}")
            
        await asyncio.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    import sys
    # Windows cp949 인코딩 오류 방지 및 출력 안정화
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
        
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 데이터베이스 초기화 및 정합성 체크
    try:
        from db import init_local_db
        init_local_db()
        logger.info("Local SQLite DB Checked and Initialized.")
    except Exception as e:
        logger.error(f"Local DB check failed: {e}")
        
    logger.info("====================================================")
    logger.info("🚀 Starting Autonomous Trading Agent in Standalone Mode...")
    logger.info("====================================================")
    
    try:
        asyncio.run(ai_trading_loop())
    except KeyboardInterrupt:
        logger.info("Agent execution terminated by user.")
