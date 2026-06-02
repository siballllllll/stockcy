import os
import json as _json
import gspread
import st_compat as st
import pandas as pd
import sqlite3
import threading
from datetime import datetime, timedelta

# 구글 스프레드시트 API 호출 429 초과 방지용 메모리 캐시 및 TTL(60초) 정의
_GSHEET_CACHE = {}
_GSHEET_CACHE_TTL = timedelta(seconds=60)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db.sqlite3")
_US_FDR_SECTOR_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_csv", "us_fdr_sector_cache.json")

def _pad_kr_ticker(ticker: str) -> str:
    """숫자로만 이루어진 국내 종목 코드는 무조건 6자리 제로패딩. 미국 주식은 대문자 반환."""
    t = str(ticker).strip()
    if t.isdigit():
        return t.zfill(6)
    return t.upper()


def get_db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    # WAL 모드: write가 진행 중에도 read가 블로킹되지 않음
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_local_db():
    conn = get_db_conn()
    cursor = conn.cursor()
    
    # 1. favorites
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            market_type TEXT,
            added_time TEXT
        )
    """)
    
    # 2. portfolio
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            owner TEXT,
            ticker TEXT,
            name TEXT,
            quantity REAL,
            buy_price REAL,
            rating TEXT,
            updated_time TEXT,
            buy_reason TEXT,
            PRIMARY KEY (owner, ticker)
        )
    """)
    
    # 3. ai_portfolio
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_portfolio (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            quantity REAL,
            buy_price REAL,
            rating TEXT,
            updated_time TEXT
        )
    """)
    
    # 4. trade_history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_history (
            owner TEXT,
            sell_date TEXT,
            ticker TEXT,
            name TEXT,
            quantity REAL,
            buy_price REAL,
            sell_price REAL,
            profit REAL,
            profit_pct REAL,
            result TEXT,
            learning_point TEXT,
            buy_reason TEXT,
            PRIMARY KEY (owner, sell_date, ticker)
        )
    """)
    
    # 5. virtual_balances
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS virtual_balances (
            owner TEXT PRIMARY KEY,
            balance REAL,
            updated_time TEXT
        )
    """)
    
    # 6. ai_recommendations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_time TEXT,
            rec_type TEXT,
            ticker TEXT,
            name TEXT,
            rating TEXT,
            buy_target TEXT,
            sell_target TEXT,
            stop_loss TEXT
        )
    """)
    
    # 7. ai_scan_logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_scan_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_time TEXT,
            ticker TEXT,
            name TEXT,
            price REAL,
            position TEXT,
            action TEXT,
            confidence INTEGER,
            reason TEXT
        )
    """)
    
    # 8. price_alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_alerts (
            market TEXT,
            ticker TEXT,
            name TEXT,
            alert_type TEXT,
            target_price REAL,
            updated_time TEXT,
            status TEXT,
            PRIMARY KEY (ticker, alert_type)
        )
    """)
    
    # 9. trade_analysis
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_analysis (
            key_name TEXT PRIMARY KEY,
            analysis_json TEXT
        )
    """)
    
    # 10. telegram_config
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telegram_config (
            key TEXT PRIMARY KEY,
            token TEXT,
            chat_id TEXT
        )
    """)

    # 11. ai_cache
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_cache (
            cache_key TEXT PRIMARY KEY,
            saved_time TEXT,
            expire_time TEXT,
            data_json TEXT
        )
    """)

    # 12. analysis_history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_time TEXT,
            market TEXT,
            ticker TEXT,
            name TEXT,
            current_price TEXT,
            buy_target TEXT,
            sell_target TEXT,
            stop_loss TEXT,
            rating TEXT,
            long_term_rating TEXT,
            short_term_view_pct TEXT,
            analysis_json TEXT
        )
    """)

    # 13. exchange_rates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exchange_rates (
            date_str TEXT PRIMARY KEY,
            rate REAL,
            updated_time TEXT
        )
    """)

    # 14. pattern_profile — 내 거래 기록에서 학습한 성공 패턴 프로파일
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pattern_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            profile_json TEXT,
            trade_count INTEGER,
            updated_time TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS screener_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            picked_date TEXT,
            ticker TEXT,
            name TEXT,
            match_score REAL,
            signal TEXT,
            rsi REAL,
            vol_ratio REAL,
            pos_52w REAL,
            ma_aligned INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pattern_profile_v2 (
            source TEXT PRIMARY KEY,
            profile_json TEXT,
            trade_count INTEGER,
            updated_time TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_daily_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_date TEXT,
            title TEXT,
            theme TEXT,
            sentiment TEXT,
            related_tickers TEXT,
            summary TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_date TEXT,
            keyword TEXT,
            scenario_json TEXT,
            created_at TEXT,
            UNIQUE(scenario_date, keyword)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decided_at TEXT,
            ticker TEXT,
            name TEXT,
            market TEXT,
            action TEXT,
            confidence INTEGER,
            entry_price REAL,
            rsi REAL,
            ma_aligned INTEGER,
            pos_52w REAL,
            vol_ratio REAL,
            reason TEXT,
            outcome_return REAL,
            outcome_checked_at TEXT,
            is_realized INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scenario_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_keyword TEXT,
            scenario_title TEXT,
            ticker TEXT,
            name TEXT,
            market TEXT DEFAULT 'kr',
            role TEXT,
            horizon TEXT,
            captured_at TEXT,
            captured_price REAL,
            d1_price REAL,
            d3_price REAL,
            d7_price REAL,
            d1_return REAL,
            d3_return REAL,
            d7_return REAL,
            updated_at TEXT
        )
    """)

    # 외국인·기관 수급 일일 스냅샷 (세력 자금 흐름 추적용)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS frgn_inst_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT,
            market TEXT,          -- J=KOSPI, Q=KOSDAQ
            ticker TEXT,
            name TEXT,
            frgn_ntby INTEGER,    -- 외국인 순매수 수량
            orgn_ntby INTEGER,    -- 기관 순매수 수량
            combined INTEGER,     -- 외국인+기관 합산 (세력 강도)
            created_at TEXT,
            UNIQUE(snapshot_date, market, ticker)
        )
    """)

    # 섹터별 외국인·기관 수급 일일 집계 (섹터 자금 로테이션 추적용)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sector_flow_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT,
            sector TEXT,
            frgn_sum INTEGER,     -- 섹터 내 외국인 순매수 합
            orgn_sum INTEGER,     -- 섹터 내 기관 순매수 합
            combined_sum INTEGER, -- 외국인+기관 합산 (섹터 세력 강도)
            stock_count INTEGER,
            created_at TEXT,
            UNIQUE(snapshot_date, sector)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS screener_backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            picked_date TEXT,
            ticker TEXT,
            name TEXT,
            match_score REAL,
            signal TEXT,
            entry_price REAL,
            d1_price REAL,
            d3_price REAL,
            d7_price REAL,
            d1_return REAL,
            d3_return REAL,
            d7_return REAL,
            computed_at TEXT,
            UNIQUE(picked_date, ticker)
        )
    """)

    # 컬럼 마이그레이션 — 이미 존재하면 무시
    for migration in [
        "ALTER TABLE portfolio ADD COLUMN trade_source TEXT DEFAULT '개인'",
        "ALTER TABLE portfolio ADD COLUMN trade_type TEXT DEFAULT '실매매'",
        "ALTER TABLE trade_history ADD COLUMN trade_source TEXT DEFAULT '개인'",
        "ALTER TABLE trade_history ADD COLUMN trade_type TEXT DEFAULT '실매매'",
        "ALTER TABLE trade_history ADD COLUMN buy_date TEXT DEFAULT ''",
        "ALTER TABLE trade_history ADD COLUMN screener_matched INTEGER DEFAULT 0",
        "ALTER TABLE screener_picks ADD COLUMN market TEXT DEFAULT 'kr'",
        "ALTER TABLE screener_backtest_results ADD COLUMN market TEXT DEFAULT 'kr'",
        "ALTER TABLE scenario_stocks ADD COLUMN horizon TEXT",
        "ALTER TABLE portfolio ADD COLUMN buy_reason TEXT DEFAULT ''",
        "ALTER TABLE trade_history ADD COLUMN buy_reason TEXT DEFAULT ''",
        "ALTER TABLE agent_decisions ADD COLUMN is_realized INTEGER DEFAULT 0",
    ]:
        try:
            cursor.execute(migration)
        except Exception:
            pass

    # 기존 데이터 티커 6자리 제로패딩 정규화 (숫자 종목코드만)
    for fix_sql in [
        """UPDATE trade_history
           SET ticker = substr('000000', 1, 6 - length(trim(ticker))) || trim(ticker)
           WHERE trim(ticker) NOT GLOB '*[^0-9]*' AND length(trim(ticker)) < 6""",
        """UPDATE portfolio
           SET ticker = substr('000000', 1, 6 - length(trim(ticker))) || trim(ticker)
           WHERE trim(ticker) NOT GLOB '*[^0-9]*' AND length(trim(ticker)) < 6""",
    ]:
        try:
            cursor.execute(fix_sql)
        except Exception:
            pass

    conn.commit()
    conn.close()

def seed_sync_from_gsheet():
    """로컬 데이터베이스가 비어있고 구글 시트 접근이 가능할 때 구글 시트 데이터를 로컬로 마이그레이션합니다."""
    def run_sync():
        try:
            conn = get_db_conn()
            cursor = conn.cursor()
            
            # 동기화가 필요한 테이블이 하나라도 비어있는지 체크
            cursor.execute("SELECT COUNT(*) FROM favorites")
            fav_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM portfolio")
            port_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM trade_history")
            trade_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM virtual_balances")
            bal_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM ai_portfolio")
            ai_port_count = cursor.fetchone()[0]
            
            if fav_count > 0 and port_count > 0 and trade_count > 0 and bal_count > 0 and ai_port_count > 0:
                conn.close()
                return

            # 스프레드시트 단 한번만 호출
            sh, _ = _get_spreadsheet()
            if not sh:
                conn.close()
                return
            
            # 1. 즐겨찾기 동기화
            if fav_count == 0:
                try:
                    ws = sh.worksheet("즐겨찾기")
                    records = safe_get_all_records(ws)
                    for r in records:
                        cursor.execute(
                            "INSERT OR IGNORE INTO favorites (ticker, name, market_type, added_time) VALUES (?, ?, ?, ?)",
                            (str(r.get("티커", "")), str(r.get("종목명", "")), str(r.get("시장", "")), str(r.get("추가시간", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))))
                        )
                except Exception:
                    pass
                        
            # 2. 현재포트폴리오 동기화
            if port_count == 0:
                try:
                    ws = sh.worksheet("현재포트폴리오")
                    records = safe_get_all_records(ws)
                    for r in records:
                        cursor.execute(
                            "INSERT OR IGNORE INTO portfolio (owner, ticker, name, quantity, buy_price, rating, updated_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (str(r.get("소유자", "USER")).upper(), str(r.get("티커", "")), str(r.get("종목명", "")),
                             float(r.get("수량", 0) or 0), float(r.get("매수가($)", 0) or 0), str(r.get("등급", "-")), str(r.get("저장시간", "")))
                        )
                except Exception:
                    pass

            # 3. 거래내역 동기화
            if trade_count == 0:
                try:
                    ws = sh.worksheet("거래내역")
                    records = safe_get_all_records(ws)
                    for r in records:
                        cursor.execute(
                            "INSERT OR IGNORE INTO trade_history (owner, sell_date, ticker, name, quantity, buy_price, sell_price, profit, profit_pct, result, learning_point) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (str(r.get("소유자", "USER")).upper(), str(r.get("매도시간", "")), str(r.get("티커", "")), str(r.get("종목명", "")),
                             float(r.get("수량", 0) or 0), float(r.get("매수가($)", 0) or 0), float(r.get("매도가($)", 0) or 0),
                             float(r.get("수익금($)", 0) or 0), float(r.get("수익률(%)", 0) or 0), str(r.get("결과", "")), str(r.get("학습포인트", "")))
                        )
                except Exception:
                    pass

            # 4. 모의계좌 잔고 동기화
            if bal_count == 0:
                try:
                    ws = sh.worksheet("모의투자계좌")
                    records = safe_get_all_records(ws)
                    for r in records:
                        cursor.execute(
                            "INSERT OR IGNORE INTO virtual_balances (owner, balance, updated_time) VALUES (?, ?, ?)",
                            (str(r.get("소유자", "")).upper(), float(r.get("잔고(₩)", 10000000)), str(r.get("최근업데이트", "")))
                        )
                except Exception:
                    pass

            # 5. AI추천포트폴리오 동기화
            if ai_port_count == 0:
                try:
                    ws = sh.worksheet("AI추천포트폴리오")
                    records = safe_get_all_records(ws)
                    for r in records:
                        cursor.execute(
                            "INSERT OR IGNORE INTO ai_portfolio (ticker, name, quantity, buy_price, rating, updated_time) VALUES (?, ?, ?, ?, ?, ?)",
                            (str(r.get("티커", "")), str(r.get("종목명", "")), float(r.get("수량", 0) or 0), float(r.get("매수가($)", 0) or 0),
                             str(r.get("등급", "-")), str(r.get("저장시간", "")))
                        )
                except Exception:
                    pass

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Seed sync failed: {e}")

    threading.Thread(target=run_sync, daemon=True).start()

def safe_get_all_records(ws) -> list[dict]:
    """gspread의 ws.get_all_records()가 헤더 중복 예외 등으로 터지는 것을 방지하는 안전한 조회 헬퍼입니다."""
    try:
        return ws.get_all_records()
    except Exception as e:
        try:
            rows = ws.get_all_values()
            if not rows:
                return []
            headers = rows[0]
            seen = {}
            unique_headers = []
            for h in headers:
                h_str = str(h).strip()
                if not h_str:
                    h_str = "empty_column"
                if h_str in seen:
                    seen[h_str] += 1
                    unique_headers.append(f"{h_str}_{seen[h_str]}")
                else:
                    seen[h_str] = 0
                    unique_headers.append(h_str)

            records = []
            for r in rows[1:]:
                row_vals = r + [""] * (len(unique_headers) - len(r))
                row_vals = row_vals[:len(unique_headers)]
                records.append(dict(zip(unique_headers, row_vals)))
            return records
        except Exception as inner_e:
            print(f"Failed safe_get_all_records fallback: {inner_e}")
            return []

def run_background_backup(target_func, *args, **kwargs):
    """지정한 동기화용 백업 함수를 백그라운드 스레드에서 안정적으로 실행합니다."""
    def worker():
        try:
            target_func(*args, **kwargs)
        except Exception as e:
            print(f"Background backup failed for {target_func.__name__}: {e}")
    threading.Thread(target=worker, daemon=True).start()


def _rebuild_pattern_profile_bg():
    """거래 기록 변경 후 패턴 프로파일(전체/개인/리딩방)을 백그라운드에서 자동 재빌드합니다."""
    try:
        from ai_engine import build_pattern_profile
        build_pattern_profile('all')
        build_pattern_profile('personal')
        build_pattern_profile('leading')
        print("[pattern] 패턴 프로파일 자동 갱신 완료")
    except Exception as e:
        print(f"[pattern] 패턴 프로파일 자동 갱신 실패: {e}")

# 모듈 로드 시 데이터베이스 및 시드 설정 가동
init_local_db()
seed_sync_from_gsheet()

@st.cache_resource
def get_gsheet_client():
    """Google Sheets 클라이언트를 초기화하고 캐싱합니다."""
    try:
        creds_json = os.getenv("GSPREAD_CREDENTIALS", "")
        creds_dict = _json.loads(creds_json) if creds_json else {}

        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

        gc = gspread.service_account_from_dict(creds_dict)
        return gc
    except Exception as e:
        return None

def _get_spreadsheet():
    gc = get_gsheet_client()
    if not gc:
        return None, "구글 시트 인증 실패. .env의 GSPREAD_CREDENTIALS 설정을 확인해주세요."
    try:
        # 환경변수에 spreadsheet_id가 있으면 직접 지정 (빠르고 안정적)
        sheet_id = os.getenv("GSPREAD_SPREADSHEET_ID", "")
        if sheet_id:
            return gc.open_by_key(sheet_id), "성공"
        # fallback: 공유된 첫 번째 시트 사용
        spreadsheets = gc.openall()
        if not spreadsheets:
            return None, "봇 계정에 공유된 스프레드시트가 없습니다. 구글 시트를 만들고 봇 이메일을 공유에 추가하거나, secrets에 spreadsheet_id를 추가해주세요."
        return spreadsheets[0], "성공"
    except Exception as e:
        return None, f"스프레드시트 접근 오류: {e}"

def _get_or_create_worksheet(sh, title, headers):
    try:
        ws = sh.worksheet(title)
        # 만약 탭은 존재하지만 내용이 완전히 비어있다면 헤더를 써줍니다
        first_row = ws.row_values(1)
        if not first_row:
            ws.update("A1", [headers])
        return ws
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=20)
        ws.update("A1", [headers])
        return ws

def _gsheet_backup_portfolio(portfolio_list, current_prices_df=None, owner="USER"):
    """[구글 시트 백업 전용] 현재 포트폴리오 스냅샷을 '현재포트폴리오' 탭에 백업합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["소유자", "저장시간", "티커", "종목명", "수량", "매수가($)", "현재가($)", "수익금($)", "수익률(%)", "등급"]
        ws = _get_or_create_worksheet(sh, "현재포트폴리오", headers)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # SQLite에서 모든 소유자 데이터를 읽어 전체 재구성 (구글 시트 read 제거)
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT owner, ticker, name, quantity, buy_price, rating FROM portfolio")
        all_rows = cursor.fetchall()
        conn.close()

        ws.clear()
        ws.append_row(headers)
        rows_to_add = []
        for r in all_rows:
            o = str(r["owner"]).upper()
            tk = str(r["ticker"])
            bp = float(r["buy_price"] or 0)
            qty = float(r["quantity"] or 0)
            cp = bp
            profit, profit_pct = 0.0, 0.0
            if o == owner.upper() and current_prices_df is not None and not current_prices_df.empty:
                if tk in current_prices_df["심볼"].values:
                    cp = current_prices_df[current_prices_df["심볼"] == tk].iloc[0]["현재가($)"]
                    invested = bp * qty
                    profit = (cp * qty) - invested
                    profit_pct = (profit / invested * 100) if invested > 0 else 0
            rows_to_add.append([o, now, tk, str(r["name"]), qty,
                                 round(bp, 2), round(cp, 2),
                                 round(profit, 2), round(profit_pct, 2), str(r["rating"] or "-")])
        if rows_to_add:
            ws.append_rows(rows_to_add)
        return True, "성공"
    except Exception as e:
        print(f"Failed to backup portfolio to Google Sheets: {e}")
        return False, str(e)

def save_portfolio_to_gsheet(portfolio_list, current_prices_df=None, owner="USER"):
    """현재 포트폴리오 목록을 로컬 SQLite에 즉시 저장하고, 백그라운드 스레드로 구글 시트에 업데이트합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        
        # 기존 DB의 포트폴리오 종목별 최초 매수 시각(updated_time)·매수 근거 조회하여 백업
        existing_times = {}
        existing_reasons = {}
        cursor.execute("SELECT ticker, updated_time, buy_reason FROM portfolio WHERE UPPER(owner) = ?", (owner.upper(),))
        for r in cursor.fetchall():
            existing_times[str(r["ticker"])] = str(r["updated_time"])
            existing_reasons[str(r["ticker"])] = str(r["buy_reason"] or "")

        # 해당 owner의 기존 포트폴리오를 지우고 새로 채움
        cursor.execute("DELETE FROM portfolio WHERE UPPER(owner) = ?", (owner.upper(),))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in portfolio_list:
            ticker = _pad_kr_ticker(item["ticker"])
            buy_time = item.get("buy_date") or item.get("updated_time") or existing_times.get(ticker) or now
            # 매수 근거: 들어온 값 우선, 없으면 기존 값 보존
            buy_reason = item.get("buy_reason")
            if buy_reason is None:
                buy_reason = existing_reasons.get(ticker, "")

            cursor.execute(
                "INSERT OR REPLACE INTO portfolio (owner, ticker, name, quantity, buy_price, rating, updated_time, trade_source, trade_type, buy_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (owner.upper(), ticker, str(item.get("name", item["ticker"])), float(item["quantity"]), float(item["buy_price"]), str(item.get("rating", "-")), buy_time,
                 str(item.get("trade_source", "개인")), str(item.get("trade_type", "실매매")), str(buy_reason or ""))
            )
        conn.commit()
        conn.close()
        
        # 구글 시트에 비동기 백업 구동
        run_background_backup(_gsheet_backup_portfolio, portfolio_list, current_prices_df, owner)
        
        return True, f"로컬 데이터베이스 및 구글 시트 백업 요청 완료! ({len(portfolio_list)}개 종목)"
    except Exception as e:
        return False, f"로컬 저장 오류: {e}"

def load_portfolio_from_gsheet(owner="USER"):
    """로컬 SQLite에서 포트폴리오 목록을 불러옵니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ticker, name, buy_price, quantity, updated_time as buy_date, rating, owner, trade_source, trade_type, buy_reason FROM portfolio WHERE UPPER(owner) = ?",
            (owner.upper(),)
        )
        rows = cursor.fetchall()
        conn.close()

        portfolio_list = []
        for r in rows:
            ticker = str(r["ticker"])
            if ticker.isdigit() and len(ticker) < 6:
                ticker = ticker.zfill(6)
            portfolio_list.append({
                "ticker": ticker,
                "name": str(r["name"]),
                "buy_price": float(r["buy_price"] or 0),
                "quantity": float(r["quantity"] or 0),
                "buy_date": str(r["buy_date"] or ""),
                "rating": str(r["rating"] or "-"),
                "owner": str(r["owner"]).upper(),
                "trade_source": str(r["trade_source"] or "개인"),
                "trade_type": str(r["trade_type"] or "실매매"),
                "buy_reason": str(r["buy_reason"] or ""),
            })
        return portfolio_list
    except Exception as e:
        print(f"Error loading portfolio from SQLite: {e}")
        return []

def _gsheet_backup_ai_portfolio(portfolio_list):
    """[구글 시트 백업 전용] AI 자동 추천 종목 목록을 'AI추천포트폴리오' 탭에 백업합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["저장시간", "티커", "종목명", "수량", "매수가($)", "등급"]
        ws = _get_or_create_worksheet(sh, "AI추천포트폴리오", headers)
        ws.clear()
        ws.append_row(headers)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in portfolio_list:
            ws.append_row([
                now,
                item["ticker"],
                item.get("name", item["ticker"]),
                item.get("quantity", 0),
                round(float(item.get("buy_price", 0)), 2),
                item.get("rating", "-"),
            ])
        return True, "성공"
    except Exception as e:
        print(f"Failed to backup AI portfolio to Google Sheets: {e}")
        return False, str(e)

def save_ai_portfolio_to_gsheet(portfolio_list):
    """AI 자동 추천 종목 목록을 로컬 SQLite에 즉시 저장하고, 백그라운드 스레드로 구글 시트에 백업합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ai_portfolio")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in portfolio_list:
            cursor.execute(
                "INSERT OR REPLACE INTO ai_portfolio (ticker, name, quantity, buy_price, rating, updated_time) VALUES (?, ?, ?, ?, ?, ?)",
                (str(item["ticker"]), str(item.get("name", item["ticker"])), float(item.get("quantity", 0)), float(item.get("buy_price", 0)), str(item.get("rating", "-")), now)
            )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_ai_portfolio, portfolio_list)
        return True, f"AI 추천 포트폴리오 {len(portfolio_list)}개 저장 및 백업 요청 완료!"
    except Exception as e:
        return False, f"로컬 저장 오류: {e}"

def load_ai_portfolio_from_gsheet():
    """로컬 SQLite에서 AI 자동 추천 포트폴리오 목록을 불러옵니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT ticker, name, buy_price, quantity, updated_time as buy_date, rating FROM ai_portfolio")
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for r in rows:
            ticker = str(r["ticker"])
            if ticker.isdigit() and len(ticker) < 6:
                ticker = ticker.zfill(6)
            result.append({
                "ticker":    ticker,
                "name":      str(r["name"]),
                "buy_price": float(r["buy_price"] or 0),
                "quantity":  int(r["quantity"] or 0),
                "buy_date":  str(r["buy_date"] or ""),
                "rating":    str(r["rating"] or "-"),
            })
        return result
    except Exception as e:
        print(f"Error loading AI portfolio from SQLite: {e}")
        return []

def _gsheet_backup_save_trade(trade, owner="USER"):
    """[구글 시트 백업 전용] 완료된 거래 1건을 '거래내역' 탭에 기록합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["소유자", "매도시간", "티커", "종목명", "수량", "매수가($)", "매도가($)", "수익금($)", "수익률(%)", "결과", "학습포인트"]
        ws = _get_or_create_worksheet(sh, "거래내역", headers)
        ws.append_row([
            owner.upper(),
            trade.get("sell_date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            trade.get("ticker", ""),
            trade.get("name", ""),
            trade.get("quantity", 0),
            round(float(trade.get("buy_price", 0)), 2),
            round(float(trade.get("sell_price", 0)), 2),
            round(float(trade.get("profit", 0)), 2),
            round(float(trade.get("profit_pct", 0)), 2),
            trade.get("result", ""),
            trade.get("learning_point", "")
        ])
        return True, "성공"
    except Exception as e:
        print(f"Failed to backup trade record to Google Sheets: {e}")
        return False, str(e)

def save_trade_record(trade, owner="USER"):
    """완료된 거래 1건을 로컬 SQLite에 즉시 저장하고, 백그라운드로 구글 시트에 업데이트합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        
        sell_date = trade.get("sell_date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        buy_date  = trade.get("buy_date") or ""
        ticker    = _pad_kr_ticker(trade.get("ticker", ""))
        cursor.execute(
            "INSERT OR REPLACE INTO trade_history (owner, sell_date, ticker, name, quantity, buy_price, sell_price, profit, profit_pct, result, learning_point, trade_source, trade_type, buy_date, buy_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (owner.upper(), sell_date, ticker, str(trade.get("name", "")),
             float(trade.get("quantity", 0)), float(trade.get("buy_price", 0)), float(trade.get("sell_price", 0)),
             float(trade.get("profit", 0)), float(trade.get("profit_pct", 0)), str(trade.get("result", "")), str(trade.get("learning_point", "")),
             str(trade.get("trade_source", "개인")), str(trade.get("trade_type", "실매매")), buy_date, str(trade.get("buy_reason", "")))
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_save_trade, trade, owner)
        run_background_backup(_rebuild_pattern_profile_bg)
        return True, "거래 내역이 로컬 DB에 기록되었으며 백업을 요청했습니다."
    except Exception as e:
        return False, f"로컬 기록 오류: {e}"

def _gsheet_backup_delete_trade(ticker, sell_date):
    """[구글 시트 백업 전용] '거래내역' 탭에서 ticker + sell_date가 일치하는 행을 삭제합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        ws = sh.worksheet("거래내역")
        rows = ws.get_all_values()
        for i in range(len(rows) - 1, 0, -1):
            row = rows[i]
            if len(row) >= 3 and str(row[1]).strip() == str(sell_date).strip() and str(row[2]).strip() == str(ticker).strip():
                ws.delete_rows(i + 1)
                return True, "구글 시트에서 삭제 완료"
        return False, "구글 시트에서 행을 찾지 못함"
    except Exception as e:
        print(f"Failed to delete trade from Google Sheets: {e}")
        return False, str(e)

def delete_trade_from_gsheet(ticker: str, sell_date: str):
    """로컬 SQLite에서 특정 거래 정보를 즉시 삭제하고, 백그라운드 스레드로 구글 시트에서 지웁니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM trade_history WHERE TRIM(sell_date) = TRIM(?) AND TRIM(ticker) = TRIM(?)",
            (sell_date, ticker)
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_delete_trade, ticker, sell_date)
        run_background_backup(_rebuild_pattern_profile_bg)
        return True, "로컬 DB에서 삭제되었으며 구글 시트 삭제 요청을 보냈습니다."
    except Exception as e:
        return False, f"로컬 삭제 오류: {e}"

def _gsheet_backup_update_learning_point(ticker, sell_date, learning_point):
    """[구글 시트 백업 전용] '거래내역' 탭에서 특정 거래의 '학습포인트' 열을 업데이트합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        ws = sh.worksheet("거래내역")
        rows = ws.get_all_values()
        headers = rows[0]
        try:
            lp_col_idx = headers.index("학습포인트") + 1
            for i in range(len(rows) - 1, 0, -1):
                row = rows[i]
                if len(row) >= 3 and str(row[1]).strip() == str(sell_date).strip() and str(row[2]).strip() == str(ticker).strip():
                    ws.update_cell(i + 1, lp_col_idx, learning_point)
                    return True, "학습포인트 구글 시트 저장 완료"
        except ValueError:
            pass
        return False, "구글 시트에서 찾지 못함"
    except Exception as e:
        print(f"Failed to update learning point in Google Sheets: {e}")
        return False, str(e)

def update_trade_source_type(ticker: str, sell_date: str, trade_source: str, trade_type: str):
    """로컬 SQLite에서 특정 거래의 출처/유형을 즉시 갱신하고, 백그라운드 스레드로 구글 시트에 동기화합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        # 티커: 제로패딩 정규화 (DB에 '96770', 프론트에서 '096770' 올 수 있음)
        # sell_date: T/공백 구분자 혼재 정규화
        cursor.execute(
            """UPDATE trade_history
               SET trade_source = ?, trade_type = ?
               WHERE LTRIM(TRIM(ticker), '0') = LTRIM(TRIM(?), '0')
                 AND REPLACE(TRIM(sell_date), 'T', ' ') = REPLACE(TRIM(?), 'T', ' ')""",
            (trade_source, trade_type, ticker, sell_date)
        )
        conn.commit()
        conn.close()
        run_background_backup(_gsheet_backup_update_trade_source_type, ticker, sell_date, trade_source, trade_type)
        run_background_backup(_rebuild_pattern_profile_bg)
        return True, "출처/유형 업데이트 완료!"
    except Exception as e:
        return False, f"로컬 업데이트 오류: {e}"


def update_trade_buy_date(ticker: str, sell_date: str, buy_date: str):
    """거래내역의 매수 시각(buy_date)을 수정하고 패턴 프로파일을 재빌드합니다.
    (시세창에서 즉시 매수해 매수 시각이 누락/부정확한 경우 보정용)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE trade_history
               SET buy_date = ?
               WHERE LTRIM(TRIM(ticker), '0') = LTRIM(TRIM(?), '0')
                 AND REPLACE(TRIM(sell_date), 'T', ' ') = REPLACE(TRIM(?), 'T', ' ')""",
            (buy_date, ticker, sell_date)
        )
        n = cursor.rowcount
        conn.commit()
        conn.close()
        if n:
            run_background_backup(_gsheet_backup_update_trade_buy_date, ticker, sell_date, buy_date)
            run_background_backup(_rebuild_pattern_profile_bg)
            return True, "매수 시각 업데이트 완료!"
        return False, "해당 거래를 찾을 수 없습니다."
    except Exception as e:
        return False, f"로컬 업데이트 오류: {e}"


def _gsheet_backup_update_trade_buy_date(ticker, sell_date, buy_date):
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        ws = sh.worksheet("거래내역")
        rows = ws.get_all_values()
        headers = rows[0]
        col_idx = None
        for col_name in ("매수시간", "매수일", "buy_date"):
            if col_name in headers:
                col_idx = headers.index(col_name) + 1
                break
        if col_idx:
            for i in range(len(rows) - 1, 0, -1):
                row = rows[i]
                if len(row) >= 3 and str(row[1]).strip() == str(sell_date).strip() and str(row[2]).strip() == str(ticker).strip():
                    ws.update_cell(i + 1, col_idx, buy_date)
                    break
    except Exception:
        pass
    return True, "ok"


def update_trade_buy_reason(ticker: str, sell_date: str, buy_reason: str):
    """거래내역의 매수 근거(리딩방이 왜 사라고 했는지 등)를 수정합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE trade_history
               SET buy_reason = ?
               WHERE LTRIM(TRIM(ticker), '0') = LTRIM(TRIM(?), '0')
                 AND REPLACE(TRIM(sell_date), 'T', ' ') = REPLACE(TRIM(?), 'T', ' ')""",
            (buy_reason, ticker, sell_date)
        )
        n = cursor.rowcount
        conn.commit()
        conn.close()
        return (True, "매수 근거 업데이트 완료!") if n else (False, "해당 거래를 찾을 수 없습니다.")
    except Exception as e:
        return False, f"로컬 업데이트 오류: {e}"


def update_portfolio_buy_time(ticker: str, owner: str, buy_time: str):
    """보유종목(portfolio)의 매수 시각(updated_time)을 수정합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE portfolio
               SET updated_time = ?
               WHERE LTRIM(TRIM(ticker), '0') = LTRIM(TRIM(?), '0')
                 AND UPPER(owner) = UPPER(?)""",
            (buy_time, ticker, owner)
        )
        n = cursor.rowcount
        conn.commit()
        conn.close()
        if n:
            return True, "보유종목 매수 시각 업데이트 완료!"
        return False, "해당 보유종목을 찾을 수 없습니다."
    except Exception as e:
        return False, f"로컬 업데이트 오류: {e}"

def _gsheet_backup_update_trade_source_type(ticker, sell_date, trade_source, trade_type):
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        ws = sh.worksheet("거래내역")
        rows = ws.get_all_values()
        headers = rows[0]
        for col_name, value in [("출처", trade_source), ("유형", trade_type)]:
            try:
                col_idx = headers.index(col_name) + 1
                for i in range(len(rows) - 1, 0, -1):
                    row = rows[i]
                    if len(row) >= 3 and str(row[1]).strip() == str(sell_date).strip() and str(row[2]).strip() == str(ticker).strip():
                        ws.update_cell(i + 1, col_idx, value)
                        break
            except ValueError:
                pass
        return True, "구글 시트 출처/유형 업데이트 완료"
    except Exception as e:
        print(f"Failed to update trade source/type in Google Sheets: {e}")
        return False, str(e)

def update_trade_learning_point(ticker: str, sell_date: str, learning_point: str):
    """로컬 SQLite에서 특정 거래의 학습포인트를 즉시 갱신하고, 백그라운드 스레드로 구글 시트에 동기화합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE trade_history SET learning_point = ? WHERE TRIM(sell_date) = TRIM(?) AND TRIM(ticker) = TRIM(?)",
            (learning_point, sell_date, ticker)
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_update_learning_point, ticker, sell_date, learning_point)
        return True, "로컬 DB 학습포인트 업데이트 및 백업 완료!"
    except Exception as e:
        return False, f"로컬 업데이트 오류: {e}"

def load_trade_history_from_gsheet(owner="USER"):
    """로컬 SQLite에서 모든 거래 기록을 DataFrame으로 불러옵니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT owner as 소유자, sell_date as 매도시간, buy_date as 매수시간, ticker as 티커, name as 종목명, quantity as 수량, buy_price as `매수가($)`, sell_price as `매도가($)`, profit as `수익금($)`, profit_pct as `수익률(%)`, result as 결과, learning_point as 학습포인트, trade_source as 출처, trade_type as 유형, buy_reason as 매수사유 FROM trade_history WHERE UPPER(owner) = ?",
            (owner.upper(),)
        )
        rows = cursor.fetchall()
        conn.close()

        filtered = []
        for r in rows:
            row_dict = dict(r)
            row_dict["티커"] = _pad_kr_ticker(str(row_dict["티커"]))
            filtered.append(row_dict)
            
        return pd.DataFrame(filtered), "성공"
    except Exception as e:
        print(f"Error loading trade history from SQLite: {e}")
        return None, f"로컬 DB 오류: {e}"

# ── 모의투자 계좌 잔고 관리 ──
def load_virtual_balances():
    """로컬 SQLite에서 소유자별 현금 잔고를 불러옵니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT owner, balance FROM virtual_balances")
        rows = cursor.fetchall()
        conn.close()
        
        balances = {"USER": 10000000.0, "AI": 10000000.0, "AI_AGENT": 10000000.0}
        for r in rows:
            balances[str(r["owner"]).upper()] = float(r["balance"] or 10000000)
        return balances
    except Exception as e:
        print(f"Error loading virtual balances from SQLite: {e}")
        return {"USER": 10000000.0, "AI": 10000000.0, "AI_AGENT": 10000000.0}

def _gsheet_backup_save_balance(owner: str, balance: float):
    """[구글 시트 백업 전용] '모의투자계좌' 탭에 소유자의 현금 잔고를 저장합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False
    try:
        headers = ["소유자", "잔고(₩)", "최근업데이트"]
        ws = _get_or_create_worksheet(sh, "모의투자계좌", headers)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # read 없이 append (시트는 로그 형태 — SQLite가 정본)
        ws.append_row([owner.upper(), balance, now])
        return True
    except Exception as e:
        print(f"Failed to backup virtual balance to Google Sheets: {e}")
        return False

def save_virtual_balance(owner: str, balance: float):
    """로컬 SQLite에 현금 잔고를 저장하고, 백그라운드 스레드로 구글 시트에 업데이트합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT OR REPLACE INTO virtual_balances (owner, balance, updated_time) VALUES (?, ?, ?)",
            (owner.upper(), float(balance), now)
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_save_balance, owner, balance)
        return True
    except Exception as e:
        print(f"Error saving virtual balance: {e}")
        return False

def _gsheet_backup_log_recommendation(rec_type: str, ticker: str, name: str, rating: str,
                                     buy_target: str, sell_target: str, stop_loss: str):
    """[구글 시트 백업 전용] AI 추천 내역을 'AI추천로그' 탭에 백업합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        headers = ["기록시간", "유형", "티커", "종목명", "등급/추천", "매수가", "목표가", "손절가"]
        ws = _get_or_create_worksheet(sh, "AI추천로그", headers)
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            rec_type, ticker, name, rating,
            str(buy_target), str(sell_target), str(stop_loss)
        ])
        return True, "성공"
    except Exception as e:
        print(f"Failed to backup AI recommendation log: {e}")
        return False, str(e)

def log_ai_recommendation(rec_type: str, ticker: str, name: str, rating: str,
                           buy_target: str, sell_target: str, stop_loss: str):
    """AI 추천 내역을 로컬 SQLite에 즉시 기록하고, 백그라운드 스레드로 구글 시트에 백업합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO ai_recommendations (logged_time, rec_type, ticker, name, rating, buy_target, sell_target, stop_loss) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (now, rec_type, ticker, name, rating, str(buy_target), str(sell_target), str(stop_loss))
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_log_recommendation, rec_type, ticker, name, rating, buy_target, sell_target, stop_loss)
        return True, "AI 추천 로그가 기록되었습니다."
    except Exception as e:
        return False, f"로컬 기록 오류: {e}"


def _gsheet_backup_save_favorite(market_type: str, ticker: str, name: str):
    """[구글 시트 백업 전용] 종목을 '즐겨찾기' 탭에 백업합니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return False, msg
    try:
        headers = ["추가시간", "시장", "티커", "종목명"]
        ws = _get_or_create_worksheet(sh, "즐겨찾기", headers)
        # 중복 체크는 SQLite에서 완료됨 — 구글 시트 read 없이 바로 append
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            market_type, ticker, name
        ])
        return True, "성공"
    except Exception as e:
        print(f"Failed to backup favorite: {e}")
        return False, str(e)

def save_favorite(market_type: str, ticker: str, name: str):
    """종목을 로컬 SQLite 즐겨찾기에 추가하고, 백그라운드로 구글 시트에 업데이트합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        
        # 중복 체크
        cursor.execute("SELECT COUNT(*) FROM favorites WHERE ticker = ?", (ticker,))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return True, "이미 즐겨찾기에 등록된 종목입니다."
            
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO favorites (ticker, name, market_type, added_time) VALUES (?, ?, ?, ?)",
            (ticker, name, market_type, now)
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_save_favorite, market_type, ticker, name)
        return True, f"[{name}] 즐겨찾기에 추가되었습니다."
    except Exception as e:
        return False, f"로컬 저장 오류: {e}"

def _gsheet_backup_remove_favorite(ticker: str):
    """[구글 시트 백업 전용] 종목을 '즐겨찾기' 탭에서 삭제합니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return False, msg
    try:
        ws = sh.worksheet("즐겨찾기")
        cells = ws.find(ticker)
        if cells:
            ws.delete_rows(cells.row)
            return True, "성공"
        return False, "찾을 수 없음"
    except Exception as e:
        print(f"Failed to delete favorite from Google Sheets: {e}")
        return False, str(e)

def remove_favorite(ticker: str):
    """로컬 SQLite 즐겨찾기에서 종목을 즉시 삭제하고, 백그라운드 스레드로 구글 시트에서 삭제합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favorites WHERE ticker = ?", (ticker,))
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_remove_favorite, ticker)
        return True, "즐겨찾기에서 삭제되었습니다."
    except Exception as e:
        return False, f"로컬 삭제 오류: {e}"

def load_favorites():
    """로컬 SQLite에서 즐겨찾기 목록을 불러옵니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT added_time as 추가시간, market_type as 시장, ticker as 티커, name as 종목명 FROM favorites")
        rows = cursor.fetchall()
        conn.close()
        
        records = []
        for r in rows:
            t = str(r["티커"])
            t_padded = t.zfill(6) if t.isdigit() and len(t) <= 6 else t
            records.append({
                "추가시간": str(r["추가시간"]),
                "시장": str(r["시장"]),
                "티커": t_padded,
                "종목명": str(r["종목명"])
            })
        return records, "성공"
    except Exception as e:
        print(f"Error loading favorites from SQLite: {e}")
        return [], f"로컬 DB 오류: {e}"


def is_favorite(ticker):
    """특정 종목이 즐겨찾기에 있는지 확인합니다."""
    favs, _ = load_favorites()
    return any(str(f.get('티커', '')) == str(ticker) for f in favs)


def _gsheet_backup_log_agent_scan(ticker: str, name: str, current_price: float, position: str, action: str, confidence: int, reason: str):
    """[구글 시트 백업 전용] AI 자율매매 에이전트의 고민/스캔 이력을 'AI스캔로그' 탭에 백업합니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return False
    try:
        headers = ["스캔시간", "티커", "종목명", "현재가", "보유상태", "AI판단", "신뢰도(%)", "판단이유"]
        ws = _get_or_create_worksheet(sh, "AI스캔로그", headers)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([
            now, ticker, name, round(float(current_price), 2),
            position, action, int(confidence), reason
        ])
        
        # 최대 100건만 유지 (구글 시트 성능 최적화)
        rows = ws.get_all_values()
        if len(rows) > 105:
            ws.delete_rows(2, len(rows) - 101)
        return True
    except Exception as e:
        print(f"Failed to backup agent scan log: {e}")
        return False

def log_agent_scan(ticker: str, name: str, current_price: float, position: str, action: str, confidence: int, reason: str):
    """AI 자율매매 에이전트의 고민/스캔 이력을 로컬 SQLite에 즉시 저장하고, 백그라운드 스레드로 구글 시트에 백업합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO ai_scan_logs (scan_time, ticker, name, price, position, action, confidence, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (now, ticker, name, float(current_price), position, action, int(confidence), reason)
        )
        
        # 로컬도 최대 200건만 유지 (로컬 DB 파일 비대화 방지)
        cursor.execute("SELECT COUNT(*) FROM ai_scan_logs")
        count = cursor.fetchone()[0]
        if count > 210:
            cursor.execute("DELETE FROM ai_scan_logs WHERE id IN (SELECT id FROM ai_scan_logs ORDER BY id ASC LIMIT ?)", (count - 200,))
            
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_log_agent_scan, ticker, name, current_price, position, action, confidence, reason)
        return True, "성공"
    except Exception as e:
        print(f"Error logging agent scan: {e}")
        return False, f"스캔로그 저장 실패: {e}"

def load_agent_scan_logs_from_gsheet():
    """로컬 SQLite 'ai_scan_logs'에서 에이전트의 스캔 로그 목록을 불러옵니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT scan_time, ticker, name, price, position, action, confidence, reason FROM ai_scan_logs ORDER BY id DESC"
        )
        rows = cursor.fetchall()
        conn.close()
        
        scan_logs = []
        for r in rows:
            ticker = str(r["ticker"])
            if ticker.isdigit() and len(ticker) < 6:
                ticker = ticker.zfill(6)
            scan_logs.append({
                "scan_time": str(r["scan_time"]),
                "ticker": ticker,
                "name": str(r["name"]),
                "price": float(r["price"] or 0),
                "position": str(r["position"] or "NONE"),
                "action": str(r["action"] or "HOLD"),
                "confidence": int(r["confidence"] or 0),
                "reason": str(r["reason"] or "")
            })
        return scan_logs
    except Exception as e:
        print(f"Error loading agent scan logs from SQLite: {e}")
        return []


def _enrich_with_krx(raw_map: dict) -> dict:
    """FinanceDataReader(KRX)로 섹터 맵의 코드·suffix를 자동 보정."""
    try:
        from data_kr import get_kr_name_to_code_map
        name_map = get_kr_name_to_code_map()
    except Exception:
        name_map = {}
    if not name_map:
        return raw_map
    enriched: dict = {}
    for sector, subsectors in raw_map.items():
        enriched[sector] = {}
        for sub, stocks in subsectors.items():
            enriched_stocks = []
            for s in stocks:
                info = name_map.get(s["name"])
                enriched_stocks.append(
                    {"name": s["name"], "code": info["code"], "suffix": info["suffix"]}
                    if info else s.copy()
                )
            enriched[sector][sub] = enriched_stocks
    return enriched


@st.cache_data(ttl=300)
def load_sector_map() -> dict:
    """로컬 sectors_kr.py의 정적 맵을 메인 데이터소스로 사용하고 FDR 업종 데이터로 자동 보강합니다."""
    from sectors_kr import KR_SECTOR_MAP
    raw = KR_SECTOR_MAP

    # ── FDR 전종목 업종 자동 병합 ────────────────────────────────────────
    try:
        from data_kr import get_kr_fdr_sector_map
        fdr_map = get_kr_fdr_sector_map()
        if fdr_map:
            existing_codes: set = {
                s["code"]
                for subs in raw.values()
                for stocks in subs.values()
                for s in stocks
                if isinstance(s, dict) and s.get("code")
            }
            for sector, subs in fdr_map.items():
                for sub, stocks in subs.items():
                    new_stocks = [
                        s for s in stocks
                        if s.get("code") and s["code"] not in existing_codes
                    ]
                    if not new_stocks:
                        continue
                    if sector not in raw:
                        raw[sector] = {}
                    if sub not in raw[sector]:
                        raw[sector][sub] = []
                    raw[sector][sub].extend(new_stocks)
                    existing_codes.update(s["code"] for s in new_stocks)
    except Exception:
        pass

    # ── 키워드 자동 분류 (테마 섹터 보강) ────────────────────────────────
    try:
        from data_kr import get_kr_fdr_sector_map as _fdr_kr
        from sector_auto_classifier import enrich_sector_map_kr
        fdr_all_list: list = []
        fdr_raw = _fdr_kr()
        for _sec, _subs in fdr_raw.items():
            for _sub, _stks in _subs.items():
                for _s in _stks:
                    fdr_all_list.append({**_s, "industry": _sec})
        raw = enrich_sector_map_kr(raw, fdr_all_list)
    except Exception:
        pass

    # ── 상장폐지 종목 제거 — pykrx 현재 거래 종목 기준 필터링 ──────────────
    try:
        from pykrx import stock as _pykrx
        import datetime as _dt
        _today = _dt.date.today().strftime("%Y%m%d")
        _active: set = set()
        for _mkt in ["KOSPI", "KOSDAQ"]:
            try:
                _active.update(_pykrx.get_market_ticker_list(_today, market=_mkt))
            except Exception:
                pass
        if _active:
            for _sec in list(raw.keys()):
                for _sub in list(raw[_sec].keys()):
                    raw[_sec][_sub] = [s for s in raw[_sec][_sub] if s.get("code") in _active]
                    if not raw[_sec][_sub]:
                        del raw[_sec][_sub]
                if not raw[_sec]:
                    del raw[_sec]
    except Exception:
        pass

    return _enrich_with_krx(raw)


# FDR Industry(한국어) → (한국어 섹터, 한국어 서브섹터) 매핑
# FDR StockListing은 Sector 없이 Industry 한국어 텍스트만 제공
_FDR_IND_MAP: dict = {
    # ── AI·반도체 ─────────────────────────────────────────────
    "반도체":                               ("AI·반도체",           "반도체"),
    "반도체 장비 및 테스트":               ("AI·반도체",           "반도체 장비·소재"),
    "전자 장비 및 부품":                   ("AI·반도체",           "전자부품"),
    "전화 및 소형 장치":                   ("AI·반도체",           "전자부품"),
    "컴퓨터 및 전자 제품 소매":            ("AI·반도체",           "전자·컴퓨터 유통"),
    # ── 빅테크·AI소프트 ──────────────────────────────────────
    "소프트웨어":                           ("빅테크·AI소프트",     "소프트웨어"),
    "IT 서비스 및 컨설팅":                 ("빅테크·AI소프트",     "IT서비스"),
    "컴퓨터 하드웨어":                     ("빅테크·AI소프트",     "컴퓨터 하드웨어"),
    "온라인 서비스":                        ("빅테크·AI소프트",     "인터넷·콘텐츠"),
    "전문 정보 서비스":                     ("빅테크·AI소프트",     "IT서비스"),
    "통합 하드웨어 및 소프트웨어":         ("빅테크·AI소프트",     "IT서비스"),
    "사무기기":                             ("빅테크·AI소프트",     "컴퓨터 하드웨어"),
    # ── 소셜미디어·디지털광고 ────────────────────────────────
    "광고 및 마케팅":                       ("소셜미디어·디지털광고","광고대행"),
    # ── 바이오·헬스케어 ──────────────────────────────────────
    "생명 공학 및 의학 연구":              ("바이오·헬스케어",     "바이오테크"),
    "제약":                                 ("바이오·헬스케어",     "제약"),
    "첨단 의료 장비 및 기술":              ("바이오·헬스케어",     "의료기기"),
    "의료 장비, 물품 및 유통":             ("바이오·헬스케어",     "의료기기·용품"),
    "의료 시설 및 서비스":                 ("바이오·헬스케어",     "의료시설"),
    "의료 관리":                            ("바이오·헬스케어",     "헬스케어 보험"),
    "의약품 소매":                          ("바이오·헬스케어",     "의약품 소매"),
    # ── 방산·우주 ─────────────────────────────────────────────
    "항공우주 및 방위":                    ("방산·우주",            "항공·방산"),
    # ── 금융·핀테크 ──────────────────────────────────────────
    "은행":                                 ("금융·핀테크",         "종합은행"),
    "생명 및 건강 보험":                   ("금융·핀테크",         "생명보험"),
    "손해보험":                             ("금융·핀테크",         "손해보험"),
    "복합보험 및 중개인":                  ("금융·핀테크",         "복합보험"),
    "재보험":                               ("금융·핀테크",         "재보험"),
    "투자 관리 및 펀드 운영":              ("금융·핀테크",         "자산운용"),
    "투자 은행 및 중개 서비스":            ("금융·핀테크",         "자본시장"),
    "금융, 상품 시장 운영 및 서비스 제공": ("금융·핀테크",         "금융데이터·거래소"),
    "소비자 대출":                          ("금융·핀테크",         "신용서비스"),
    "핀테크":                               ("금융·핀테크",         "핀테크"),
    "기타 핀테크 인프라":                  ("금융·핀테크",         "핀테크 인프라"),
    "기업 금융 서비스":                     ("금융·핀테크",         "자본시장"),
    "다각적 투자 서비스":                  ("금융·핀테크",         "투자서비스"),
    "투자 지주 회사":                       ("금융·핀테크",         "자산운용"),
    "온라인 소액 투자 중개":               ("금융·핀테크",         "핀테크"),
    "블록 체인 및 암호화폐":               ("금융·핀테크",         "암호화폐·블록체인"),
    # ── EV·로봇·자율주행 ─────────────────────────────────────
    "자동차 및 트럭 제조":                 ("EV·로봇·자율주행",    "자동차 제조"),
    "자동차, 트럭 및 오토바이 부품":       ("EV·로봇·자율주행",    "자동차 부품"),
    "자동차 차량, 부품 및 서비스 소매":    ("EV·로봇·자율주행",    "자동차 딜러"),
    "타이어 및 고무 제품":                  ("EV·로봇·자율주행",    "자동차 부품"),
    # ── 소비재·유통 ──────────────────────────────────────────
    "기타 전문 소매":                       ("소비재·유통",         "전문 소매"),
    "의류 및 액세서리":                     ("소비재·유통",         "의류 제조"),
    "의류 및 액세서리 소매":               ("소비재·유통",         "의류 소매"),
    "직물 및 가죽제품":                     ("소비재·유통",         "의류 제조"),
    "제화":                                 ("소비재·유통",         "의류 소매"),
    "백화점":                               ("소비재·유통",         "백화점·유통"),
    "할인점":                               ("소비재·유통",         "할인점"),
    "식품 소매 및 유통":                   ("소비재·유통",         "식료품점"),
    "레스토랑 및 바":                       ("소비재·유통",         "외식업"),
    "가전제품, 도구 및 가정 용품":         ("소비재·유통",         "소비자가전"),
    "가정용 전자 제품":                     ("소비재·유통",         "소비자가전"),
    "가정용 제품":                           ("소비재·유통",         "생활·개인용품"),
    "가정용 가구":                           ("소비재·유통",         "생활·개인용품"),
    "가정용 가구 소매":                     ("소비재·유통",         "생활·개인용품"),
    "개인 생활 필수 용품":                  ("소비재·유통",         "생활·개인용품"),
    "소비재 대기업":                        ("소비재·유통",         "생활·개인용품"),
    "식품 가공":                             ("소비재·유통",         "가공식품"),
    "무알콜 음료":                           ("소비재·유통",         "비알코올음료"),
    "양조업":                               ("소비재·유통",         "주류"),
    "증류주 및 포도주":                     ("소비재·유통",         "주류"),
    "담배":                                 ("소비재·유통",         "담배"),
    "주택 개조 제품 및 서비스 소매":        ("소비재·유통",         "홈인테리어 소매"),
    "개인 서비스":                           ("소비재·유통",         "개인서비스"),
    "기타 교육 서비스 제공":               ("소비재·유통",         "교육·훈련"),
    "전문 및 비즈니스 교육":               ("소비재·유통",         "교육·훈련"),
    "초, 중, 고등 교육기관":               ("소비재·유통",         "교육·훈련"),
    "오락용 제품":                           ("소비재·유통",         "레저"),
    "여가 및 오락시설":                     ("소비재·유통",         "레저"),
    "장난감 및 어린이 제품":               ("소비재·유통",         "레저"),
    # ── 미디어·엔터·게임 ─────────────────────────────────────
    "엔터테인먼트 제작":                    ("미디어·엔터·게임",    "엔터테인먼트"),
    "방송":                                 ("미디어·엔터·게임",    "방송"),
    "소비자 출판":                           ("미디어·엔터·게임",    "출판·미디어"),
    "상업 인쇄 서비스":                     ("미디어·엔터·게임",    "출판·미디어"),
    # ── 통신·네트워크 ────────────────────────────────────────
    "무선 통신 서비스":                     ("통신·네트워크",       "통신서비스"),
    "통합 통신 서비스":                     ("통신·네트워크",       "통신서비스"),
    "통신 및 네트워킹":                     ("통신·네트워크",       "네트워크 장비"),
    # ── 항공·여행·관광 ───────────────────────────────────────
    "항공사":                               ("항공·여행·관광",      "항공사"),
    "호텔, 모텔 및 크루즈 라인":           ("항공·여행·관광",      "호텔·모텔"),
    "지상 및 해상 여객 운송":              ("항공·여행·관광",      "여행서비스"),
    "공항 운영 및 서비스":                  ("항공·여행·관광",      "여행서비스"),
    "카지노 및 도박":                       ("항공·여행·관광",      "리조트·카지노"),
    # ── 에너지·원자력 ────────────────────────────────────────
    "오일 및 가스 시추":                   ("에너지·원자력",       "석유·가스 탐사"),
    "오일, 가스 탐사 및 생산":             ("에너지·원자력",       "석유·가스 탐사"),
    "통합 오일 및 가스":                   ("에너지·원자력",       "석유·가스 통합"),
    "오일, 가스 정제 및 마케팅":           ("에너지·원자력",       "정유·마케팅"),
    "오일 관련 서비스 및 장비":            ("에너지·원자력",       "석유·가스 장비"),
    "오일 및 가스 수송 서비스":            ("에너지·원자력",       "석유·가스 미드스트림"),
    "우라늄":                               ("에너지·원자력",       "우라늄"),
    "재생 가능 에너지 장비 및 서비스":     ("에너지·원자력",       "태양광"),
    "재생 가능 연료":                       ("에너지·원자력",       "태양광"),
    "석탄":                                 ("에너지·원자력",       "석탄"),
    # ── 전력 인프라·그리드 ───────────────────────────────────
    "전력 유틸리티":                        ("전력 인프라·그리드",  "규제 전력"),
    "민자 발전 사업":                       ("전력 인프라·그리드",  "독립발전사"),
    "복합 유틸리티":                        ("전력 인프라·그리드",  "다각화 유틸리티"),
    "수자원 유틸리티":                      ("전력 인프라·그리드",  "규제 수도"),
    "천연가스 유틸리티":                    ("전력 인프라·그리드",  "규제 가스"),
    "전기 부품 및 장비":                   ("전력 인프라·그리드",  "전기장비·부품"),
    "중전기장비":                           ("전력 인프라·그리드",  "전기장비·부품"),
    # ── 리츠·부동산 ──────────────────────────────────────────
    "복합부동산 REITs":                     ("리츠·부동산",         "다각화 리츠"),
    "상업용 REITs":                         ("리츠·부동산",         "오피스 리츠"),
    "주거용 REITs":                         ("리츠·부동산",         "주거 리츠"),
    "특수 REITs":                           ("리츠·부동산",         "특수 리츠"),
    "부동산 서비스":                        ("리츠·부동산",         "부동산 서비스"),
    "부동산 임대, 개발 및 운영":           ("리츠·부동산",         "복합 부동산"),
    # ── 전통 산업·소재 ───────────────────────────────────────
    "산업용 기계 및 장비":                 ("전통 산업·소재",      "산업기계"),
    "중장비 및 차량":                       ("전통 산업·소재",      "농기계·중장비"),
    "건설 및 엔지니어링":                  ("전통 산업·소재",      "엔지니어링·건설"),
    "건설 자재":                             ("전통 산업·소재",      "건설 소재"),
    "건설 자재 및 비품":                   ("전통 산업·소재",      "건설 소재"),
    "주택 건설":                             ("전통 산업·소재",      "건설 소재"),
    "환경 서비스 및 장비":                  ("전통 산업·소재",      "폐기물관리"),
    "고용 서비스":                           ("전통 산업·소재",      "인력파견"),
    "경영 지원 서비스":                     ("전통 산업·소재",      "비즈니스서비스"),
    "다각적 산업용 제품 도매":              ("전통 산업·소재",      "비즈니스서비스"),
    "비즈니스 지원 용품":                   ("전통 산업·소재",      "비즈니스서비스"),
    "지상 화물 및 물류":                   ("전통 산업·소재",      "물류·택배"),
    "배달, 우편, 항공 화물 및 육상 물류": ("전통 산업·소재",      "물류·택배"),
    "해양 화물 및 물류":                   ("전통 산업·소재",      "해운"),
    "항만 운영 및 서비스":                  ("전통 산업·소재",      "해운"),
    "상품 화학":                             ("전통 산업·소재",      "화학"),
    "다각적 화학 산업":                     ("전통 산업·소재",      "화학"),
    "특수 화학제":                           ("전통 산업·소재",      "특수화학"),
    "철 및 강철":                           ("전통 산업·소재",      "철강"),
    "알루미늄":                             ("전통 산업·소재",      "알루미늄"),
    "농화학제":                             ("전통 산업·소재",      "농업 소재"),
    "어업 및 농업":                         ("전통 산업·소재",      "농산물"),
    "용기(종이 제외) 및 포장재":           ("전통 산업·소재",      "포장재"),
    "종이 제품":                             ("전통 산업·소재",      "제지"),
    "종이 포장재":                           ("전통 산업·소재",      "제지"),
    "임업 및 목재 제품":                   ("전통 산업·소재",      "목재"),
    # ── 광업·귀금속·원자재 ───────────────────────────────────
    "금":                                   ("광업·귀금속·원자재",  "금광"),
    "금 제외 귀금속 및 광물":              ("광업·귀금속·원자재",  "귀금속·광물"),
    "다각적 채굴":                           ("광업·귀금속·원자재",  "기타 광업"),
    "특수 채굴 및 금속":                   ("광업·귀금속·원자재",  "기타 광업"),
    "채굴 지원 서비스 및 장비":            ("광업·귀금속·원자재",  "기타 광업"),
}

_US_FDR_REFRESH_LOCK = threading.Lock()

def refresh_us_fdr_sector_cache() -> None:
    """FDR에서 미국 전종목 업종 데이터를 가져와 JSON 캐시 파일에 저장한다.
    백그라운드 스레드에서 실행 — 완료까지 수분 소요될 수 있음."""
    if not _US_FDR_REFRESH_LOCK.acquire(blocking=False):
        return  # 이미 다른 스레드가 갱신 중
    try:
        import FinanceDataReader as _fdr
        import pandas as _pd
        frames = []
        for mkt, exch in [("NASDAQ", "NASDAQ"), ("NYSE", "NYSE"), ("AMEX", "AMEX")]:
            try:
                df = _fdr.StockListing(mkt).copy()
                df["_exchange"] = exch
                frames.append(df)
            except Exception:
                continue
        if not frames:
            return
        all_df = _pd.concat(frames, ignore_index=True)
        all_df.columns = [str(c).strip() for c in all_df.columns]
        cols = {c.lower(): c for c in all_df.columns}
        sym  = cols.get("symbol",   cols.get("code",     cols.get("ticker")))
        name = cols.get("name",     cols.get("longname", cols.get("shortname")))
        ind  = cols.get("industry", cols.get("industrycode"))
        if not sym or not ind:
            return
        cache: dict = {}
        for _, row in all_df.iterrows():
            ticker = str(row.get(sym, "")).strip().upper()
            if not ticker or not (1 <= len(ticker) <= 5) or not ticker.isalpha():
                continue
            industry = str(row.get(ind, "")).strip()
            mapping  = _FDR_IND_MAP.get(industry)
            if not mapping:
                continue
            kr_sec, kr_sub = mapping
            sname = str(row.get(name, ticker) if name else ticker).strip()
            exch2 = str(row.get("_exchange", "NASDAQ"))
            cache[ticker] = {"name": sname, "sector": kr_sec, "subsector": kr_sub, "exchange": exch2}
        with open(_US_FDR_SECTOR_CACHE_PATH, "w", encoding="utf-8") as f:
            _json.dump(cache, f, ensure_ascii=False)
        # 캐시 갱신 후 in-memory 캐시 초기화
        load_us_sector_map.clear()
    except Exception:
        pass
    finally:
        _US_FDR_REFRESH_LOCK.release()


@st.cache_data(ttl=43200)
def load_us_sector_map() -> dict:
    """정적 sectors_us.py 맵 + JSON 캐시(FDR 업종)를 병합한 미국 섹터 맵을 반환합니다."""
    import copy
    from sectors_us import US_SECTOR_MAP
    raw = copy.deepcopy(US_SECTOR_MAP)
    existing = {s["ticker"] for subs in raw.values() for stks in subs.values() for s in stks}

    try:
        if os.path.exists(_US_FDR_SECTOR_CACHE_PATH):
            with open(_US_FDR_SECTOR_CACHE_PATH, encoding="utf-8") as f:
                fdr_cache: dict = _json.load(f)
            for ticker, info in fdr_cache.items():
                if ticker in existing:
                    continue
                kr_sec = info.get("sector", "")
                kr_sub = info.get("subsector", "")
                if kr_sec not in raw:
                    continue
                raw[kr_sec].setdefault(kr_sub, []).append(
                    {"name": info.get("name", ticker), "ticker": ticker, "exchange": info.get("exchange", "NASDAQ")}
                )
                existing.add(ticker)
    except Exception:
        pass

    return raw


def init_us_sector_sheet():
    """sectors_us.py 기본 데이터를 Google Sheets 섹터DB_US 탭에 업로드 (덮어쓰기)."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        from sectors_us import US_SECTOR_MAP
        headers = ["섹터", "세부섹터", "종목명", "티커", "exchange"]
        ws = _get_or_create_worksheet(sh, "섹터DB_US", headers)
        ws.clear()
        ws.append_row(headers)
        rows_to_add = []
        for sec, subs in US_SECTOR_MAP.items():
            for sub, stocks in subs.items():
                for s in stocks:
                    rows_to_add.append([sec, sub, s["name"], s["ticker"], s["exchange"]])
        if rows_to_add:
            ws.append_rows(rows_to_add)
        load_us_sector_map.clear()
        return True, f"섹터DB_US에 {len(rows_to_add)}개 종목 업로드 완료!"
    except Exception as e:
        return False, f"업로드 오류: {e}"


def init_sector_sheet():
    """sectors_kr.py 기본 데이터를 Google Sheets 섹터DB 탭에 업로드 (덮어쓰기)."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg
    try:
        from sectors_kr import KR_SECTOR_MAP
        headers = ["섹터", "세부섹터", "종목명", "종목코드", "suffix"]
        ws = _get_or_create_worksheet(sh, "섹터DB", headers)
        ws.clear()
        ws.append_row(headers)
        rows_to_add = []
        for sec, subs in KR_SECTOR_MAP.items():
            for sub, stocks in subs.items():
                for s in stocks:
                    rows_to_add.append([sec, sub, s["name"], s["code"], s["suffix"]])
        if rows_to_add:
            ws.append_rows(rows_to_add)
        load_sector_map.clear()
        return True, f"섹터DB에 {len(rows_to_add)}개 종목 업로드 완료!"
    except Exception as e:
        return False, f"업로드 오류: {e}"


def _gsheet_backup_save_trade_analysis_record(trade_data: dict, analysis_result: dict):
    """[구글 시트 백업 전용] AI 거래 분석 결과를 '거래분석DB' 탭에 저장합니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return False, msg
    try:
        headers = [
            "분석시간", "티커", "종목명", "매도일", "수익률(%)", "결과",
            "섹터", "섹터특성", "사회적요인", "수급요인", "기술적요인",
            "성공이유", "실패이유", "교훈"
        ]
        ws = _get_or_create_worksheet(sh, "거래분석DB", headers)
        ticker = str(trade_data.get("ticker", ""))
        sell_date = str(trade_data.get("sell_date", ""))[:10]
        # 중복 체크는 SQLite에서 완료됨 — 구글 시트 read 없이 바로 append
        trades_list = analysis_result.get("trades", [])
        tr = trades_list[0] if trades_list else {}
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ticker, str(trade_data.get("name", "")), sell_date,
            round(float(trade_data.get("profit_pct", 0)), 2),
            str(trade_data.get("result", "")), str(tr.get("sector", "")),
            str(tr.get("sector_characteristic", "")), str(tr.get("social_factor", "")),
            str(tr.get("institutional_factor", "")), str(tr.get("technical_factor", "")),
            str(tr.get("success_reason", "")), str(tr.get("failure_reason", "")),
            str(tr.get("lesson", "")),
        ])
        return True, "성공"
    except Exception as e:
        print(f"Failed to backup trade analysis record: {e}")
        return False, str(e)

def save_trade_analysis_record(trade_data: dict, analysis_result: dict):
    """AI 거래 분석 결과를 로컬 SQLite 'trade_analysis'에 즉시 저장하고, 백그라운드로 구글 시트에 업데이트합니다."""
    try:
        ticker = str(trade_data.get("ticker", ""))
        sell_date = str(trade_data.get("sell_date", ""))[:10]
        key = f"record_{ticker}_{sell_date}"
        
        # trade_data와 analysis_result를 통합하여 JSON 저장
        payload = {
            "trade_data": trade_data,
            "analysis_result": analysis_result,
            "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO trade_analysis (key_name, analysis_json) VALUES (?, ?)",
            (key, _json.dumps(payload, ensure_ascii=False))
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_save_trade_analysis_record, trade_data, analysis_result)
        return True, "거래 분석이 로컬 DB에 기록되었습니다."
    except Exception as e:
        return False, f"로컬 저장 오류: {e}"

def load_trade_analysis_records():
    """로컬 SQLite 'trade_analysis' 테이블에서 모든 분석 기록을 로드합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT analysis_json FROM trade_analysis WHERE key_name LIKE 'record_%'")
        rows = cursor.fetchall()
        conn.close()
        
        records = []
        for r in rows:
            payload = _json.loads(r["analysis_json"])
            trade_data = payload.get("trade_data", {})
            analysis_result = payload.get("analysis_result", {})
            trades_list = analysis_result.get("trades", [])
            tr = trades_list[0] if trades_list else {}
            
            records.append({
                "분석시간": payload.get("analyzed_at", ""),
                "티커": trade_data.get("ticker", ""),
                "종목명": trade_data.get("name", ""),
                "매도일": trade_data.get("sell_date", "")[:10],
                "수익률(%)": round(float(trade_data.get("profit_pct", 0)), 2),
                "결과": trade_data.get("result", ""),
                "섹터": tr.get("sector", ""),
                "섹터특성": tr.get("sector_characteristic", ""),
                "사회적요인": tr.get("social_factor", ""),
                "수급요인": tr.get("institutional_factor", ""),
                "기술적요인": tr.get("technical_factor", ""),
                "성공이유": tr.get("success_reason", ""),
                "실패이유": tr.get("failure_reason", ""),
                "교훈": tr.get("lesson", "")
            })
        return records, "성공"
    except Exception as e:
        print(f"Error loading trade analysis records: {e}")
        return [], f"로컬 DB 오류: {e}"


def _gsheet_backup_save_trade_analysis(analysis: dict):
    """[구글 시트 백업 전용] AI 거래 분석 결과를 '매매분석일지' 탭에 백업합니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return False, msg
    try:
        headers = ["분석시간", "총거래", "승", "패", "승률(%)", "성공패턴", "실패패턴", "핵심인사이트", "향후전략", "종목별분석(JSON)"]
        ws = _get_or_create_worksheet(sh, "매매분석일지", headers)
        summary = analysis.get("summary", {})
        total = summary.get("total", 0)
        wins = summary.get("win_count", 0)
        losses = summary.get("loss_count", 0)
        win_rate = round(wins / total * 100, 1) if total > 0 else 0
        insights = " | ".join(summary.get("key_insights", []))
        trades_json = _json.dumps(analysis.get("trades", []), ensure_ascii=False)
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total, wins, losses, win_rate,
            summary.get("win_pattern", ""),
            summary.get("loss_pattern", ""),
            insights,
            summary.get("future_strategy", ""),
            trades_json,
        ])
        return True, "성공"
    except Exception as e:
        print(f"Failed to backup trade analysis: {e}")
        return False, str(e)

def save_trade_analysis(analysis: dict):
    """AI 거래 분석 결과를 로컬 SQLite 'trade_analysis'에 저장하고 백그라운드로 구글 시트에 업데이트합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        summary = analysis.get("summary", {})
        total = summary.get("total", 0)
        wins = summary.get("win_count", 0)
        losses = summary.get("loss_count", 0)
        win_rate = round(wins / total * 100, 1) if total > 0 else 0
        insights = " | ".join(summary.get("key_insights", []))
        
        payload = {
            "analyzed_at": now,
            "analysis": analysis,
            "total": total,
            "win_count": wins,
            "loss_count": losses,
            "win_rate": win_rate,
            "win_pattern": summary.get("win_pattern", ""),
            "loss_pattern": summary.get("loss_pattern", ""),
            "insights": insights,
            "future_strategy": summary.get("future_strategy", "")
        }
        
        cursor.execute(
            "INSERT OR REPLACE INTO trade_analysis (key_name, analysis_json) VALUES (?, ?)",
            ("latest_analysis", _json.dumps(payload, ensure_ascii=False))
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_save_trade_analysis, analysis)
        return True, "매매 분석 결과가 로컬 DB에 저장되었습니다."
    except Exception as e:
        return False, f"로컬 저장 오류: {e}"

def load_trade_analysis():
    """로컬 SQLite 'trade_analysis'에서 가장 최근 분석 결과를 불러옵니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT analysis_json FROM trade_analysis WHERE key_name = 'latest_analysis'")
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None, "저장된 분석 결과가 없습니다."
            
        payload = _json.loads(row["analysis_json"])
        analysis = payload.get("analysis", {})
        summary = analysis.get("summary", {})
        
        return {
            "analyzed_at": payload.get("analyzed_at", ""),
            "summary": {
                "total": payload.get("total", 0),
                "win_count": payload.get("win_count", 0),
                "loss_count": payload.get("loss_count", 0),
                "win_rate": payload.get("win_rate", 0),
                "win_pattern": payload.get("win_pattern", ""),
                "loss_pattern": payload.get("loss_pattern", ""),
                "key_insights": summary.get("key_insights", []),
                "future_strategy": payload.get("future_strategy", "")
            },
            "trades": analysis.get("trades", [])
        }, "성공"
    except Exception as e:
        print(f"Error loading trade analysis: {e}")
        return None, f"로컬 DB 오류: {e}"


def test_connection_and_write():
    """연결 테스트용 함수 (하위 호환성 유지)."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False, msg

    try:
        ws = sh.sheet1
        if not ws.get_all_values():
            ws.append_row(["시간", "종목명", "추천가", "목표가", "상태"])
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([now, "연결테스트_OK", "-", "-", "성공"])
        return True, f"연결 성공! '{sh.title}' 시트에 테스트 데이터가 입력되었습니다."
    except Exception as e:
        return False, f"에러 발생: {e}"


def _gsheet_backup_ai_cache(cache_key: str, data_json: str, saved_time: str, expire_time: str):
    """[구글 시트 백업 전용] AI 생성 캐시를 'AI캐시' 탭에 백업합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False
    try:
        headers = ["캐시키", "저장시간", "만료시간", "데이터"]
        ws = _get_or_create_worksheet(sh, "AI캐시", headers)
        rows = ws.get_all_values()
        for i in range(len(rows) - 1, 0, -1):
            if len(rows[i]) >= 1 and rows[i][0] == cache_key:
                ws.delete_rows(i + 1)
        ws.append_row([
            cache_key,
            saved_time,
            expire_time,
            data_json,
        ])
        return True
    except Exception as e:
        print(f"Failed to backup AI cache to Google Sheets: {e}")
        return False

def save_ai_cache(cache_key: str, data: dict, ttl_hours: int = 12):
    """AI 생성 결과를 로컬 SQLite 'ai_cache'에 즉시 저장하고, 백그라운드 스레드로 구글 시트에 백업합니다."""
    import json as _json
    try:
        now = datetime.now()
        expire = now + timedelta(hours=ttl_hours)
        saved_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        expire_time_str = expire.strftime("%Y-%m-%d %H:%M:%S")
        data_json = _json.dumps(data, ensure_ascii=False)
        
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO ai_cache (cache_key, saved_time, expire_time, data_json) VALUES (?, ?, ?, ?)",
            (cache_key, saved_time_str, expire_time_str, data_json)
        )
        conn.commit()
        conn.close()
        
        # 구글 시트에 비동기 백업 구동
        run_background_backup(_gsheet_backup_ai_cache, cache_key, data_json, saved_time_str, expire_time_str)
        return True, "캐시 저장 완료"
    except Exception as e:
        return False, f"캐시 저장 오류: {e}"

def load_ai_cache(cache_key: str) -> dict | None:
    """로컬 SQLite 'ai_cache'에서 유효한 캐시를 로드합니다. 만료되었거나 없으면 None을 반환합니다."""
    import json as _json
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT saved_time, expire_time, data_json FROM ai_cache WHERE cache_key = ?",
            (cache_key,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
            
        expire_str = str(row["expire_time"] or "")
        if expire_str:
            try:
                expire_dt = datetime.strptime(expire_str, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > expire_dt:
                    # 만료되었으면 로컬 DB에서 삭제
                    delete_ai_cache(cache_key)
                    return None
            except ValueError:
                pass
                
        data_str = str(row["data_json"] or "")
        if data_str:
            return _json.loads(data_str)
        return None
    except Exception as e:
        print(f"Error loading AI cache from SQLite: {e}")
        return None

def _gsheet_backup_delete_ai_cache(cache_key: str):
    """[구글 시트 백업 전용] 'AI캐시' 탭에서 특정 캐시를 삭제합니다."""
    sh, msg = _get_spreadsheet()
    if not sh:
        return False
    try:
        ws = sh.worksheet("AI캐시")
        rows = ws.get_all_values()
        for i in range(len(rows) - 1, 0, -1):
            if len(rows[i]) >= 1 and rows[i][0] == cache_key:
                ws.delete_rows(i + 1)
        return True
    except Exception as e:
        print(f"Failed to backup delete AI cache: {e}")
        return False

def delete_ai_cache(cache_key: str):
    """로컬 SQLite 'ai_cache'에서 특정 키의 캐시를 즉시 삭제하고, 백그라운드 스레드로 구글 시트에서 비동기 삭제합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ai_cache WHERE cache_key = ?", (cache_key,))
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_delete_ai_cache, cache_key)
        return True
    except Exception as e:
        print(f"Error deleting AI cache from SQLite: {e}")
        return False


# ── 종목 AI 분석 이력 ──────────────────────────────────────────────────────────

_ANALYSIS_HISTORY_HEADERS = [
    "분석시간", "시장", "티커", "종목명", "현재가",
    "매수구간", "목표가", "손절가", "등급", "중장기등급", "단기전망률", "JSON",
]


def _gsheet_backup_analysis_history(analysis_time: str, market: str, ticker: str, name: str, current_price: str, buy_target: str, sell_target: str, stop_loss: str, rating: str, long_term_rating: str, short_term_view_pct: str, analysis_json: str):
    """[구글 시트 백업 전용] 종목 분석 이력을 '종목분석이력' 탭에 백업합니다."""
    sh, _ = _get_spreadsheet()
    if not sh:
        return False
    try:
        ws = _get_or_create_worksheet(sh, "종목분석이력", _ANALYSIS_HISTORY_HEADERS)
        ws.append_row([
            analysis_time,
            market,
            ticker,
            name,
            current_price,
            buy_target,
            sell_target,
            stop_loss,
            rating,
            long_term_rating,
            short_term_view_pct,
            analysis_json,
        ])
        return True
    except Exception as e:
        print(f"Failed to backup analysis history to Google Sheets: {e}")
        return False

def save_stock_analysis_history(market: str, ticker: str, name: str, current_price, analysis: dict) -> bool:
    """종목 AI 분석 결과를 로컬 SQLite 'analysis_history'에 즉시 추가하고, 백그라운드 스레드로 구글 시트에 백업합니다."""
    try:
        import json as _json
        analysis_time = (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")
        curr_price_str = str(current_price) if current_price else ""
        buy_t = str(analysis.get("buy_target", ""))
        sell_t = str(analysis.get("sell_target", ""))
        stop_l = str(analysis.get("stop_loss", ""))
        rat = str(analysis.get("rating", ""))
        lt_rat = str(analysis.get("long_term_rating", ""))
        st_view = str(analysis.get("short_term_view_pct", ""))
        analysis_json = _json.dumps(analysis, ensure_ascii=False)[:6000]
        
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO analysis_history (
                analysis_time, market, ticker, name, current_price,
                buy_target, sell_target, stop_loss, rating, long_term_rating,
                short_term_view_pct, analysis_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (analysis_time, market, ticker, name, curr_price_str,
             buy_t, sell_t, stop_l, rat, lt_rat, st_view, analysis_json)
        )
        conn.commit()
        conn.close()
        
        # 구글 시트에 비동기 백업
        run_background_backup(
            _gsheet_backup_analysis_history,
            analysis_time, market, ticker, name, curr_price_str,
            buy_t, sell_t, stop_l, rat, lt_rat, st_view, analysis_json
        )
        return True
    except Exception as e:
        print(f"Error saving analysis history to SQLite: {e}")
        return False


def _gsheet_backup_save_alert(market, ticker, name, alert_type, target_price):
    """[구글 시트 백업 전용] 가격 알림을 '알림설정' 탭에 백업합니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return False, msg
    try:
        headers = ["설정시간", "시장", "티커", "종목명", "알림유형", "목표가", "상태"]
        ws = _get_or_create_worksheet(sh, "알림설정", headers)
        existing = safe_get_all_records(ws)
        for i in range(len(existing) - 1, -1, -1):
            r = existing[i]
            if str(r.get("티커")) == str(ticker) and r.get("알림유형") == alert_type:
                ws.delete_rows(i + 2)
                break
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            market, ticker, name, alert_type,
            round(float(target_price), 4),
            "활성",
        ])
        return True, "성공"
    except Exception as e:
        print(f"Failed to backup price alert: {e}")
        return False, str(e)

def save_price_alert(market: str, ticker: str, name: str,
                     alert_type: str, target_price: float) -> tuple:
    """가격 알림을 로컬 SQLite 'price_alerts'에 저장하고 백그라운드로 구글 시트에 업데이트합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT OR REPLACE INTO price_alerts (market, ticker, name, alert_type, target_price, updated_time, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (market, ticker, name, alert_type, float(target_price), now, "활성")
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_save_alert, market, ticker, name, alert_type, target_price)
        return True, f"[{name}] {alert_type} 알림이 설정되었습니다."
    except Exception as e:
        return False, f"알림 저장 오류: {e}"

def load_price_alerts() -> list:
    """로컬 SQLite 'price_alerts'에서 활성 알림 목록을 반환합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT market, ticker, name, alert_type, target_price FROM price_alerts WHERE status = '활성'"
        )
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for r in rows:
            ticker = str(r["ticker"])
            if ticker.isdigit() and len(ticker) < 6:
                ticker = ticker.zfill(6)
            result.append({
                "market":     str(r["market"]),
                "ticker":     ticker,
                "name":       str(r["name"]),
                "alert_type": str(r["alert_type"]),
                "target_price": float(r["target_price"] or 0),
            })
        return result
    except Exception as e:
        print(f"Error loading price alerts from SQLite: {e}")
        return []

def _gsheet_backup_delete_alert(ticker, alert_type):
    """[구글 시트 백업 전용] '알림설정' 탭에서 특정 알림을 삭제합니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return False, msg
    try:
        ws = sh.worksheet("알림설정")
        records = safe_get_all_records(ws)
        for i in range(len(records) - 1, -1, -1):
            r = records[i]
            if str(r.get("티커")) == str(ticker) and r.get("알림유형") == alert_type:
                ws.delete_rows(i + 2)
                return True, "성공"
        return False, "찾을 수 없음"
    except Exception as e:
        print(f"Failed to backup delete alert: {e}")
        return False, str(e)

def delete_price_alert(ticker: str, alert_type: str) -> tuple:
    """로컬 SQLite 'price_alerts'에서 특정 알림을 즉시 삭제하고, 백그라운드 스레드로 구글 시트에서 삭제합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM price_alerts WHERE ticker = ? AND alert_type = ?",
            (ticker, alert_type)
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_delete_alert, ticker, alert_type)
        return True, "알림이 삭제되었습니다."
    except Exception as e:
        return False, f"삭제 오류: {e}"

def _gsheet_backup_update_alert_status(ticker, alert_type, new_status):
    """[구글 시트 백업 전용] 알림 상태를 업데이트합니다."""
    sh, _ = _get_spreadsheet()
    if not sh: return False
    try:
        ws = sh.worksheet("알림설정")
        records = safe_get_all_records(ws)
        for i, r in enumerate(records):
            if str(r.get("티커")) == str(ticker) and r.get("알림유형") == alert_type:
                header = ws.row_values(1)
                status_col = header.index("상태") + 1
                ws.update_cell(i + 2, status_col, new_status)
                return True
        return False
    except Exception as e:
        print(f"Failed to backup update alert status: {e}")
        return False

def update_price_alert_status(ticker: str, alert_type: str, new_status: str) -> bool:
    """로컬 SQLite 'price_alerts'에서 알림 상태를 갱신하고, 백그라운드 스레드로 구글 시트에 반영합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE price_alerts SET status = ? WHERE ticker = ? AND alert_type = ?",
            (new_status, ticker, alert_type)
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_update_alert_status, ticker, alert_type, new_status)
        return True
    except Exception as e:
        print(f"Error updating price alert status: {e}")
        return False


def load_stock_analysis_history(ticker: str, limit: int = 10) -> list[dict]:
    """로컬 SQLite 'analysis_history'에서 해당 티커의 최근 분석 기록을 반환합니다 (오래된→최신 순)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT analysis_time, market, ticker, name, current_price,
                   buy_target, sell_target, stop_loss, rating, long_term_rating,
                   short_term_view_pct, analysis_json
            FROM analysis_history
            WHERE ticker = ?
            ORDER BY id ASC
            """,
            (ticker,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        hits = []
        for r in rows:
            hits.append({
                "분석시간": str(r["analysis_time"] or ""),
                "시장": str(r["market"] or ""),
                "티커": str(r["ticker"] or ""),
                "종목명": str(r["name"] or ""),
                "현재가": str(r["current_price"] or ""),
                "매수구간": str(r["buy_target"] or ""),
                "목표가": str(r["sell_target"] or ""),
                "손절가": str(r["stop_loss"] or ""),
                "등급": str(r["rating"] or ""),
                "중장기등급": str(r["long_term_rating"] or ""),
                "단기전망률": str(r["short_term_view_pct"] or ""),
                "JSON": str(r["analysis_json"] or ""),
            })
            
        return hits[-limit:] if len(hits) > limit else hits
    except Exception as e:
        print(f"Error loading analysis history from SQLite: {e}")
        return []


def _gsheet_backup_save_telegram(token, chat_id):
    """[구글 시트 백업 전용] 텔레그램 설정을 구글 시트에 백업합니다."""
    sh, msg = _get_spreadsheet()
    if not sh: return False
    try:
        headers = ["저장시간", "토큰", "챗아이디"]
        ws = _get_or_create_worksheet(sh, "텔레그램설정", headers)
        ws.clear()
        ws.append_row(headers)
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            token.strip(),
            chat_id.strip()
        ])
        return True
    except Exception as e:
        print(f"Failed to backup telegram config: {e}")
        return False

def save_telegram_config(token: str, chat_id: str) -> tuple[bool, str]:
    """로컬 SQLite 'telegram_config'에 설정을 즉시 저장하고, 백그라운드 스레드로 구글 시트에 백업합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO telegram_config (key, token, chat_id) VALUES (?, ?, ?)",
            ("main", token.strip(), chat_id.strip())
        )
        conn.commit()
        conn.close()
        
        run_background_backup(_gsheet_backup_save_telegram, token, chat_id)
        return True, "텔레그램 설정이 성공적으로 저장 및 백업 요청되었습니다."
    except Exception as e:
        return False, f"텔레그램 설정 저장 중 로컬 오류 발생: {e}"

def load_telegram_config() -> tuple[str, str]:
    """로컬 SQLite에서 저장된 텔레그램 설정을 불러옵니다. 없으면 환경변수 fallback."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT token, chat_id FROM telegram_config WHERE key = 'main'")
        row = cursor.fetchone()
        conn.close()
        
        if row and row["token"] and row["chat_id"]:
            return str(row["token"]).strip(), str(row["chat_id"]).strip()
    except Exception as e:
        print(f"Error loading telegram config from SQLite: {e}")
        
    # 환경변수 fallback
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    return token, chat_id


# ── 패턴 프로파일 저장/로드 ────────────────────────────────────────────────────

def save_pattern_profile(profile: dict, trade_count: int) -> tuple[bool, str]:
    """학습된 매매 패턴 프로파일을 SQLite에 저장합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """INSERT OR REPLACE INTO pattern_profile (id, profile_json, trade_count, updated_time)
               VALUES (1, ?, ?, ?)""",
            (_json.dumps(profile, ensure_ascii=False), trade_count, now)
        )
        conn.commit()
        conn.close()
        return True, "패턴 프로파일 저장 완료"
    except Exception as e:
        return False, f"패턴 프로파일 저장 오류: {e}"


def load_pattern_profile() -> dict | None:
    """저장된 패턴 프로파일을 불러옵니다. 없으면 None."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT profile_json, trade_count, updated_time FROM pattern_profile WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        if row and row["profile_json"]:
            data = _json.loads(row["profile_json"])
            data["_trade_count"]   = row["trade_count"]
            data["_updated_time"]  = row["updated_time"]
            return data
        return None
    except Exception as e:
        print(f"Error loading pattern profile: {e}")
        return None


def save_pattern_profile_v2(profile: dict, trade_count: int, source: str) -> tuple[bool, str]:
    """source별(personal/leading/all) 패턴 프로파일을 저장합니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """INSERT OR REPLACE INTO pattern_profile_v2 (source, profile_json, trade_count, updated_time)
               VALUES (?, ?, ?, ?)""",
            (source, _json.dumps(profile, ensure_ascii=False), trade_count, now)
        )
        conn.commit()
        conn.close()
        return True, f"패턴 프로파일({source}) 저장 완료"
    except Exception as e:
        return False, f"패턴 프로파일 저장 오류: {e}"


def load_pattern_profile_v2(source: str) -> dict | None:
    """source별 패턴 프로파일 로드. 없으면 None."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT profile_json, trade_count, updated_time FROM pattern_profile_v2 WHERE source = ?",
            (source,)
        )
        row = cursor.fetchone()
        conn.close()
        if row and row["profile_json"]:
            data = _json.loads(row["profile_json"])
            data["_trade_count"] = row["trade_count"]
            data["_updated_time"] = row["updated_time"]
            return data
        return None
    except Exception as e:
        print(f"Error loading pattern_profile_v2({source}): {e}")
        return None


def save_agent_daily_issues(issues: list):
    """에이전트가 매일 아침 분석한 핫이슈를 저장 (당일 기존 항목 교체). 최근 20일치만 유지."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("DELETE FROM agent_daily_issues WHERE issue_date = ?", (today,))
        for iss in issues:
            tickers = iss.get("related_tickers", [])
            tickers_str = ",".join(str(t) for t in tickers) if isinstance(tickers, list) else str(tickers)
            cursor.execute(
                """INSERT INTO agent_daily_issues
                   (issue_date, title, theme, sentiment, related_tickers, summary, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (today, iss.get("title", ""), iss.get("theme", ""), iss.get("sentiment", ""),
                 tickers_str, iss.get("summary", ""), now)
            )
        # 20일 이전 데이터 정리
        cursor.execute(
            "DELETE FROM agent_daily_issues WHERE issue_date < date('now', '-20 days')"
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"save_agent_daily_issues error: {e}")


def save_agent_scenario(keyword: str, scenario_obj: dict):
    """에이전트가 자동 생성한 시나리오 1건 저장 (당일+키워드 유니크). 20일 이전 정리."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """INSERT OR REPLACE INTO agent_scenarios (scenario_date, keyword, scenario_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (today, keyword, _json.dumps(scenario_obj, ensure_ascii=False), now)
        )
        cursor.execute("DELETE FROM agent_scenarios WHERE scenario_date < date('now', '-20 days')")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"save_agent_scenario error: {e}")


def load_agent_scenarios(days: int = 1) -> list:
    """최근 N일 에이전트 자동 생성 시나리오 로드 (시나리오 탭 표시용)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            f"""SELECT scenario_date, keyword, scenario_json FROM agent_scenarios
                WHERE scenario_date >= date('now', '-{int(days)} days')
                ORDER BY scenario_date DESC, id ASC"""
        )
        rows = cursor.fetchall()
        conn.close()
        out = []
        for r in rows:
            try:
                obj = _json.loads(r["scenario_json"])
                obj["_scenario_date"] = r["scenario_date"]
                obj["_keyword"] = r["keyword"]
                out.append(obj)
            except Exception:
                pass
        return out
    except Exception as e:
        print(f"load_agent_scenarios error: {e}")
        return []


def has_today_agent_scenarios() -> bool:
    """오늘 생성된 에이전트 시나리오가 있는지."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*) FROM agent_scenarios WHERE scenario_date = ?", (today,))
        n = cursor.fetchone()[0]
        conn.close()
        return n > 0
    except Exception:
        return False


def has_today_agent_issues() -> bool:
    """오늘 날짜로 분석된 에이전트 이슈가 이미 있는지 확인 (서버 재시작 시 중복 분석 방지)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*) FROM agent_daily_issues WHERE issue_date = ?", (today,))
        n = cursor.fetchone()[0]
        conn.close()
        return n > 0
    except Exception as e:
        print(f"has_today_agent_issues error: {e}")
        return False


def load_agent_daily_issues(days: int = 3) -> list:
    """최근 N일 에이전트 핫이슈 로드."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            f"""SELECT issue_date, title, theme, sentiment, related_tickers, summary
                FROM agent_daily_issues
                WHERE issue_date >= date('now', '-{int(days)} days')
                ORDER BY issue_date DESC, id ASC"""
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"load_agent_daily_issues error: {e}")
        return []


def save_agent_decision(d: dict):
    """AI 에이전트의 매수/매도 판단 1건을 지표와 함께 기록 (학습용)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO agent_decisions
               (decided_at, ticker, name, market, action, confidence, entry_price,
                rsi, ma_aligned, pos_52w, vol_ratio, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             d.get("ticker"), d.get("name"), d.get("market"), d.get("action"),
             int(d.get("confidence", 0) or 0), d.get("entry_price"),
             d.get("rsi"), 1 if d.get("ma_aligned") else 0, d.get("pos_52w"),
             d.get("vol_ratio"), d.get("reason"))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"save_agent_decision error: {e}")


def update_agent_decision_unrealized(ticker: str, unrealized_pct: float):
    """보유 중(미매도) 종목의 가장 최근 BUY 판단에 '잠정(미실현)' 수익률을 기록한다.
    에이전트 스캔이 어차피 현재가를 계산하므로 추가 네트워크 호출 없이 마크투마켓.
    is_realized=0 인 행만 갱신하므로, 매도로 확정된 행은 건드리지 않는다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE agent_decisions
               SET outcome_return = ?, outcome_checked_at = ?
               WHERE id = (
                   SELECT id FROM agent_decisions
                   WHERE ticker = ? AND action='BUY' AND COALESCE(is_realized, 0) = 0
                   ORDER BY decided_at DESC LIMIT 1
               )""",
            (float(unrealized_pct), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ticker)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"update_agent_decision_unrealized error: {e}")


def load_agent_learning_summary() -> dict:
    """에이전트 자기학습 요약 — 결과가 기록된 BUY 판단들의 조건별 승률.
    다른 AI 기능(스크리너/시나리오)에서도 공용으로 참조 가능.
    """
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        # 결과(outcome_return)가 채워진 BUY 판단 — 매도 확정(is_realized=1) + 보유 중 잠정(is_realized=0)
        cursor.execute(
            """SELECT rsi, ma_aligned, pos_52w, vol_ratio, outcome_return,
                      COALESCE(is_realized, 0) AS is_realized
               FROM agent_decisions
               WHERE action='BUY' AND outcome_return IS NOT NULL"""
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        realized_n   = sum(1 for r in rows if r["is_realized"] == 1)
        provisional_n = len(rows) - realized_n

        if not rows:
            return {"sample": 0, "realized_sample": 0, "provisional_sample": 0, "rules": []}

        wins = [r for r in rows if (r["outcome_return"] or 0) > 0]
        rules = []

        def _bucket_winrate(predicate, label):
            subset = [r for r in rows if predicate(r)]
            if len(subset) < 3:
                return None
            w = sum(1 for r in subset if (r["outcome_return"] or 0) > 0)
            avg = sum(r["outcome_return"] or 0 for r in subset) / len(subset)
            return {"label": label, "count": len(subset),
                    "win_rate": round(w / len(subset) * 100, 1),
                    "avg_return": round(avg, 2)}

        candidates = [
            (lambda r: (r["rsi"] or 0) < 40, "RSI 40 미만 매수"),
            (lambda r: 40 <= (r["rsi"] or 0) < 60, "RSI 40~60 매수"),
            (lambda r: (r["rsi"] or 0) >= 60, "RSI 60 이상 매수"),
            (lambda r: r["ma_aligned"] == 1, "MA 정배열 매수"),
            (lambda r: (r["vol_ratio"] or 0) >= 2, "거래량 2배+ 매수"),
            (lambda r: (r["pos_52w"] or 0) >= 80, "52주 고점권 매수"),
        ]
        for pred, label in candidates:
            res = _bucket_winrate(pred, label)
            if res:
                rules.append(res)
        rules.sort(key=lambda x: x["win_rate"], reverse=True)

        return {
            "sample": len(rows),
            "realized_sample": realized_n,
            "provisional_sample": provisional_n,
            "overall_win_rate": round(len(wins) / len(rows) * 100, 1),
            "overall_avg_return": round(sum(r["outcome_return"] or 0 for r in rows) / len(rows), 2),
            "rules": rules,
        }
    except Exception as e:
        print(f"load_agent_learning_summary error: {e}")
        return {"sample": 0, "realized_sample": 0, "provisional_sample": 0, "rules": []}


def save_frgn_inst_snapshot(market: str, rows: list) -> int:
    """외국인·기관 순매수 스냅샷을 오늘 날짜로 저장 (세력 자금 흐름 히스토리).
    rows: [{'종목코드','종목명','외국인순매수','기관순매수'}, ...]. 반환: 저장 건수."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n = 0
        for r in rows:
            code = str(r.get("종목코드", "")).strip()
            if not code:
                continue
            frgn = int(r.get("외국인순매수", 0) or 0)
            orgn = int(r.get("기관순매수", 0) or 0)
            cursor.execute(
                """INSERT OR REPLACE INTO frgn_inst_snapshots
                   (snapshot_date, market, ticker, name, frgn_ntby, orgn_ntby, combined, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (today, market, code, str(r.get("종목명", code)), frgn, orgn, frgn + orgn, now)
            )
            n += 1
        conn.commit()
        conn.close()
        return n
    except Exception as e:
        print(f"save_frgn_inst_snapshot error: {e}")
        return 0


def load_frgn_inst_snapshot_dates(limit: int = 10) -> list:
    """저장된 수급 스냅샷 날짜 목록 (최신순)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT snapshot_date FROM frgn_inst_snapshots ORDER BY snapshot_date DESC LIMIT ?",
            (limit,)
        )
        dates = [r["snapshot_date"] for r in cursor.fetchall()]
        conn.close()
        return dates
    except Exception:
        return []


def load_frgn_inst_snapshot(snapshot_date: str, market: str | None = None) -> list:
    """특정 날짜의 수급 스냅샷 로드 (combined 내림차순)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        if market:
            cursor.execute(
                """SELECT * FROM frgn_inst_snapshots WHERE snapshot_date=? AND market=?
                   ORDER BY combined DESC""", (snapshot_date, market))
        else:
            cursor.execute(
                """SELECT * FROM frgn_inst_snapshots WHERE snapshot_date=?
                   ORDER BY combined DESC""", (snapshot_date,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"load_frgn_inst_snapshot error: {e}")
        return []


def save_sector_flow_snapshot(snapshot_date: str, rows: list) -> int:
    """특정 날짜의 섹터별 수급 집계를 저장(교체). rows: [{sector, frgn_sum, orgn_sum, combined_sum, stock_count}]."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("DELETE FROM sector_flow_snapshots WHERE snapshot_date=?", (snapshot_date,))
        n = 0
        for r in rows:
            cursor.execute(
                """INSERT INTO sector_flow_snapshots
                   (snapshot_date, sector, frgn_sum, orgn_sum, combined_sum, stock_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (snapshot_date, str(r.get("sector", "")), int(r.get("frgn_sum", 0) or 0),
                 int(r.get("orgn_sum", 0) or 0), int(r.get("combined_sum", 0) or 0),
                 int(r.get("stock_count", 0) or 0), now)
            )
            n += 1
        conn.commit()
        conn.close()
        return n
    except Exception as e:
        print(f"save_sector_flow_snapshot error: {e}")
        return 0


def load_sector_flow_dates(limit: int = 30) -> list:
    """섹터 흐름 스냅샷 날짜 목록 (최신순)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT snapshot_date FROM sector_flow_snapshots ORDER BY snapshot_date DESC LIMIT ?", (limit,))
        dates = [r["snapshot_date"] for r in cursor.fetchall()]
        conn.close()
        return dates
    except Exception:
        return []


def load_sector_flow_snapshot(snapshot_date: str) -> list:
    """특정 날짜 섹터 흐름 (combined_sum 내림차순)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sector_flow_snapshots WHERE snapshot_date=? ORDER BY combined_sum DESC", (snapshot_date,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"load_sector_flow_snapshot error: {e}")
        return []


def load_sector_flow_series(sector: str | None = None, limit_days: int = 14) -> list:
    """최근 N일 섹터 흐름 시계열 (날짜 오름차순). sector 지정 시 해당 섹터만."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        dates = [r["snapshot_date"] for r in cursor.execute(
            "SELECT DISTINCT snapshot_date FROM sector_flow_snapshots ORDER BY snapshot_date DESC LIMIT ?", (limit_days,)).fetchall()]
        if not dates:
            conn.close()
            return []
        oldest = min(dates)
        if sector:
            cursor.execute("SELECT * FROM sector_flow_snapshots WHERE snapshot_date>=? AND sector=? ORDER BY snapshot_date ASC", (oldest, sector))
        else:
            cursor.execute("SELECT * FROM sector_flow_snapshots WHERE snapshot_date>=? ORDER BY snapshot_date ASC, combined_sum DESC", (oldest,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"load_sector_flow_series error: {e}")
        return []


def save_scenario_stocks(scenario_keyword: str, scenario_title: str, stocks: list):
    """시나리오에 등장한 종목들을 DB에 저장 (중복 키워드+티커는 갱신 안 함, 첫 등장만 기록)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for s in stocks:
            ticker = str(s.get("ticker") or s.get("code") or "").strip()
            name = str(s.get("name") or ticker).strip()
            role = str(s.get("role") or s.get("type") or "").strip()
            horizon = str(s.get("horizon") or "").strip()
            market = "us" if any(c.isalpha() for c in ticker) else "kr"
            if not ticker:
                continue
            cursor.execute(
                """SELECT id FROM scenario_stocks WHERE scenario_keyword=? AND ticker=?""",
                (scenario_keyword, ticker)
            )
            if cursor.fetchone():
                continue
            cursor.execute(
                """INSERT INTO scenario_stocks
                   (scenario_keyword, scenario_title, ticker, name, market, role, horizon, captured_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (scenario_keyword, scenario_title, ticker, name, market, role, horizon, now, now)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"save_scenario_stocks error: {e}")


def load_scenario_stocks_by_ticker(ticker: str) -> list:
    """특정 티커가 등장한 시나리오 목록 반환."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT scenario_keyword, scenario_title, role, captured_at, d3_return
               FROM scenario_stocks WHERE ticker = ? ORDER BY captured_at DESC LIMIT 5""",
            (ticker,)
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"load_scenario_stocks_by_ticker error: {e}")
        return []


def load_scenario_stocks_set() -> dict:
    """모든 시나리오 등장 종목의 ticker → 시나리오 개수 맵."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT ticker, COUNT(DISTINCT scenario_keyword) AS n FROM scenario_stocks GROUP BY ticker"""
        )
        result = {row["ticker"]: int(row["n"]) for row in cursor.fetchall()}
        conn.close()
        return result
    except Exception as e:
        print(f"load_scenario_stocks_set error: {e}")
        return {}


def save_backtest_result(row: dict):
    """백테스트 1건 저장 (picked_date+ticker 유니크)."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO screener_backtest_results
               (picked_date, ticker, name, match_score, signal,
                entry_price, d1_price, d3_price, d7_price,
                d1_return, d3_return, d7_return, computed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row.get("picked_date"), row.get("ticker"), row.get("name"),
             row.get("match_score"), row.get("signal"),
             row.get("entry_price"), row.get("d1_price"), row.get("d3_price"), row.get("d7_price"),
             row.get("d1_return"), row.get("d3_return"), row.get("d7_return"),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"save_backtest_result error: {e}")


def load_backtest_stats() -> dict:
    """백테스트 결과 집계 통계."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) AS n,
                      AVG(d1_return) AS avg_d1, AVG(d3_return) AS avg_d3, AVG(d7_return) AS avg_d7,
                      SUM(CASE WHEN d1_return > 0 THEN 1 ELSE 0 END) AS win_d1,
                      SUM(CASE WHEN d3_return > 0 THEN 1 ELSE 0 END) AS win_d3,
                      SUM(CASE WHEN d7_return > 0 THEN 1 ELSE 0 END) AS win_d7
               FROM screener_backtest_results
               WHERE d1_return IS NOT NULL"""
        )
        overall = dict(cursor.fetchone() or {})

        # 매칭 점수 구간별 통계
        buckets = []
        for label, min_s, max_s in [("80점 이상", 80, 101), ("60~79점", 60, 80), ("60점 미만", 0, 60)]:
            cursor.execute(
                """SELECT COUNT(*) AS n, AVG(d3_return) AS avg_d3,
                          SUM(CASE WHEN d3_return > 0 THEN 1 ELSE 0 END) AS wins
                   FROM screener_backtest_results
                   WHERE d3_return IS NOT NULL AND match_score >= ? AND match_score < ?""",
                (min_s, max_s)
            )
            r = dict(cursor.fetchone() or {})
            cnt = r.get("n", 0) or 0
            wins = r.get("wins", 0) or 0
            buckets.append({
                "label": label,
                "count": cnt,
                "win_rate": round(wins / cnt * 100, 1) if cnt else 0,
                "avg_return": round(r.get("avg_d3") or 0, 2),
            })

        # 최근 결과 샘플
        cursor.execute(
            """SELECT picked_date, ticker, name, match_score,
                      entry_price, d3_price, d3_return
               FROM screener_backtest_results
               WHERE d3_return IS NOT NULL
               ORDER BY picked_date DESC LIMIT 10"""
        )
        recent = [dict(r) for r in cursor.fetchall()]

        conn.close()
        n = overall.get("n", 0) or 0
        return {
            "total_picks_backtested": n,
            "overall": {
                "avg_d1_return": round(overall.get("avg_d1") or 0, 2),
                "avg_d3_return": round(overall.get("avg_d3") or 0, 2),
                "avg_d7_return": round(overall.get("avg_d7") or 0, 2),
                "win_rate_d1":   round((overall.get("win_d1") or 0) / n * 100, 1) if n else 0,
                "win_rate_d3":   round((overall.get("win_d3") or 0) / n * 100, 1) if n else 0,
                "win_rate_d7":   round((overall.get("win_d7") or 0) / n * 100, 1) if n else 0,
            },
            "score_buckets": buckets,
            "recent": recent,
        }
    except Exception as e:
        print(f"load_backtest_stats error: {e}")
        return {"total_picks_backtested": 0, "overall": {}, "score_buckets": [], "recent": []}


def save_screener_picks(picks: list):
    """패턴 스크리너 추천 결과를 DB에 저장합니다. 당일 기존 기록은 덮어씁니다."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("DELETE FROM screener_picks WHERE picked_date = ?", (today,))
        for p in picks:
            cursor.execute(
                """INSERT INTO screener_picks
                   (picked_date, ticker, name, match_score, signal, rsi, vol_ratio, pos_52w, ma_aligned)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (today, _pad_kr_ticker(p.get("code", "")), p.get("name", ""),
                 p.get("match_score"), p.get("signal"), p.get("rsi"),
                 p.get("vol_ratio"), p.get("pos_52w"),
                 1 if p.get("ma_aligned") else 0)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"save_screener_picks error: {e}")


def load_screener_feedback_stats() -> dict:
    """스크리너 피드백 통계: 추천 이력 + 리딩방 매칭/비매칭 성과 비교."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(DISTINCT picked_date) AS days, COUNT(*) AS total FROM screener_picks"
        )
        picks_row = dict(cursor.fetchone() or {})

        cursor.execute(
            """SELECT COALESCE(screener_matched, 0) AS matched,
                      COUNT(*) AS cnt,
                      SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) AS wins,
                      AVG(profit_pct) AS avg_pct
               FROM trade_history
               WHERE LOWER(COALESCE(trade_source,'')) LIKE '%리딩방%'
               GROUP BY COALESCE(screener_matched, 0)"""
        )
        groups = {"matched": {"cnt": 0, "wins": 0, "win_rate": 0, "avg_pct": 0},
                  "unmatched": {"cnt": 0, "wins": 0, "win_rate": 0, "avg_pct": 0}}
        for r in cursor.fetchall():
            d = dict(r)
            key = "matched" if d["matched"] == 1 else "unmatched"
            cnt = d["cnt"] or 0
            wins = d["wins"] or 0
            groups[key] = {
                "cnt": cnt,
                "wins": wins,
                "win_rate": round(wins / cnt * 100, 1) if cnt else 0,
                "avg_pct": round(d["avg_pct"] or 0, 2),
            }
        conn.close()
        return {
            "pick_days": picks_row.get("days", 0),
            "total_picks": picks_row.get("total", 0),
            **groups,
        }
    except Exception as e:
        print(f"load_screener_feedback_stats error: {e}")
        return {"pick_days": 0, "total_picks": 0,
                "matched": {"cnt": 0, "wins": 0, "win_rate": 0, "avg_pct": 0},
                "unmatched": {"cnt": 0, "wins": 0, "win_rate": 0, "avg_pct": 0}}


def match_screener_for_trade(ticker: str, sell_date: str) -> bool:
    """매도 종목이 최근 7일 이내 스크리너 추천 종목이면 trade_history에 screener_matched=1 기록."""
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        padded = _pad_kr_ticker(ticker)
        sell_day = sell_date[:10] if sell_date else datetime.now().strftime("%Y-%m-%d")
        cutoff = (datetime.strptime(sell_day, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT id FROM screener_picks WHERE ticker = ? AND picked_date >= ? AND picked_date <= ?",
            (padded, cutoff, sell_day)
        )
        matched = cursor.fetchone() is not None
        if matched:
            cursor.execute(
                "UPDATE trade_history SET screener_matched = 1 WHERE ticker = ? AND SUBSTR(sell_date, 1, 10) = ? AND LOWER(COALESCE(trade_source,'')) LIKE '%리딩방%'",
                (padded, sell_day)
            )
            conn.commit()
        conn.close()
        return matched
    except Exception as e:
        print(f"match_screener_for_trade error: {e}")
        return False

