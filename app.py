import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
try:
    from streamlit_autorefresh import st_autorefresh as _st_autorefresh
    _HAVE_AUTOREFRESH = True
except ImportError:
    _HAVE_AUTOREFRESH = False
from data import get_us_stock_data, get_us_market_indices, get_us_stock_detail
from data_kr import (get_us_prices_bulk_kis, get_kr_index_history,
                     get_kr_market_index, get_kr_stock_price,
                     get_kr_investor_trend, get_kr_volume_ranking,
                     get_kr_minute_chart, get_kr_daily_chart,
                     get_kr_stock_name_kis, get_kr_name_to_code_map,
                     get_kr_major_tickers)

# 1. 페이지 기본 설정 (항상 최상단에 위치)
st.set_page_config(
    page_title="Stockcy | AI 단타 트레이딩 어시스턴트",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed" # 사이드바를 숨기고 메인 화면을 넓게 씁니다.
)

# --- CSS 디자인 시스템 (다크모드 및 색상) ---
# PRD 가이드: 다크모드, 국내(상승 Red/하락 Blue), 미국(상승 Green/하락 Red)
def inject_custom_css():
    st.markdown("""
        <style>
        /* ── 색상 ── */
        .up-kr   { color: #ff4b4b; font-weight: 700; }
        .down-kr { color: #2b7cff; font-weight: 700; }
        .up-us   { color: #00c853; font-weight: 700; }
        .down-us { color: #ff4b4b; font-weight: 700; }

        /* ── Toss 스타일 버튼 (pill) ── */
        div[data-testid="stButton"] > button {
            border-radius: 20px !important;
            font-size: 0.82rem !important;
            padding: 4px 14px !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
            transition: all 0.15s ease !important;
        }
        div[data-testid="stButton"] > button[kind="primary"] {
            background: rgba(255,255,255,0.12) !important;
            color: #fff !important;
            border-color: rgba(255,255,255,0.25) !important;
        }
        div[data-testid="stButton"] > button:hover {
            background: rgba(255,255,255,0.1) !important;
            border-color: rgba(255,255,255,0.3) !important;
        }

        /* ── Toss 스타일 카드 ── */
        .toss-card {
            background: rgba(255,255,255,0.035);
            border: 1px solid rgba(255,255,255,0.07);
            border-radius: 14px;
            padding: 14px 16px;
            margin: 6px 0;
        }
        .toss-card-sm {
            background: rgba(255,255,255,0.025);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px;
            padding: 8px 12px;
            margin: 3px 0;
        }

        /* ── 상단 지수 배너 ── */
        .index-banner {
            display: flex;
            gap: 28px;
            align-items: center;
            padding: 8px 4px 4px 2px;
        }
        .index-item { display: flex; flex-direction: column; }
        .index-name { font-size: 0.7rem; color: #888; letter-spacing: 0.04em; }
        .index-val  { font-size: 1.05rem; font-weight: 700; line-height: 1.2; }
        .index-chg  { font-size: 0.72rem; margin-top: 1px; }

        /* ── 종목 행 hover ── */
        .stock-row:hover { background: rgba(255,255,255,0.04); border-radius: 8px; }

        /* ── 섹터 태그 ── */
        .sector-pill {
            display: inline-block;
            background: rgba(255,255,255,0.07);
            border-radius: 20px;
            padding: 2px 10px;
            font-size: 0.72rem;
            color: #bbb;
            margin: 1px;
        }

        /* ── 구분선 ── */
        .toss-divider {
            border: none;
            border-top: 1px solid rgba(255,255,255,0.07);
            margin: 10px 0;
        }

        .disclaimer {
            font-size: 0.78rem;
            color: #666;
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.07);
        }
        </style>
    """, unsafe_allow_html=True)

# --- 세션 상태 초기화 ---
def init_session_state():
    if "market" not in st.session_state:
        st.session_state.market = "국내 주식 🇰🇷"
    
@st.dialog("오늘의 데일리 브리핑 📝")
def show_daily_briefing():
    with st.spinner("🧠 AI가 글로벌 실시간 뉴스를 분석하여 브리핑을 작성 중입니다..."):
        from ai_engine import generate_daily_briefing
        data = generate_daily_briefing()
        st.session_state.daily_briefing_data = data # 발굴기에 컨텍스트로 넘기기 위해 저장
        
        if not data:
            st.error("뉴스를 불러오지 못했습니다.")
        elif "error" in data:
            st.error(f"서버 과부하 또는 오류 발생: {data['error']}")
        else:
            st.markdown("### 🔥 오늘의 주요 섹터")
            st.caption("관심 있는 키워드(섹터)를 클릭하면 상승/하락 이유와 실제 뉴스를 확인할 수 있습니다.")
            
            for sector in data.get("sectors", []):
                # 중점이 되는 핵심 섹터는 진한 글씨체와 아이콘으로 강조
                if sector.get("is_main"):
                    keyword_display = f"⭐ **{sector.get('keyword', '')}** (핵심 주도 테마)"
                else:
                    keyword_display = sector.get("keyword", "")
                
                # 아코디언(확장 패널) 형태로 클릭 시 내용 전개
                with st.expander(keyword_display):
                    st.markdown(f"**💡 시장 영향 및 분석:**\n{sector.get('reason', '')}")
                    
                    news_title = sector.get('reference_news_title', '관련 뉴스 보기')
                    news_url = sector.get('reference_news_url', '#')
                    st.markdown(f"**📰 신뢰도 검증:** [{news_title}]({news_url})")
                    
                    # 객관성 확보: 해당 섹터 관련 미국 주식 실시간 등락률 표시
                    related_stocks = sector.get("related_stocks", [])
                    if related_stocks:
                        tickers = [stock.get("ticker", "") for stock in related_stocks if stock.get("ticker")]
                        ticker_to_name = {stock.get("ticker"): stock.get("name_kr") for stock in related_stocks}
                        
                        if tickers:
                            col_title, col_btn = st.columns([4, 1])
                            with col_title:
                                st.markdown(f"**📊 섹터 대표 종목 실시간 시세**")
                            with col_btn:
                                if st.button("🔄 갱신", key=f"refresh_{sector.get('keyword', '')}"):
                                    st.cache_data.clear()
                                    st.rerun()
                                    
                            # 스피너를 추가하여 로딩 상태를 명확히 표시
                            with st.spinner("실시간 시세 데이터를 불러오는 중..."):
                                from data import get_us_stock_data
                                sector_df = get_us_stock_data(tickers)
                                
                            if not sector_df.empty:
                                # 심볼 컬럼을 "한글명 (티커)" 로 변경
                                sector_df["종목명"] = sector_df["심볼"].apply(lambda x: f"{ticker_to_name.get(x, x)} ({x})")
                                cols = ["종목명", "현재가($)", "등락률(%)", "상태"]
                                sector_df = sector_df[cols]
                                
                                def color_change(val):
                                    if isinstance(val, str):
                                        if '상승' in val: return 'color: #00c853; font-weight: bold;'
                                        elif '하락' in val: return 'color: #ff4b4b; font-weight: bold;'
                                    return ''
                                st.dataframe(
                                    sector_df.style.map(color_change, subset=['상태']),
                                    use_container_width=True,
                                    hide_index=True
                                )
                            else:
                                st.warning("사내 방화벽으로 인해 실시간 시세를 불러올 수 없습니다.")
                                st.markdown("**해당 섹터의 추천 관련주:**")
                                for t in tickers:
                                    st.markdown(f"- **{ticker_to_name.get(t, t)}** (`{t}`)")
                    
    if st.button("닫기"):
        st.rerun()

def main():
    if _HAVE_AUTOREFRESH:
        _st_autorefresh(interval=60000, limit=None, key="stockcy_refresh")
    init_session_state()
    inject_custom_css()
    
    # --- 상단 영역 (컴팩트) ---
    _h1, _h2, _h3 = st.columns([1.4, 3, 1.6])
    with _h1:
        st.markdown(
            "<p style='margin:6px 0 0 0;font-size:1.25rem;font-weight:800;letter-spacing:-0.5px'>📈 Stockcy</p>",
            unsafe_allow_html=True,
        )
    with _h2:
        selected_market = st.radio(
            "시장 선택",
            ["국내 주식 🇰🇷", "미국 주식 🇺🇸"],
            horizontal=True,
            label_visibility="collapsed",
        )
        if selected_market != st.session_state.market:
            st.session_state.market = selected_market
            st.rerun()
    with _h3:
        if st.button("📰 데일리 브리핑", use_container_width=True):
            show_daily_briefing()
    st.markdown("<hr class='toss-divider'>", unsafe_allow_html=True)
    
    import streamlit.components.v1 as components

    # ── 국내 주요 종목 티커 (CSS 마키, KIS/yfinance 직접 호출) ──────────
    _kr_idx   = get_kr_market_index() or {}
    _kr_ticks = get_kr_major_tickers()
    _kr_items = []

    def _ticker_pill(label, price_str, pct, is_index=False):
        c  = "#ff4b4b" if pct >= 0 else "#2b7cff"
        bg = "rgba(255,75,75,0.12)" if pct >= 0 else "rgba(43,124,255,0.12)"
        arrow = "▲" if pct >= 0 else "▼"
        sign  = "+" if pct >= 0 else ""
        badge_bg = "rgba(255,255,255,0.08)" if is_index else "rgba(255,255,255,0.04)"
        return (
            f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'background:{badge_bg};border:1px solid rgba(255,255,255,0.1);'
            f'border-radius:20px;padding:3px 10px;margin:0 6px;white-space:nowrap">'
            f'<span style="font-size:0.72rem;color:#aaa;font-weight:600">{label}</span>'
            f'<span style="font-size:0.8rem;color:#eee;font-weight:700">{price_str}</span>'
            f'<span style="font-size:0.72rem;color:{c};font-weight:700;'
            f'background:{bg};border-radius:10px;padding:1px 6px">'
            f'{arrow} {sign}{pct:.2f}%</span>'
            f'</span>'
        )

    for _iname, _id in _kr_idx.items():
        _ip = _id.get("change_pct", 0)
        _iv = _id.get("index", 0)
        _kr_items.append(_ticker_pill(_iname, f"{_iv:,.2f}", _ip, is_index=True))

    for _t in _kr_ticks:
        _kr_items.append(_ticker_pill(_t["name"], f'₩{_t["price"]:,}', _t["pct"]))

    if _kr_items:
        _kr_body = "".join(_kr_items)
        components.html(f"""
        <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.07);
                    border-radius:10px;overflow:hidden;padding:4px 0;margin-bottom:4px;height:36px;
                    display:flex;align-items:center">
          <div style="display:inline-flex;align-items:center;white-space:nowrap;
                      animation:krtick 50s linear infinite">
            {_kr_body}{_kr_body}
          </div>
        </div>
        <style>
          @keyframes krtick {{
            from {{ transform: translateX(0); }}
            to   {{ transform: translateX(-50%); }}
          }}
        </style>""", height=44)

    # ── 미국·글로벌 TradingView 티커 ────────────────────────────────────
    components.html("""
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
      {
        "symbols": [
          {"description": "S&P500",      "proName": "AMEX:SPY"},
          {"description": "나스닥100",    "proName": "NASDAQ:QQQ"},
          {"description": "다우존스",     "proName": "AMEX:DIA"},
          {"description": "원/달러",      "proName": "FX_IDC:USDKRW"},
          {"description": "엔비디아",     "proName": "NASDAQ:NVDA"},
          {"description": "애플",         "proName": "NASDAQ:AAPL"},
          {"description": "테슬라",       "proName": "NASDAQ:TSLA"},
          {"description": "마이크로소프트","proName": "NASDAQ:MSFT"},
          {"description": "메타",         "proName": "NASDAQ:META"},
          {"description": "구글",         "proName": "NASDAQ:GOOGL"},
          {"description": "아마존",       "proName": "NASDAQ:AMZN"},
          {"description": "금",           "proName": "TVC:GOLD"},
          {"description": "WTI유가",      "proName": "TVC:USOIL"},
          {"description": "비트코인",     "proName": "CRYPTO:BTCUSD"},
          {"description": "이더리움",     "proName": "CRYPTO:ETHUSD"}
        ],
        "showSymbolLogo": true,
        "isTransparent": true,
        "displayMode": "adaptive",
        "colorTheme": "dark",
        "locale": "kr"
      }
      </script>
    </div>""", height=75)
    
    # --- 메인 콘텐츠 (탭 없이 섹션으로 구성) ---
    tab1 = st.container()
    tab2 = st.expander("📈 성과 트래킹", expanded=False)
    tab3 = st.expander("🔧 관리자", expanded=False)
    
    with tab1:
        if "국내" in st.session_state.market:

            # KIS API 키 설정 확인
            try:
                _ = st.secrets["kis"]["app_key"]
            except Exception:
                st.error("KIS API 키가 설정되지 않았습니다. Streamlit Cloud → Settings → Secrets에 아래 내용을 추가해주세요.")
                st.code("[kis]\napp_key = \"발급받은_앱키\"\napp_secret = \"발급받은_앱시크릿\"", language="toml")
                st.stop()

            with st.spinner(""):
                indices = get_kr_market_index()

            # 세션 상태 초기화
            for _k, _v in [
                ("kr_mode", "🎯 AI 타점 보드"),
                ("kr_selected_code", "005930"),
                ("kr_selected_name", "삼성전자"),
                ("kr_selected_sector", "반도체"),
                ("kr_sector_view", "list"),
                ("kr_sector_detail_code", ""),
                ("kr_sector_detail_name", ""),
                ("kr_index_tab", "KOSPI"),
                ("kr_index_period", "1d"),
                ("ai_pattern_kw", ""),
                ("kr_ai_market_run", False),
                ("kr_chart_type", "일봉"),
                ("kr_daily_period", "3mo"),
                ("kr_right_tab", "📊 시세"),
            ]:
                if _k not in st.session_state:
                    st.session_state[_k] = _v

            kr_mode = st.session_state.kr_mode

            selected_code_kr = st.session_state.kr_selected_code

            # ══════════════════════════════════════════════════════════════
            # 🎯 AI 타점 보드 (항상 표시)
            # ══════════════════════════════════════════════════════════════
            if True:
                _pb_key  = "kr_picks_result"
                _run_key = "_kr_picks_pending"

                # 상단: 버튼 + 마지막 업데이트
                _ph_top = st.empty()
                _pb_col1, _pb_col2 = st.columns([3, 1])
                with _pb_col1:
                    if st.button("🔄 AI 타점 분석 실행", key="kr_picks_btn",
                                 type="primary", use_container_width=True):
                        st.session_state[_run_key] = True
                        if _pb_key in st.session_state:
                            del st.session_state[_pb_key]
                        st.rerun()
                with _pb_col2:
                    if st.button("🗑 초기화", key="kr_picks_clear", use_container_width=True):
                        st.session_state.pop(_pb_key, None)
                        st.rerun()

                # 플래그 서 있으면 AI 호출
                if st.session_state.get(_run_key) and _pb_key not in st.session_state:
                    with st.spinner("AI가 시장·뉴스·수급을 분석 중입니다..."):
                        try:
                            from ai_engine import generate_realtime_picks
                            _mkt = get_kr_market_index() or {}
                            _vol = get_kr_volume_ranking() or []
                            from data_kr import get_kr_change_ranking
                            # KOSPI + KOSDAQ 합산 → 더 넓은 종목 풀
                            _chg = (get_kr_change_ranking("J") or []) + (get_kr_change_ranking("Q") or [])
                            _picks = generate_realtime_picks(_mkt, _vol, _chg)
                        except Exception as _pe:
                            _picks = {"error": str(_pe), "picks": []}
                        _picks["_ts"] = datetime.now().strftime("%H:%M")
                        st.session_state[_pb_key] = _picks
                        st.session_state[_run_key] = False
                    st.rerun()

                # 결과 표시
                if _pb_key in st.session_state:
                    _res = st.session_state[_pb_key]
                    _ts  = _res.get("_ts", "")
                    _cond = _res.get("market_condition", "")
                    _comment = _res.get("market_comment", "")
                    _cond_color = "#ff4b4b" if "상승" in _cond else "#2b7cff" if "하락" in _cond else "#f5c518"
                    _cond_icon  = "🟢" if "상승" in _cond else "🔴" if "하락" in _cond else "🟡"

                    # 시장 컨디션 배너
                    st.markdown(
                        f"<div style='background:rgba(255,255,255,0.04);border-left:3px solid {_cond_color};"
                        f"border-radius:8px;padding:8px 14px;margin-bottom:12px;display:flex;"
                        f"justify-content:space-between;align-items:center'>"
                        f"<span>{_cond_icon} <b style='color:{_cond_color}'>{_cond}</b>"
                        f"&nbsp;&nbsp;<span style='color:#ccc;font-size:0.83rem'>{_comment}</span></span>"
                        f"<span style='font-size:0.72rem;color:#666'>업데이트 {_ts}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                    if _res.get("error") and not _res.get("picks"):
                        st.error(f"분석 오류: {_res['error']}")
                    elif not _res.get("picks"):
                        st.info("추천 종목이 없습니다. 다시 시도해주세요.")
                    else:
                        _pick_cols = st.columns(len(_res["picks"]))
                        for _ci, (_pick, _pcol) in enumerate(zip(_res["picks"], _pick_cols)):
                            _urg     = _pick.get("urgency", "")
                            _horizon = _pick.get("horizon", "")
                            _pattern = _pick.get("pattern", "")

                            # 긴급도 배지
                            _urg_icon  = "⚡" if "즉시" in _urg else ("🌙" if "내일" in _urg else "🕐")
                            _urg_color = "#ff9800" if "즉시" in _urg else ("#a78bfa" if "내일" in _urg else "#888")
                            _urg_bg    = ("rgba(255,152,0,0.15)" if "즉시" in _urg
                                          else "rgba(167,139,250,0.15)" if "내일" in _urg
                                          else "rgba(255,255,255,0.06)")

                            # 시간축 배지 (당일스캘핑 / 1~2일스윙)
                            _hz_color = "#00c853" if "스캘핑" in _horizon or "당일" in _horizon else "#f5c518"
                            _hz_label = "⚡당일" if "스캘핑" in _horizon or "당일" in _horizon else "📅1~2일"

                            _entry  = _pick.get("entry", 0)
                            _target = _pick.get("target", 0)
                            _stop   = _pick.get("stop", 0)
                            _cur    = _pick.get("current_price", 0)
                            _cpct   = float(_pick.get("change_pct", 0) or 0)
                            _upside = round((_target - _entry) / _entry * 100, 1) if _entry > 0 else 0
                            _themes = [t.strip() for t in str(_pick.get("theme","")).split(",") if t.strip()]
                            _already_surged = _cpct >= 10

                            with _pcol:
                                _cpct_color = "#ff4b4b" if _cpct >= 0 else "#2b7cff"
                                _cpct_sign  = "▲" if _cpct >= 0 else "▼"

                                # 현재가 + 등락률
                                _cur_html = (
                                    f"<div style='font-size:0.8rem;color:#aaa;margin-bottom:8px'>"
                                    f"현재 <b style='color:#eee'>₩{int(_cur):,}</b>&nbsp;"
                                    f"<span style='color:{_cpct_color};font-weight:700'>"
                                    f"{_cpct_sign} {abs(_cpct):.2f}%</span></div>"
                                ) if _cur > 0 else ""

                                # 감지된 패턴 배지
                                _pattern_html = (
                                    f"<div style='font-size:0.62rem;color:#7dd3fc;"
                                    f"background:rgba(125,211,252,0.08);border-radius:6px;"
                                    f"padding:3px 8px;margin-bottom:8px;display:inline-block'>"
                                    f"📊 {_pattern}</div>"
                                ) if _pattern else ""

                                # 테마 태그
                                _theme_html = "".join(
                                    f"<span style='background:rgba(255,255,255,0.08);"
                                    f"border-radius:10px;padding:2px 7px;font-size:0.63rem;"
                                    f"color:#aaa;margin-right:4px'>{th}</span>"
                                    for th in _themes
                                )

                                # 이미 급등 경고
                                _warn_html = (
                                    "<div style='background:rgba(255,75,75,0.15);border:1px solid #ff4b4b;"
                                    "border-radius:8px;padding:4px 8px;font-size:0.65rem;color:#ff4b4b;"
                                    "margin-bottom:8px'>⚠️ 이미 많이 오른 종목 — 진입 신중</div>"
                                ) if _already_surged else ""

                                _border_color = "rgba(255,75,75,0.3)" if _already_surged else "rgba(255,255,255,0.1)"

                                _card_html = (
                                    f"<div style='background:rgba(255,255,255,0.035);"
                                    f"border:1px solid {_border_color};border-radius:14px;"
                                    f"padding:14px 14px 12px 14px'>"
                                    # 헤더: 종목명 + 긴급도 배지
                                    f"<div style='display:flex;justify-content:space-between;"
                                    f"align-items:flex-start;margin-bottom:6px'>"
                                    f"<div>"
                                    f"<span style='font-size:0.7rem;color:#888'>#{_pick.get('rank',_ci+1)}</span>&nbsp;"
                                    f"<span style='font-size:1rem;font-weight:700'>{_pick.get('name','')}</span><br>"
                                    f"<span style='font-size:0.68rem;color:#666'>{_pick.get('code','')}</span>"
                                    f"</div>"
                                    f"<div style='text-align:right'>"
                                    f"<span style='background:{_urg_bg};color:{_urg_color};"
                                    f"border-radius:10px;padding:2px 7px;font-size:0.65rem;font-weight:700;"
                                    f"display:block;margin-bottom:3px'>{_urg_icon} {_urg}</span>"
                                    f"<span style='color:{_hz_color};font-size:0.6rem;font-weight:600'>{_hz_label}</span>"
                                    f"</div></div>"
                                    + _warn_html
                                    + _pattern_html
                                    + _cur_html +
                                    # 타점 그리드
                                    f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;"
                                    f"gap:6px;margin-bottom:10px'>"
                                    f"<div style='background:rgba(255,255,255,0.06);border-radius:8px;"
                                    f"padding:6px;text-align:center'>"
                                    f"<div style='font-size:0.6rem;color:#888'>매수 타점</div>"
                                    f"<div style='font-size:0.85rem;font-weight:700'>₩{int(_entry):,}</div></div>"
                                    f"<div style='background:rgba(0,200,83,0.1);border-radius:8px;"
                                    f"padding:6px;text-align:center'>"
                                    f"<div style='font-size:0.6rem;color:#888'>목표가</div>"
                                    f"<div style='font-size:0.85rem;font-weight:700;color:#00c853'>"
                                    f"₩{int(_target):,}</div>"
                                    f"<div style='font-size:0.6rem;color:#00c853'>+{_upside}%</div></div>"
                                    f"<div style='background:rgba(43,124,255,0.1);border-radius:8px;"
                                    f"padding:6px;text-align:center'>"
                                    f"<div style='font-size:0.6rem;color:#888'>손절가</div>"
                                    f"<div style='font-size:0.85rem;font-weight:700;color:#2b7cff'>"
                                    f"₩{int(_stop):,}</div></div>"
                                    f"</div>"
                                    # 추천 근거
                                    f"<div style='font-size:0.72rem;color:#bbb;line-height:1.6;"
                                    f"margin-bottom:8px'>{_pick.get('reason','')}</div>"
                                    + _theme_html
                                    + "</div>"
                                )
                                st.markdown(_card_html, unsafe_allow_html=True)
                                if st.button("상세 분석 →", key=f"pk_detail_{_pick.get('code',_ci)}",
                                             use_container_width=True):
                                    st.session_state.kr_selected_code = _pick.get("code", "005930")
                                    st.session_state.kr_selected_name = _pick.get("name", "")
                                    st.session_state.kr_mode = "📊 일반 주식 검색"
                                    st.rerun()
                else:
                    st.markdown(
                        "<div style='text-align:center;padding:60px 0;color:#555'>"
                        "<div style='font-size:2rem'>🎯</div>"
                        "<div style='margin-top:8px;font-size:0.9rem'>AI 타점 분석 실행 버튼을 눌러<br>"
                        "실시간 추천 종목을 받아보세요</div>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
            # (end of AI 타점 보드 section)

            # ══════════════════════════════════════════════════════════════
            # 📊 종목 탐색 (일반 주식 검색 / 오늘의 이슈 섹터)
            # ══════════════════════════════════════════════════════════════
            with st.expander("📊 종목 탐색", expanded=False):
                _kn1, _kn2 = st.columns(2)
                with _kn1:
                    if st.button(
                        "📊 일반 주식 검색",
                        key="kr_nav2_search",
                        type="primary" if kr_mode == "📊 일반 주식 검색" else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state.kr_mode = "📊 일반 주식 검색"
                        st.rerun()
                with _kn2:
                    if st.button(
                        "🔥 오늘의 이슈 섹터",
                        key="kr_nav2_sector",
                        type="primary" if kr_mode == "🔥 오늘의 이슈 섹터" else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state.kr_mode = "🔥 오늘의 이슈 섹터"
                        st.rerun()

                _need_price = (
                    kr_mode == "📊 일반 주식 검색"
                    or st.session_state.kr_sector_view == "detail"
                )
                price_kr = None
                if _need_price:
                    with st.spinner("시세 조회 중..."):
                        price_kr = get_kr_stock_price(selected_code_kr)
                is_up = is_dn = False
                arrow = "-"
                d_color = "off"
                if price_kr:
                    is_up = price_kr["sign"] in ("1", "2")
                    is_dn = price_kr["sign"] in ("4", "5")
                    arrow = "▲" if is_up else "▼" if is_dn else "-"
                    d_color = "normal" if is_up else "inverse" if is_dn else "off"

                col_chart, col_right = st.columns([5, 5])
                with col_chart:
                    # ── 이슈 섹터 모드 ──────────────────────────────────────
                    if kr_mode == "🔥 오늘의 이슈 섹터":

                        if st.session_state.kr_sector_view == "detail":
                            # 선택 종목 Plotly 차트 (최근 60봉 한정 → 1초봉 현상 방지)
                            _dtv_code = st.session_state.kr_sector_detail_code
                            _dtv_name = st.session_state.kr_sector_detail_name
                            pct_color = "up-kr" if is_up else "down-kr" if is_dn else ""
                            if price_kr:
                                st.markdown(
                                    f"**{_dtv_name}** ({_dtv_code}) &nbsp; "
                                    f"₩{price_kr['price']:,} &nbsp; "
                                    f'<span class="{pct_color}">{arrow} {price_kr["change_pct"]:+.2f}%</span>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.markdown(f"**{_dtv_name}** ({_dtv_code})")

                            _si_c1, _si_c2, _ = st.columns([2, 1, 4])
                            with _si_c1:
                                _sec_interval = st.selectbox(
                                    "분봉", [5, 10, 15, 30], index=0,
                                    key="kr_sec_chart_interval",
                                    format_func=lambda x: f"{x}분봉",
                                )
                            with _si_c2:
                                if st.button("🔄", key="refresh_sec_chart", help="새로고침"):
                                    get_kr_minute_chart.clear()
                                    st.rerun()

                            with st.spinner("차트 조회 중..."):
                                df_sec = get_kr_minute_chart(_dtv_code, interval=_sec_interval)

                            if not df_sec.empty:
                                from plotly.subplots import make_subplots
                                from datetime import datetime as _dt_s
                                import pytz as _pytz_s
                                df_sec["ma5"]  = df_sec["close"].rolling(5).mean()
                                df_sec["ma20"] = df_sec["close"].rolling(20).mean()
                                _vc = ["#ff4b4b" if c >= o else "#2b7cff"
                                       for c, o in zip(df_sec["close"], df_sec["open"])]
                                _now_s  = _dt_s.now(_pytz_s.timezone("Asia/Seoul")).replace(tzinfo=None)
                                _xs_cl  = _dt_s.combine(_now_s.date(), _dt_s.strptime("15:30", "%H:%M").time())
                                _xs_end = min(_now_s, _xs_cl).strftime("%Y-%m-%d %H:%M")
                                _xs_st  = df_sec["datetime"].iloc[0].strftime("%Y-%m-%d 09:00")

                                _fig_s = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                                       row_heights=[0.70, 0.30], vertical_spacing=0.02)
                                _fig_s.add_trace(go.Candlestick(
                                    x=df_sec["datetime"],
                                    open=df_sec["open"], high=df_sec["high"],
                                    low=df_sec["low"],   close=df_sec["close"],
                                    increasing=dict(line=dict(color="#ff4b4b", width=1), fillcolor="#ff4b4b"),
                                    decreasing=dict(line=dict(color="#2b7cff", width=1), fillcolor="#2b7cff"),
                                    name="가격", showlegend=False,
                                ), row=1, col=1)
                                _fig_s.add_trace(go.Scatter(x=df_sec["datetime"], y=df_sec["ma5"],
                                    line=dict(color="#f5c518", width=1.2), name="MA5"), row=1, col=1)
                                _fig_s.add_trace(go.Scatter(x=df_sec["datetime"], y=df_sec["ma20"],
                                    line=dict(color="#00b4d8", width=1.2), name="MA20"), row=1, col=1)
                                _fig_s.add_trace(go.Bar(x=df_sec["datetime"], y=df_sec["volume"],
                                    marker_color=_vc, name="거래량", showlegend=False), row=2, col=1)
                                _ax = dict(gridcolor="rgba(255,255,255,0.08)", showline=False)
                                _fig_s.update_layout(
                                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                    font=dict(color="white", size=11),
                                    xaxis=dict(**_ax, rangeslider=dict(visible=False),
                                               showticklabels=False, range=[_xs_st, _xs_end]),
                                    xaxis2=dict(**_ax, range=[_xs_st, _xs_end], tickformat="%H:%M"),
                                    yaxis=dict(**_ax, tickformat=",", side="right", autorange=True),
                                    yaxis2=dict(**_ax, tickformat=".2s", side="right", autorange=True),
                                    legend=dict(orientation="h", x=0, y=1.05,
                                                bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
                                    hovermode="x unified",
                                    margin=dict(l=0, r=60, t=30, b=5), height=540,
                                )
                                _fig_s.update_xaxes(
                                    rangebreaks=[
                                        dict(bounds=["sat", "mon"]),
                                        dict(bounds=[15.5, 9], pattern="hour"),
                                    ]
                                )
                                st.plotly_chart(_fig_s, use_container_width=True)
                            else:
                                st.info("분봉 데이터를 불러올 수 없습니다. 장 운영 시간(09:00~15:30) 중 다시 시도해주세요.")

                        else:
                            # 섹터 목록 뷰 → KOSPI/KOSDAQ Toss 스타일 라인 차트

                            # KOSPI / KOSDAQ 탭 토글
                            _itab_c1, _itab_c2 = st.columns(2)
                            for _itc, _itn in [(_itab_c1, "KOSPI"), (_itab_c2, "KOSDAQ")]:
                                _active = st.session_state.kr_index_tab == _itn
                                if _itc.button(
                                    _itn,
                                    key=f"idx_tab_{_itn}",
                                    use_container_width=True,
                                    type="primary" if _active else "secondary",
                                ):
                                    st.session_state.kr_index_tab = _itn
                                    st.rerun()

                            _cur_tab    = st.session_state.kr_index_tab
                            _cur_symbol = "^KS11" if _cur_tab == "KOSPI" else "^KQ11"
                            _idx_data   = indices.get(_cur_tab, {})
                            _idx_val    = _idx_data.get("index", 0)
                            _idx_chg    = _idx_data.get("change", 0)
                            _idx_pct    = _idx_data.get("change_pct", 0)
                            _is_up_idx  = _idx_chg >= 0
                            _lc         = "#ff4b4b" if _is_up_idx else "#2b7cff"
                            _fc         = "rgba(255,75,75,0.12)" if _is_up_idx else "rgba(43,124,255,0.12)"
                            _sign       = "+" if _is_up_idx else ""

                            # 현재 지수값 + 등락 표시 (토스 스타일: 크고 굵게)
                            st.markdown(
                                f"<div style='margin:8px 0 4px 0'>"
                                f"<span style='font-size:1.55rem;font-weight:700'>"
                                f"{_idx_val:,.2f}</span>&nbsp;"
                                f"<span style='font-size:0.88rem;color:{_lc};font-weight:600'>"
                                f"{_sign}{_idx_chg:.2f}p&nbsp;({_sign}{_idx_pct:.2f}%)</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                            # 기간 선택 버튼
                            _periods = [("1일","1d"),("1주","5d"),("1달","1mo"),("3달","3mo"),("1년","1y")]
                            _pcols   = st.columns(len(_periods))
                            for _pi, (_pl, _pv) in enumerate(_periods):
                                _sel = st.session_state.kr_index_period == _pv
                                if _pcols[_pi].button(
                                    _pl, key=f"idx_per_{_pv}",
                                    use_container_width=True,
                                    type="primary" if _sel else "secondary",
                                ):
                                    st.session_state.kr_index_period = _pv
                                    st.rerun()

                            # 차트 그리기
                            _period = st.session_state.kr_index_period
                            with st.spinner(""):
                                _df_idx = get_kr_index_history(_cur_symbol, _period)

                            if not _df_idx.empty:
                                import pytz as _pytz_idx
                                _now_kst_idx = datetime.now(_pytz_idx.timezone("Asia/Seoul")).replace(tzinfo=None)
                                _fig_idx = go.Figure()
                                _fig_idx.add_trace(go.Scatter(
                                    x=_df_idx["datetime"],
                                    y=_df_idx["close"],
                                    mode="lines",
                                    line=dict(color=_lc, width=2),
                                    fill="tozeroy",
                                    fillcolor=_fc,
                                    hovertemplate="%{x|%m/%d %H:%M}<br><b>%{y:,.2f}</b><extra></extra>",
                                ))
                                # 1일 뷰: 09:00~15:30 전체 장 시간 고정 (HTS 스타일)
                                _xax_1d = _period == "1d"
                                _xax_cfg = dict(
                                    showgrid=False, showline=False, zeroline=False,
                                    tickfont=dict(size=10, color="#666"),
                                    tickformat="%H:%M" if _xax_1d else "%m/%d",
                                )
                                if _xax_1d:
                                    _xax_cfg["type"] = "date"
                                    _xax_cfg["range"] = [
                                        _now_kst_idx.strftime("%Y-%m-%d 09:00"),
                                        _now_kst_idx.strftime("%Y-%m-%d 15:30"),
                                    ]
                                _fig_idx.update_layout(
                                    height=285,
                                    margin=dict(l=0, r=4, t=4, b=0),
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    plot_bgcolor="rgba(0,0,0,0)",
                                    showlegend=False,
                                    xaxis=_xax_cfg,
                                    yaxis=dict(
                                        showgrid=False, showline=False, zeroline=False,
                                        tickfont=dict(size=10, color="#666"),
                                        side="right", tickformat=",.0f",
                                    ),
                                    hovermode="x unified",
                                )
                                st.plotly_chart(
                                    _fig_idx, use_container_width=True,
                                    config={"displayModeBar": False},
                                )
                            else:
                                st.info("차트 데이터를 불러올 수 없습니다.")

                    # ── 일반 주식 검색 모드 ──────────────────────────────────
                    else:
                        if price_kr:
                            pct_color = "up-kr" if is_up else "down-kr" if is_dn else ""
                            st.markdown(
                                f"**{price_kr['name']}** ({selected_code_kr}) &nbsp; "
                                f"₩{price_kr['price']:,} &nbsp; "
                                f'<span class="{pct_color}">{arrow} {price_kr["change_pct"]:+.2f}%</span>',
                                unsafe_allow_html=True,
                            )

                            # 차트 타입 토글: 일봉(기본) | 분봉(당일)
                            _ct_c1, _ct_c2, _ct_c3, _ = st.columns([1.2, 1.2, 1.2, 4])
                            for _ctcol, _ctn in [(_ct_c1, "일봉"), (_ct_c2, "분봉")]:
                                if _ctcol.button(
                                    _ctn, key=f"chart_type_{_ctn}",
                                    type="primary" if st.session_state.kr_chart_type == _ctn else "secondary",
                                    use_container_width=True,
                                ):
                                    st.session_state.kr_chart_type = _ctn
                                    st.rerun()
                            if _ct_c3.button("🔄", key="refresh_kr_chart_all", help="차트 새로고침"):
                                get_kr_minute_chart.clear()
                                get_kr_daily_chart.clear()
                                st.rerun()

                            from plotly.subplots import make_subplots

                            if st.session_state.kr_chart_type == "분봉":
                                _iv_c1, _ = st.columns([2, 6])
                                interval_kr = _iv_c1.selectbox(
                                    "분봉", [1, 3, 5, 10, 15, 30], index=2,
                                    key="kr_chart_interval", format_func=lambda x: f"{x}분봉"
                                )
                                with st.spinner("분봉 데이터 조회 중..."):
                                    df_kr_chart = get_kr_minute_chart(selected_code_kr, interval=interval_kr)

                                if not df_kr_chart.empty:
                                    from datetime import datetime as _dt_c
                                    import pytz as _pytz_c
                                    df_kr_chart["ma5"]  = df_kr_chart["close"].rolling(5).mean()
                                    df_kr_chart["ma20"] = df_kr_chart["close"].rolling(20).mean()
                                    vol_colors = [
                                        "#ff4b4b" if c >= o else "#2b7cff"
                                        for c, o in zip(df_kr_chart["close"], df_kr_chart["open"])
                                    ]
                                    _now_kr_c = _dt_c.now(_pytz_c.timezone("Asia/Seoul")).replace(tzinfo=None)
                                    # 항상 09:00~15:30 전체 장 시간 표시 (HTS/MTS 스타일)
                                    _x_start  = _now_kr_c.strftime("%Y-%m-%d 09:00")
                                    _x_end    = _now_kr_c.strftime("%Y-%m-%d 15:30")

                                    fig_kr = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                                           row_heights=[0.70, 0.30], vertical_spacing=0.02)
                                    fig_kr.add_trace(go.Candlestick(
                                        x=df_kr_chart["datetime"],
                                        open=df_kr_chart["open"], high=df_kr_chart["high"],
                                        low=df_kr_chart["low"],   close=df_kr_chart["close"],
                                        increasing=dict(line=dict(color="#ff4b4b", width=1.5), fillcolor="#ff4b4b"),
                                        decreasing=dict(line=dict(color="#2b7cff", width=1.5), fillcolor="#2b7cff"),
                                        name="가격", showlegend=False,
                                        whiskerwidth=0.3,
                                    ), row=1, col=1)
                                    fig_kr.add_trace(go.Scatter(x=df_kr_chart["datetime"], y=df_kr_chart["ma5"],
                                        line=dict(color="#f5c518", width=1.2), name="MA5"), row=1, col=1)
                                    fig_kr.add_trace(go.Scatter(x=df_kr_chart["datetime"], y=df_kr_chart["ma20"],
                                        line=dict(color="#00b4d8", width=1.2), name="MA20"), row=1, col=1)
                                    fig_kr.add_trace(go.Bar(x=df_kr_chart["datetime"], y=df_kr_chart["volume"],
                                        marker_color=vol_colors, name="거래량", showlegend=False), row=2, col=1)
                                    _ax = dict(gridcolor="rgba(255,255,255,0.08)", showline=False)
                                    fig_kr.update_layout(
                                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                        font=dict(color="white", size=11),
                                        xaxis=dict(**_ax, rangeslider=dict(visible=False),
                                                   showticklabels=False, range=[_x_start, _x_end],
                                                   type="date"),
                                        xaxis2=dict(**_ax, range=[_x_start, _x_end],
                                                    tickformat="%H:%M", type="date"),
                                        yaxis=dict(**_ax, tickformat=",", side="right", autorange=True),
                                        yaxis2=dict(**_ax, tickformat=".2s", side="right", autorange=True),
                                        legend=dict(orientation="h", x=0, y=1.05, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
                                        hovermode="x unified",
                                        margin=dict(l=0, r=60, t=30, b=5), height=540,
                                    )
                                    fig_kr.update_xaxes(rangebreaks=[
                                        dict(bounds=["sat", "mon"]),
                                        dict(bounds=[15.5, 9], pattern="hour"),
                                    ])
                                    st.plotly_chart(fig_kr, use_container_width=True)
                                else:
                                    st.info("분봉 데이터를 불러올 수 없습니다. 장 운영 시간(09:00~15:30) 중 다시 시도해주세요.")

                            else:  # 일봉
                                _dp_labels = [("1개월","1mo"),("3개월","3mo"),("6개월","6mo"),("1년","1y"),("2년","2y"),("5년","5y")]
                                _dp_cols   = st.columns(len(_dp_labels))
                                for _dpi, (_dpl, _dpv) in enumerate(_dp_labels):
                                    if _dp_cols[_dpi].button(
                                        _dpl, key=f"daily_per_{_dpv}",
                                        type="primary" if st.session_state.kr_daily_period == _dpv else "secondary",
                                        use_container_width=True,
                                    ):
                                        st.session_state.kr_daily_period = _dpv
                                        st.rerun()

                                with st.spinner("일봉 데이터 조회 중..."):
                                    df_d = get_kr_daily_chart(selected_code_kr, period=st.session_state.kr_daily_period)

                                if not df_d.empty:
                                    df_d["ma5"]  = df_d["close"].rolling(5).mean()
                                    df_d["ma20"] = df_d["close"].rolling(20).mean()
                                    df_d["ma60"] = df_d["close"].rolling(60).mean()
                                    _dvc = ["#ff4b4b" if c >= o else "#2b7cff"
                                            for c, o in zip(df_d["close"], df_d["open"])]
                                    fig_d = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                                          row_heights=[0.70, 0.30], vertical_spacing=0.02)
                                    fig_d.add_trace(go.Candlestick(
                                        x=df_d["datetime"],
                                        open=df_d["open"], high=df_d["high"],
                                        low=df_d["low"],   close=df_d["close"],
                                        increasing=dict(line=dict(color="#ff4b4b", width=1), fillcolor="#ff4b4b"),
                                        decreasing=dict(line=dict(color="#2b7cff", width=1), fillcolor="#2b7cff"),
                                        name="가격", showlegend=False,
                                    ), row=1, col=1)
                                    fig_d.add_trace(go.Scatter(x=df_d["datetime"], y=df_d["ma5"],
                                        line=dict(color="#f5c518", width=1.2), name="MA5"), row=1, col=1)
                                    fig_d.add_trace(go.Scatter(x=df_d["datetime"], y=df_d["ma20"],
                                        line=dict(color="#00b4d8", width=1.2), name="MA20"), row=1, col=1)
                                    fig_d.add_trace(go.Scatter(x=df_d["datetime"], y=df_d["ma60"],
                                        line=dict(color="#ff9800", width=1.2, dash="dot"), name="MA60"), row=1, col=1)
                                    fig_d.add_trace(go.Bar(x=df_d["datetime"], y=df_d["volume"],
                                        marker_color=_dvc, name="거래량", showlegend=False), row=2, col=1)
                                    _ax = dict(gridcolor="rgba(255,255,255,0.08)", showline=False)
                                    _xrng = [str(df_d["datetime"].min())[:10],
                                             str(df_d["datetime"].max())[:10]]
                                    fig_d.update_layout(
                                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                        font=dict(color="white", size=11),
                                        xaxis=dict(**_ax, rangeslider=dict(visible=False),
                                                   showticklabels=False, range=_xrng),
                                        xaxis2=dict(**_ax, tickformat="%y/%m/%d", range=_xrng),
                                        yaxis=dict(**_ax, tickformat=",", side="right", autorange=True),
                                        yaxis2=dict(**_ax, tickformat=".2s", side="right", autorange=True),
                                        legend=dict(orientation="h", x=0, y=1.05, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
                                        hovermode="x unified",
                                        margin=dict(l=0, r=60, t=30, b=5), height=540,
                                    )
                                    fig_d.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
                                    st.plotly_chart(fig_d, use_container_width=True)
                                else:
                                    st.info("일봉 데이터를 불러올 수 없습니다.")
                        else:
                            st.warning(
                                f"종목코드 **{selected_code_kr}** 시세를 불러올 수 없습니다.  \n"
                                "KIS API와 yfinance 모두 실패했습니다. "
                                "장 운영 시간(09:00~15:30) 확인 또는 잠시 후 다시 시도해주세요."
                            )

                with col_right:
                    if kr_mode == "📊 일반 주식 검색":
                        _cur_code = st.session_state.kr_selected_code
                        _cur_name = st.session_state.kr_selected_name
                        _krx_map = get_kr_name_to_code_map()
                        new_code = _cur_code
                        new_name = _cur_name
                        if _krx_map:
                            _all_opts = sorted(_krx_map.items(), key=lambda x: x[0])
                            _opt_labels = [f"{n} ({i['code']})" for n, i in _all_opts]
                            _opt_codes  = [i["code"] for _, i in _all_opts]
                            _def_idx = next((i for i, c in enumerate(_opt_codes) if c == _cur_code), 0)
                            _sel_label = st.selectbox(
                                "종목 검색 (이름·코드 입력하면 필터링)",
                                _opt_labels,
                                index=_def_idx,
                                key="kr_stock_search",
                            )
                            new_code = _opt_codes[_opt_labels.index(_sel_label)]
                            new_name = _sel_label.split(" (")[0]
                        else:
                            POPULAR_KR = {
                                "삼성전자 (005930)": "005930",
                                "SK하이닉스 (000660)": "000660",
                                "현대차 (005380)": "005380",
                                "NAVER (035420)": "035420",
                                "카카오 (035720)": "035720",
                                "LG에너지솔루션 (373220)": "373220",
                                "삼성바이오로직스 (207940)": "207940",
                                "POSCO홀딩스 (005490)": "005490",
                                "기아 (000270)": "000270",
                            }
                            _pop = dict(POPULAR_KR)
                            if _cur_code not in _pop.values():
                                _pop = {f"[현재] {_cur_name} ({_cur_code})": _cur_code, **_pop}
                            col_sel, col_manual = st.columns([3, 1])
                            with col_sel:
                                _def_label = next(
                                    (lbl for lbl, code in _pop.items() if code == _cur_code),
                                    list(_pop.keys())[0]
                                )
                                selected_label = st.selectbox(
                                    "인기 종목 빠른 선택", list(_pop.keys()),
                                    index=list(_pop.keys()).index(_def_label)
                                )
                                new_code = _pop[selected_label]
                                new_name = selected_label.split(" (")[0]
                            with col_manual:
                                manual_code_kr = st.text_input("직접 입력 (6자리 코드)", "").strip()
                            if manual_code_kr and len(manual_code_kr) == 6 and manual_code_kr.isdigit():
                                new_code = manual_code_kr
                                new_name = manual_code_kr
                        if new_code != st.session_state.kr_selected_code:
                            st.session_state.kr_selected_code = new_code
                            st.session_state.kr_selected_name = new_name
                            st.rerun()

                        # ── 우측 패널 탭 ──────────────────────────────────────
                        _rp_tabs = ["📊 시세", "💰 수급", "🧠 AI 분석"]
                        _rp_c1, _rp_c2, _rp_c3 = st.columns(3)
                        for _rpc, _rpt in [(_rp_c1, _rp_tabs[0]), (_rp_c2, _rp_tabs[1]), (_rp_c3, _rp_tabs[2])]:
                            if _rpc.button(
                                _rpt, key=f"rp_{_rpt}",
                                type="primary" if st.session_state.kr_right_tab == _rpt else "secondary",
                                use_container_width=True,
                            ):
                                st.session_state.kr_right_tab = _rpt
                                st.rerun()

                        if price_kr:
                            # ── 탭 1: 시세 ────────────────────────────────────
                            if st.session_state.kr_right_tab == _rp_tabs[0]:
                                with st.container(border=True):
                                    # 현재가 강조
                                    _pc = "#ff4b4b" if is_up else "#2b7cff" if is_dn else "#aaa"
                                    st.markdown(
                                        f"<div style='margin:4px 0'>"
                                        f"<span style='font-size:1.5rem;font-weight:700'>₩{price_kr['price']:,}</span>"
                                        f"&nbsp;<span style='font-size:0.9rem;color:{_pc};font-weight:600'>"
                                        f"{arrow} {abs(price_kr['change']):,}원 ({price_kr['change_pct']:+.2f}%)</span>"
                                        f"</div>",
                                        unsafe_allow_html=True,
                                    )
                                    _m1, _m2, _m3 = st.columns(3)
                                    _m1.metric("거래량", f"{price_kr['volume']:,}주")
                                    _m2.metric("거래대금", f"₩{price_kr['amount']//100000000:,}억" if price_kr['amount']>0 else "-")
                                    _m3.metric("시가총액", f"₩{price_kr['market_cap']}억" if price_kr['market_cap'] != '-' else "-")
                                    _m4, _m5, _m6 = st.columns(3)
                                    _m4.metric("시가", f"₩{price_kr['open']:,}")
                                    _m5.metric("고가", f"₩{price_kr['high']:,}")
                                    _m6.metric("저가", f"₩{price_kr['low']:,}")
                                    _m7, _m8, _m9 = st.columns(3)
                                    _m7.metric("PER", price_kr['per'])
                                    _m8.metric("PBR", price_kr['pbr'])
                                    _m9.metric("52주 최고", f"₩{price_kr['w52_high']:,}")

                                    # 52주 가격 밴드 게이지
                                    _wl = price_kr.get("w52_low", 0) or 0
                                    _wh = price_kr.get("w52_high", 0) or 0
                                    _cp = price_kr["price"]
                                    if _wh > _wl > 0:
                                        _band_pct = max(0, min(100, (_cp - _wl) / (_wh - _wl) * 100))
                                        st.markdown(
                                            f"<div style='margin:8px 0 2px 0'>"
                                            f"<span style='font-size:0.7rem;color:#888'>52주 가격 위치</span>"
                                            f"</div>"
                                            f"<div style='position:relative;background:rgba(255,255,255,0.08);"
                                            f"border-radius:4px;height:6px;margin:0 0 4px 0'>"
                                            f"<div style='background:{_pc};border-radius:4px;height:6px;"
                                            f"width:{_band_pct:.1f}%'></div>"
                                            f"</div>"
                                            f"<div style='display:flex;justify-content:space-between;"
                                            f"font-size:0.65rem;color:#888'>"
                                            f"<span>최저 ₩{_wl:,}</span>"
                                            f"<span style='color:{_pc};font-weight:700'>{_band_pct:.0f}%</span>"
                                            f"<span>최고 ₩{_wh:,}</span>"
                                            f"</div>",
                                            unsafe_allow_html=True,
                                        )

                                # 단타 적합성 판단
                                _chg = price_kr["change_pct"]
                                if _chg >= 5.0:
                                    st.success(f"✅ **강력 단타 추천** {_chg:+.2f}% — 강한 모멘텀, 눌림목 진입 권장")
                                elif _chg >= 3.0:
                                    st.success(f"✅ **단타 추천** {_chg:+.2f}% — 수급 확인 후 진입, 손절: 당일 저점")
                                elif _chg >= 1.5:
                                    st.warning(f"⚠️ **관망** {_chg:+.2f}% — 3% 돌파 확인 후 진입 검토")
                                elif _chg <= -3.0:
                                    st.info(f"🔵 **반등 포착 관찰** {_chg:+.2f}% — 지지선·거래량 확인 필수")
                                else:
                                    st.error(f"❌ **단타 비적합** {_chg:+.2f}% — 수수료·세금 감안 시 실익 없음")

                            # ── 탭 2: 수급 ────────────────────────────────────
                            elif st.session_state.kr_right_tab == _rp_tabs[1]:
                                with st.spinner("수급 데이터 조회 중..."):
                                    investor_kr = get_kr_investor_trend(selected_code_kr)
                                if investor_kr:
                                    df_inv = pd.DataFrame(investor_kr)
                                    fig_inv = go.Figure()
                                    for _cn, _cc in [("외국인","#ff4b4b"),("기관","#2b7cff"),("개인","#888")]:
                                        fig_inv.add_trace(go.Bar(
                                            name=_cn, x=df_inv["날짜"], y=df_inv[_cn], marker_color=_cc
                                        ))
                                    fig_inv.update_layout(
                                        barmode="group",
                                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                        font=dict(color="white"), legend=dict(orientation="h"),
                                        xaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
                                        yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="순매수(주)"),
                                        margin=dict(l=10, r=10, t=10, b=10), height=240,
                                    )
                                    st.plotly_chart(fig_inv, use_container_width=True)
                                    _lat = investor_kr[0]
                                    _fe = "🔴" if _lat["외국인"] > 0 else "🔵"
                                    _ie = "🔴" if _lat["기관"] > 0 else "🔵"
                                    st.markdown(
                                        f"**{_lat['날짜']} 수급**  \n"
                                        f"외국인 {_fe} **{_lat['외국인']:+,}주** &nbsp;|&nbsp; "
                                        f"기관 {_ie} **{_lat['기관']:+,}주**"
                                    )
                                    # 5일 누계
                                    _total_f = sum(r["외국인"] for r in investor_kr)
                                    _total_i = sum(r["기관"] for r in investor_kr)
                                    with st.container(border=True):
                                        _tc1, _tc2 = st.columns(2)
                                        _tc1.metric("외국인 5일 순매수", f"{_total_f:+,}주",
                                                    delta_color="normal" if _total_f >= 0 else "inverse")
                                        _tc2.metric("기관 5일 순매수", f"{_total_i:+,}주",
                                                    delta_color="normal" if _total_i >= 0 else "inverse")
                                else:
                                    st.info("수급 데이터를 불러올 수 없습니다.")

                            # ── 탭 3: AI 분석 ─────────────────────────────────
                            elif st.session_state.kr_right_tab == _rp_tabs[2]:
                                _ai_key  = f"kr_report_{selected_code_kr}"
                                _run_key = "_kr_ai_pending"

                                # 버튼 클릭 → 플래그만 세우고 rerun (핸들러 내 긴 작업 방지)
                                if st.button("🎯 AI 수급 & 타점 분석 실행", key="kr_ai_btn",
                                             use_container_width=True, type="primary"):
                                    st.session_state[_run_key] = selected_code_kr
                                    if _ai_key in st.session_state:
                                        del st.session_state[_ai_key]
                                    st.rerun()

                                # 플래그가 서 있으면 분석 실행
                                if st.session_state.get(_run_key) == selected_code_kr and _ai_key not in st.session_state:
                                    with st.spinner("AI가 수급과 뉴스를 융합 분석 중..."):
                                        try:
                                            from ai_engine import generate_kr_stock_report
                                            inv_for_ai = get_kr_investor_trend(selected_code_kr)
                                            kr_rep = generate_kr_stock_report(
                                                selected_code_kr, price_kr["name"], price_kr, inv_for_ai
                                            )
                                        except Exception as _e:
                                            kr_rep = {
                                                "rating": "분석 실패",
                                                "buy_target": "-", "sell_target": "-", "stop_loss": "-",
                                                "세력분석": "-",
                                                "analysis": f"오류가 발생했습니다: {_e}",
                                            }
                                        st.session_state[_ai_key] = kr_rep
                                        st.session_state[_run_key] = None
                                        try:
                                            from db import log_ai_recommendation
                                            log_ai_recommendation(
                                                "국내주식분석", selected_code_kr, price_kr["name"],
                                                kr_rep.get("rating", "-"), kr_rep.get("buy_target", "-"),
                                                kr_rep.get("sell_target", "-"), kr_rep.get("stop_loss", "-")
                                            )
                                        except Exception:
                                            pass
                                    st.rerun()

                                if _ai_key in st.session_state:
                                    rep_kr = st.session_state[_ai_key]
                                    rating_kr = rep_kr.get("rating", "")
                                    r_emoji = "🟢" if "강력" in rating_kr else "🟡" if "추천" in rating_kr else "🔴"
                                    st.markdown(f"##### {r_emoji} {rating_kr}")
                                    rk1, rk2 = st.columns(2)
                                    rk1.metric("매수 타점", rep_kr.get("buy_target", "-"))
                                    rk2.metric("목표가",    rep_kr.get("sell_target", "-"))
                                    st.metric("손절가",     rep_kr.get("stop_loss", "-"))
                                    if rep_kr.get("세력분석"):
                                        st.info(f"**세력 분석:** {rep_kr['세력분석']}")
                                    if rep_kr.get("analysis"):
                                        with st.container(border=True):
                                            st.markdown(rep_kr["analysis"])
                                else:
                                    st.info("버튼을 눌러 AI 분석을 실행하세요.")

                    else:  # 🔥 오늘의 이슈 섹터
                        from db import load_sector_map, init_sector_sheet
                        from data_kr import get_kr_prices_bulk

                        sector_map = load_sector_map()
                        sector_names = list(sector_map.keys())
                        if st.session_state.kr_selected_sector not in sector_map:
                            st.session_state.kr_selected_sector = sector_names[0]

                        # ── 종목 상세 뷰 (▶ 클릭 후) ──────────────────────────────
                        if st.session_state.kr_sector_view == "detail":
                            detail_code = st.session_state.kr_sector_detail_code
                            detail_name = st.session_state.kr_sector_detail_name

                            if st.button("← 섹터 목록으로", key="sec_back",
                                         use_container_width=True):
                                st.session_state.kr_sector_view = "list"
                                st.rerun()

                            st.markdown(
                                f"<h4 style='margin:4px 0 2px 0'>{detail_name}</h4>"
                                f"<p style='margin:0;font-size:0.78rem;color:#888'>"
                                f"종목코드 {detail_code} · {st.session_state.kr_selected_sector}</p>",
                                unsafe_allow_html=True,
                            )

                            with st.container(height=490):
                                # 시세 카드
                                if price_kr:
                                    chg = price_kr["change_pct"]
                                    pct_col = "#ff4b4b" if chg > 0 else "#2b7cff" if chg < 0 else "#888"
                                    with st.container(border=True):
                                        m1, m2, m3 = st.columns(3)
                                        m1.metric("현재가", f"₩{price_kr['price']:,}",
                                                  f"{arrow} {abs(price_kr['change']):,}원 ({chg:+.2f}%)",
                                                  delta_color=d_color)
                                        m2.metric("거래량", f"{price_kr['volume']:,}주")
                                        m3.metric("거래대금",
                                                  f"₩{price_kr['amount']//100000000:,}억"
                                                  if price_kr["amount"] > 0 else "-")
                                        n1, n2, n3 = st.columns(3)
                                        n1.metric("고가", f"₩{price_kr['high']:,}")
                                        n2.metric("저가", f"₩{price_kr['low']:,}")
                                        n3.metric("PER", price_kr["per"])

                                    # 단타 적합성 판단 (기준: 3% 이상 상승)
                                    st.markdown("#### 🎯 단타 적합성 판단")
                                    if chg >= 5.0:
                                        st.success(
                                            f"✅ **강력 단타 추천** — 등락률 **{chg:+.2f}%**\n\n"
                                            "5% 이상 강한 상승 모멘텀. 세력/기관 유입 가능성 높음.\n"
                                            "단, 고점 추격 매수는 주의 — 눌림목 진입 우선 고려."
                                        )
                                    elif chg >= 3.0:
                                        st.success(
                                            f"✅ **단타 추천** — 등락률 **{chg:+.2f}%**\n\n"
                                            "3% 이상 모멘텀 확인. 수급 확인 후 진입 권장.\n"
                                            "손절가: 당일 저점 / 목표: +3~5% 추가 수익 구간."
                                        )
                                    elif chg >= 1.5:
                                        st.warning(
                                            f"⚠️ **관망** — 등락률 {chg:+.2f}%\n\n"
                                            "모멘텀 발생 초기 단계. 3% 돌파 확인 후 진입 검토.\n"
                                            "수수료(0.015~0.3%) 감안 시 최소 3% 이상 수익 목표 필요."
                                        )
                                    elif chg <= -3.0:
                                        st.info(
                                            f"🔵 **반등 포착 관찰** — 등락률 {chg:+.2f}%\n\n"
                                            "급락 후 반등 매매 고려 가능 (역발상 단타).\n"
                                            "지지선·거래량 급증 확인 필수. 고위험 전략."
                                        )
                                    else:
                                        st.error(
                                            f"❌ **단타 비적합** — 등락률 {chg:+.2f}%\n\n"
                                            "3% 미만 변동은 수수료·세금 차감 후 실익 없음.\n"
                                            "모멘텀 발생 시 재검토 권장."
                                        )

                                # 외국인/기관 수급
                                st.markdown("#### 💰 외국인/기관 수급")
                                with st.spinner("수급 조회 중..."):
                                    investor_detail = get_kr_investor_trend(detail_code)
                                if investor_detail:
                                    df_inv_d = pd.DataFrame(investor_detail)
                                    fig_inv_d = go.Figure()
                                    for _cn, _cc in [("외국인","#ff4b4b"),("기관","#2b7cff"),("개인","#888")]:
                                        fig_inv_d.add_trace(go.Bar(
                                            name=_cn, x=df_inv_d["날짜"], y=df_inv_d[_cn],
                                            marker_color=_cc
                                        ))
                                    fig_inv_d.update_layout(
                                        barmode="group",
                                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                        font=dict(color="white"), legend=dict(orientation="h"),
                                        xaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
                                        yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="순매수(주)"),
                                        margin=dict(l=10,r=10,t=10,b=10), height=170
                                    )
                                    st.plotly_chart(fig_inv_d, use_container_width=True)
                                    _lat = investor_detail[0]
                                    st.markdown(
                                        f"외국인 {'🔴' if _lat['외국인']>0 else '🔵'} {_lat['외국인']:+,}주 | "
                                        f"기관 {'🔴' if _lat['기관']>0 else '🔵'} {_lat['기관']:+,}주"
                                    )
                                else:
                                    st.info("수급 데이터를 불러올 수 없습니다.")

                                # AI 심층 분석
                                st.markdown("#### 🧠 AI 단타 심층 분석")
                                if st.button("🎯 AI 단타 분석 실행", type="primary",
                                             use_container_width=True, key="sec_detail_ai"):
                                    with st.spinner("AI가 수급·뉴스·차트를 융합 분석 중..."):
                                        from ai_engine import generate_kr_stock_report
                                        _inv_ai = get_kr_investor_trend(detail_code)
                                        _rep = generate_kr_stock_report(
                                            detail_code, detail_name,
                                            price_kr or {}, _inv_ai
                                        )
                                        st.session_state[f"sec_rep_{detail_code}"] = _rep
                                        from db import log_ai_recommendation
                                        log_ai_recommendation(
                                            "섹터단타분석", detail_code, detail_name,
                                            _rep.get("rating","-"), _rep.get("buy_target","-"),
                                            _rep.get("sell_target","-"), _rep.get("stop_loss","-")
                                        )

                                if f"sec_rep_{detail_code}" in st.session_state:
                                    _r = st.session_state[f"sec_rep_{detail_code}"]
                                    _rtg = _r.get("rating","")
                                    _re = "🟢" if "강력" in _rtg else "🟡" if "추천" in _rtg else "🔴"
                                    st.markdown(f"##### {_re} {_rtg}")
                                    _rk1, _rk2 = st.columns(2)
                                    _rk1.metric("매수 타점", _r.get("buy_target","-"))
                                    _rk2.metric("목표가",    _r.get("sell_target","-"))
                                    st.metric("손절가", _r.get("stop_loss","-"))
                                    if _r.get("세력분석"):
                                        st.info(f"**세력 분석:** {_r['세력분석']}")
                                    if _r.get("analysis"):
                                        st.markdown("---")
                                        with st.container(border=True):
                                            st.markdown(_r["analysis"])

                        # ── 섹터 목록 뷰 (기본) ───────────────────────────────────
                        else:
                            st.markdown("### 🔥 이슈 섹터")

                            # 탭 토글: AI 시장분석 / 전체탐색
                            if "kr_sector_panel_tab" not in st.session_state:
                                st.session_state.kr_sector_panel_tab = "📊 AI 시장분석"
                            _spt_tabs = ["📊 AI 시장분석", "📚 전체 섹터 탐색"]
                            _stc1, _stc2 = st.columns(2)
                            for _stcol, _stn in [(_stc1, _spt_tabs[0]), (_stc2, _spt_tabs[1])]:
                                if _stcol.button(
                                    _stn, key=f"spt_{_stn}",
                                    type="primary" if st.session_state.kr_sector_panel_tab == _stn else "secondary",
                                    use_container_width=True,
                                ):
                                    st.session_state.kr_sector_panel_tab = _stn
                                    st.rerun()

                            # ── AI 시장분석 탭 (거래량 + 급등주 + 핫섹터 통합) ──
                            if st.session_state.kr_sector_panel_tab == _spt_tabs[0]:
                                from ai_engine import analyze_today_market, analyze_kr_hot_sectors

                                _am_hdr, _am_ref = st.columns([8, 1])
                                _am_hdr.markdown(
                                    "<p style='font-size:0.75rem;color:#888;margin:4px 0'>거래량 TOP10 · 급등 종목 이유 · AI 핫 섹터 통합</p>",
                                    unsafe_allow_html=True,
                                )
                                if st.session_state.kr_ai_market_run:
                                    if _am_ref.button("🔄", key="ai_mkt_refresh", help="전체 재분석"):
                                        try: analyze_today_market.clear()
                                        except: pass
                                        try: analyze_kr_hot_sectors.clear()
                                        except: pass
                                        get_kr_volume_ranking.clear()
                                        st.rerun()

                                if not st.session_state.kr_ai_market_run:
                                    st.markdown(
                                        "<div style='text-align:center;padding:40px 20px'>"
                                        "<p style='color:#888;font-size:0.85rem;margin-bottom:16px'>"
                                        "거래량 TOP10, 급등 종목 이유 분석, AI 핫 섹터를 한번에 확인합니다</p>"
                                        "</div>",
                                        unsafe_allow_html=True,
                                    )
                                    if st.button("🤖 AI 시장분석 실행", use_container_width=True,
                                                 type="primary", key="run_ai_market"):
                                        st.session_state.kr_ai_market_run = True
                                        st.rerun()
                                else:
                                    with st.spinner("📊 시장 데이터 불러오는 중..."):
                                        _tm       = analyze_today_market()
                                        _ai_res   = analyze_kr_hot_sectors()
                                        _vol_rank = get_kr_volume_ranking()

                                    _quota_err = (
                                        (isinstance(_tm, dict) and _tm.get("error") == "QUOTA") or
                                        (isinstance(_ai_res, dict) and _ai_res.get("error") == "QUOTA")
                                    )
                                    if _quota_err:
                                        st.warning(
                                            "⚠️ **Gemini API 무료 할당량 초과**\n\n"
                                            "오늘의 AI 분석 횟수가 모두 소진되었습니다.  \n"
                                            "• 내일 자정(KST) 자동 초기화  \n"
                                            "• 즉시 해결: [Google AI Studio](https://aistudio.google.com) 에서 유료 전환 (월 $10 미만)"
                                        )
                                    elif isinstance(_tm, dict) and _tm.get("error"):
                                        st.info(f"⏸ {_tm['error']}")

                                    # 시장 요약 배너
                                    if isinstance(_tm, dict) and _tm.get("market_summary"):
                                        st.markdown(
                                            f"<div style='background:rgba(255,255,255,0.04);border-left:3px solid #ff9800;"
                                            f"padding:8px 12px;border-radius:4px;margin-bottom:8px'>"
                                            f"<span style='font-size:0.72rem;color:#ff9800;font-weight:700'>📌 오늘 시장 요약</span><br>"
                                            f"<span style='font-size:0.73rem;color:#ccc'>{_tm['market_summary']}</span>"
                                            f"</div>",
                                            unsafe_allow_html=True,
                                        )

                                    # 주도 테마 태그
                                    _themes = _tm.get("leading_themes", []) if isinstance(_tm, dict) else []
                                    _top_th = _tm.get("top_theme", "") if isinstance(_tm, dict) else ""
                                    if _themes:
                                        _theme_html = " ".join(
                                            f"<span style='background:rgba(255,75,75,0.2);border:1px solid #ff4b4b;"
                                            f"border-radius:12px;padding:2px 8px;font-size:0.68rem;color:#ff4b4b;"
                                            f"font-weight:700'>{t}</span>"
                                            if t == _top_th else
                                            f"<span style='background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.15);"
                                            f"border-radius:12px;padding:2px 8px;font-size:0.68rem;color:#aaa'>{t}</span>"
                                            for t in _themes
                                        )
                                        st.markdown(
                                            f"<div style='margin-bottom:8px'>🔥 주도 테마: {_theme_html}</div>",
                                            unsafe_allow_html=True,
                                        )

                                    # ── 거래량 TOP 10 ─────────────────────────────
                                    st.markdown(
                                        "<p style='font-size:0.78rem;font-weight:700;color:#aaa;margin:6px 0 4px 0'>📊 거래량 TOP 10</p>",
                                        unsafe_allow_html=True,
                                    )
                                    if _vol_rank:
                                        _df_vol = pd.DataFrame(_vol_rank)

                                        def _color_vol(val):
                                            if isinstance(val, (int, float)):
                                                if val > 0: return "color: #ff4b4b; font-weight: bold"
                                                if val < 0: return "color: #2b7cff; font-weight: bold"
                                            return ""

                                        st.dataframe(
                                            _df_vol.style.map(_color_vol, subset=["등락률(%)"]),
                                            use_container_width=True, hide_index=True, height=220,
                                        )
                                    else:
                                        st.caption("거래량 데이터를 불러올 수 없습니다.")

                                    st.markdown("<hr style='margin:8px 0;border:none;border-top:1px solid rgba(255,255,255,0.07)'>", unsafe_allow_html=True)

                                    # ── 오늘의 급등 종목 ──────────────────────────
                                    st.markdown(
                                        "<p style='font-size:0.78rem;font-weight:700;color:#aaa;margin:4px 0'>📈 오늘의 급등 종목</p>",
                                        unsafe_allow_html=True,
                                    )
                                    if isinstance(_tm, dict) and not _tm.get("error") and _tm.get("stocks"):
                                        with st.container(height=320):
                                            for _si, _stk in enumerate(_tm.get("stocks", [])):
                                                _cpct = _stk.get("change_pct", 0) or 0
                                                _col  = "#ff4b4b" if _cpct > 0 else "#2b7cff"
                                                _mkt  = _stk.get("market", "")
                                                _thm  = _stk.get("theme", "")
                                                _rsn  = _stk.get("reason", "")
                                                _nm   = _stk.get("name", "")
                                                _cd   = _stk.get("code", "")

                                                with st.container(border=True):
                                                    _r1c1, _r1c2, _r1c3 = st.columns([4, 2, 1.2])
                                                    _r1c1.markdown(
                                                        f"<span style='font-size:0.88rem;font-weight:700'>{_nm}</span>"
                                                        f"<span style='font-size:0.68rem;color:#888;margin-left:6px'>{_mkt}</span>",
                                                        unsafe_allow_html=True,
                                                    )
                                                    _r1c2.markdown(
                                                        f"<span style='font-size:0.82rem;color:#888'>{_cd}</span>",
                                                        unsafe_allow_html=True,
                                                    )
                                                    _r1c3.markdown(
                                                        f"<span style='font-size:0.88rem;font-weight:700;color:{_col}'>{_cpct:+.1f}%</span>",
                                                        unsafe_allow_html=True,
                                                    )
                                                    if _thm:
                                                        st.markdown(
                                                            f"<span style='font-size:0.67rem;background:rgba(255,152,0,0.15);"
                                                            f"border-radius:10px;padding:1px 7px;color:#ff9800'>#{_thm}</span>",
                                                            unsafe_allow_html=True,
                                                        )
                                                    if _rsn:
                                                        st.markdown(
                                                            f"<p style='font-size:0.73rem;color:#bbb;margin:3px 0 0 0'>{_rsn}</p>",
                                                            unsafe_allow_html=True,
                                                        )
                                                    if _cd and st.button("▶ 차트", key=f"tm_cd_{_cd}_{_si}"):
                                                        st.session_state.kr_selected_code      = _cd
                                                        st.session_state.kr_selected_name      = _nm
                                                        st.session_state.kr_sector_detail_code = _cd
                                                        st.session_state.kr_sector_detail_name = _nm
                                                        st.session_state.kr_sector_view        = "detail"
                                                        st.session_state.kr_mode               = "📊 일반 주식 검색"
                                                        st.rerun()
                                    elif not _quota_err:
                                        st.caption("급등 종목 데이터를 불러올 수 없습니다.")

                                    st.markdown("<hr style='margin:8px 0;border:none;border-top:1px solid rgba(255,255,255,0.07)'>", unsafe_allow_html=True)

                                    # ── AI 핫 섹터 ───────────────────────────────
                                    st.markdown(
                                        "<p style='font-size:0.78rem;font-weight:700;color:#aaa;margin:4px 0'>🔥 AI 핫 섹터</p>",
                                        unsafe_allow_html=True,
                                    )
                                    if isinstance(_ai_res, dict) and not _ai_res.get("error") and _ai_res.get("sectors"):
                                        _ai_sectors = sorted(
                                            _ai_res.get("sectors", []),
                                            key=lambda x: -x.get("hot_score", 0),
                                        )
                                        _ai_sector_db = load_sector_map()

                                        _all_ai_tickers: list = []
                                        _ai_code_suffix: dict = {}
                                        for _as in _ai_sectors:
                                            _kw_pre = _as.get("keyword", "")
                                            _hot_codes_pre = _as.get("hot_codes", [])
                                            _all_sec_stocks = []
                                            for _sub_stks in _ai_sector_db.get(_kw_pre, {}).values():
                                                _all_sec_stocks.extend(_sub_stks)
                                            _display_pre = [s for s in _all_sec_stocks if not _hot_codes_pre or s["code"] in _hot_codes_pre]
                                            if not _display_pre:
                                                _display_pre = _all_sec_stocks[:10]
                                            for _ds in _display_pre[:10]:
                                                if _ds["code"] not in _ai_code_suffix:
                                                    _ai_code_suffix[_ds["code"]] = _ds["suffix"]
                                                    _all_ai_tickers.append((_ds["code"], _ds["code"] + _ds["suffix"]))
                                        with st.spinner(""):
                                            _ai_prices = get_kr_prices_bulk(tuple(_all_ai_tickers)) if _all_ai_tickers else {}

                                        # 신규 이슈 섹터 요약 패널
                                        _new_sec_list = [
                                            s for s in _ai_sectors
                                            if not any(_ai_sector_db.get(s.get("keyword", ""), {}).values())
                                        ]
                                        _all_dyn_subs = [
                                            (s.get("keyword", ""), ds)
                                            for s in _ai_sectors
                                            for ds in s.get("dynamic_subsectors", [])
                                        ]
                                        if _new_sec_list or _all_dyn_subs:
                                            st.markdown(
                                                "<p style='font-size:0.78rem;font-weight:700;color:#4caf50;margin:8px 0 4px 0'>"
                                                "⚡ 오늘의 신규 이슈 감지</p>",
                                                unsafe_allow_html=True,
                                            )
                                            _iss_cols = st.columns(min(len(_new_sec_list) + len(_all_dyn_subs), 4))
                                            _iss_idx = 0
                                            for _nsl in _new_sec_list:
                                                if _iss_idx < len(_iss_cols):
                                                    _iss_cols[_iss_idx].markdown(
                                                        f"<div style='background:rgba(76,175,80,0.1);border:1px solid #4caf50;"
                                                        f"border-radius:8px;padding:6px 10px;margin:2px 0'>"
                                                        f"<span style='font-size:0.72rem;font-weight:700;color:#4caf50'>🆕 {_nsl['keyword']}</span><br>"
                                                        f"<span style='font-size:0.68rem;color:#aaa'>{_nsl.get('reason','')[:50]}...</span>"
                                                        f"</div>",
                                                        unsafe_allow_html=True,
                                                    )
                                                    _iss_idx += 1
                                            for _par, _ds in _all_dyn_subs:
                                                if _iss_idx < len(_iss_cols):
                                                    _iss_cols[_iss_idx].markdown(
                                                        f"<div style='background:rgba(255,152,0,0.1);border:1px solid #ff9800;"
                                                        f"border-radius:8px;padding:6px 10px;margin:2px 0'>"
                                                        f"<span style='font-size:0.72rem;font-weight:700;color:#ff9800'>📡 {_ds['name']}</span><br>"
                                                        f"<span style='font-size:0.68rem;color:#aaa'>{_par} › {_ds.get('reason','')[:40]}...</span>"
                                                        f"</div>",
                                                        unsafe_allow_html=True,
                                                    )
                                                    _iss_idx += 1
                                            st.markdown("<hr style='margin:6px 0;border:none;border-top:1px solid rgba(255,255,255,0.07)'>", unsafe_allow_html=True)

                                        # 역사적 패턴 분석 결과 패널
                                        _pat_kw = st.session_state.get("ai_pattern_kw", "")
                                        if _pat_kw:
                                            from ai_engine import analyze_market_pattern
                                            with st.spinner(f"🔍 {_pat_kw} 역사적 패턴 분석 중..."):
                                                _pat_data = analyze_market_pattern(_pat_kw)
                                            with st.container(border=True):
                                                _pcol1, _pcol2 = st.columns([9, 1])
                                                _pcol1.markdown(
                                                    f"<p style='font-size:0.82rem;font-weight:700;color:#64b5f6;margin:0'>📊 {_pat_kw} — 역사적 패턴 분석</p>",
                                                    unsafe_allow_html=True,
                                                )
                                                if _pcol2.button("✕", key="pat_close"):
                                                    st.session_state["ai_pattern_kw"] = ""
                                                    st.rerun()
                                                if "error" in _pat_data:
                                                    st.error(f"패턴 분석 오류: {_pat_data['error']}")
                                                else:
                                                    for _hp in _pat_data.get("historical_patterns", []):
                                                        st.markdown(
                                                            f"**📅 {_hp.get('period','')}** — {_hp.get('trigger','')}  \n"
                                                            f"{_hp.get('what_happened','')} *({_hp.get('duration','')})*"
                                                        )
                                                    if _pat_data.get("current_similarity"):
                                                        st.markdown(f"**🔗 현재 유사도**: {_pat_data['current_similarity']}")
                                                    if _pat_data.get("prediction"):
                                                        st.markdown(
                                                            f"<div style='background:rgba(100,181,246,0.08);border-left:3px solid #64b5f6;"
                                                            f"padding:6px 10px;border-radius:4px;margin:4px 0'>"
                                                            f"<span style='font-size:0.78rem;color:#64b5f6;font-weight:700'>🎯 예측</span><br>"
                                                            f"<span style='font-size:0.75rem;color:#ccc'>{_pat_data['prediction']}</span>"
                                                            f"</div>",
                                                            unsafe_allow_html=True,
                                                        )
                                                    if _pat_data.get("risk_factors"):
                                                        st.markdown(f"**⚠️ 리스크**: {_pat_data['risk_factors']}")
                                                    _watch = _pat_data.get("key_stocks_to_watch", [])
                                                    if _watch:
                                                        st.markdown("**👀 주목 종목**: " + " · ".join(_watch))
                                            st.markdown("")

                                        with st.container(height=460):
                                            for _asi, _as in enumerate(_ai_sectors):
                                                _kw        = _as.get("keyword", "")
                                                _score     = _as.get("hot_score", 0)
                                                _reason    = _as.get("reason", "")
                                                _news      = _as.get("news_title", "")
                                                _hot_codes = _as.get("hot_codes", [])
                                                _all_sec   = []
                                                for _sub_stks in _ai_sector_db.get(_kw, {}).values():
                                                    _all_sec.extend(_sub_stks)
                                                _display = [s for s in _all_sec if not _hot_codes or s["code"] in _hot_codes]
                                                if not _display:
                                                    _display = _all_sec[:10]
                                                _is_new_sector = len(_all_sec) == 0

                                                with st.container(border=True):
                                                    _fire = "🔥" * max(1, min(int(_score / 2.5), 4))
                                                    _new_badge = " <span style='font-size:0.65rem;color:#4caf50;border:1px solid #4caf50;border-radius:3px;padding:1px 4px'>NEW</span>" if _is_new_sector else ""
                                                    st.markdown(
                                                        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:2px'>"
                                                        f"<span style='font-size:0.9rem;font-weight:700'>{_kw}{_new_badge}</span>"
                                                        f"<span style='font-size:0.78rem;color:#ff9800'>{_fire} {_score}/10</span>"
                                                        f"</div>",
                                                        unsafe_allow_html=True,
                                                    )
                                                    if _reason:
                                                        st.markdown(
                                                            f"<p style='font-size:0.73rem;color:#aaa;margin:0 0 2px 0'>{_reason}</p>",
                                                            unsafe_allow_html=True,
                                                        )
                                                    if _news:
                                                        st.markdown(
                                                            f"<p style='font-size:0.7rem;color:#777;margin:0 0 5px 0'>📰 {_news}</p>",
                                                            unsafe_allow_html=True,
                                                        )

                                                    for _si, _stk in enumerate(_display[:10]):
                                                        if _si > 0:
                                                            st.markdown(
                                                                '<hr style="margin:1px 0;border:none;border-top:1px solid rgba(255,255,255,0.07)">',
                                                                unsafe_allow_html=True,
                                                            )
                                                        _pd  = _ai_prices.get(_stk["code"], {"price": 0, "change_pct": 0.0})
                                                        _pct = _pd["change_pct"]
                                                        _pv  = _pd["price"]
                                                        _pc  = "#ff4b4b" if _pct > 0 else "#2b7cff" if _pct < 0 else "#888"
                                                        _badge = "🔑 " if _stk.get("r") == "core" else ""
                                                        _bc0, _bc1, _bc2, _bc3, _bc4 = st.columns([0.3, 2.6, 1.8, 1.4, 0.45])
                                                        _bc0.markdown("✅" if _pct >= 3.0 else "&nbsp;", unsafe_allow_html=True)
                                                        _bc1.markdown(f"<span style='font-size:0.82rem'>{_badge}{_stk['name']}</span>", unsafe_allow_html=True)
                                                        _bc2.markdown(f"<span style='font-size:0.82rem'>{'₩'+format(_pv,',') if _pv>0 else '---'}</span>", unsafe_allow_html=True)
                                                        _bc3.markdown(f"<span style='font-size:0.82rem;font-weight:bold;color:{_pc}'>{_pct:+.2f}%</span>", unsafe_allow_html=True)
                                                        if _bc4.button("▶", key=f"ai_s_{_stk['code']}_{_kw[:6]}_{_si}"):
                                                            st.session_state.kr_selected_code       = _stk["code"]
                                                            st.session_state.kr_selected_name       = _stk["name"]
                                                            st.session_state.kr_sector_detail_code  = _stk["code"]
                                                            st.session_state.kr_sector_detail_name  = _stk["name"]
                                                            st.session_state.kr_sector_view         = "detail"
                                                            st.rerun()

                                                    for _ns in _as.get("new_stocks", [])[:2]:
                                                        st.markdown(
                                                            f"<span class='sector-pill'>🤖 {_ns.get('name','')} — {_ns.get('reason','')}</span>",
                                                            unsafe_allow_html=True,
                                                        )

                                                    _dyn_subs = _as.get("dynamic_subsectors", [])
                                                    if _dyn_subs:
                                                        st.markdown(
                                                            "<hr style='margin:4px 0;border:none;border-top:1px solid rgba(255,152,0,0.2)'>",
                                                            unsafe_allow_html=True,
                                                        )
                                                    for _dys in _dyn_subs:
                                                        st.markdown(
                                                            f"<div style='padding:4px 8px;background:rgba(255,152,0,0.07);"
                                                            f"border-left:2px solid #ff9800;border-radius:0 4px 4px 0;margin:2px 0'>"
                                                            f"<span style='font-size:0.72rem;color:#ff9800;font-weight:700'>📡 {_dys['name']}</span>"
                                                            f"<span style='font-size:0.68rem;color:#aaa;margin-left:8px'>{_dys.get('reason','')}</span>"
                                                            f"</div>",
                                                            unsafe_allow_html=True,
                                                        )
                                                        for _dns in _dys.get("new_stocks", [])[:2]:
                                                            st.markdown(
                                                                f"<span class='sector-pill' style='font-size:0.67rem'>↳ {_dns.get('name','')} — {_dns.get('reason','')}</span>",
                                                                unsafe_allow_html=True,
                                                            )

                                                    if st.button("📊 역사적 패턴", key=f"pat_btn_{_asi}", help=f"{_kw} 섹터 과거 패턴 기반 미래 예측"):
                                                        st.session_state["ai_pattern_kw"] = _kw
                                                        st.rerun()
                                    elif not _quota_err:
                                        st.caption("섹터 데이터를 불러올 수 없습니다.")


                            # ── 전체 섹터 탐색 탭 ──────────────────────────────
                            elif st.session_state.kr_sector_panel_tab == _spt_tabs[1]:
                                hdr2_c1, hdr2_c2 = st.columns([8, 1])
                                if hdr2_c2.button("🔄", key="sec_refresh",
                                                  help="섹터 캐시 초기화"):
                                    load_sector_map.clear()
                                    st.rerun()

                                # 섹터 선택 드롭다운
                                _cur_idx = sector_names.index(st.session_state.kr_selected_sector) \
                                    if st.session_state.kr_selected_sector in sector_names else 0
                                _sel_sector = st.selectbox(
                                    "섹터 선택",
                                    sector_names,
                                    index=_cur_idx,
                                    key="kr_sector_selectbox",
                                    label_visibility="collapsed",
                                )
                                if _sel_sector != st.session_state.kr_selected_sector:
                                    st.session_state.kr_selected_sector = _sel_sector
                                    st.rerun()

                                selected_sector = st.session_state.kr_selected_sector
                                subsectors = sector_map[selected_sector]

                                # 다중 섹터 위치 계산
                                code_locations: dict = {}
                                for sec, subs in sector_map.items():
                                    for sub, stklist in subs.items():
                                        for s in stklist:
                                            code_locations.setdefault(s["code"], []).append(f"{sec} › {sub}")

                                seen_codes: set = set()
                                unique_tickers = []
                                for sub_stocks in subsectors.values():
                                    for s in sub_stocks:
                                        if s["code"] not in seen_codes:
                                            seen_codes.add(s["code"])
                                            unique_tickers.append((s["code"], s["code"] + s["suffix"]))

                                _n_stocks = len(unique_tickers)
                                _est_sec  = max(3, min(_n_stocks // 8, 20))
                                _load_ph  = st.empty()
                                _load_ph.markdown(
                                    f"""<div style='display:flex;flex-direction:column;align-items:center;
                                        justify-content:center;padding:48px 0;gap:14px;'>
                                      <div style='font-size:2rem;animation:spin 1s linear infinite'>⏳</div>
                                      <div style='font-size:1rem;font-weight:600;color:#ccc'>
                                        시세 조회 중 ({_n_stocks}개 종목)</div>
                                      <div style='font-size:0.82rem;color:#888'>
                                        약 {_est_sec}초 소요</div>
                                    </div>
                                    <style>@keyframes spin{{
                                      0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}}
                                    }}</style>""",
                                    unsafe_allow_html=True,
                                )
                                prices = get_kr_prices_bulk(tuple(unique_tickers))
                                _load_ph.empty()

                                _hcols = st.columns([0.35, 2.8, 1.8, 1.4, 0.45])
                                for _hc, _ht in zip(_hcols[:4], ["단타", "종목명", "현재가", "등락률"]):
                                    _hc.markdown(f"<p style='margin:0;font-size:0.72rem;color:#888'>{_ht}</p>", unsafe_allow_html=True)

                                def _render_sector_stocks(sub_name, stocks, prices, code_locations, selected_sector):
                                    for i, s in enumerate(stocks):
                                        if i > 0:
                                            st.markdown('<hr style="margin:2px 0;border:none;border-top:1px solid rgba(255,255,255,0.1)">', unsafe_allow_html=True)
                                        pdata = prices.get(s["code"], {"price": 0, "change_pct": 0.0})
                                        pct   = pdata["change_pct"]
                                        pval  = pdata["price"]
                                        pct_color = "#ff4b4b" if pct > 0 else "#2b7cff" if pct < 0 else "#888"
                                        other_locs = [loc for loc in code_locations.get(s["code"], []) if loc != f"{selected_sector} › {sub_name}"]
                                        help_text = f"다중 섹터: {', '.join(other_locs)}" if other_locs else None
                                        c0, c1, c2, c3, c4 = st.columns([0.35, 2.8, 1.8, 1.4, 0.45])
                                        c0.markdown("✅" if pct >= 3.0 else "&nbsp;", unsafe_allow_html=True)
                                        name_html = (
                                            f"<span style='font-size:0.85rem'>{s['name']}</span>"
                                            + (f"<span style='font-size:0.7rem;color:#666'> 🔗</span>" if other_locs else "")
                                        )
                                        c1.markdown(name_html, unsafe_allow_html=True)
                                        c2.markdown(f"<span style='font-size:0.85rem'>{'₩'+format(pval,',') if pval>0 else '---'}</span>", unsafe_allow_html=True)
                                        c3.markdown(f"<span style='font-size:0.85rem;font-weight:bold;color:{pct_color}'>{pct:+.2f}%</span>", unsafe_allow_html=True)
                                        if c4.button("▶", key=f"stock_{s['code']}_{sub_name}_{i}",
                                                     use_container_width=True):
                                            st.session_state.kr_selected_code      = s["code"]
                                            st.session_state.kr_selected_name      = s["name"]
                                            st.session_state.kr_sector_detail_code = s["code"]
                                            st.session_state.kr_sector_detail_name = s["name"]
                                            st.session_state.kr_sector_view        = "detail"
                                            st.rerun()

                                def _sub_avg_pct(stocks, prices):
                                    vals = [prices.get(s["code"], {}).get("change_pct", 0.0) for s in stocks]
                                    vals = [v for v in vals if v != 0.0]
                                    return sum(vals) / len(vals) if vals else 0.0

                                def _sub_ai_summary(parent_sector, sub_name, avg_pct, stocks, prices):
                                    from ai_engine import _call_gemini
                                    import datetime
                                    # 등락률 있는 종목만 추출, 없으면 전체 이름 사용
                                    all_names = [s["name"] for s in stocks]
                                    with_pct = sorted(
                                        [(s["name"], prices.get(s["code"], {}).get("change_pct", 0.0))
                                         for s in stocks if prices.get(s["code"], {}).get("change_pct", 0.0) != 0.0],
                                        key=lambda x: abs(x[1]), reverse=True
                                    )
                                    stock_detail = ", ".join(f"{n}({p:+.1f}%)" for n, p in with_pct[:8])
                                    if not stock_detail:
                                        stock_detail = ", ".join(all_names[:8])
                                    prompt = (
                                        f"오늘({datetime.date.today()}) 한국 증시 분석 요청.\n"
                                        f"분석 범위: '{parent_sector}' 섹터 내 '{sub_name}' 세부섹터 ({len(stocks)}개 종목)\n"
                                        f"해당 세부섹터 종목: {stock_detail}\n"
                                        f"세부섹터 평균 등락률: {avg_pct:+.2f}%\n\n"
                                        f"위 {len(stocks)}개 종목으로 구성된 '{sub_name}' 세부섹터만을 대상으로, "
                                        f"오늘 이 종목들이 이렇게 움직이는 이유를 뉴스·공시·시장 흐름 기반으로 "
                                        f"3~5줄 이내로 간결하게 요약해주세요. 이모지 없이 핵심만."
                                    )
                                    try:
                                        resp = _call_gemini(prompt, use_search=True, temperature=0.4)
                                        return resp.text.strip() if resp and resp.text else "분석 정보 없음"
                                    except Exception:
                                        return "AI 분석을 불러올 수 없습니다."

                                with st.container(height=600):
                                    for sub_name, stocks in subsectors.items():
                                        avg_pct = _sub_avg_pct(stocks, prices)
                                        pct_color = "#ff4b4b" if avg_pct > 0 else "#2b7cff" if avg_pct < 0 else "#888"
                                        tok = f"_sub_open_{selected_sector}__{sub_name}"
                                        if tok not in st.session_state:
                                            st.session_state[tok] = False
                                        is_open = st.session_state[tok]

                                        with st.container(border=True):
                                            # ── 헤더 행: 항상 표시 (접힌 상태에서도 색상 있는 평균 등락률 노출) ──
                                            h0, h1, h2, h3, h4 = st.columns([0.35, 2.8, 1.8, 1.4, 0.45])
                                            tog_label = "▼" if is_open else "▶"
                                            if h0.button(tog_label, key=f"tog_{sub_name}", use_container_width=True):
                                                st.session_state[tok] = not is_open
                                                st.rerun()
                                            h1.markdown(
                                                f"<span style='font-size:0.85rem;font-weight:600'>📌 {sub_name}</span>"
                                                f"<span style='font-size:0.75rem;color:#888'>　{len(stocks)}개</span>",
                                                unsafe_allow_html=True,
                                            )
                                            # 현재가 컬럼(h2)은 비워둠
                                            h3.markdown(
                                                f"<span style='font-size:0.92rem;font-weight:700;color:{pct_color}'>{avg_pct:+.2f}%</span>",
                                                unsafe_allow_html=True,
                                            )
                                            ai_key = f"_sub_ai_{selected_sector}__{sub_name}"
                                            if h4.button("AI", key=f"ai_btn_{sub_name}", help="AI 섹터 분석"):
                                                st.session_state[ai_key] = _sub_ai_summary(selected_sector, sub_name, avg_pct, stocks, prices)

                                            # ── 펼쳐진 내용 ──
                                            if is_open:
                                                if ai_key in st.session_state:
                                                    st.markdown(
                                                        f"<div style='background:rgba(255,255,255,0.05);border-left:3px solid {pct_color};"
                                                        f"border-radius:6px;padding:8px 12px;margin:4px 0 8px 0;"
                                                        f"font-size:0.82rem;line-height:1.55;color:#ddd'>"
                                                        f"{st.session_state[ai_key]}</div>",
                                                        unsafe_allow_html=True,
                                                    )
                                                st.markdown('<hr style="margin:4px 0 6px 0;border:none;border-top:1px solid rgba(255,255,255,0.15)">', unsafe_allow_html=True)
                                                _render_sector_stocks(sub_name, stocks, prices, code_locations, selected_sector)




        else:
            # ── 미국 시장 지수 배너 (Toss 스타일) ──────────────────────────
            with st.spinner(""):
                us_indices = get_us_market_indices()

            _us_banner = []
            for _in in ["S&P500", "NASDAQ", "DOW"]:
                _id  = (us_indices or {}).get(_in, {})
                _iv  = _id.get("price", 0)
                _ic  = _id.get("change", 0)
                _ip  = _id.get("change_pct", 0)
                _col = "#00c853" if _ic >= 0 else "#ff4b4b"
                _sg  = "+" if _ic >= 0 else ""
                if _iv > 0:
                    _us_banner.append(
                        f"<div class='index-item'>"
                        f"<span class='index-name'>{_in}</span>"
                        f"<span class='index-val' style='color:{_col}'>{_iv:,.2f}</span>"
                        f"<span class='index-chg' style='color:{_col}'>{_sg}{_ic:.2f} ({_sg}{_ip:.2f}%)</span>"
                        f"</div>"
                    )
            if _us_banner:
                st.markdown(
                    f"<div class='index-banner'>{''.join(_us_banner)}</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("<hr class='toss-divider'>", unsafe_allow_html=True)

            # ── 세션 상태 초기화 ──────────────────────────────────────────
            for _k, _v in [
                ("us_mode",               "📊 일반 주식 검색"),
                ("us_selected_ticker",    "NVDA"),
                ("us_selected_name",      "엔비디아"),
                ("us_selected_sector_us", "AI·반도체"),
                ("us_sector_view",        "list"),
                ("us_sector_detail_ticker",   ""),
                ("us_sector_detail_name",     ""),
                ("us_sector_detail_exchange", "NASDAQ"),
                ("us_tv_interval",   "15"),
                ("us_right_tab",     "📊 시세"),
                ("us_ai_market_run", False),
                ("us_sector_panel_tab", "📊 AI 시장분석"),
                ("us_index_tab",     "S&P500"),
            ]:
                if _k not in st.session_state:
                    st.session_state[_k] = _v

            # ── 모드 토글 ─────────────────────────────────────────────────
            _us_modes = ["📊 일반 주식 검색", "🔥 오늘의 이슈 섹터"]
            _us_idx = _us_modes.index(st.session_state.us_mode) if st.session_state.us_mode in _us_modes else 0
            us_mode = st.radio(
                "US 모드 선택", _us_modes,
                horizontal=True, label_visibility="collapsed", index=_us_idx,
            )
            if us_mode != st.session_state.us_mode:
                st.session_state.us_mode = us_mode
                st.rerun()

            _us_ticker_cur = st.session_state.us_selected_ticker
            _us_name_cur   = st.session_state.us_selected_name

            _us_need_price = (
                us_mode == "📊 일반 주식 검색"
                or st.session_state.us_sector_view == "detail"
            )
            detail_us = None
            if _us_need_price:
                with st.spinner(""):
                    detail_us = get_us_stock_detail(_us_ticker_cur)

            _YF_TO_TV = {
                "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
                "NYQ": "NYSE",   "NYS": "NYSE",   "PCX": "NYSE",   "ASE": "AMEX",
            }

            col_us_chart, col_us_right = st.columns([5, 5])

            with col_us_chart:
                if us_mode == "🔥 오늘의 이슈 섹터":
                    if st.session_state.us_sector_view == "detail":
                        _us_dticker   = st.session_state.us_sector_detail_ticker
                        _us_dname     = st.session_state.us_sector_detail_name
                        _us_dexchange = st.session_state.get("us_sector_detail_exchange", "NASDAQ")
                        _us_tv_sym    = f"{_us_dexchange}:{_us_dticker}"
                        if detail_us:
                            _chg_cur = detail_us["change_pct"]
                            _col_cur = "#00c853" if _chg_cur >= 0 else "#ff4b4b"
                            _ar_cur  = "▲" if _chg_cur >= 0 else "▼"
                            st.markdown(
                                f"**{_us_dname}** ({_us_dticker}) &nbsp; "
                                f"${detail_us['price']:,.2f} &nbsp; "
                                f"<span style='color:{_col_cur}'>{_ar_cur} {_chg_cur:+.2f}%</span>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(f"**{_us_dname}** ({_us_dticker})")
                        _tv_ivs_d = [("5분","5"),("15분","15"),("1시간","60"),("1일","D")]
                        _tv_iv_cols_d = st.columns(len(_tv_ivs_d))
                        for _tii, (_til, _tiv) in enumerate(_tv_ivs_d):
                            if _tv_iv_cols_d[_tii].button(
                                _til, key=f"us_sec_tv_iv_{_tiv}",
                                type="primary" if st.session_state.us_tv_interval == _tiv else "secondary",
                                use_container_width=True,
                            ):
                                st.session_state.us_tv_interval = _tiv
                                st.rerun()
                        _tv_iv_cur = st.session_state.us_tv_interval
                        components.html(
                            f'''<div class="tradingview-widget-container" style="height:480px;width:100%">
                          <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
                          <script type="text/javascript"
                            src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
                          {{"autosize":true,"symbol":"{_us_tv_sym}","interval":"{_tv_iv_cur}",
                           "timezone":"America/New_York","theme":"dark","style":"1","locale":"kr",
                           "allow_symbol_change":false,"hide_top_toolbar":false,"save_image":false,
                           "backgroundColor":"rgba(0,0,0,1)"}}
                          </script></div>''', height=480)
                    else:
                        _US_IDX_TV = {"S&P500": "SP:SPX", "NASDAQ": "NASDAQ:IXIC", "DOW": "DJ:DJI"}
                        _us_idx_list = list(_US_IDX_TV.keys())
                        _it_cols = st.columns(len(_us_idx_list))
                        for _iti, _itn in enumerate(_us_idx_list):
                            if _it_cols[_iti].button(
                                _itn, key=f"us_idx_tab_{_itn}",
                                use_container_width=True,
                                type="primary" if st.session_state.us_index_tab == _itn else "secondary",
                            ):
                                st.session_state.us_index_tab = _itn
                                st.rerun()
                        _cur_us_tab = st.session_state.us_index_tab
                        _cur_us_idx = (us_indices or {}).get(_cur_us_tab, {})
                        _cur_us_val = _cur_us_idx.get("price", 0)
                        _cur_us_chg = _cur_us_idx.get("change", 0)
                        _cur_us_pct = _cur_us_idx.get("change_pct", 0)
                        _lc_us = "#00c853" if _cur_us_chg >= 0 else "#ff4b4b"
                        _sg_us = "+" if _cur_us_chg >= 0 else ""
                        if _cur_us_val > 0:
                            st.markdown(
                                f"<div style='margin:8px 0 4px 0'>"
                                f"<span style='font-size:1.55rem;font-weight:700'>{_cur_us_val:,.2f}</span>&nbsp;"
                                f"<span style='font-size:0.88rem;color:{_lc_us};font-weight:600'>"
                                f"{_sg_us}{_cur_us_chg:.2f}&nbsp;({_sg_us}{_cur_us_pct:.2f}%)</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                        _tv_ivs_l = [("1분","1"),("5분","5"),("15분","15"),("1시간","60"),("1일","D")]
                        _tv_iv_cols_l = st.columns(len(_tv_ivs_l))
                        for _tii, (_til, _tiv) in enumerate(_tv_ivs_l):
                            if _tv_iv_cols_l[_tii].button(
                                _til, key=f"us_idx_tv_{_tiv}",
                                type="primary" if st.session_state.us_tv_interval == _tiv else "secondary",
                                use_container_width=True,
                            ):
                                st.session_state.us_tv_interval = _tiv
                                st.rerun()
                        _us_idx_sym = _US_IDX_TV.get(_cur_us_tab, "SP:SPX")
                        _us_idx_iv  = st.session_state.us_tv_interval
                        components.html(
                            f'''<div class="tradingview-widget-container" style="height:430px;width:100%">
                          <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
                          <script type="text/javascript"
                            src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
                          {{"autosize":true,"symbol":"{_us_idx_sym}","interval":"{_us_idx_iv}",
                           "timezone":"America/New_York","theme":"dark","style":"1","locale":"kr",
                           "allow_symbol_change":false,"hide_top_toolbar":false,"save_image":false,
                           "backgroundColor":"rgba(0,0,0,1)"}}
                          </script></div>''', height=430)
                else:
                    if detail_us:
                        _chg = detail_us["change_pct"]
                        _col = "#00c853" if _chg >= 0 else "#ff4b4b"
                        _ar  = "▲" if _chg >= 0 else "▼"
                        st.markdown(
                            f"**{detail_us['name']}** ({_us_ticker_cur}) &nbsp; "
                            f"${detail_us['price']:,.2f} &nbsp; "
                            f"<span style='color:{_col}'>{_ar} {_chg:+.2f}%</span>",
                            unsafe_allow_html=True,
                        )
                    _tv_ivs = [("1분","1"),("5분","5"),("15분","15"),("1시간","60"),("1일","D")]
                    _tv_ivcols = st.columns(len(_tv_ivs))
                    for _tii, (_til, _tiv) in enumerate(_tv_ivs):
                        if _tv_ivcols[_tii].button(
                            _til, key=f"us_tv_iv_{_tiv}",
                            type="primary" if st.session_state.us_tv_interval == _tiv else "secondary",
                            use_container_width=True,
                        ):
                            st.session_state.us_tv_interval = _tiv
                            st.rerun()
                    _yf_ex  = (detail_us or {}).get("exchange", "")
                    _tv_ex  = _YF_TO_TV.get(_yf_ex, "NASDAQ")
                    _tv_sym = f"{_tv_ex}:{_us_ticker_cur}"
                    _tv_iv  = st.session_state.us_tv_interval
                    components.html(
                        f'''<div class="tradingview-widget-container" style="height:480px;width:100%">
                      <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
                      <script type="text/javascript"
                        src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
                      {{"autosize":true,"symbol":"{_tv_sym}","interval":"{_tv_iv}",
                       "timezone":"America/New_York","theme":"dark","style":"1","locale":"kr",
                       "allow_symbol_change":false,"hide_top_toolbar":false,"hide_legend":false,
                       "save_image":false,"backgroundColor":"rgba(0,0,0,1)"}}
                      </script></div>''', height=480)

            with col_us_right:
                if us_mode == "📊 일반 주식 검색":
                    from db import load_us_sector_map as _load_us_sm
                    _us_sm = _load_us_sm()
                    _us_all_stk: dict = {}
                    for _ss in _us_sm.values():
                        for _sst in _ss.values():
                            for _s in _sst:
                                _lbl = f"{_s['name']} ({_s['ticker']})"
                                _us_all_stk[_lbl] = {"ticker": _s["ticker"], "exchange": _s.get("exchange", "NASDAQ")}
                    for _pn, _pt, _pe in [
                        ("엔비디아","NVDA","NASDAQ"),("애플","AAPL","NASDAQ"),
                        ("마이크로소프트","MSFT","NASDAQ"),("테슬라","TSLA","NASDAQ"),
                        ("아마존","AMZN","NASDAQ"),("메타","META","NASDAQ"),
                        ("알파벳","GOOGL","NASDAQ"),("팔란티어","PLTR","NYSE"),
                        ("브로드컴","AVGO","NASDAQ"),("TSMC","TSM","NYSE"),
                    ]:
                        _pl = f"{_pn} ({_pt})"
                        if _pl not in _us_all_stk:
                            _us_all_stk[_pl] = {"ticker": _pt, "exchange": _pe}
                    _us_opts    = sorted(_us_all_stk.keys())
                    _us_def_lbl = next((l for l in _us_opts if f"({_us_ticker_cur})" in l), _us_opts[0] if _us_opts else "")

                    _us_man = st.text_input(
                        "티커 직접 입력", "", placeholder="예: TSLA",
                        label_visibility="collapsed", key="us_manual_input",
                    ).upper().strip()
                    if not _us_man:
                        _us_sel_lbl = st.selectbox(
                            "종목 검색 (이름·티커 입력하면 필터링)",
                            _us_opts,
                            index=_us_opts.index(_us_def_lbl) if _us_def_lbl in _us_opts else 0,
                            key="us_stock_search",
                        )
                        _new_ticker = _us_all_stk[_us_sel_lbl]["ticker"]
                        _new_name   = _us_sel_lbl.split(" (")[0]
                    else:
                        _new_ticker = _us_man
                        _new_name   = _us_man
                    if _new_ticker != st.session_state.us_selected_ticker:
                        st.session_state.us_selected_ticker = _new_ticker
                        st.session_state.us_selected_name   = _new_name
                        st.rerun()

                    _rp_tabs = ["📊 시세", "💰 수급", "🧠 AI 분석"]
                    _rp_c1, _rp_c2, _rp_c3 = st.columns(3)
                    for _rpc, _rpt in [(_rp_c1, _rp_tabs[0]), (_rp_c2, _rp_tabs[1]), (_rp_c3, _rp_tabs[2])]:
                        if _rpc.button(
                            _rpt, key=f"us_rp_{_rpt}",
                            type="primary" if st.session_state.us_right_tab == _rpt else "secondary",
                            use_container_width=True,
                        ):
                            st.session_state.us_right_tab = _rpt
                            st.rerun()

                    if detail_us:
                        _us_chg = detail_us["change_pct"]
                        _us_col = "#00c853" if _us_chg >= 0 else "#ff4b4b"

                        if st.session_state.us_right_tab == _rp_tabs[0]:
                            with st.container(border=True):
                                _us_ar = "▲" if _us_chg >= 0 else "▼"
                                st.markdown(
                                    f"<div style='margin:4px 0'>"
                                    f"<span style='font-size:1.5rem;font-weight:700'>${detail_us['price']:,.2f}</span>"
                                    f"&nbsp;<span style='font-size:0.9rem;color:{_us_col};font-weight:600'>"
                                    f"{_us_ar} {detail_us['change']:+.2f} ({_us_chg:+.2f}%)</span>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                                _um1, _um2, _um3 = st.columns(3)
                                _um1.metric("거래량",   f"{detail_us['volume']:,}")
                                _um2.metric("시가",     f"${detail_us['open']:,.2f}")
                                _um3.metric("시가총액", detail_us["market_cap"])
                                _um4, _um5, _um6 = st.columns(3)
                                _um4.metric("고가", f"${detail_us['high']:,.2f}")
                                _um5.metric("저가", f"${detail_us['low']:,.2f}")
                                _um6.metric("PER",  str(detail_us["per"]))
                                _um7, _um8, _um9 = st.columns(3)
                                _um7.metric("52주 최고", f"${detail_us['w52_high']:,.2f}")
                                _um8.metric("52주 최저", f"${detail_us['w52_low']:,.2f}")
                                _um9.metric("베타",      str(detail_us["beta"]))
                                _uwl = detail_us.get("w52_low",  0) or 0
                                _uwh = detail_us.get("w52_high", 0) or 0
                                _ucp = detail_us["price"]
                                if _uwh > _uwl > 0:
                                    _ubp = max(0, min(100, (_ucp - _uwl) / (_uwh - _uwl) * 100))
                                    st.markdown(
                                        f"<div style='margin:8px 0 2px 0'>"
                                        f"<span style='font-size:0.7rem;color:#888'>52주 가격 위치</span></div>"
                                        f"<div style='position:relative;background:rgba(255,255,255,0.08);"
                                        f"border-radius:4px;height:6px;margin:0 0 4px 0'>"
                                        f"<div style='background:{_us_col};border-radius:4px;height:6px;"
                                        f"width:{_ubp:.1f}%'></div></div>"
                                        f"<div style='display:flex;justify-content:space-between;"
                                        f"font-size:0.65rem;color:#888'>"
                                        f"<span>최저 ${_uwl:,.2f}</span>"
                                        f"<span style='color:{_us_col};font-weight:700'>{_ubp:.0f}%</span>"
                                        f"<span>최고 ${_uwh:,.2f}</span></div>",
                                        unsafe_allow_html=True,
                                    )
                            if _us_chg >= 5.0:
                                st.success(f"✅ **강력 단타 추천** {_us_chg:+.2f}% — 강한 모멘텀, 눌림목 진입 권장")
                            elif _us_chg >= 3.0:
                                st.success(f"✅ **단타 추천** {_us_chg:+.2f}% — 수급 확인 후 진입, 손절: 당일 저점")
                            elif _us_chg >= 1.5:
                                st.warning(f"⚠️ **관망** {_us_chg:+.2f}% — 3% 돌파 확인 후 진입 검토")
                            elif _us_chg <= -3.0:
                                st.info(f"🔵 **반등 포착 관찰** {_us_chg:+.2f}% — 지지선·거래량 확인 필수")
                            else:
                                st.error(f"❌ **단타 비적합** {_us_chg:+.2f}% — 수수료·세금 감안 시 실익 없음")

                        elif st.session_state.us_right_tab == _rp_tabs[1]:
                            if detail_us["institutional_pct"] > 0 or detail_us["insider_pct"] > 0:
                                st.markdown("#### 📊 기관/내부자 보유율")
                                _retail_p = max(0.0, 100.0 - detail_us["institutional_pct"] - detail_us["insider_pct"])
                                fig_own = go.Figure(go.Bar(
                                    x=["기관", "내부자", "기타"],
                                    y=[detail_us["institutional_pct"], detail_us["insider_pct"], _retail_p],
                                    marker_color=["#2b7cff", "#ff4b4b", "#888"],
                                ))
                                fig_own.update_layout(
                                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                    font=dict(color="white"),
                                    yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="%", range=[0, 100]),
                                    margin=dict(l=10, r=10, t=10, b=10), height=220,
                                )
                                st.plotly_chart(fig_own, use_container_width=True)
                            else:
                                st.info("보유율 데이터가 없습니다.")
                            st.markdown("#### 🔗 AI 관련주")
                            if st.button("🔍 관련주 발굴", use_container_width=True, key="us_related_btn"):
                                with st.spinner("관련주 분석 중..."):
                                    from ai_engine import generate_related_stocks
                                    _rel = generate_related_stocks(_us_ticker_cur, detail_us.get("sector", ""))
                                    st.session_state[f"us_related_{_us_ticker_cur}"] = _rel
                            if f"us_related_{_us_ticker_cur}" in st.session_state:
                                for _r in st.session_state[f"us_related_{_us_ticker_cur}"]:
                                    _rt = _r.get("ticker", "")
                                    _rn = _r.get("name", _rt)
                                    if st.button(f"{_rn} ({_rt})", key=f"goto_{_rt}_{_us_ticker_cur}",
                                                 use_container_width=True):
                                        st.session_state.us_selected_ticker = _rt
                                        st.session_state.us_selected_name   = _rn
                                        st.rerun()

                        elif st.session_state.us_right_tab == _rp_tabs[2]:
                            st.markdown(
                                "<p style='font-size:0.78rem;font-weight:700;color:#aaa;margin:4px 0'>"
                                "🎯 오늘의 단타 핫종목 발굴</p>",
                                unsafe_allow_html=True,
                            )
                            if st.button("✨ AI 핫종목 발굴", use_container_width=True, key="us_discover_btn"):
                                with st.spinner("세력 수급·호재 종목 탐색 중..."):
                                    from ai_engine import discover_hot_day_trading_stock
                                    _hs = discover_hot_day_trading_stock("")
                                    if _hs.get("ticker") != "N/A":
                                        st.session_state.discovered_ticker    = _hs.get("ticker")
                                        st.session_state.discovered_name      = _hs.get("name_kr")
                                        st.session_state.discovered_buy       = _hs.get("buy_target", "-")
                                        st.session_state.discovered_sell      = _hs.get("sell_target", "-")
                                        st.session_state.discovered_stop      = _hs.get("stop_loss", "-")
                                        st.session_state.discovered_reasoning = _hs.get("reasoning")
                                        from db import log_ai_recommendation
                                        log_ai_recommendation(
                                            "단타발굴", _hs.get("ticker",""), _hs.get("name_kr",""),
                                            "AI발굴", _hs.get("buy_target","-"),
                                            _hs.get("sell_target","-"), _hs.get("stop_loss","-")
                                        )
                                    else:
                                        st.error(_hs.get("reasoning"))
                            if "discovered_ticker" in st.session_state:
                                with st.container(border=True):
                                    st.markdown(
                                        f"**{st.session_state.discovered_name} "
                                        f"({st.session_state.discovered_ticker})**"
                                    )
                                    _dc1, _dc2, _dc3 = st.columns(3)
                                    _dc1.metric("매수가", st.session_state.discovered_buy)
                                    _dc2.metric("목표가", st.session_state.discovered_sell)
                                    _dc3.metric("손절",   st.session_state.discovered_stop)
                                    if st.session_state.discovered_reasoning:
                                        st.markdown(st.session_state.discovered_reasoning)
                            st.markdown(
                                "<hr style='margin:8px 0;border:none;border-top:1px solid rgba(255,255,255,0.07)'>",
                                unsafe_allow_html=True,
                            )
                            st.markdown(
                                "<p style='font-size:0.78rem;font-weight:700;color:#aaa;margin:4px 0'>"
                                "🧠 세력 수급 & 타점 분석</p>",
                                unsafe_allow_html=True,
                            )
                            _cur_p = detail_us["price"]
                            _chg_p = detail_us["change_pct"]
                            _us_ai_key  = f"report_{_us_ticker_cur}"
                            _us_run_key = "_us_ai_pending"
                            if st.button("🎯 AI 분석 실행", use_container_width=True,
                                         type="primary", key="us_ai_report_btn"):
                                st.session_state[_us_run_key] = _us_ticker_cur
                                if _us_ai_key in st.session_state:
                                    del st.session_state[_us_ai_key]
                                st.rerun()

                            if st.session_state.get(_us_run_key) == _us_ticker_cur and _us_ai_key not in st.session_state:
                                with st.spinner("AI가 수급·뉴스·차트를 융합 분석 중..."):
                                    try:
                                        from ai_engine import generate_stock_report
                                        _rep_j = generate_stock_report(_us_ticker_cur, _cur_p, _chg_p)
                                    except Exception as _e:
                                        _rep_j = {
                                            "rating": "분석 실패", "buy_target": "-",
                                            "sell_target": "-", "stop_loss": "-",
                                            "analysis": f"오류: {_e}",
                                        }
                                    st.session_state[_us_ai_key] = _rep_j
                                    st.session_state[_us_run_key] = None
                                    try:
                                        from db import log_ai_recommendation
                                        log_ai_recommendation(
                                            "미국주식분석", _us_ticker_cur,
                                            detail_us.get("name", _us_ticker_cur),
                                            _rep_j.get("rating","-"), _rep_j.get("buy_target","-"),
                                            _rep_j.get("sell_target","-"), _rep_j.get("stop_loss","-"),
                                        )
                                    except Exception:
                                        pass
                                    if ("추천" in _rep_j.get("rating","") and
                                            "비추천" not in _rep_j.get("rating","")):
                                        if "ai_portfolio" not in st.session_state:
                                            st.session_state.ai_portfolio = []
                                        if not any(i["ticker"] == _us_ticker_cur
                                                   for i in st.session_state.ai_portfolio):
                                            st.session_state.ai_portfolio.append({
                                                "ticker": _us_ticker_cur,
                                                "name": detail_us["name"],
                                                "buy_price": _cur_p, "quantity": 10,
                                                "buy_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                            })
                                            st.toast(f"AI 자동 담기: {_us_ticker_cur}")
                                st.rerun()
                            if _us_ai_key in st.session_state:
                                _rep = st.session_state[_us_ai_key]
                                _re  = ("🟢" if "강력 추천" in _rep.get("rating","")
                                        else "🟡" if "추천" in _rep.get("rating","") else "🔴")
                                st.markdown(f"##### {_re} {_rep.get('rating','')}")
                                _rt1, _rt2 = st.columns(2)
                                _rt1.metric("매수가", _rep.get("buy_target","-"))
                                _rt2.metric("목표가", _rep.get("sell_target","-"))
                                st.metric("손절", _rep.get("stop_loss","-"))
                                if st.button("🎒 포트폴리오에 담기", use_container_width=True,
                                             type="primary", key="us_port_btn"):
                                    if "portfolio" not in st.session_state:
                                        st.session_state.portfolio = []
                                    if not any(i["ticker"] == _us_ticker_cur
                                               for i in st.session_state.portfolio):
                                        st.session_state.portfolio.append({
                                            "ticker": _us_ticker_cur,
                                            "name": detail_us["name"],
                                            "buy_price": _cur_p, "quantity": 10,
                                            "buy_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                        })
                                        st.success(f"{_us_ticker_cur} 포트폴리오에 추가!")
                                    else:
                                        st.warning("이미 포트폴리오에 있습니다.")
                                if _rep.get("analysis"):
                                    with st.container(border=True):
                                        st.markdown(_rep["analysis"])
                            st.markdown(
                                "<hr style='margin:8px 0;border:none;border-top:1px solid rgba(255,255,255,0.07)'>",
                                unsafe_allow_html=True,
                            )
                            if st.button("🌌 시장 자금 흐름 마인드맵", use_container_width=True,
                                         key="us_mindmap_btn"):
                                @st.dialog("🌌 실시간 시장 자금 흐름 마인드맵", width="large")
                                def _show_mindmap():
                                    with st.spinner("AI 마인드맵 생성 중..."):
                                        from ai_engine import generate_mindmap_data
                                        _mc = generate_mindmap_data()
                                        _html = (
                                            "<script type='module'>import mermaid from "
                                            "'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';"
                                            "mermaid.initialize({startOnLoad:true,theme:'dark'});</script>"
                                            f"<div class='mermaid' style='background:#111;padding:20px;"
                                            f"border-radius:10px'>{_mc}</div>"
                                        )
                                        components.html(_html, height=500, scrolling=True)
                                _show_mindmap()
                    else:
                        st.warning("데이터를 불러오지 못했습니다.")

                else:
                    from db import load_us_sector_map, init_us_sector_sheet

                    us_sector_map   = load_us_sector_map()
                    us_sector_names = list(us_sector_map.keys())
                    if st.session_state.us_selected_sector_us not in us_sector_map:
                        st.session_state.us_selected_sector_us = us_sector_names[0]

                    if st.session_state.us_sector_view == "detail":
                        _us_dticker   = st.session_state.us_sector_detail_ticker
                        _us_dname     = st.session_state.us_sector_detail_name
                        _us_dexchange = st.session_state.get("us_sector_detail_exchange", "NASDAQ")

                        if st.button("← 섹터 목록으로", key="us_sec_back", use_container_width=True):
                            st.session_state.us_sector_view = "list"
                            st.rerun()

                        st.markdown(
                            f"<h4 style='margin:4px 0 2px 0'>{_us_dname}</h4>"
                            f"<p style='margin:0;font-size:0.78rem;color:#888'>"
                            f"티커 {_us_dticker} · {st.session_state.us_selected_sector_us}</p>",
                            unsafe_allow_html=True,
                        )

                        with st.spinner(""):
                            us_detail = get_us_stock_detail(_us_dticker, _us_dexchange)

                        with st.container(height=490):
                            if us_detail:
                                chg = us_detail["change_pct"]
                                d_c = "normal" if chg >= 0 else "inverse"
                                ar  = "▲" if chg >= 0 else "▼"
                                with st.container(border=True):
                                    m1, m2, m3 = st.columns(3)
                                    m1.metric("현재가", f"${us_detail['price']:,.2f}",
                                              f"{ar} {abs(us_detail['change']):.2f} ({chg:+.2f}%)",
                                              delta_color=d_c)
                                    m2.metric("거래량",   f"{us_detail['volume']:,}")
                                    m3.metric("시가총액", us_detail["market_cap"])
                                    n1, n2, n3 = st.columns(3)
                                    n1.metric("고가", f"${us_detail['high']:,.2f}")
                                    n2.metric("저가", f"${us_detail['low']:,.2f}")
                                    n3.metric("PER",  str(us_detail["per"]))
                                    n4, n5, n6 = st.columns(3)
                                    n4.metric("52주 최고", f"${us_detail['w52_high']:,.2f}")
                                    n5.metric("52주 최저", f"${us_detail['w52_low']:,.2f}")
                                    n6.metric("베타",      str(us_detail["beta"]))
                                st.markdown("#### 🎯 단타 적합성 판단")
                                if chg >= 5.0:
                                    st.success(f"✅ **강력 단타 추천** — 등락률 **{chg:+.2f}%**")
                                elif chg >= 3.0:
                                    st.success(f"✅ **단타 추천** — 등락률 **{chg:+.2f}%**")
                                elif chg >= 1.5:
                                    st.warning(f"⚠️ **관망** — 등락률 {chg:+.2f}%")
                                elif chg <= -3.0:
                                    st.info(f"🔵 **반등 포착 관찰** — 등락률 {chg:+.2f}%")
                                else:
                                    st.error(f"❌ **단타 비적합** — 등락률 {chg:+.2f}%")
                                if us_detail["institutional_pct"] > 0 or us_detail["insider_pct"] > 0:
                                    st.markdown("#### 📊 기관/내부자 보유율")
                                    retail_p = max(0.0, 100.0 - us_detail["institutional_pct"] - us_detail["insider_pct"])
                                    fig_own2 = go.Figure(go.Bar(
                                        x=["기관", "내부자", "기타"],
                                        y=[us_detail["institutional_pct"], us_detail["insider_pct"], retail_p],
                                        marker_color=["#2b7cff", "#ff4b4b", "#888"]
                                    ))
                                    fig_own2.update_layout(
                                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                        font=dict(color="white"),
                                        yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="%", range=[0, 100]),
                                        margin=dict(l=10, r=10, t=10, b=10), height=170
                                    )
                                    st.plotly_chart(fig_own2, use_container_width=True)
                                st.markdown("#### 🧠 AI 단타 심층 분석")
                                if st.button("🎯 AI 단타 분석 실행", type="primary",
                                             use_container_width=True, key="us_sec_detail_ai"):
                                    with st.spinner("AI가 수급·뉴스·차트를 융합 분석 중..."):
                                        from ai_engine import generate_stock_report
                                        _us_rep = generate_stock_report(_us_dticker, us_detail["price"], chg)
                                        st.session_state[f"us_sec_rep_{_us_dticker}"] = _us_rep
                                        from db import log_ai_recommendation
                                        log_ai_recommendation(
                                            "미국섹터단타", _us_dticker, _us_dname,
                                            _us_rep.get("rating","-"), _us_rep.get("buy_target","-"),
                                            _us_rep.get("sell_target","-"), _us_rep.get("stop_loss","-")
                                        )
                                if f"us_sec_rep_{_us_dticker}" in st.session_state:
                                    _ur = st.session_state[f"us_sec_rep_{_us_dticker}"]
                                    _urtg = _ur.get("rating","")
                                    _ure  = "🟢" if "강력" in _urtg else "🟡" if "추천" in _urtg else "🔴"
                                    st.markdown(f"##### {_ure} {_urtg}")
                                    _urk1, _urk2 = st.columns(2)
                                    _urk1.metric("매수 타점", _ur.get("buy_target","-"))
                                    _urk2.metric("목표가",    _ur.get("sell_target","-"))
                                    st.metric("손절가", _ur.get("stop_loss","-"))
                                    if _ur.get("analysis"):
                                        st.markdown("---")
                                        with st.container(border=True):
                                            st.markdown(_ur["analysis"])
                            else:
                                st.warning("시세 데이터를 불러오지 못했습니다.")

                    else:
                        st.markdown("### 🔥 이슈 섹터")

                        _us_spt_tabs = ["📊 AI 시장분석", "📚 전체 섹터 탐색"]
                        _us_stc1, _us_stc2 = st.columns(2)
                        for _us_stcol, _us_stn in [(_us_stc1, _us_spt_tabs[0]), (_us_stc2, _us_spt_tabs[1])]:
                            if _us_stcol.button(
                                _us_stn, key=f"us_spt_{_us_stn}",
                                type="primary" if st.session_state.us_sector_panel_tab == _us_stn else "secondary",
                                use_container_width=True,
                            ):
                                st.session_state.us_sector_panel_tab = _us_stn
                                st.rerun()

                        if st.session_state.us_sector_panel_tab == _us_spt_tabs[0]:
                            from ai_engine import discover_hot_day_trading_stock, generate_dynamic_themes
                            _us_am_hdr, _us_am_ref = st.columns([8, 1])
                            _us_am_hdr.markdown(
                                "<p style='font-size:0.75rem;color:#888;margin:4px 0'>"
                                "AI 핫종목 발굴 · 핫 테마 분석 통합</p>",
                                unsafe_allow_html=True,
                            )
                            if st.session_state.us_ai_market_run:
                                if _us_am_ref.button("🔄", key="us_ai_mkt_refresh", help="재분석"):
                                    try: generate_dynamic_themes.clear()
                                    except: pass
                                    st.rerun()
                            if not st.session_state.us_ai_market_run:
                                st.markdown(
                                    "<div style='text-align:center;padding:40px 20px'>"
                                    "<p style='color:#888;font-size:0.85rem;margin-bottom:16px'>"
                                    "AI 핫종목 발굴과 오늘의 핫 테마를 한번에 분석합니다</p>"
                                    "</div>",
                                    unsafe_allow_html=True,
                                )
                                if st.button("🤖 AI 시장분석 실행", use_container_width=True,
                                             type="primary", key="us_run_ai_market"):
                                    st.session_state.us_ai_market_run = True
                                    st.rerun()
                            else:
                                st.markdown(
                                    "<p style='font-size:0.78rem;font-weight:700;color:#aaa;"
                                    "margin:6px 0 4px 0'>🎯 오늘의 AI 단타 핫종목</p>",
                                    unsafe_allow_html=True,
                                )
                                if st.button("✨ AI 핫종목 새로 발굴", key="us_sec_discover",
                                             use_container_width=True):
                                    with st.spinner("탐색 중..."):
                                        _us_hs = discover_hot_day_trading_stock("")
                                        if _us_hs.get("ticker") != "N/A":
                                            st.session_state.us_sec_hot = _us_hs
                                            from db import log_ai_recommendation
                                            log_ai_recommendation(
                                                "단타발굴(섹터)", _us_hs.get("ticker",""),
                                                _us_hs.get("name_kr",""), "AI발굴",
                                                _us_hs.get("buy_target","-"),
                                                _us_hs.get("sell_target","-"),
                                                _us_hs.get("stop_loss","-"),
                                            )
                                if "us_sec_hot" in st.session_state:
                                    _sh = st.session_state.us_sec_hot
                                    with st.container(border=True):
                                        st.markdown(f"**{_sh.get('name_kr','')} ({_sh.get('ticker','')})**")
                                        _shc1, _shc2, _shc3 = st.columns(3)
                                        _shc1.metric("매수가", _sh.get("buy_target","-"))
                                        _shc2.metric("목표가", _sh.get("sell_target","-"))
                                        _shc3.metric("손절",   _sh.get("stop_loss","-"))
                                        if _sh.get("reasoning"):
                                            st.markdown(
                                                f"<p style='font-size:0.73rem;color:#bbb;"
                                                f"margin:4px 0'>{_sh['reasoning'][:200]}...</p>",
                                                unsafe_allow_html=True,
                                            )
                                        if st.button("▶ 차트 보기", key="us_hot_chart"):
                                            st.session_state.us_selected_ticker      = _sh.get("ticker","")
                                            st.session_state.us_selected_name        = _sh.get("name_kr","")
                                            st.session_state.us_sector_detail_ticker = _sh.get("ticker","")
                                            st.session_state.us_sector_detail_name   = _sh.get("name_kr","")
                                            st.session_state.us_sector_view          = "detail"
                                            st.rerun()
                                st.markdown(
                                    "<hr style='margin:8px 0;border:none;"
                                    "border-top:1px solid rgba(255,255,255,0.07)'>",
                                    unsafe_allow_html=True,
                                )
                                st.markdown(
                                    "<p style='font-size:0.78rem;font-weight:700;color:#aaa;"
                                    "margin:4px 0'>🔥 오늘의 AI 핫 테마</p>",
                                    unsafe_allow_html=True,
                                )
                                with st.spinner("AI가 오늘의 핫 테마 분석 중..."):
                                    _us_themes = generate_dynamic_themes()
                                if _us_themes.get("error"):
                                    st.info(f"⏸ {_us_themes['error']}")
                                else:
                                    with st.container(height=380):
                                        for _ut in _us_themes.get("themes", []):
                                            with st.container(border=True):
                                                _ul  = _ut.get("leader_stock", {})
                                                _uls = _ul.get("ticker","")
                                                _uln = _ul.get("name_kr", _uls)
                                                st.markdown(
                                                    f"<span style='font-size:0.9rem;font-weight:700'>"
                                                    f"{_ut.get('theme_name','')}</span>",
                                                    unsafe_allow_html=True,
                                                )
                                                st.markdown(
                                                    f"<p style='font-size:0.73rem;color:#aaa;"
                                                    f"margin:2px 0'>{_ut.get('correlation','')[:120]}...</p>",
                                                    unsafe_allow_html=True,
                                                )
                                                st.markdown(
                                                    f"<span style='font-size:0.78rem;font-weight:700;"
                                                    f"color:#f5c518'>👑 대장주: {_uln} ({_uls})</span>",
                                                    unsafe_allow_html=True,
                                                )
                                                _rels = " · ".join(
                                                    f"{r.get('name_kr','')} ({r.get('ticker','')})"
                                                    for r in _ut.get("related_stocks",[])
                                                )
                                                if _rels:
                                                    st.markdown(
                                                        f"<p style='font-size:0.68rem;color:#888;"
                                                        f"margin:2px 0'>관련주: {_rels}</p>",
                                                        unsafe_allow_html=True,
                                                    )
                                                if _uls and st.button("▶ 차트", key=f"us_theme_{_uls}"):
                                                    st.session_state.us_selected_ticker      = _uls
                                                    st.session_state.us_selected_name        = _uln
                                                    st.session_state.us_sector_detail_ticker = _uls
                                                    st.session_state.us_sector_detail_name   = _uln
                                                    st.session_state.us_sector_view          = "detail"
                                                    st.rerun()

                        elif st.session_state.us_sector_panel_tab == _us_spt_tabs[1]:
                            _uh1, _uh2, _uh3 = st.columns([4, 1, 1])
                            with _uh2:
                                if st.button("🔄", key="us_sec_refresh", use_container_width=True, help="캐시 초기화"):
                                    load_us_sector_map.clear()
                                    st.rerun()
                            with _uh3:
                                if st.button("☁️", key="us_sec_init", use_container_width=True, help="시트 업로드"):
                                    ok, msg_init = init_us_sector_sheet()
                                    st.toast(msg_init if ok else f"오류: {msg_init}")

                            _us_cur_si = (us_sector_names.index(st.session_state.us_selected_sector_us)
                                          if st.session_state.us_selected_sector_us in us_sector_names else 0)
                            _us_sel_sec = st.selectbox(
                                "섹터 선택", us_sector_names, index=_us_cur_si,
                                key="us_sector_selectbox", label_visibility="collapsed",
                            )
                            if _us_sel_sec != st.session_state.us_selected_sector_us:
                                st.session_state.us_selected_sector_us = _us_sel_sec
                                st.rerun()

                            us_selected_sector = st.session_state.us_selected_sector_us
                            us_subsectors      = us_sector_map[us_selected_sector]

                            us_ticker_locations: dict = {}
                            for _s, _subs in us_sector_map.items():
                                for _sb, _stks in _subs.items():
                                    for _stk in _stks:
                                        us_ticker_locations.setdefault(_stk["ticker"], []).append(
                                            f"{_s} › {_sb}"
                                        )

                            _us_seen: set = set()
                            _us_unique: list = []
                            for _stks in us_subsectors.values():
                                for _stk in _stks:
                                    if _stk["ticker"] not in _us_seen:
                                        _us_seen.add(_stk["ticker"])
                                        _us_unique.append((_stk["ticker"], _stk.get("exchange","NASDAQ")))

                            _us_n   = len(_us_unique)
                            _us_est = max(3, min(_us_n // 6, 20))
                            _us_load_ph = st.empty()
                            _us_load_ph.markdown(
                                f"""<div style='display:flex;align-items:center;gap:14px;
                                    background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
                                    border-radius:12px;padding:14px 18px;margin:8px 0'>
                                  <div style='font-size:1.3rem;animation:spin 1.2s linear infinite;display:inline-block'>⏳</div>
                                  <div>
                                    <div style='font-size:0.85rem;font-weight:600'>실시간 시세 조회 중 ({_us_n}개 종목)</div>
                                    <div style='font-size:0.82rem;color:#888'>약 {_us_est}초 소요</div>
                                  </div>
                                </div>
                                <style>@keyframes spin{{0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}}}}</style>""",
                                unsafe_allow_html=True,
                            )
                            us_prices = get_us_prices_bulk_kis(tuple(_us_unique))
                            _us_load_ph.empty()

                            _us_hcols = st.columns([0.35, 2.8, 1.8, 1.4, 0.45])
                            for _uhc, _uht in zip(_us_hcols[:4], ["단타", "종목명", "현재가($)", "등락률"]):
                                _uhc.markdown(
                                    f"<p style='margin:0;font-size:0.72rem;color:#888'>{_uht}</p>",
                                    unsafe_allow_html=True,
                                )

                            def _us_sub_avg_pct(stocks, prices):
                                vals = [prices.get(s["ticker"], {}).get("change_pct", 0.0) for s in stocks]
                                vals = [v for v in vals if v != 0.0]
                                return sum(vals) / len(vals) if vals else 0.0

                            def _us_sub_ai_summary(parent_sector, sub_name, avg_pct, stocks, prices):
                                from ai_engine import _call_gemini
                                import datetime as _dt
                                with_pct = sorted(
                                    [(s["name"], prices.get(s["ticker"], {}).get("change_pct", 0.0))
                                     for s in stocks if prices.get(s["ticker"], {}).get("change_pct", 0.0) != 0.0],
                                    key=lambda x: abs(x[1]), reverse=True
                                )
                                stock_detail = ", ".join(f"{n}({p:+.1f}%)" for n, p in with_pct[:8])
                                if not stock_detail:
                                    stock_detail = ", ".join(s["name"] for s in stocks[:8])
                                prompt = (
                                    f"오늘({_dt.date.today()}) 미국 증시 분석 요청.\n"
                                    f"분석 범위: '{parent_sector}' 섹터 내 '{sub_name}' 세부섹터 ({len(stocks)}개 종목)\n"
                                    f"해당 세부섹터 종목: {stock_detail}\n"
                                    f"세부섹터 평균 등락률: {avg_pct:+.2f}%\n\n"
                                    f"위 {len(stocks)}개 종목으로 구성된 '{sub_name}' 세부섹터만을 대상으로, "
                                    f"오늘 이 종목들이 이렇게 움직이는 이유를 뉴스·실적·매크로 기반으로 "
                                    f"3~5줄 이내로 간결하게 요약해주세요. 이모지 없이 핵심만."
                                )
                                try:
                                    resp = _call_gemini(prompt, use_search=True, temperature=0.4)
                                    return resp.text.strip() if resp and resp.text else "분석 정보 없음"
                                except Exception:
                                    return "AI 분석을 불러올 수 없습니다."

                            with st.container(height=600):
                                for us_sub_name, us_stocks in us_subsectors.items():
                                    us_avg_pct   = _us_sub_avg_pct(us_stocks, us_prices)
                                    us_pct_color = "#00c853" if us_avg_pct > 0 else "#ff4b4b" if us_avg_pct < 0 else "#888"
                                    us_tok       = f"_us_sub_open_{us_selected_sector}__{us_sub_name}"
                                    if us_tok not in st.session_state:
                                        st.session_state[us_tok] = False
                                    us_is_open = st.session_state[us_tok]
                                    us_ai_key  = f"_us_sub_ai_{us_selected_sector}__{us_sub_name}"

                                    with st.container(border=True):
                                        uh0, uh1, uh2, uh3, uh4 = st.columns([0.35, 2.8, 1.8, 1.4, 0.45])
                                        if uh0.button(
                                            "▼" if us_is_open else "▶",
                                            key=f"us_tog_{us_sub_name}", use_container_width=True,
                                        ):
                                            st.session_state[us_tok] = not us_is_open
                                            st.rerun()
                                        uh1.markdown(
                                            f"<span style='font-size:0.85rem;font-weight:600'>📌 {us_sub_name}</span>"
                                            f"<span style='font-size:0.75rem;color:#888'>　{len(us_stocks)}개</span>",
                                            unsafe_allow_html=True,
                                        )
                                        uh3.markdown(
                                            f"<span style='font-size:0.92rem;font-weight:700;color:{us_pct_color}'>"
                                            f"{us_avg_pct:+.2f}%</span>",
                                            unsafe_allow_html=True,
                                        )
                                        if uh4.button("AI", key=f"us_ai_btn_{us_sub_name}", use_container_width=True):
                                            st.session_state[us_ai_key] = _us_sub_ai_summary(
                                                us_selected_sector, us_sub_name, us_avg_pct, us_stocks, us_prices
                                            )

                                        if us_is_open:
                                            if us_ai_key in st.session_state:
                                                st.markdown(
                                                    f"<div style='background:rgba(255,255,255,0.05);"
                                                    f"border-left:3px solid {us_pct_color};"
                                                    f"border-radius:6px;padding:8px 12px;margin:4px 0 8px 0;"
                                                    f"font-size:0.82rem;line-height:1.55;color:#ddd'>"
                                                    f"{st.session_state[us_ai_key]}</div>",
                                                    unsafe_allow_html=True,
                                                )
                                            st.markdown(
                                                '<hr style="margin:4px 0 6px 0;border:none;'
                                                'border-top:1px solid rgba(255,255,255,0.15)">',
                                                unsafe_allow_html=True,
                                            )
                                            for _ui, _us in enumerate(us_stocks):
                                                if _ui > 0:
                                                    st.markdown(
                                                        '<hr style="margin:2px 0;border:none;'
                                                        'border-top:1px solid rgba(255,255,255,0.1)">',
                                                        unsafe_allow_html=True,
                                                    )
                                                _updata = us_prices.get(_us["ticker"], {"price": 0.0, "change_pct": 0.0})
                                                _upct   = _updata["change_pct"]
                                                _upval  = _updata["price"]
                                                _upct_c = "#00c853" if _upct > 0 else "#ff4b4b" if _upct < 0 else "#888"
                                                _other_locs = [
                                                    loc for loc in us_ticker_locations.get(_us["ticker"],[])
                                                    if loc != f"{us_selected_sector} › {us_sub_name}"
                                                ]
                                                _uc0, _uc1, _uc2, _uc3, _uc4 = st.columns([0.35, 2.8, 1.8, 1.4, 0.45])
                                                _uc0.markdown("✅" if _upct >= 3.0 else "&nbsp;", unsafe_allow_html=True)
                                                _uc1.markdown(
                                                    f"<span style='font-size:0.85rem'>{_us['name']}"
                                                    f"{'&nbsp;🔗' if _other_locs else ''}</span>",
                                                    unsafe_allow_html=True,
                                                )
                                                _uc2.markdown(
                                                    f"<span style='font-size:0.85rem'>"
                                                    f"{'$'+f'{_upval:,.2f}' if _upval > 0 else '---'}</span>",
                                                    unsafe_allow_html=True,
                                                )
                                                _uc3.markdown(
                                                    f"<span style='font-size:0.85rem;font-weight:bold;"
                                                    f"color:{_upct_c}'>{_upct:+.2f}%</span>",
                                                    unsafe_allow_html=True,
                                                )
                                                if _uc4.button("▶", key=f"us_stk_{_us['ticker']}_{us_sub_name}_{_ui}",
                                                               use_container_width=True):
                                                    st.session_state.us_selected_ticker        = _us["ticker"]
                                                    st.session_state.us_selected_name          = _us["name"]
                                                    st.session_state.us_sector_detail_ticker   = _us["ticker"]
                                                    st.session_state.us_sector_detail_name     = _us["name"]
                                                    st.session_state.us_sector_detail_exchange = _us.get("exchange","NASDAQ")
                                                    st.session_state.us_sector_view            = "detail"
                                                    st.rerun()

    with tab2:
        st.subheader("📊 성과 트래킹 보드")

        if "trade_history" not in st.session_state:
            st.session_state.trade_history = []
        if "portfolio" not in st.session_state:
            st.session_state.portfolio = []
        if "ai_portfolio" not in st.session_state:
            st.session_state.ai_portfolio = []

        tab_holding, tab_history = st.tabs([
            "📈 보유 종목",
            "📋 거래 성과",
        ])

        def render_holdings(portfolio_key, show_add=False):
            # 매도/삭제 pending 처리
            pending_key = f"_remove_{portfolio_key}"
            if pending_key in st.session_state:
                ticker_to_remove = st.session_state.pop(pending_key)
                st.session_state[portfolio_key] = [
                    x for x in st.session_state.get(portfolio_key, [])
                    if x["ticker"] != ticker_to_remove
                ]

            port_list = st.session_state.get(portfolio_key, [])

            if show_add:
                with st.expander("➕ 종목 직접 추가"):
                    c1, c2, c3, c4 = st.columns(4)
                    nt = c1.text_input("티커 (예: TSLA)", key=f"nt_{portfolio_key}").upper().strip()
                    nn = c2.text_input("종목명 (예: 테슬라)", key=f"nn_{portfolio_key}")
                    np_val = c3.number_input("매수가($)", min_value=0.01, value=100.0, key=f"np_{portfolio_key}")
                    nq_val = c4.number_input("수량", min_value=1, value=10, step=1, key=f"nq_{portfolio_key}")
                    if st.button("➕ 추가", key=f"add_{portfolio_key}"):
                        if nt and not any(x["ticker"] == nt for x in port_list):
                            st.session_state[portfolio_key].append({
                                "ticker": nt,
                                "name": nn or nt,
                                "buy_price": float(np_val),
                                "quantity": int(nq_val),
                                "buy_date": datetime.now().strftime("%Y-%m-%d %H:%M")
                            })
                            st.success(f"{nt} 추가 완료!")
                            st.rerun()
                        elif not nt:
                            st.warning("티커를 입력해주세요.")
                        else:
                            st.warning("이미 포트폴리오에 있는 종목입니다.")

            port_list = st.session_state.get(portfolio_key, [])
            if not port_list:
                st.info("보유 종목이 없습니다. 분석 탭에서 '포트폴리오에 담기'를 누르거나 위 폼으로 추가하세요.")
                return

            tickers = list(set(x["ticker"] for x in port_list))
            with st.spinner("실시간 시세 조회 중..."):
                price_df = get_us_stock_data(tickers)

            total_inv, total_cur = 0.0, 0.0
            for item in port_list:
                bp, qty = item["buy_price"], item["quantity"]
                total_inv += bp * qty
                if not price_df.empty and item["ticker"] in price_df["심볼"].values:
                    cp = price_df[price_df["심볼"] == item["ticker"]].iloc[0]["현재가($)"]
                    total_cur += cp * qty
                else:
                    total_cur += bp * qty

            total_pnl = total_cur - total_inv
            total_pnl_pct = (total_pnl / total_inv * 100) if total_inv > 0 else 0

            cm1, cm2, cm3 = st.columns(3)
            cm1.metric("총 매수 금액", f"${total_inv:,.2f}")
            cm2.metric("총 평가 금액", f"${total_cur:,.2f}")
            cm3.metric("총 수익", f"${total_pnl:,.2f}", f"{total_pnl_pct:.2f}%",
                       delta_color="normal" if total_pnl >= 0 else "inverse")

            st.markdown("---")

            for idx, item in enumerate(port_list):
                ticker = item["ticker"]
                name = item.get("name", ticker)
                bp = item["buy_price"]
                qty = item["quantity"]

                if not price_df.empty and ticker in price_df["심볼"].values:
                    cp = price_df[price_df["심볼"] == ticker].iloc[0]["현재가($)"]
                else:
                    cp = bp

                pnl = (cp - bp) * qty
                pnl_pct = ((cp - bp) / bp * 100) if bp > 0 else 0
                emoji = "🟢" if pnl_pct > 0 else "🔴" if pnl_pct < 0 else "⚪"

                with st.container(border=True):
                    cl, cr = st.columns([3, 2])
                    with cl:
                        st.markdown(f"**{emoji} {name} ({ticker})** <small style='color:#888'>{item.get('buy_date', '')}</small>",
                                    unsafe_allow_html=True)
                        dc1, dc2, dc3 = st.columns(3)
                        dc1.metric("매수가", f"${bp:,.2f}")
                        dc2.metric("현재가", f"${cp:,.2f}")
                        dc3.metric("수익률", f"{pnl_pct:.2f}%", f"${pnl:,.2f}",
                                   delta_color="normal" if pnl >= 0 else "inverse")
                    with cr:
                        st.markdown("**매도가($) 입력 후 기록**")
                        sell_p = st.number_input(
                            "매도가", min_value=0.01, value=float(cp),
                            key=f"sellp_{portfolio_key}_{idx}",
                            label_visibility="collapsed"
                        )
                        bc1, bc2 = st.columns(2)
                        with bc1:
                            if st.button("✅ 매도", key=f"sell_{portfolio_key}_{idx}",
                                         type="primary", use_container_width=True):
                                invested = bp * qty
                                sell_val = sell_p * qty
                                p = sell_val - invested
                                p_pct = (p / invested * 100) if invested > 0 else 0
                                trade = {
                                    "ticker": ticker, "name": name, "quantity": qty,
                                    "buy_price": bp, "sell_price": sell_p,
                                    "profit": p, "profit_pct": p_pct,
                                    "buy_date": item.get("buy_date", "-"),
                                    "sell_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "result": "승" if p >= 0 else "패"
                                }
                                st.session_state.trade_history.append(trade)
                                from db import save_trade_record
                                save_trade_record(trade)
                                st.session_state[pending_key] = ticker
                                st.toast(f"✅ {ticker} 매도 기록 완료!")
                                st.rerun()
                        with bc2:
                            if st.button("🗑️ 삭제", key=f"del_{portfolio_key}_{idx}",
                                         use_container_width=True):
                                st.session_state[pending_key] = ticker
                                st.rerun()

            st.markdown("---")
            if st.button("🗑️ 전체 초기화", key=f"clear_{portfolio_key}", type="secondary"):
                st.session_state[portfolio_key] = []
                st.rerun()

        with tab_holding:
            st.markdown("### 🤖 AI 자동 추천 종목")
            st.caption("AI 분석에서 '추천' 이상 등급을 받으면 자동으로 기록됩니다.")
            render_holdings("ai_portfolio", show_add=False)

            st.markdown("---")
            st.markdown("### 👤 내 수동 포트폴리오")
            st.caption("분석 탭에서 '포트폴리오에 담기'를 눌렀거나 아래 폼으로 직접 추가한 종목입니다.")
            render_holdings("portfolio", show_add=True)

        with tab_history:
            history = st.session_state.trade_history

            col_load, _ = st.columns([2, 3])
            with col_load:
                if st.button("☁️ 구글 시트에서 거래내역 불러오기", use_container_width=True):
                    from db import load_trade_history_from_gsheet
                    with st.spinner("로드 중..."):
                        df_loaded, load_msg = load_trade_history_from_gsheet()
                    if df_loaded is not None and not df_loaded.empty:
                        existing_keys = {(t.get("ticker", ""), t.get("sell_date", "")) for t in history}
                        added = 0
                        for row in df_loaded.to_dict("records"):
                            key = (str(row.get("티커", "")), str(row.get("매도시간", "")))
                            if key not in existing_keys:
                                history.append({
                                    "ticker": str(row.get("티커", "")),
                                    "name": str(row.get("종목명", "")),
                                    "quantity": row.get("수량", 0),
                                    "buy_price": float(row.get("매수가($)", 0) or 0),
                                    "sell_price": float(row.get("매도가($)", 0) or 0),
                                    "profit": float(row.get("수익금($)", 0) or 0),
                                    "profit_pct": float(row.get("수익률(%)", 0) or 0),
                                    "sell_date": str(row.get("매도시간", "")),
                                    "result": str(row.get("결과", ""))
                                })
                                added += 1
                        st.session_state.trade_history = history
                        st.success(f"구글 시트에서 {added}건 신규 로드 완료!")
                        st.rerun()
                    else:
                        st.info(load_msg)

            if not history:
                st.info("완료된 거래가 없습니다. 보유 종목 탭에서 '✅ 매도' 버튼을 눌러 거래를 기록하세요.")
            else:
                wins = sum(1 for t in history if t.get("result") == "승")
                total = len(history)
                win_rate = (wins / total * 100) if total > 0 else 0
                avg_pct = sum(float(t.get("profit_pct", 0)) for t in history) / total
                total_profit_sum = sum(float(t.get("profit", 0)) for t in history)

                st.markdown("### 📊 전체 성과 요약")
                cs1, cs2, cs3, cs4 = st.columns(4)
                cs1.metric("총 거래 수", f"{total}건")
                cs2.metric("승률", f"{win_rate:.1f}%", f"{wins}승 {total - wins}패")
                cs3.metric("평균 수익률", f"{avg_pct:.2f}%")
                cs4.metric("누적 수익금", f"${total_profit_sum:,.2f}",
                           delta_color="normal" if total_profit_sum >= 0 else "inverse")

                if len(history) >= 2:
                    cumulative, x_pts, y_pts = 0.0, [], []
                    for t in history:
                        cumulative += float(t.get("profit", 0))
                        x_pts.append(t.get("sell_date", ""))
                        y_pts.append(round(cumulative, 2))

                    line_color = "#00c853" if cumulative >= 0 else "#ff4b4b"
                    fill_color = "rgba(0,200,83,0.15)" if cumulative >= 0 else "rgba(255,75,75,0.15)"
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=x_pts, y=y_pts, mode="lines+markers",
                        line=dict(color=line_color, width=2),
                        fill="tozeroy", fillcolor=fill_color,
                        name="누적 수익금"
                    ))
                    fig.update_layout(
                        title="📈 누적 수익금 추이",
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="white"),
                        xaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
                        yaxis=dict(gridcolor="rgba(255,255,255,0.1)", tickprefix="$"),
                        margin=dict(l=10, r=10, t=40, b=10)
                    )
                    st.plotly_chart(fig, use_container_width=True)

                st.markdown("### 📋 거래 내역")
                df_hist = pd.DataFrame([{
                    "매도일": t.get("sell_date", ""),
                    "티커": t.get("ticker", ""),
                    "종목명": t.get("name", ""),
                    "수량": t.get("quantity", 0),
                    "매수가": f"${float(t.get('buy_price', 0)):,.2f}",
                    "매도가": f"${float(t.get('sell_price', 0)):,.2f}",
                    "수익금": f"${float(t.get('profit', 0)):,.2f}",
                    "수익률": f"{float(t.get('profit_pct', 0)):.2f}%",
                    "결과": t.get("result", "")
                } for t in reversed(history)])

                def color_result(val):
                    if val == "승":
                        return "color: #00c853; font-weight: bold"
                    if val == "패":
                        return "color: #ff4b4b; font-weight: bold"
                    return ""

                st.dataframe(
                    df_hist.style.map(color_result, subset=["결과"]),
                    use_container_width=True, hide_index=True
                )

                if st.button("🗑️ 거래 내역 초기화", type="secondary"):
                    st.session_state.trade_history = []
                    st.rerun()

    with tab3:
        st.subheader("🔧 관리자")

        st.markdown("### ☁️ Google Sheets 연동")
        st.info("`secrets.toml`에 구글 시트 서비스 계정 정보(gspread 섹션)가 등록되어야 합니다.")

        st.markdown("#### 포트폴리오 저장")
        gs1, gs2 = st.columns(2)
        with gs1:
            if st.button("💾 내 포트폴리오 → 구글 시트 저장", use_container_width=True):
                from db import save_portfolio_to_gsheet
                port = st.session_state.get("portfolio", [])
                if port:
                    tickers_gs = [x["ticker"] for x in port]
                    price_df_gs = get_us_stock_data(tickers_gs)
                    with st.spinner("저장 중..."):
                        ok, msg_gs = save_portfolio_to_gsheet(port, price_df_gs)
                    if ok:
                        st.success(msg_gs)
                    else:
                        st.error(msg_gs)
                else:
                    st.warning("저장할 종목이 없습니다.")
        with gs2:
            if st.button("💾 AI 추천 포트폴리오 → 구글 시트 저장", use_container_width=True):
                from db import save_portfolio_to_gsheet
                port = st.session_state.get("ai_portfolio", [])
                if port:
                    tickers_gs = [x["ticker"] for x in port]
                    price_df_gs = get_us_stock_data(tickers_gs)
                    with st.spinner("저장 중..."):
                        ok, msg_gs = save_portfolio_to_gsheet(port, price_df_gs)
                    if ok:
                        st.success(msg_gs)
                    else:
                        st.error(msg_gs)
                else:
                    st.warning("저장할 종목이 없습니다.")

        st.markdown("---")
        st.markdown("#### 거래 내역 조회 & 연결 테스트")
        gt1, gt2 = st.columns(2)
        with gt1:
            if st.button("📥 구글 시트 거래내역 조회", use_container_width=True):
                from db import load_trade_history_from_gsheet
                with st.spinner("로드 중..."):
                    df_gs, msg_gs = load_trade_history_from_gsheet()
                if df_gs is not None and not df_gs.empty:
                    st.success(f"{len(df_gs)}건 조회 성공!")
                    st.dataframe(df_gs, use_container_width=True, hide_index=True)
                else:
                    st.info(msg_gs)
        with gt2:
            if st.button("🔗 연결 테스트", use_container_width=True):
                from db import test_connection_and_write
                with st.spinner("연결 테스트 중..."):
                    ok, msg_gs = test_connection_and_write()
                if ok:
                    st.success(msg_gs)
                else:
                    st.error(msg_gs)

        st.markdown("---")
        st.markdown("#### 종목 코드 검증 (KRX 전체 종목)")
        if st.button("🔍 KRX 데이터로 전체 종목 코드 검증", use_container_width=True):
            from sectors_kr import KR_SECTOR_MAP
            with st.spinner("전체 종목 로드 중... (FinanceDataReader → pykrx → KRX 순으로 시도)"):
                krx_map = get_kr_name_to_code_map()
            if not krx_map:
                st.error("전체 종목 데이터 로드 실패 (FinanceDataReader·pykrx·KRX 모두 실패).\n\n"
                         "Streamlit Cloud 서버가 한국 거래소 API에 접근할 수 없는 상태입니다.\n"
                         "잠시 후 다시 시도하거나, 아래 KIS API 개별 검증을 이용해주세요.")
            else:
                st.info(f"KRX 종목 {len(krx_map):,}개 로드 완료")
                mismatches = []
                not_found  = []
                for sector, subsectors in KR_SECTOR_MAP.items():
                    for subsector, stocks in subsectors.items():
                        for s in stocks:
                            krx_info = krx_map.get(s["name"])
                            if krx_info is None:
                                not_found.append({"종목명": s["name"], "저장코드": s.get("code",""),
                                                  "섹터": sector, "서브섹터": subsector})
                            elif krx_info["code"] != s.get("code", ""):
                                mismatches.append({
                                    "종목명": s["name"],
                                    "저장코드": s.get("code", ""),
                                    "KRX코드": krx_info["code"],
                                    "저장suffix": s.get("suffix",""),
                                    "KRX suffix": krx_info["suffix"],
                                    "섹터": sector, "서브섹터": subsector,
                                })
                total = sum(len(st_list) for subs in KR_SECTOR_MAP.values() for st_list in subs.values())
                problems = len(mismatches) + len(not_found)
                if not problems:
                    st.success(f"전체 {total}개 종목 코드 완전 일치!")
                else:
                    st.warning(f"전체 {total}개 중 문제 {problems}건 발견")
                if mismatches:
                    st.markdown("**코드 불일치** (sectors_kr.py 코드가 KRX와 다름)")
                    st.dataframe(pd.DataFrame(mismatches), use_container_width=True, hide_index=True)
                if not_found:
                    with st.expander(f"KRX 미확인 종목 {len(not_found)}건 (상장폐지·이름 상이 등)"):
                        st.dataframe(pd.DataFrame(not_found), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### 종목 코드 검증 (KIS API)")
        st.caption("약 3분 소요. 페이지를 닫지 마세요.")
        if st.button("🔍 KIS API로 섹터 종목 코드 검증", use_container_width=True):
            from sectors_kr import KR_SECTOR_MAP
            import time as _time
            all_stocks: dict = {}
            for _sec, _subs in KR_SECTOR_MAP.items():
                for _sub, _stks in _subs.items():
                    for s in _stks:
                        code = s.get("code", "")
                        if code and code not in all_stocks:
                            all_stocks[code] = {"name": s["name"], "sector": _sec, "subsector": _sub}
            mismatches, errors = [], []
            total = len(all_stocks)
            prog = st.progress(0, text=f"0 / {total} 검증 중...")
            err_placeholder = st.empty()
            for i, (code, info) in enumerate(all_stocks.items()):
                prog.progress((i + 1) / total, text=f"{i+1} / {total} — {code} {info['name']}")
                _time.sleep(0.25)  # 초당 4건 — rate limit 안전권
                kis_name, err_msg = get_kr_stock_name_kis(code)
                if kis_name is None:
                    # rate limit 오류면 2초 대기 후 재시도 1회
                    if err_msg and ("초과" in err_msg or "EGW" in err_msg or "limit" in err_msg.lower()):
                        _time.sleep(2)
                        kis_name, err_msg = get_kr_stock_name_kis(code)
                if kis_name is None:
                    errors.append({"코드": code, "저장명": info["name"], "KIS오류": err_msg})
                elif kis_name != info["name"]:
                    mismatches.append({"코드": code, "저장명": info["name"], "KIS명": kis_name,
                                       "섹터": info["sector"], "서브섹터": info["subsector"]})
            prog.empty()
            err_placeholder.empty()
            verified = total - len(errors)
            if mismatches:
                st.warning(f"불일치 {len(mismatches)}건 (검증 성공 {verified}/{total})")
                st.dataframe(pd.DataFrame(mismatches), use_container_width=True, hide_index=True)
            elif errors:
                st.info(f"불일치 없음 — 조회 실패 {len(errors)}건 포함 (검증 성공 {verified}/{total})")
            else:
                st.success(f"전체 {total}개 완전 일치!")
            if errors:
                with st.expander(f"조회 실패 {len(errors)}건"):
                    st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)

    # --- 하단 면책 조항 ---
    st.markdown("""
    <div class="disclaimer">
        <b>면책 조항 (Disclaimer):</b> 스톡시(Stockcy)에서 제공하는 모든 정보(종목 추천, 타점, AI 리포트 등)는 투자 참고용일 뿐이며, 
        실제 투자에 대한 결정 및 책임은 전적으로 사용자 본인에게 있습니다.
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
