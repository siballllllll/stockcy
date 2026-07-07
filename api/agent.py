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

INTERVAL_SECONDS = 1800  # 30분 주기 (스윙/데이 트레이딩 템포)


def _position_size(cash_krw: float, price: float, market: str, confidence: float,
                   ml_d7=None, usdkrw: float = 1350.0) -> tuple:
    """[지능형 포지션 사이징 v3.116.0] 고정 수량(국내 10주/미국 1주) → 예산·확신 기반.
    기존 방식은 NAVER 211만원 vs 유니켐 4만원처럼 금액이 주가에 끌려다녔음.
    - 기본 예산 = 현금의 12% (풀현금 기준 약 8포지션 분산)
    - 확신 가중 0.6~1.4배: Gemini confidence(60~100)와 자체 ML 7일 확률(40~70%)의 평균
    - 하드캡 = 현금의 25% (한 종목 몰빵 방지)
    반환 (qty, budget_krw). qty 0 = 예산 대비 주가가 너무 높아 진입 스킵."""
    conf_c = max(0.0, min(1.0, (float(confidence or 60) - 60) / 40.0))
    ml_c = max(0.0, min(1.0, (float(ml_d7) - 40.0) / 30.0)) if ml_d7 is not None else 0.5
    mult = 0.6 + 0.8 * ((conf_c + ml_c) / 2)
    budget = min(cash_krw * 0.12 * mult, cash_krw * 0.25)
    px_krw = float(price or 0) * (usdkrw if market == "미국" else 1.0)
    if px_krw <= 0:
        return 0, budget
    qty = int(budget // px_krw)
    if qty < 1:
        # 고가주 소액 진입 허용: 1주가 예산의 1.5배 이내 + 현금 25% 이내면 1주
        if px_krw <= budget * 1.5 and px_krw <= cash_krw * 0.25:
            qty = 1
        else:
            return 0, budget
    return qty, budget


# ── 시장 레짐 스위치 (v3.117.0) ──────────────────────────────────────────────
# 실측 근거: 2026-05 표본 승률 4.5% vs 6월 47.4% — 시장 국면이 개별 지표보다 큼.
# 지수 20일 모멘텀: 공격(+1%↑) / 중립 / 수비(-3%↓). 수비 국면엔 신규 진입 스캔 생략.
_REGIME_CACHE = {"t": 0.0, "kr": ("중립", 0.0), "us": ("중립", 0.0)}


def _market_regime(market: str) -> tuple:
    """(레짐 라벨, 20일 모멘텀%) 반환. 6시간 캐시, 조회 실패 시 직전값 유지."""
    import time as _t
    if _t.time() - _REGIME_CACHE["t"] > 21600:
        _REGIME_CACHE["t"] = _t.time()   # 실패해도 재시도 폭주 방지
        try:
            import FinanceDataReader as fdr
            from datetime import timedelta
            start = (datetime.now() - timedelta(days=70)).strftime("%Y-%m-%d")
            for key, code in (("kr", "KS11"), ("us", "US500")):
                try:
                    c = fdr.DataReader(code, start)["Close"].dropna()
                    if len(c) >= 21:
                        mom = (float(c.iloc[-1]) / float(c.iloc[-21]) - 1) * 100
                        label = "공격" if mom >= 1.0 else ("수비" if mom <= -3.0 else "중립")
                        _REGIME_CACHE[key] = (label, round(mom, 2))
                except Exception as _re:
                    logger.error(f"[regime] {code} 조회 실패: {_re}")
        except Exception:
            pass
    return _REGIME_CACHE["kr" if market == "국내" else "us"]


# ── 포지션 상태 (v3.117.0) — 트레일링 스탑용 고점·부분익절 여부 추적 ─────────
def _pos_state(ticker: str, current_price: float = None) -> tuple:
    """(peak_price, partial_taken) 조회. current_price를 주면 고점 갱신도 수행."""
    try:
        from db import get_db_conn
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS agent_position_state (
            ticker TEXT PRIMARY KEY, peak_price REAL, partial_taken INTEGER DEFAULT 0, updated_at TEXT)""")
        cur.execute("SELECT peak_price, partial_taken FROM agent_position_state WHERE ticker=?", (ticker,))
        row = cur.fetchone()
        peak = float(row["peak_price"]) if row and row["peak_price"] else 0.0
        partial = bool(row["partial_taken"]) if row else False
        if current_price and current_price > peak:
            cur.execute(
                "INSERT OR REPLACE INTO agent_position_state (ticker, peak_price, partial_taken, updated_at) VALUES (?, ?, ?, ?)",
                (ticker, float(current_price), 1 if partial else 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            peak = float(current_price)
        conn.close()
        return peak, partial
    except Exception as e:
        logger.error(f"[pos state] {ticker}: {e}")
        return 0.0, False


def _pos_state_write(ticker: str, peak: float = None, partial: bool = None, clear: bool = False):
    """포지션 상태 기록/삭제 — 신규 매수 시 리셋, 부분익절 시 플래그, 전량 청산 시 삭제."""
    try:
        from db import get_db_conn
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS agent_position_state (
            ticker TEXT PRIMARY KEY, peak_price REAL, partial_taken INTEGER DEFAULT 0, updated_at TEXT)""")
        if clear:
            cur.execute("DELETE FROM agent_position_state WHERE ticker=?", (ticker,))
        else:
            cur.execute("SELECT peak_price, partial_taken FROM agent_position_state WHERE ticker=?", (ticker,))
            row = cur.fetchone()
            new_peak = float(peak) if peak is not None else (float(row["peak_price"]) if row and row["peak_price"] else 0.0)
            new_partial = (1 if partial else 0) if partial is not None else (int(row["partial_taken"]) if row else 0)
            cur.execute(
                "INSERT OR REPLACE INTO agent_position_state (ticker, peak_price, partial_taken, updated_at) VALUES (?, ?, ?, ?)",
                (ticker, new_peak, new_partial, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"[pos state write] {ticker}: {e}")


def _run_one_scan(force: bool = False) -> dict:
    """에이전트 1회 스캔(동기). 백그라운드 루프와 수동 트리거가 공유.
    force=True면 휴장이어도 진행(수동 점검용). 반환: 스캔 요약 dict.
    블로킹 호출이 많아 반드시 워커 스레드(to_thread)에서 실행할 것."""
    summary: dict = {"scanned": 0, "buy": 0, "sell": 0, "hold": 0, "skipped": None}
    shadow_candidates: list = []   # 섀도우 리그에 넘길 (지표 포함) 후보 — 메인 스캔 결과 재사용
    if True:
        try:
            kr_open = _is_market_open("국내")
            us_open = _is_market_open("미국")

            if not kr_open and not us_open and not force:
                logger.info("[agent] 모든 시장 휴장 중. 스캔 건너뜀.")
                summary["skipped"] = "market_closed"
                return summary

            logger.info(f"[agent] 시장 스캔 시작 (국내: {'개장' if kr_open else '휴장'}, 미국: {'개장' if us_open else '휴장'}, force={force})")

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
            
            # (6) 눌림목 스크리너 후보 편입 (v3.116.0) — 실측 승률 66.7% 엣지를 에이전트가 직접 매매.
            #     패턴 스크리너 top5는 ml_training_samples(pattern)에 기록됨 → 최근 2일분 재사용(비용 0).
            #     기존 유니버스는 '핫종목'(실측 승률 22% 구간 다수) 중심이라 좋은 후보가 늘 굶었음.
            try:
                from db import get_db_conn
                _c = get_db_conn(); _cu = _c.cursor()
                _cu.execute(
                    """SELECT DISTINCT ticker, name FROM ml_training_samples
                       WHERE source='pattern' AND decided_at >= date('now','-2 day')
                       ORDER BY decided_at DESC LIMIT 8""")
                for _r in _cu.fetchall():
                    _tk = str(_r["ticker"]).strip()
                    _tk = _tk.zfill(6) if _tk.isdigit() else _tk.upper()
                    if _tk and _tk not in seen_tickers:
                        seen_tickers.add(_tk)
                        scan_universe.append({
                            "티커": _tk,
                            "종목명": _r["name"] or _tk,
                            "시장": "국내" if _tk.isdigit() else "미국",
                            "source": "PULLBACK",
                        })
                _c.close()
            except Exception as e:
                logger.error(f"눌림목 스크리너 후보 로드 실패: {e}")

            # 2. AI의 현재 포트폴리오(보유 종목) 조회
            ai_portfolio = load_portfolio_from_gsheet(owner=AI_OWNER_NAME)
            ai_holdings = {p["ticker"]: p for p in ai_portfolio}

            # ★ 보유 종목을 스캔 유니버스 최우선으로 강제 편입 (매도 판단 기회 보장)
            #   기존엔 보유 종목이 핫종목/즐겨찾기에 없으면 평가조차 안 돼 영영 HOLD되는 버그가 있었음
            holding_universe = []
            for tk, hp in ai_holdings.items():
                if tk in seen_tickers:
                    continue
                seen_tickers.add(tk)
                is_kr_tk = str(tk).strip().isdigit()
                holding_universe.append({
                    "티커": tk,
                    "종목명": hp.get("name", tk),
                    "시장": "국내" if is_kr_tk else "미국",
                    "source": "HOLDING",
                })
            # 보유 종목을 맨 앞에 배치 (우선 평가)
            scan_universe = holding_universe + scan_universe

            if not scan_universe:
                logger.info("[agent] 스캔할 감시 대상 종목이 없습니다 (즐겨찾기·보유종목 비어있음).")
                summary["skipped"] = "no_universe"
                return summary
            
            # 3. 각 종목 순회하며 AI 판단 요청
            from data_kr import get_kr_stock_price
            from data import get_us_stock_detail
            
            for fav in scan_universe:
                market = fav.get("시장", "국내")
                ticker = fav.get("티커", "")
                name = fav.get("종목명", ticker)
                source_type = fav.get("source", "FAVORITE")
                
                source_korean = {
                    "HOLDING": "보유 종목",
                    "FAVORITE": "즐겨찾기",
                    "KR_HOT_VOLUME": "국내 거래대금 핫종목",
                    "KR_HOT_CHANGE": "국내 상승률 핫종목",
                    "US_HOT_VOLUME": "미국 거래대금 핫종목",
                    "US_HOT_CHANGE": "미국 상승률 핫종목",
                    "PULLBACK": "눌림목 스크리너 후보"
                }.get(source_type, "주도주")
                
                if not ticker: continue
                if not force and not _is_market_open(market):
                    continue

                # [시장 레짐 스위치 v3.117.0] 수비 국면(지수 20일 모멘텀 -3%↓)에는
                # 미보유 종목 신규진입 스캔 자체를 생략 — 5월 승률 4.5% 같은 하락장 방어 + Gemini 비용 절약.
                # 보유 종목은 계속 평가(매도·물타기 판단은 하락장일수록 중요).
                _regime, _regime_mom = _market_regime(market)
                if _regime == "수비" and ticker not in ai_holdings and not force:
                    summary["regime_skipped"] = (summary.get("regime_skipped") or 0) + 1
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

                # ★ 보유 종목 마크투마켓 — 안 팔았어도 현재 평가손익을 '잠정' 학습 표본에 기록
                #   (스캔이 이미 현재가를 구했으므로 추가 네트워크 호출 없음. 매도 시 확정값으로 교체)
                if position == "HOLDING" and avg_price and avg_price > 0:
                    try:
                        from db import update_agent_decision_unrealized
                        unreal_pct = (current_price - avg_price) / avg_price * 100.0
                        update_agent_decision_unrealized(ticker, unreal_pct)
                    except Exception as _ue:
                        logger.error(f"[agent] 잠정 수익률 갱신 실패 {ticker}: {_ue}")

                # ── [강제 청산 가드 v3.113.0] 포지션 성격별 차등 적용 ──
                # 매수 시 Gemini가 지정한 성격 태그(rating의 '[스윙]'/'[중장기]')로 구분:
                #  · 스윙: -5% 강제 손절 / +8% 강제 익절 (프롬프트 권고 -3/+2.5의 백스톱)
                #  · 중장기(태그 없는 기존 보유 포함): 재난용 -20% 손절만, 익절 강제 없음
                #    — 에이전트 보유가 중장기 관찰 데이터 소스이기도 해서(사용자 결정 07-06)
                #      차트 구조가 유효한 장기 포지션은 코드가 끊지 않고 Gemini 판단에 맡긴다.
                forced_exit = False
                decision = None
                if position == "HOLDING" and avg_price and avg_price > 0:
                    _fee_rt = 0.21 if market == "국내" else 0.15   # 왕복 수수료+거래세 %
                    _net = (current_price - avg_price) / avg_price * 100.0 - _fee_rt
                    _is_swing = "[스윙]" in str(holding.get("rating") or "")
                    _peak, _partial = _pos_state(ticker, current_price)   # 고점 갱신 + 부분익절 여부
                    if _is_swing and _net <= -5.0:
                        # [스마트 손절 v3.125.0] -5%~-8% 구간은 '지금 이 순간'의 회복 지표를 보고 유예.
                        # 실측: 눌림목 계열이 -5% 터치 후 7일 내 플러스 회복 37.3% — 회복 지표(ML 55%+
                        # 또는 볼린저 하단권=과매도 지지) 우세 시 즉시 자르지 않고 Gemini 판단에 넘긴다.
                        # -8% 밑은 무조건 손절(하드 플로어). 유예는 매 스캔(30분)마다 재평가됨.
                        _rescue = False
                        _rescue_note = ""
                        if _net > -8.0:
                            try:
                                from ai_engine import _get_trade_indicators
                                from ml_model import predict_win_proba
                                _d2 = _get_trade_indicators(ticker, "").get("daily", {})
                                _mlx2 = _d2.get("ml_extra") or {}
                                _f2 = {"rsi": _d2.get("rsi"), "pos_52w": _d2.get("pos_52w_pct"),
                                       "vol_ratio": _d2.get("volume_ratio"),
                                       "is_us": 0.0 if str(ticker).strip().isdigit() else 1.0}
                                _f2.update(_mlx2)
                                _ml7r = predict_win_proba(_f2, "d7")
                                _bb2 = _mlx2.get("bb_pctb")
                                if (_ml7r is not None and _ml7r >= 55.0) or (_bb2 is not None and _bb2 <= 0.2):
                                    _rescue = True
                                    _rescue_note = f"ML d7 {_ml7r}% · 볼린저 %b {_bb2}"
                            except Exception as _re2:
                                logger.error(f"[smart stop] {ticker} 회복 지표 확인 실패: {_re2}")
                        if _rescue:
                            logger.info(f"AI Agent: {name} 손절 유예 - 실질 {_net:+.2f}%, 회복 지표 우세 ({_rescue_note})")
                            try:
                                log_agent_scan(ticker, name, current_price, position, "HOLD", 70,
                                    f"[손절 유예] 실질 {_net:+.2f}%로 손절선 이탈이나 회복 지표 우세({_rescue_note}) — -8% 하드 플로어까지 유예, 최종 판단은 AI에게 위임")
                            except Exception:
                                pass
                            # forced_exit 미설정 → 아래에서 Gemini가 회복 근거를 보고 최종 판단
                        else:
                            forced_exit = True
                            decision = {"action": "SELL", "confidence": 99,
                                        "reason": (f"[강제 손절 가드·스윙] 실질 손익 {_net:+.2f}% — "
                                                   + ("-8% 하드 플로어 이탈, 회복 여부 무관 즉시 청산" if _net <= -8.0
                                                      else "손절선(-5%) 이탈 + 회복 지표 열세, 즉시 청산")),
                                        "learning_point": f"스윙 손절 {_net:+.2f}% 확정 — 회복 지표 열세 구간은 버티지 않는다"}
                    elif _is_swing and _net >= 8.0 and not _partial:
                        # [부분 익절 v3.117.0] 전량 익절 → 절반 익절 + 잔여 트레일링.
                        # 기존 +8% 전량 청산은 +142% 같은 대시세 꼬리를 전부 놓치는 구조였음.
                        forced_exit = True
                        _hold_q = float(holding.get("quantity") or 0)
                        if _hold_q >= 2:
                            _half = int(_hold_q // 2)
                            decision = {"action": "SELL", "confidence": 95, "sell_qty": _half,
                                        "reason": f"[부분 익절 가드·스윙] 실질 {_net:+.2f}% ≥ +8% — 절반({_half}주) 익절 확정, 잔여는 고점 대비 -7% 트레일링으로 대시세 추적",
                                        "learning_point": f"+8% 도달 절반 익절, 잔여 트레일링 전환 (실질 {_net:+.2f}%)"}
                        else:
                            decision = {"action": "SELL", "confidence": 95,
                                        "reason": f"[강제 익절 가드·스윙] 실질 손익 {_net:+.2f}% ≥ +8% — 1주 포지션이라 전량 수익 확정",
                                        "learning_point": f"실질 {_net:+.2f}% 익절 확정 (스윙 강제 가드)"}
                    elif _is_swing and _partial and _peak > 0 and current_price <= _peak * 0.93 and _net > 0:
                        # [트레일링 스탑 v3.117.0] 부분 익절 후 잔여분 — 고점 대비 -7% 이탈 시 수익 확정
                        forced_exit = True
                        decision = {"action": "SELL", "confidence": 95,
                                    "reason": f"[트레일링 스탑·스윙] 고점 {_peak:,.0f} 대비 -7% 이탈 (현재 {current_price:,.0f}) — 잔여 전량 수익 확정 (실질 {_net:+.2f}%)",
                                    "learning_point": f"트레일링 스탑 발동 — 고점 대비 -7%, 최종 {_net:+.2f}% 확정"}
                    elif (not _is_swing) and _net <= -30.0:
                        # 중장기 재난선 -30% — 물타기 허용 구간(-25%까지, v3.115.0)과 겹치지 않게 여유 확보.
                        # 실측: d7 -15%↓ 표본 36건은 d20까지 평균 -9.7%p 추가 하락(반등 13.9%) — 바닥 아래 바닥 방어선.
                        forced_exit = True
                        decision = {"action": "SELL", "confidence": 99,
                                    "reason": f"[재난 손절 가드·중장기] 실질 손익 {_net:+.2f}% ≤ -30% — 중장기 포지션도 감내 한도를 벗어나 강제 청산",
                                    "learning_point": f"중장기 보유가 {_net:+.2f}%까지 악화 — 투자 논리 붕괴 시점 재점검 필요"}

                # AI에게 매수/매도/홀딩 판단 요청 (강제 청산이면 Gemini 호출 생략 — 비용 0)
                if decision is None:
                    logger.info(f"AI Agent: {name}({ticker}) 분석 중... (Position: {position})")
                    decision = analyze_autonomous_trading(
                        ticker, name, current_price, market, position, avg_price
                    )

                if not decision: continue
                
                action = decision.get("action", "HOLD").upper()
                reason = decision.get("reason", "이유 없음")
                confidence = decision.get("confidence", 50)
                
                logger.info(f"[agent] {name} -> {action} (신뢰도: {confidence}%)")

                # 섀도우 리그 후보 수집 (v3.118.0) — 이미 수집된 지표·시세 재사용 (추가 다운로드 0)
                _ind_sh = decision.get("_indicators") or {}
                if _ind_sh:
                    shadow_candidates.append({"ticker": ticker, "name": name, "market": market,
                                              "price": current_price, "ind": _ind_sh})

                # 고민 일지(scan log) 기록
                summary["scanned"] += 1
                summary["buy" if action == "BUY" else "sell" if action == "SELL" else "hold"] += 1
                try:
                    log_agent_scan(ticker, name, current_price, position, action, confidence, f"[{source_korean}] {reason}")
                except Exception as ex:
                    logger.error(f"[agent] scan log 저장 실패: {ex}")
                
                if action == "BUY" and position == "NONE" and confidence >= 60:
                    # [실측 하드필터 v3.112.0] 스크리너(v3.111.0)와 동일 기준 — 급등 추격 매수 차단.
                    # 실측 561건: 5일 +10%↑ 승률 22%, (+5%↑ AND RSI70↑/거래량4배↑) 승률 13~20%.
                    _snap = decision.get("_indicators") or {}
                    _m5 = _snap.get("mom_5"); _rsi_s = _snap.get("rsi") or 0; _vr_s = _snap.get("vol_ratio") or 0
                    if _m5 is not None and (_m5 >= 10 or (_m5 >= 5 and (_rsi_s >= 70 or _vr_s >= 4))):
                        logger.info(f"AI Agent: {name} 매수 차단 - 급등 추격 구간 (5일 모멘텀 {_m5:+.1f}%, 실측 저승률 하드필터)")
                        try:
                            log_agent_scan(ticker, name, current_price, position, "HOLD", confidence,
                                f"[{source_korean}] AI는 BUY 결정을 내렸으나 실측 하드필터(5일 {_m5:+.1f}% 급등 추격 구간, 과거 승률 22% 이하)로 매수를 차단합니다.")
                        except Exception:
                            pass
                        continue

                    # [가격 순단 가드 v3.114.2] 실시간가가 일봉 기준가와 크게 어긋나면 매수 차단.
                    # 유니켐(6/11) 사고: 시세 API가 3,970원을 397원(1/10)으로 반환 → 평단 오염+수익률 +755% 오표기.
                    _pxd = _snap.get("px_daily")
                    if _pxd and current_price and not (0.55 <= current_price / float(_pxd) <= 1.8):
                        logger.info(f"AI Agent: {name} 매수 차단 - 가격 소스 불일치 (실시간 {current_price:,.0f} vs 일봉 {float(_pxd):,.0f})")
                        try:
                            log_agent_scan(ticker, name, current_price, position, "HOLD", confidence,
                                f"[{source_korean}] 실시간가({current_price:,.0f})와 일봉 기준가({float(_pxd):,.0f})가 크게 달라 데이터 순단 의심 — 매수 보류.")
                        except Exception:
                            pass
                        continue

                    # 하루 매수 한도(3회) 검증 (과도한 매매 제한)
                    today_buy_count = _get_today_buy_count()
                    if today_buy_count >= 3:
                        logger.info(f"AI Agent: {name} 매수 제한 - 하루 매수 한도(3회) 초과. (오늘 매수: {today_buy_count}회)")
                        try:
                            log_agent_scan(ticker, name, current_price, position, "HOLD", confidence,
                                f"[{source_korean}] AI는 BUY 결정을 내렸으나 하루 최대 매수 제한(3회) 도달로 신규 매수를 차단합니다. (오늘 매수: {today_buy_count}회)")
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

                    # [지능형 포지션 사이징 v3.116.0] 예산(현금 12%)×확신 가중(Gemini+ML)
                    _rate_sz = _get_usd_krw_rate() if market == "미국" else 1.0
                    qty, _budget = _position_size(ai_cash, current_price, market, confidence,
                                                  ml_d7=_snap.get("ml_d7"), usdkrw=_rate_sz)
                    if _regime == "중립" and qty > 1:
                        qty = max(1, int(qty * 0.8))   # 중립 국면 — 포지션 20% 축소
                    if qty < 1:
                        logger.info(f"AI Agent: {name} 매수 보류 - 예산({_budget:,.0f}원) 대비 주가 높음")
                        try:
                            log_agent_scan(ticker, name, current_price, position, "HOLD", confidence,
                                f"[{source_korean}] 포지션 예산({_budget:,.0f}원) 대비 주가가 높아 매수 보류 (분산 원칙).")
                        except Exception:
                            pass
                        continue

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
                            log_agent_scan(ticker, name, current_price, position, "HOLD", confidence,
                                f"[{source_korean}] 자금 부족으로 매수 보류 (필요: {trade_cost:,.0f}원, 잔고: {ai_cash:,.0f}원)")
                        except Exception:
                            pass
                        continue
                        
                    # 2. 예수금 차감 및 저장
                    new_ai_cash = ai_cash - trade_cost
                    save_virtual_balance("AI", new_ai_cash)
                    
                    # 3. 포트폴리오 반영 + ai_holdings 즉시 동기화 (중복 매수 방지)
                    # 포지션 성격 태그(v3.113.0): Gemini가 BUY 시 지정한 horizon(swing/long)을
                    # rating에 박아 강제 청산 가드가 차등 적용되게 함. 미지정 시 스윙.
                    _hz_tag = "[중장기]" if str(decision.get("horizon") or "").lower() == "long" else "[스윙]"
                    new_item = {
                        "ticker": ticker,
                        "name": name,
                        "buy_price": current_price,
                        "quantity": qty,
                        "buy_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "rating": f"AI 자동 매수 {_hz_tag} ({source_korean})",
                        "buy_reason": f"{_hz_tag}[{source_korean}] {reason}",   # AI 매수 판단 근거 — 보유종목에 표시
                    }
                    ai_portfolio.append(new_item)
                    ai_holdings[ticker] = new_item  # 즉시 동기화
                    save_portfolio_to_gsheet(ai_portfolio, owner=AI_OWNER_NAME)
                    _pos_state_write(ticker, peak=current_price, partial=False)   # 트레일링 고점 초기화
                    
                    # [노이즈 절감] AI 모의매매는 학습 목적 — 매수 텔레그램 알림 비활성.
                    #   체결·학습 기록은 위에서 완료됨. 결과는 앱 내 AI 포트폴리오에서 확인.
                    
                elif action == "BUY" and position == "HOLDING" and confidence >= 70:
                    # ── [물타기(추가매수) v3.113.0 → v3.115.0 구간 확대] 중장기 포지션 한정 ──
                    # 사용자 방침: 중장기는 깊은 손실에서도 평단을 내릴 수 있어야 함 → -25%까지 허용.
                    # 단 실측(d7 -15%↓ 표본의 86%가 d20까지 추가 하락)이 경고하는 '떨어지는 칼날' 방어로
                    # -15% 이하 깊은 구간은 확신도 80+ 필요, 2회차 물타기는 -15% 이하에서만(간격 확보).
                    _rating_h = str(holding.get("rating") or "")
                    _fee_rt3 = 0.21 if market == "국내" else 0.15
                    _net3 = (current_price - avg_price) / avg_price * 100.0 - _fee_rt3 if avg_price else 0.0
                    _adds = str(holding.get("buy_reason") or "").count("[물타기]")
                    _block = None
                    if "[스윙]" in _rating_h:
                        _block = "스윙 포지션은 물타기 금지 (손절 원칙)"
                    elif _regime == "수비":
                        _block = f"시장 수비 국면(20일 모멘텀 {_regime_mom:+.1f}%) — 하락장 물타기 보류"
                    elif _net3 > -3.0:
                        _block = f"실질 손익 {_net3:+.2f}% — -3% 이상에서는 물타기 불필요"
                    elif _net3 <= -25.0:
                        _block = f"실질 손익 {_net3:+.2f}% — -25% 초과 손실은 물타기 금지 (재난 손절선 -30% 인접)"
                    elif _net3 <= -15.0 and confidence < 80:
                        _block = f"실질 손익 {_net3:+.2f}% 깊은 구간 — 확신도 80 이상일 때만 물타기 (현재 {confidence})"
                    elif _adds >= 2:
                        _block = "물타기 한도(종목당 2회) 도달"
                    elif _adds == 1 and _net3 > -15.0:
                        _block = f"2회차 물타기는 실질 -15% 이하에서만 (현재 {_net3:+.2f}%, 간격 확보)"
                    elif _get_today_buy_count() >= 3:
                        _block = "하루 매수 한도(3회) 도달"
                    if _block:
                        try:
                            log_agent_scan(ticker, name, current_price, position, "HOLD", confidence,
                                f"[{source_korean}] AI가 추가매수(물타기)를 제안했으나 차단: {_block}")
                        except Exception:
                            pass
                        continue

                    from db import load_virtual_balances, save_virtual_balance
                    balances = load_virtual_balances()
                    ai_cash = balances.get("AI", 10000000.0)
                    # 물타기 수량도 지능형 사이징 — 단 기존 보유 수량을 상한으로(평단 조작 방지,
                    # 한 번의 물타기가 포지션을 2배 초과로 키우지 않게)
                    _rate_sz = _get_usd_krw_rate() if market == "미국" else 1.0
                    _q_size, _budget = _position_size(ai_cash, current_price, market, confidence, usdkrw=_rate_sz)
                    _q_cap = int(holding.get("quantity") or 0) or (1 if market == "미국" else 10)
                    qty = min(_q_size, _q_cap) if _q_size >= 1 else 0
                    if qty < 1:
                        try:
                            log_agent_scan(ticker, name, current_price, position, "HOLD", confidence,
                                f"[{source_korean}] 물타기 예산({_budget:,.0f}원) 대비 주가가 높아 보류.")
                        except Exception:
                            pass
                        continue
                    base_cost = current_price * qty
                    fee_rate = 0.00015 if market == "국내" else 0.0007
                    trade_cost = base_cost * (1 + fee_rate)
                    if market == "미국":
                        trade_cost *= _get_usd_krw_rate()
                    if ai_cash < trade_cost:
                        try:
                            log_agent_scan(ticker, name, current_price, position, "HOLD", confidence,
                                f"[{source_korean}] 물타기 자금 부족으로 보류 (필요: {trade_cost:,.0f}원, 잔고: {ai_cash:,.0f}원)")
                        except Exception:
                            pass
                        continue
                    save_virtual_balance("AI", ai_cash - trade_cost)

                    # 동일 티커 append → save_portfolio_to_gsheet가 평단 가중평균·수량 합산으로 병합
                    add_item = {
                        "ticker": ticker,
                        "name": name,
                        "buy_price": current_price,
                        "quantity": qty,
                        "buy_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "rating": _rating_h or "AI 자동 매수 [중장기]",
                        "buy_reason": f"[물타기]({_adds + 1}/2, 평단 {avg_price:,.0f}→현재가 {current_price:,.0f}, 실질 {_net3:+.2f}%) {reason}",
                    }
                    ai_portfolio.append(add_item)
                    save_portfolio_to_gsheet(ai_portfolio, owner=AI_OWNER_NAME)
                    logger.info(f"AI Agent: {name} 물타기 체결 ({_adds + 1}/2회, {_net3:+.2f}% 구간, {qty}주)")

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
                            
                    # 강제 청산 가드는 리스크 관리라 4시간 최소보유 예외 (스캘핑 방지 목적과 무관)
                    if not is_holding_time_valid and not forced_exit:
                        logger.info(f"AI Agent: {name} 매도 제한 - 최소 보유 시간(4시간) 미달. (현재 보유 시간: {holding_hours:.1f}시간)")
                        try:
                            log_agent_scan(ticker, name, current_price, position, "HOLD", confidence,
                                f"[{source_korean}] AI는 SELL 신호를 보냈으나, 최소 보유 시간(4시간) 미달로 매도를 보류하고 HOLD를 강제 유지합니다. (보유 시간: {holding_hours:.1f}시간)")
                        except Exception:
                            pass
                        continue

                    # 매도 체결 로직 및 거래세/수수료 공제
                    # [부분 익절 v3.117.0] decision.sell_qty가 있으면 그 수량만 매도(잔여는 트레일링)
                    _hold_qty = float(holding["quantity"])
                    _sell_qty = decision.get("sell_qty")
                    qty = min(float(_sell_qty), _hold_qty) if _sell_qty else _hold_qty
                    partial_exit = qty < _hold_qty
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
                        "learning_point": learning_point,
                        # 매수 시점 정보를 거래기록에 전파 — 거래일지 '매수근거→매도사유' 연결 + 매수사유별 성과 학습.
                        "buy_reason": str(holding.get("buy_reason") or "").strip(),
                        "buy_date": str(holding.get("buy_date") or holding.get("updated_time") or "").strip(),
                    }
                    save_trade_record(trade_record, owner=AI_OWNER_NAME)

                    # 2-b. 자기학습 루프 — 이 종목의 가장 최근 '미확정' BUY 판단에 실제 결과(수익률) 확정 기록
                    #   (보유 중 잠정값이 채워져 있을 수 있으므로 is_realized=0 행을 찾아 확정값으로 교체 + is_realized=1)
                    #   부분 익절은 잔여분이 남아있으므로 확정하지 않음(전량 청산 시 확정).
                    try:
                        if not partial_exit:
                            from db import get_db_conn
                            _conn = get_db_conn()
                            _cur = _conn.cursor()
                            _cur.execute(
                                """UPDATE agent_decisions
                                   SET outcome_return = ?, outcome_checked_at = ?, is_realized = 1
                                   WHERE id = (
                                       SELECT id FROM agent_decisions
                                       WHERE ticker = ? AND action='BUY' AND COALESCE(is_realized, 0) = 0
                                       ORDER BY decided_at DESC LIMIT 1
                                   )""",
                                (float(profit_pct), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ticker)
                            )
                            _conn.commit()
                            _conn.close()
                    except Exception as _le:
                        logger.error(f"agent learning update failed: {_le}")

                    # 3. 포트폴리오 반영 — 부분 익절이면 잔여 수량 갱신, 전량이면 삭제
                    if partial_exit:
                        _remain = _hold_qty - qty
                        for p in ai_portfolio:
                            if p["ticker"] == ticker:
                                p["quantity"] = _remain
                        holding["quantity"] = _remain   # ai_holdings 동기화 (동일 객체)
                        save_portfolio_to_gsheet(ai_portfolio, owner=AI_OWNER_NAME)
                        _pos_state_write(ticker, partial=True)   # 잔여분 트레일링 모드 전환
                    else:
                        ai_portfolio = [p for p in ai_portfolio if p["ticker"] != ticker]
                        ai_holdings.pop(ticker, None)  # 즉시 동기화 (매도 후 재매수 방지)
                        save_portfolio_to_gsheet(ai_portfolio, owner=AI_OWNER_NAME)
                        _pos_state_write(ticker, clear=True)     # 고점·부분익절 상태 제거
                    
                    # [노이즈 절감] AI 모의매매는 학습 목적 — 매도 텔레그램 알림 비활성.
                    #   체결·학습 기록은 위에서 완료됨. 결과는 앱 내 AI 포트폴리오에서 확인.
                    
            # ── 섀도우 리그 (v3.118.0) — 대조군 전략 가상매매 (Gemini 무호출, 비용 0) ──
            try:
                from shadow_league import run_shadow_cycle
                summary["shadow"] = run_shadow_cycle(
                    shadow_candidates, kr_open=kr_open, us_open=us_open,
                    force=force, usdkrw=_get_usd_krw_rate(),
                    regimes={"국내": _market_regime("국내")[0], "미국": _market_regime("미국")[0]})
            except Exception as _se:
                logger.error(f"[shadow] 사이클 오류: {_se}")

            logger.info(f"[agent] 1주기 스캔 완료. scanned={summary['scanned']} buy={summary['buy']} sell={summary['sell']} hold={summary['hold']}")

        except Exception as e:
            logger.error(f"[agent] scan error: {e}", exc_info=True)
            summary["error"] = str(e)
    return summary


async def ai_trading_loop():
    """백그라운드 에이전트 루프 — 블로킹 스캔을 워커 스레드에서 실행해 이벤트 루프 정지 방지."""
    logger.info("[agent] AI Trading Agent Loop Started")
    while True:
        try:
            summary = await asyncio.wait_for(asyncio.to_thread(_run_one_scan), timeout=600)
            logger.info(f"[agent] heartbeat: {summary}")
        except asyncio.TimeoutError:
            logger.error("[agent] 스캔 타임아웃(10분) — 다음 주기로 넘어감")
        except Exception as e:
            logger.error(f"[agent] loop error: {e}")
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
