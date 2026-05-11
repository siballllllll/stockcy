import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
try:
    from streamlit_autorefresh import st_autorefresh as _st_autorefresh
    _HAVE_AUTOREFRESH = True
except ImportError:
    _HAVE_AUTOREFRESH = False
from data import get_us_stock_data, get_us_market_indices, get_us_stock_detail, get_us_market_session
from data_kr import (get_us_prices_bulk_kis, get_kr_index_history,
                     get_kr_market_index, get_kr_stock_price,
                     get_kr_investor_trend, get_kr_volume_ranking,
                     get_kr_change_ranking, get_kr_prices_bulk,
                     get_kr_minute_chart, get_kr_daily_chart,
                     get_kr_stock_name_kis, get_kr_name_to_code_map,
                     get_kr_code_to_name_map, get_kr_major_tickers)
from ai_engine import analyze_sector_rotation
import re

def render_ai_content(text):
    """AI가 생성한 텍스트 내의 종목명(코드) 패턴을 찾아 새 창 링크로 변환하여 렌더링합니다."""
    if not text:
        return ""
    
    # 1. 국내 주식 패턴: 종목명(6자리숫자) -> [종목명](/?market=KR&code=6자리숫자)
    # 2. 미국 주식 패턴: 종목명(1~5자리대문자) -> [종목명](/?market=US&code=대문자)
    
    def replace_kr(match):
        name = match.group(1).strip()
        code = match.group(2)
        return f"<a href='/?market=KR&code={code}' target='_blank' style='color:#ff4b4b;font-weight:700;text-decoration:none;'>{name}</a>"

    def replace_us(match):
        name = match.group(1).strip()
        ticker = match.group(2)
        return f"<a href='/?market=US&code={ticker}' target='_blank' style='color:#00c853;font-weight:700;text-decoration:none;'>{name}</a>"

    # 국내: 한글/영문/숫자(6자리숫자). 종목명과 괄호 사이 공백 허용
    text = re.sub(r'([가-힣a-zA-Z0-9\s]+?)\s*\((0\d{5}|[1-9]\d{5})\)', replace_kr, text)
    # 미국: 영문(대문자티커) - 티커는 보통 1-5자 대문자
    text = re.sub(r'([가-힣a-zA-Z0-9\s]+?)\s*\(([A-Z]{1,5})\)', replace_us, text)
    
    st.markdown(text.replace("\n", "  \n"), unsafe_allow_html=True)

def render_star_toggle(market, code, name, key_suffix=""):
    """종목명 옆에 즐겨찾기 별 아이콘을 렌더링하고 토글 기능을 제공합니다."""
    from db import is_favorite, save_favorite, remove_favorite
    _is_fav = is_favorite(code)
    _label = "⭐" if _is_fav else "☆"
    # 리스트용 컴팩트 스타일 버튼
    if st.button(_label, key=f"star_{code}_{key_suffix}", help=f"{name} 즐겨찾기", 
                 use_container_width=False, type="secondary"):
        if _is_fav:
            remove_favorite(code)
        else:
            save_favorite(market, code, name)
        st.rerun()

def _get_chart_colors():
    """Return (font_color, grid_color) adapted to the current Streamlit theme."""
    try:
        _base = st.get_option("theme.base") or "dark"
    except Exception:
        _base = "dark"
    _light = (_base == "light")
    return (
        "#333333" if _light else "rgba(255,255,255,0.82)",
        "rgba(0,0,0,0.08)" if _light else "rgba(255,255,255,0.10)",
    )

def _tv_chart(symbol: str, interval: str = "D", height: int = 660) -> None:
    """TradingView Advanced Chart 위젯을 Streamlit에 렌더링 (iframe URL 방식)."""
    import urllib.parse
    if ":" not in symbol:
        symbol = f"NASDAQ:{symbol}"
    try:
        _dark = (st.get_option("theme.base") or "dark") != "light"
    except Exception:
        _dark = True
    _theme = "dark" if _dark else "light"
    _params = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": interval,
        "timezone": "Asia/Seoul",
        "theme": _theme,
        "style": "1",
        "locale": "kr",
        "enable_publishing": "false",
        "hide_top_toolbar": "false",
        "hide_legend": "false",
        "save_image": "false",
        "allow_symbol_change": "false",
        "autosize": "1",
    })
    _url = f"https://www.tradingview.com/widgetembed/?{_params}"
    st.markdown(
        f'<iframe src="{_url}" width="100%" height="{height}"'
        f' frameborder="0" scrolling="no" allowtransparency="true"'
        f' style="border-radius:12px;"></iframe>',
        unsafe_allow_html=True,
    )

def _kr_plotly_chart(code: str, interval: str = "D", height: int = 660) -> None:
    """Plotly 기반 국내 주식 차트 (TradingView 대안)"""
    with st.spinner("차트 데이터 로딩 중..."):
        if interval == "D":
            df = get_kr_daily_chart(code)
        else:
            df = get_kr_minute_chart(code)
            
        if df is None or df.empty:
            st.warning("차트 데이터를 불러올 수 없습니다.")
            return

        fig = go.Figure(data=[go.Candlestick(
            x=df['datetime'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            increasing_line_color='#ff4b4b',
            decreasing_line_color='#2b7cff'
        )])
        fig.update_layout(
            height=height,
            margin=dict(l=0, r=4, t=4, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_rangeslider_visible=False,
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=False, side="right", tickformat=",.0f"),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

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
    # selectbox 드롭다운 위치 보정 (zoom 오프셋)
    st.markdown("""<style>
        [data-baseweb="popover"]{zoom:1.3!important;transform-origin:top left!important}
    </style>""", unsafe_allow_html=True)
    st.markdown("""
        <style>
        /* ── 77% 축소 — zoom + 높이 보정으로 클리핑 방지 ── */
        html { zoom: 0.77; font-size: 19px; }
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {
            height: calc(100vh / 0.77) !important;
            min-height: calc(100vh / 0.77) !important;
            overflow-y: auto !important;
        }
        [data-testid="stMainBlockContainer"] {
            padding: 0.5rem 1rem 2rem !important;
            max-width: 100% !important;
        }

        /* ── Streamlit 기본 헤더(share·별·메뉴) 숨김 ── */
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"] {
            display: none !important;
        }

        /* ══════════════════════════════════════════════════════════
           다크 모드 — 기본값
           핵심 원리: 카드가 배경보다 충분히 밝아야 입체감이 생김
        ══════════════════════════════════════════════════════════ */
        :root {
            --sc-divider:       rgba(255,255,255,0.10);
            --sc-divider-str:   rgba(255,255,255,0.20);
            /* 카드: 배경보다 확실히 밝게 */
            --sc-card-bg:       #1e2130;
            --sc-card-bg-sm:    #1a1d2e;
            --sc-card-border:   rgba(255,255,255,0.13);
            --sc-card-hi:       rgba(255,255,255,0.20);  /* 상단 하이라이트 */
            /* 그림자: 카드 가장자리 주변을 더 어둡게 → 카드가 떠 보임 */
            --sc-shadow-card:
                0 0 0 1px rgba(0,0,0,0.40),
                0 4px 16px rgba(0,0,0,0.60),
                0 1px 3px  rgba(0,0,0,0.50),
                inset 0 1px 0 rgba(255,255,255,0.12);
            --sc-shadow-sm:
                0 0 0 1px rgba(0,0,0,0.35),
                0 2px 8px  rgba(0,0,0,0.50),
                inset 0 1px 0 rgba(255,255,255,0.09);
            /* 텍스트 */
            --sc-text-muted:    #a0a4b8;
            --sc-text-subtle:   #6b7080;
            /* 태그/pill */
            --sc-pill-bg:       rgba(255,255,255,0.09);
            --sc-pill-color:    #c0c4d8;
            --sc-row-hover:     rgba(255,255,255,0.05);
            /* 네비 */
            --sc-nav-inactive:  #888;
            --sc-nav-hover:     #ddd;
            --sc-nav-hover-bg:  rgba(255,255,255,0.05);
            /* 마켓 버튼 */
            --sc-mkt-border:    rgba(255,255,255,0.16);
            --sc-mkt-inactive:  #777;
            --sc-mkt-act-bg:    rgba(255,255,255,0.16);
            --sc-mkt-act-fg:    #fff;
            --sc-mkt-act-bdr:   rgba(255,255,255,0.32);
            /* 일반 버튼 */
            --sc-btn-border:    rgba(255,255,255,0.14);
            --sc-btn-pri-bg:    rgba(255,255,255,0.13);
            --sc-btn-pri-fg:    #f0f0f0;
            --sc-btn-hover-bg:  rgba(255,255,255,0.09);
            /* 섹션 구분 강조색 */
            --sc-accent:        #ff9800;
        }

        /* ══════════════════════════════════════════════════════════
           라이트 모드 — CSS 변수 재정의
           html.sc-light 클래스만 사용 (OS prefers-color-scheme 무시)
           → syncTheme() JS가 Streamlit 실제 테마를 감지해 클래스 부여
        ══════════════════════════════════════════════════════════ */
        html.sc-light {
            --sc-divider:       rgba(0,0,0,0.10);
            --sc-divider-str:   rgba(0,0,0,0.18);
            --sc-card-bg:       #ffffff;
            --sc-card-bg-sm:    #f4f5f8;
            --sc-card-border:   rgba(0,0,0,0.08);
            --sc-card-hi:       #ffffff;
            --sc-shadow-card:
                0 0 0 1px rgba(0,0,0,0.07),
                0 4px 20px rgba(0,0,0,0.13),
                0 1px 4px  rgba(0,0,0,0.09);
            --sc-shadow-sm:
                0 0 0 1px rgba(0,0,0,0.05),
                0 2px 10px rgba(0,0,0,0.10),
                0 1px 2px  rgba(0,0,0,0.06);
            --sc-text-muted:    #4a4e5c;
            --sc-text-subtle:   #6b7080;
            --sc-pill-bg:       rgba(0,0,0,0.07);
            --sc-pill-color:    #3a3d4a;
            --sc-row-hover:     rgba(0,0,0,0.04);
            --sc-nav-inactive:  #4a4e5c;
            --sc-nav-hover:     #111;
            --sc-nav-hover-bg:  rgba(0,0,0,0.04);
            --sc-mkt-border:    rgba(0,0,0,0.15);
            --sc-mkt-inactive:  #4a4e5c;
            --sc-mkt-act-bg:    rgba(0,0,0,0.08);
            --sc-mkt-act-fg:    #111;
            --sc-mkt-act-bdr:   rgba(0,0,0,0.24);
            --sc-btn-border:    rgba(0,0,0,0.13);
            --sc-btn-pri-bg:    rgba(0,0,0,0.07);
            --sc-btn-pri-fg:    #111;
            --sc-btn-hover-bg:  rgba(0,0,0,0.05);
            --sc-accent:        #e65100;
        }

        /* ══════════════════════════════════════════════════════════
           라이트 모드 — 페이지 배경 강제 회색
           + 인라인 스타일 밝은 텍스트 → 어두운 색으로 일괄 덮어쓰기
        ══════════════════════════════════════════════════════════ */
        html.sc-light .stApp,
        html.sc-light [data-testid="stAppViewContainer"],
        html.sc-light [data-testid="stMain"],
        html.sc-light [data-testid="stMainBlockContainer"],
        html.sc-light section.main .block-container,
        html.sc-light .main .block-container {
            background-color: #eef0f5 !important;
        }

        /* 흰/밝은 텍스트(다크모드용) → 라이트모드에서 어두운 색으로 */
        html.sc-light [style*="color:#eee"],html.sc-light [style*="color: #eee"],
        html.sc-light [style*="color:#eeeeee"],html.sc-light [style*="color:#f0f0f0"],
        html.sc-light [style*="color:#fafafa"],
        html.sc-light [style*="color:#fff"],html.sc-light [style*="color: #fff"],
        html.sc-light [style*="color:#ffffff"],
        html.sc-light [style*="color:white"],html.sc-light [style*="color: white"],
        html.sc-light [style*="color:#ddd"],html.sc-light [style*="color:#ccc"] {
            color: #1a1d2a !important;
        }
        html.sc-light [style*="color:#aaa"],html.sc-light [style*="color:#bbb"],
        html.sc-light [style*="color:#999"],html.sc-light [style*="color:#888"],
        html.sc-light [style*="color:#a0a4b8"],html.sc-light [style*="color:#c0c4d8"] {
            color: #3a3d4a !important;
        }
        html.sc-light [style*="color:#777"],html.sc-light [style*="color:#666"],
        html.sc-light [style*="color:#555"],html.sc-light [style*="color:#6b7080"] {
            color: #2a2d3a !important;
        }
        html.sc-light .stMarkdown,
        html.sc-light .stMarkdown p,
        html.sc-light [data-testid="stText"] { color: #1a1d2a; }
        html.sc-light [data-testid="stExpander"] summary p { color: #1a1d2a !important; }

        /* ══════════════════════════════════════════════════════════
           Streamlit 컨테이너 — 상하 여백 최소화
        ══════════════════════════════════════════════════════════ */
        .stMainBlockContainer, section.main .block-container {
            padding-top: 0 !important;
            padding-bottom: 0.5rem !important;
        }
        /* 최상단 element-container 들 (헤더~티커) 사이 여백 제거 */
        [data-testid="stVerticalBlock"] > [data-testid="element-container"] {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        /* Streamlit expander에 카드 느낌 */
        [data-testid="stExpander"] {
            border: 1px solid var(--sc-card-border) !important;
            border-radius: 12px !important;
            box-shadow: var(--sc-shadow-sm) !important;
            overflow: hidden !important;
        }
        /* dataframe 컨테이너 */
        [data-testid="stDataFrame"] {
            border-radius: 10px !important;
            overflow: hidden !important;
            box-shadow: var(--sc-shadow-sm) !important;
        }

        /* ══════════════════════════════════════════════════════════
           글로벌 hr — 전체 구분선
        ══════════════════════════════════════════════════════════ */
        hr {
            border: none !important;
            border-top: 1px solid var(--sc-divider) !important;
        }

        /* ── 색상 ── */
        .up-kr   { color: #ff4b4b; font-weight: 700; }
        .down-kr { color: #2b7cff; font-weight: 700; }
        .up-us   { color: #00c853; font-weight: 700; }
        .down-us { color: #ff4b4b; font-weight: 700; }

        /* ── 버튼 ── */
        div[data-testid="stButton"] > button {
            border-radius: 20px !important;
            font-size: 0.82rem !important;
            padding: 4px 14px !important;
            border: 1px solid var(--sc-btn-border) !important;
            transition: all 0.15s ease !important;
        }
        div[data-testid="stButton"] > button[kind="primary"] {
            background: var(--sc-btn-pri-bg) !important;
            color: var(--sc-btn-pri-fg) !important;
            border-color: var(--sc-divider-str) !important;
        }
        div[data-testid="stButton"] > button:hover {
            background: var(--sc-btn-hover-bg) !important;
            border-color: var(--sc-divider-str) !important;
        }

        /* ══════════════════════════════════════════════════════════
           카드 클래스 — 진짜 입체감
           핵심: shadow 레이어 3개 + 상단 하이라이트
        ══════════════════════════════════════════════════════════ */
        .toss-card {
            background: var(--sc-card-bg);
            border: 1px solid var(--sc-card-border);
            border-top: 1px solid var(--sc-card-hi);
            border-radius: 14px;
            padding: 14px 16px;
            margin: 6px 0;
            box-shadow: var(--sc-shadow-card);
        }
        .toss-card-sm {
            background: var(--sc-card-bg-sm);
            border: 1px solid var(--sc-card-border);
            border-top: 1px solid var(--sc-card-hi);
            border-radius: 10px;
            padding: 8px 12px;
            margin: 3px 0;
            box-shadow: var(--sc-shadow-sm);
        }

        /* ── elevation 유틸리티 (인라인 스타일 위에 shadow 강제 적용) ── */
        .sc-card {
            box-shadow: var(--sc-shadow-card) !important;
            border-top-color: var(--sc-card-hi) !important;
        }
        .sc-card-sm {
            box-shadow: var(--sc-shadow-sm) !important;
            border-top-color: var(--sc-card-hi) !important;
        }

        /* ── 지수 배너 ── */
        .index-banner {
            display: flex; gap: 28px; align-items: center;
            padding: 8px 4px 4px 2px;
        }
        .index-item { display: flex; flex-direction: column; }
        .index-name { font-size: 0.7rem; color: var(--sc-text-muted); letter-spacing: 0.04em; }
        .index-val  { font-size: 1.05rem; font-weight: 700; line-height: 1.2; }
        .index-chg  { font-size: 0.72rem; margin-top: 1px; }

        /* ── 종목 행 hover ── */
        .stock-row:hover { background: var(--sc-row-hover); border-radius: 8px; }

        /* ── 섹터 태그 ── */
        .sector-pill {
            display: inline-block;
            background: var(--sc-pill-bg);
            border-radius: 20px;
            padding: 2px 10px;
            font-size: 0.72rem;
            color: var(--sc-pill-color);
            margin: 1px;
        }

        /* ── 구분선 ── */
        .toss-divider {
            border: none;
            border-top: 1px solid var(--sc-divider);
            margin: 8px 0;
        }
        /* 섹션 간 강한 구분선 */
        .sc-section-divider {
            border: none;
            border-top: 2px solid var(--sc-divider-str);
            margin: 18px 0;
        }

        /* ══════════════════════════════════════════════════════════
           섹션 헤더 — 오렌지 왼쪽 바 + 배경 블록으로 구역 명확히
        ══════════════════════════════════════════════════════════ */
        .sc-section-label {
            display: inline-block;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--sc-accent);
            border-left: 3px solid var(--sc-accent);
            padding: 2px 0 2px 8px;
            margin: 16px 0 8px 0;
        }

        /* ── 네비 탭 버튼 — 컴팩트 ── */
        div[data-testid="stButton"] > button[data-navbtn] {
            background: transparent !important;
            border: none !important;
            border-bottom: 2px solid transparent !important;
            border-radius: 4px 4px 0 0 !important;
            font-size: 0.72rem !important;
            font-weight: 500 !important;
            color: var(--sc-nav-inactive) !important;
            padding: 3px 6px !important;
            transition: color 0.15s, border-color 0.15s !important;
            width: 100% !important;
            box-shadow: none !important;
            white-space: nowrap !important;
        }
        div[data-testid="stButton"] > button[data-navbtn]:hover {
            color: var(--sc-nav-hover) !important;
            background: var(--sc-nav-hover-bg) !important;
        }
        div[data-testid="stButton"] > button[data-navbtn="active"] {
            color: #ff9800 !important;
            font-weight: 700 !important;
            border-bottom: 2px solid #ff9800 !important;
            background: rgba(255,152,0,0.08) !important;
        }

        /* ── 마켓 pill 버튼 — 컴팩트 ── */
        div[data-testid="stButton"] > button[data-mktbtn] {
            background: transparent !important;
            border: 1px solid var(--sc-mkt-border) !important;
            border-radius: 20px !important;
            font-size: 0.68rem !important;
            color: var(--sc-mkt-inactive) !important;
            padding: 2px 7px !important;
            transition: all 0.15s !important;
            box-shadow: none !important;
            white-space: nowrap !important;
        }
        div[data-testid="stButton"] > button[data-mktbtn]:hover {
            color: var(--sc-nav-hover) !important;
            border-color: var(--sc-divider-str) !important;
        }
        div[data-testid="stButton"] > button[data-mktbtn="active"] {
            background: var(--sc-mkt-act-bg) !important;
            border-color: var(--sc-mkt-act-bdr) !important;
            color: var(--sc-mkt-act-fg) !important;
            font-weight: 700 !important;
        }

        .disclaimer {
            font-size: 0.78rem;
            color: var(--sc-text-subtle);
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid var(--sc-divider);
        }

        /* ── iframe 여백 전면 제거 ── */
        /* Streamlit은 components.html() 마다 element-container div를 감싸고
           거기에 기본 margin을 추가함 → 전부 0으로 */
        [data-testid="stIFrame"] { margin: 0 !important; padding: 0 !important; }
        [data-testid="element-container"]:has(iframe) {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            line-height: 0 !important;
        }

        /* JS 주입용 1px iframe — 완전히 눈에 안 보이게, 공간도 최소로 */
        iframe[height="1"] {
            display: block !important;
            height: 1px !important;
            max-height: 1px !important;
            margin: -8px 0 -8px 0 !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }

        /* Streamlit 기본 element 사이 여백 완화 (상단 티커 영역만) */
        [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"]
            > [data-testid="element-container"]:nth-child(-n+6) {
            margin-bottom: 0 !important;
        }

        /* Plotly 차트 너비 강제 (html zoom 보정) */
        [data-testid="stPlotlyChart"],
        [data-testid="stPlotlyChart"] > div {
            width: 100% !important;
            min-width: 0 !important;
            flex: 1 1 auto !important;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 세션 상태 초기화 ---
def init_session_state():
    if "market" not in st.session_state:
        st.session_state.market = "국내 주식 🇰🇷"
    if "kr_mode" not in st.session_state:
        st.session_state.kr_mode = "🎯 AI 타점 보드"
    if "us_mode" not in st.session_state:
        st.session_state.us_mode = "🎯 AI 타점 보드"
    
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

def show_favorites_center():
    st.markdown('### ⭐ AI 즐겨찾기 센터')
    st.markdown('<p style="font-size:0.85rem;color:#888">관심 종목의 실시간 시세와 AI 매수 타이밍을 한눈에 관리합니다.</p>', unsafe_allow_html=True)
    
    from db import load_favorites, remove_favorite
    favs, msg = load_favorites()
    
    if not favs:
        st.info('아직 등록된 즐겨찾기 종목이 없습니다. 종목 상세 페이지에서 ⭐ 버튼을 눌러 등록하세요!')
        return

    # 실시간 시세 업데이트
    from data_kr import get_kr_stock_price
    from data import get_us_prices_bulk
    
    # 3열 레이아웃
    rows = [favs[i:i + 3] for i in range(0, len(favs), 3)]
    
    for row in rows:
        cols = st.columns(3)
        for i, fav in enumerate(row):
            with cols[i]:
                with st.container(border=True):
                    mkt = fav.get('시장', '국내')
                    ticker = fav.get('티커', '')
                    name = fav.get('종목명', '')
                    
                    # 시세 조회
                    price, pct = 0, 0
                    if mkt == '국내':
                        p_data = get_kr_stock_price(ticker)
                        price = p_data.get('price', 0)
                        pct = p_data.get('change_pct', 0)
                        price_str = f'₩{price:,}'
                    else:
                        p_map = get_us_prices_bulk((ticker,))
                        p_data = p_map.get(ticker, {"price": 0, "change_pct": 0})
                        price = p_data.get('price', 0)
                        pct = p_data.get('change_pct', 0)
                        price_str = f'${price:,.2f}'
                    
                    color = "#ff4b4b" if pct > 0 else "#00c853" if pct < 0 else "#888"
                    st.markdown(f"**{name}** ({ticker})")
                    st.markdown(f"<h3 style='margin:0;color:{color}'>{price_str} <small>({pct:+.2f}%)</small></h3>", unsafe_allow_html=True)
                    
                    # AI 타이밍 가이드 (버튼)
                    if st.button('🤖 AI 전략', key=f'fav_ai_{ticker}', use_container_width=True):
                        with st.spinner('분석 중...'):
                            from ai_engine import analyze_stock_theme_position
                            # 팩트 수집
                            investor_data = []
                            if mkt == '국내':
                                try:
                                    from data_kr import get_kr_investor_trend
                                    investor_data = get_kr_investor_trend(ticker)
                                except: pass
                            
                            res = analyze_stock_theme_position(
                                ticker, name, p_data, investor_data, "관심섹터", 
                                [{"name": name, "code": ticker, "change_pct": pct}]
                            )
                            
                            if isinstance(res, dict) and "error" in res:
                                st.error(f"분석 오류: {res['error']}")
                            else:
                                st.markdown("---")
                                pos = res.get('position', '분석불가')
                                timing = res.get('entry_timing', '-')
                                reason = res.get('entry_reason', '-')
                                st.markdown(f"**📍 포지션:** {pos}")
                                st.markdown(f"**⏱ 타이밍:** `{timing}`")
                                st.info(f"**💡 전략:** {reason}")
                                with st.expander("📊 상세 분석 (차트/수급/패턴)"):
                                    st.markdown(f"**수급분석:** {res.get('supply_analysis','-')}")
                                    st.markdown(f"**차트패턴:** {res.get('chart_pattern','-')}")
                                    st.markdown(f"**매수타점:** {res.get('buy_target','-')} | **목표가:** {res.get('sell_target','-')}")
                    
                    if st.button('🗑️ 삭제', key=f'fav_del_{ticker}', use_container_width=True):
                        ok, dmsg = remove_favorite(str(ticker))
                        if ok: 
                            st.success(dmsg)
                            st.rerun()
                        else: st.error(dmsg)

def main():
    # ── URL 파라미터 처리 (종목 즉시 이동) ──────────────────────────────
    _qp = st.query_params
    if "market" in _qp and "code" in _qp:
        _q_mkt = _qp.get("market")
        _q_code = _qp.get("code")
        # 파라미터 소모 (한 번만 실행되도록)
        st.query_params.clear()
        
        if _q_mkt == "KR":
            st.session_state.market = "국내 주식 🇰🇷"
            st.session_state.kr_mode = "📊 일반 주식 검색"
            st.session_state.kr_selected_code = _q_code
        elif _q_mkt == "US":
            st.session_state.market = "미국 주식 🇺🇸"
            st.session_state.us_mode = "📊 일반 주식 검색"
            st.session_state.us_selected_ticker = _q_code
        st.rerun()

    if _HAVE_AUTOREFRESH:
        _st_autorefresh(interval=60000, limit=None, key="stockcy_refresh")
    init_session_state()
    inject_custom_css()
    
    _is_kr_nav = "국내" in st.session_state.market
    _nav_mode_key = "kr_mode" if _is_kr_nav else "us_mode"

    # ── 상단 네비게이션 바 (Streamlit 버튼 + JS 스타일링) ─────────────────
    _nav_cur_mode = st.session_state.get(_nav_mode_key, "🎯 AI 타점 보드")
    _nav_sig_k = "_kr_sig_count_last" if _is_kr_nav else "_us_sig_count_last"
    _nav_sig_n = st.session_state.get(_nav_sig_k, 0)
    _picks_label = f"🎯 타점보드" + (f" {_nav_sig_n}" if _nav_sig_n > 0 else "")

    _hdr_l, _hn1, _hn2, _hn3, _hn5, _hn4, _sp, _hm1, _hm2, _hset, _hcache = st.columns(
        [0.85, 0.55, 0.55, 0.55, 0.55, 0.45, 1.35, 0.75, 0.75, 0.4, 0.4], gap="small"
    )
    with _hdr_l:
        st.markdown(
            "<p style='margin:6px 0 0 0;font-size:1.05rem;font-weight:800;"
            "letter-spacing:-0.5px;white-space:nowrap'>📈 Stockcy</p>",
            unsafe_allow_html=True,
        )
    with _hn1:
        if st.button(_picks_label, key="top_nav_picks",
                     type="primary" if _nav_cur_mode == "🎯 AI 타점 보드" else "secondary",
                     use_container_width=True):
            st.session_state[_nav_mode_key] = "🎯 AI 타점 보드"
            st.rerun()
    with _hn2:
        if st.button("📊 종목검색", key="top_nav_search",
                     type="primary" if _nav_cur_mode == "📊 일반 주식 검색" else "secondary",
                     use_container_width=True):
            st.session_state[_nav_mode_key] = "📊 일반 주식 검색"
            st.rerun()
    with _hn3:
        if st.button("🔥 섹터분석", key="top_nav_sector",
                     type="primary" if _nav_cur_mode == "🔥 오늘의 이슈 섹터" else "secondary",
                     use_container_width=True):
            st.session_state[_nav_mode_key] = "🔥 오늘의 이슈 섹터"
            st.rerun()
    with _hn5:
        if st.button("⭐ 즐겨찾기", key="top_nav_fav",
                     type="primary" if _nav_cur_mode == "⭐ 즐겨찾기 관리" else "secondary",
                     use_container_width=True):
            st.session_state[_nav_mode_key] = "⭐ 즐겨찾기 관리"
            st.rerun()
    with _hn4:
        if st.button("📰 브리핑", key="top_nav_briefing", use_container_width=True):
            show_daily_briefing()
    with _hm1:
        if st.button("🇰🇷 국내", key="top_mkt_kr",
                     type="primary" if _is_kr_nav else "secondary",
                     use_container_width=True):
            if not _is_kr_nav:
                st.session_state.market = "국내 주식 🇰🇷"
                st.rerun()
    with _hm2:
        if st.button("🇺🇸 미국", key="top_mkt_us",
                     type="primary" if not _is_kr_nav else "secondary",
                     use_container_width=True):
            if _is_kr_nav:
                st.session_state.market = "미국 주식 🇺🇸"
                st.rerun()
    with _hset:
        if st.button("⚙️", key="btn_settings_menu", use_container_width=True, help="설정 / 테마 변경"):
            st.session_state["_sc_open_native_menu"] = True
            st.rerun()
    with _hcache:
        if st.button("🔄", key="btn_cache_clear", use_container_width=True, help="캐시 초기화"):
            st.cache_data.clear()
            st.rerun()

    # ── ⚙️ 버튼 → Streamlit 기본 메뉴 열기 (JS로 햄버거 버튼 클릭) ──────
    if st.session_state.pop("_sc_open_native_menu", False):
        import streamlit.components.v1 as _cmp_menu
        _cmp_menu.html("""<script>
(function(){
  var doc = window.parent.document;
  setTimeout(function(){
    /* Streamlit 기본 메뉴(햄버거) 버튼 — 숨겨져 있어도 DOM에 존재 */
    var btn = doc.querySelector('[data-testid="stMainMenu"] button');
    if (!btn) {
      /* 헤더 내 마지막 버튼으로 폴백 */
      var hdr = doc.querySelector('[data-testid="stHeader"]');
      if (hdr) {
        var btns = hdr.querySelectorAll('button');
        if (btns.length) btn = btns[btns.length - 1];
      }
    }
    if (btn) { btn.click(); }
  }, 150);
})();
</script>""", height=1)

    st.markdown("<hr class='toss-divider' style='margin:2px 0'>", unsafe_allow_html=True)

    import streamlit.components.v1 as components
    # JS: 버튼에 data 속성 부여 → CSS가 탭/pill 스타일로 렌더링
    # height=1: 최소 높이로 iframe 렌더링 보장 (height=0 은 일부 환경에서 스크립트 미실행)
    components.html("""<style>body{margin:0;overflow:hidden}</style><script>
(function(){
  var NAV = ['타점보드','종목검색','섹터분석','브리핑'];
  var MKT = ['🇰🇷','🇺🇸'];

  function isActive(b){
    return b.getAttribute('kind')==='primary'
        || b.getAttribute('data-testid')==='baseButton-primary';
  }

  /* Streamlit 테마 감지 → 부모 <html>에 sc-light 클래스 토글
     Streamlit이 :root에 주입하는 --background-color CSS 변수를 직접 읽어 판단.
     OS prefers-color-scheme 완전 무시, Streamlit 활성 테마만 따름. */
  function syncTheme(){
    try{
      var doc = window.parent.document;
      var root = doc.documentElement;
      var isLight = false;

      /* Streamlit이 :root에 직접 설정하는 CSS 변수 */
      var bg = getComputedStyle(root).getPropertyValue('--background-color').trim();
      if(bg){
        var m = bg.match(/\d+/g);
        if(m && m.length >= 3){
          /* rgb/rgba: 평균 150 초과 → 라이트 */
          isLight = (parseInt(m[0])+parseInt(m[1])+parseInt(m[2]))/3 > 150;
        } else {
          /* hex: c이상(#cde, #eee, #fff 등) → 라이트 */
          isLight = /^#[c-fC-F]/i.test(bg) || bg==='white';
        }
      } else {
        /* 폴백: body 배경 직접 확인 */
        var m2 = getComputedStyle(doc.body).backgroundColor.match(/\d+/g);
        if(m2 && m2.length >= 3){
          isLight = (parseInt(m2[0])+parseInt(m2[1])+parseInt(m2[2]))/3 > 150;
        }
      }

      root.classList.toggle('sc-light', isLight);
    }catch(e){}
  }

  function tag(){
    try{
      var doc = window.parent.document;
      doc.querySelectorAll('button').forEach(function(b){
        var t = (b.textContent||'').trim();
        var isNav = NAV.some(function(k){return t.indexOf(k)>=0;});
        var isMkt = MKT.some(function(k){return t.indexOf(k)>=0;});
        if(isNav) b.setAttribute('data-navbtn', isActive(b)?'active':'1');
        if(isMkt) b.setAttribute('data-mktbtn', isActive(b)?'active':'1');
      });
    }catch(e){}
  }

  /* Plotly 차트 너비: html zoom(0.77)으로 getBoundingClientRect가 줄어든 값을 반환하므로
     offsetWidth(CSS 레이아웃 픽셀, zoom 미반영)로 직접 relayout 호출 */
  function fixPlotlyWidths(){
    try{
      var doc=window.parent.document;
      var P=window.parent.Plotly;
      if(!P) return;
      doc.querySelectorAll('.js-plotly-plot').forEach(function(plot){
        var ctr=plot.closest('[data-testid="stPlotlyChart"]');
        if(!ctr) return;
        var w=ctr.offsetWidth;
        if(w>100) P.relayout(plot,{width:w});
      });
    }catch(e){}
  }
  setTimeout(fixPlotlyWidths,400);
  setTimeout(fixPlotlyWidths,1200);
  setTimeout(fixPlotlyWidths,3000);

  syncTheme(); tag();
  setInterval(function(){ syncTheme(); tag(); }, 300);
})();
</script>""", height=1, scrolling=False)

    # ── 상단 슬라이딩 티커 (KR/US 조건부) ──────────────────────────────
    def _ticker_pill(label, price_str, pct, is_index=False):
        c     = "#ff4b4b" if pct >= 0 else "#2b7cff"
        bg    = "rgba(255,75,75,0.14)" if pct >= 0 else "rgba(43,124,255,0.14)"
        arrow = "▲" if pct >= 0 else "▼"
        sign  = "+" if pct >= 0 else ""
        cls   = "pill pill-idx" if is_index else "pill"
        return (
            f'<span class="{cls}">'
            f'<span class="pl">{label}</span>'
            f'<span class="pp">{price_str}</span>'
            f'<span style="font-size:0.88rem;color:{c};font-weight:700;'
            f'background:{bg};border-radius:10px;padding:2px 8px">'
            f'{arrow} {sign}{pct:.2f}%</span>'
            f'</span>'
        )

    def _render_scroll_ticker(items, speed=50):
        body = "".join(items)
        components.html(f"""
        <style>
          :root {{
            --tk-wrap-bg:  rgba(255,255,255,0.02);
            --tk-wrap-bdr: rgba(255,255,255,0.08);
            --tk-pill-bg:  rgba(255,255,255,0.05);
            --tk-pill-idx: rgba(255,255,255,0.09);
            --tk-pill-bdr: rgba(255,255,255,0.11);
            --tk-label:    #bbb;
            --tk-price:    #f0f0f0;
          }}
          body {{ margin:0; overflow:hidden; background:transparent; }}
          .wrap {{
            background: var(--tk-wrap-bg);
            border: 1px solid var(--tk-wrap-bdr);
            border-radius:8px; overflow:hidden;
            box-sizing:border-box;
            padding:4px 0; height:75px; display:flex; align-items:center;
          }}
          .track {{
            display:inline-flex; align-items:center; white-space:nowrap;
            animation:krtick {speed}s linear infinite;
          }}
          .pill {{
            display:inline-flex; align-items:center; gap:9px;
            background:var(--tk-pill-bg);
            border:1px solid var(--tk-pill-bdr);
            border-radius:20px; padding:5px 15px; margin:0 8px;
          }}
          .pill-idx {{ background:var(--tk-pill-idx); }}
          .pl {{ font-size:0.96rem; color:var(--tk-label); font-weight:600; }}
          .pp {{ font-size:1.05rem; color:var(--tk-price); font-weight:700; }}
          @keyframes krtick {{
            from {{ transform: translateX(0); }}
            to   {{ transform: translateX(-50%); }}
          }}
        </style>
        <div class="wrap">
          <div class="track">{body}{body}</div>
        </div>
        <script>
        (function(){{
          var DARK = {{
            '--tk-wrap-bg':  'rgba(255,255,255,0.02)',
            '--tk-wrap-bdr': 'rgba(255,255,255,0.08)',
            '--tk-pill-bg':  'rgba(255,255,255,0.05)',
            '--tk-pill-idx': 'rgba(255,255,255,0.09)',
            '--tk-pill-bdr': 'rgba(255,255,255,0.11)',
            '--tk-label':    '#bbb',
            '--tk-price':    '#f0f0f0'
          }};
          var LIGHT = {{
            '--tk-wrap-bg':  'rgba(0,0,0,0.03)',
            '--tk-wrap-bdr': 'rgba(0,0,0,0.12)',
            '--tk-pill-bg':  'rgba(0,0,0,0.05)',
            '--tk-pill-idx': 'rgba(0,0,0,0.09)',
            '--tk-pill-bdr': 'rgba(0,0,0,0.12)',
            '--tk-label':    '#444',
            '--tk-price':    '#111'
          }};
          function applyTheme(){{
            try{{
              var isLight = window.parent.document.documentElement
                              .classList.contains('sc-light');
              var vars = isLight ? LIGHT : DARK;
              var root = document.documentElement;
              for(var k in vars) root.style.setProperty(k, vars[k]);
              document.body.style.background = isLight
                ? 'rgba(240,242,246,0)' : 'transparent';
            }}catch(e){{}}
          }}
          applyTheme();
          setInterval(applyTheme, 400);
        }})();
        </script>""", height=80)

    _is_us_mode = "미국" in st.session_state.get("market", "")

    if _is_us_mode:
        # ── 미국 주식 슬라이딩 티커 ──
        try:
            _us_tick_data = get_kr_change_ranking_us() or []
        except Exception:
            _us_tick_data = []
        _us_idx_data = get_us_market_indices() or {}
        _us_tick_items = []
        for _in, _id in [("S&P 500", _us_idx_data.get("S&P 500", {})),
                          ("NASDAQ",  _us_idx_data.get("NASDAQ", {})),
                          ("DOW",     _us_idx_data.get("DOW", {}))]:
            _iv = _id.get("price", 0)
            _ip = _id.get("change_pct", 0)
            if _iv > 0:
                _us_tick_items.append(_ticker_pill(_in, f"{_iv:,.2f}", _ip, is_index=True))
        for _t in _us_tick_data[:18]:
            _us_tick_items.append(_ticker_pill(
                _t.get("name", _t.get("티커", _t.get("ticker", ""))),
                f'${_t.get("현재가($)", _t.get("price", 0)):,.2f}',
                _t.get("등락률(%)", _t.get("change_pct", 0))
            ))
        # 데이터 없을 때도 티커 바가 사라지지 않도록 폴백 아이템 추가
        if not _us_tick_items:
            for _fb in ["NVDA", "TSLA", "AAPL", "MSFT", "META", "AMZN"]:
                _us_tick_items.append(_ticker_pill(_fb, "—", 0.0))
        _render_scroll_ticker(_us_tick_items, speed=60)
    else:
        # ── 국내 주식 슬라이딩 티커 ──
        _kr_idx   = get_kr_market_index() or {}
        _kr_ticks = get_kr_major_tickers()
        _kr_items = []
        for _iname, _id in _kr_idx.items():
            _ip = _id.get("change_pct", 0)
            _iv = _id.get("index", 0)
            _kr_items.append(_ticker_pill(_iname, f"{_iv:,.2f}", _ip, is_index=True))
        for _t in _kr_ticks:
            _kr_items.append(_ticker_pill(_t["name"], f'₩{_t["price"]:,}', _t["pct"]))
        if not _kr_items:
            _kr_items.append(_ticker_pill("KOSPI", "—", 0.0, is_index=True))
        _render_scroll_ticker(_kr_items, speed=50)

    # ── 미국·글로벌 TradingView 티커 ────────────────────────────────────
    components.html("""
    <style>body{margin:0;padding:0;overflow:hidden}
    .tradingview-widget-container{margin:0;padding:0;height:75px}
    .tradingview-widget-container__widget{height:75px}
    </style>
    <div class="tradingview-widget-container">
      <div id="tv-widget-target"></div>
    </div>
    <script>
    (function(){
      var isLight = false;
      try { isLight = window.parent.document.documentElement.classList.contains('sc-light'); } catch(e){}
      var colorTheme = isLight ? "light" : "dark";
      var s = document.createElement("script");
      s.type = "text/javascript";
      s.src = "https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js";
      s.async = true;
      s.innerHTML = JSON.stringify({
        "symbols": [
          {"description":"S&P500","proName":"AMEX:SPY"},
          {"description":"나스닥100","proName":"NASDAQ:QQQ"},
          {"description":"다우존스","proName":"AMEX:DIA"},
          {"description":"원/달러","proName":"FX_IDC:USDKRW"},
          {"description":"엔비디아","proName":"NASDAQ:NVDA"},
          {"description":"애플","proName":"NASDAQ:AAPL"},
          {"description":"테슬라","proName":"NASDAQ:TSLA"},
          {"description":"마이크로소프트","proName":"NASDAQ:MSFT"},
          {"description":"메타","proName":"NASDAQ:META"},
          {"description":"구글","proName":"NASDAQ:GOOGL"},
          {"description":"아마존","proName":"NASDAQ:AMZN"},
          {"description":"금","proName":"TVC:GOLD"},
          {"description":"WTI유가","proName":"TVC:USOIL"},
          {"description":"비트코인","proName":"CRYPTO:BTCUSD"},
          {"description":"이더리움","proName":"CRYPTO:ETHUSD"}
        ],
        "showSymbolLogo": false,
        "isTransparent": true,
        "displayMode": "compact",
        "colorTheme": colorTheme,
        "locale": "kr"
      });
      document.querySelector(".tradingview-widget-container").appendChild(s);
    })();
    </script>""", height=75)
    
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
                ("kr_selected_pick_idx", 0),
            ]:
                if _k not in st.session_state:
                    st.session_state[_k] = _v

            kr_mode = st.session_state.kr_mode

            selected_code_kr = st.session_state.kr_selected_code

            # ── 신호 스캔 (모드 무관, 항상 실행 → 네비 배지용) ──────────────
            if _HAVE_AUTOREFRESH:
                _st_autorefresh(interval=180_000, key="kr_signal_autorefresh")

            def _quick_signal_scan() -> int:
                try:
                    from ai_engine import _compute_prebreakout_signals
                    _qvol = get_kr_volume_ranking() or []
                    _qchg = (get_kr_change_ranking("J") or []) + (get_kr_change_ranking("Q") or [])
                    _qpre, _ = _compute_prebreakout_signals(_qvol, _qchg)
                    return sum(1 for x in _qpre if x.get("_signal", {}).get("signal_score", 0) >= 3)
                except Exception:
                    return 0

            _sig_count_key = "_kr_sig_count_last"
            _sig_ts_key    = "_kr_sig_ts_last"
            _new_count = _quick_signal_scan()
            st.session_state[_sig_count_key] = _new_count
            st.session_state[_sig_ts_key] = (datetime.now() + timedelta(hours=9)).strftime("%H:%M")
            _sig_ts = st.session_state.get(_sig_ts_key, "")

            # ══════════════════════════════════════════════════════════════
            # 🎯 AI 타점 보드
            # ══════════════════════════════════════════════════════════════
            if kr_mode == "⭐ 즐겨찾기 관리":
                show_favorites_center()
            elif kr_mode == "🎯 AI 타점 보드":
                _pb_key  = "kr_picks_result"
                _run_key = "_kr_picks_pending"

                # AI 호출 — 버튼 클릭 후 rerun 시 실행 (패널 렌더 전에 처리)
                if st.session_state.get(_run_key) and _pb_key not in st.session_state:
                    with st.spinner("AI가 시장·테마·수급·뉴스를 종합 분석 중입니다..."):
                        try:
                            from ai_engine import generate_realtime_picks
                            _mkt = get_kr_market_index() or {}
                            _vol = get_kr_volume_ranking() or []
                            _chg = (get_kr_change_ranking("J") or []) + (get_kr_change_ranking("Q") or [])
                            _hot_secs = []
                            try:
                                from ai_engine import analyze_kr_hot_sectors
                                _hs_res = analyze_kr_hot_sectors()
                                if isinstance(_hs_res, dict):
                                    _hot_secs = _hs_res.get("sectors", [])
                            except Exception:
                                pass
                            _picks = generate_realtime_picks(_mkt, _vol, _chg, hot_sectors=_hot_secs)
                        except Exception as _pe:
                            _picks = {"error": str(_pe), "picks": []}
                        _picks["_ts"] = (datetime.now() + timedelta(hours=9)).strftime("%H:%M")
                        st.session_state[_pb_key] = _picks
                        st.session_state[_run_key] = False
                    st.rerun()

                # ── 좌/우 2패널 레이아웃 ─────────────────────────────────
                _pb_left, _pb_right = st.columns([4, 6], gap="small")

                # ── 좌 패널: 컨트롤 + 종목 목록 ─────────────────────────
                with _pb_left:
                    with st.container(height=750):
                        # 신호 배너
                        if _new_count > 0 and _pb_key not in st.session_state:
                            st.markdown(
                                f"""<div style='background:linear-gradient(90deg,rgba(255,75,75,0.18),rgba(255,152,0,0.12));
                                    border:1.5px solid #ff4b4b;border-radius:10px;padding:8px 14px;margin-bottom:8px;
                                    display:flex;align-items:center;gap:8px;animation:pulse 1.5s ease-in-out infinite;'>
                                  <span style='font-size:1rem'>🔥</span>
                                  <span style='flex:1;font-size:0.75rem;font-weight:700;color:#ff6b6b'>
                                    {_new_count}개 신호 감지 ({_sig_ts})</span>
                                </div>
                                <style>@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.6}}}}</style>""",
                                unsafe_allow_html=True,
                            )
                        elif _new_count == 0 and _sig_ts:
                            st.caption(f"🟢 스캔: {_sig_ts} — 신호 없음")

                        # 실행 / 초기화 버튼
                        _pb_c1, _pb_c2 = st.columns([3, 1])
                        with _pb_c1:
                            if st.button("🔄 AI 타점 분석 실행", key="kr_picks_btn",
                                         type="primary", use_container_width=True):
                                st.session_state[_run_key] = True
                                if _pb_key in st.session_state:
                                    del st.session_state[_pb_key]
                                st.rerun()
                        with _pb_c2:
                            if st.button("🗑", key="kr_picks_clear", use_container_width=True):
                                st.session_state.pop(_pb_key, None)
                                st.session_state["kr_selected_pick_idx"] = 0
                                st.rerun()

                        if _pb_key in st.session_state:
                            _res   = st.session_state[_pb_key]
                            _cond  = _res.get("market_condition", "")
                            _cond_color = "#ff4b4b" if "상승" in _cond else "#2b7cff" if "하락" in _cond else "#f5c518"
                            _cond_icon  = "🟢" if "상승" in _cond else "🔴" if "하락" in _cond else "🟡"
                            st.markdown(
                                f"<div style='font-size:0.7rem;padding:4px 8px;margin:6px 0;"
                                f"border-left:3px solid {_cond_color};border-radius:0 6px 6px 0'>"
                                f"{_cond_icon} <b style='color:{_cond_color}'>{_cond}</b>"
                                f"&nbsp;<span style='color:#666;font-size:0.62rem'>{_res.get('_ts','')}</span></div>",
                                unsafe_allow_html=True,
                            )
                            if _res.get("error") and not _res.get("picks"):
                                st.error(f"분석 오류: {_res['error']}")
                            elif not _res.get("picks"):
                                st.info("추천 종목이 없습니다.")
                            else:
                                _sel = st.session_state.get("kr_selected_pick_idx", 0)
                                st.markdown(
                                    f"<div style='font-size:0.65rem;color:#666;margin-bottom:4px'>"
                                    f"총 {len(_res['picks'])}개 종목 — 클릭하여 상세 확인</div>",
                                    unsafe_allow_html=True,
                                )
                                for _ci, _pick in enumerate(_res["picks"]):
                                    _cpct2   = float(_pick.get("change_pct", 0) or 0)
                                    _entry2  = _pick.get("entry", 0)
                                    _target2 = _pick.get("target", 0)
                                    _upside2 = round((_target2 - _entry2) / _entry2 * 100, 1) if _entry2 > 0 else 0
                                    _urg2    = _pick.get("urgency", "")
                                    _urg_icon2  = "⚡" if "즉시" in _urg2 else ("🌙" if "내일" in _urg2 else "🕐")
                                    _urg_color2 = "#ff9800" if "즉시" in _urg2 else ("#a78bfa" if "내일" in _urg2 else "#888")
                                    _cpct_c2 = "#ff4b4b" if _cpct2 >= 0 else "#2b7cff"
                                    _is_sel  = (_ci == _sel)
                                    _row_bg  = "rgba(255,152,0,0.10)" if _is_sel else "rgba(255,255,255,0.03)"
                                    _row_bdr = "1px solid rgba(255,152,0,0.5)" if _is_sel else "1px solid rgba(255,255,255,0.07)"
                                    _s_col, _c_col = st.columns([0.15, 0.85])
                                    with _s_col:
                                        render_star_toggle("국내", _pick.get("code", ""), _pick.get("name", ""), f"pick_{_ci}")
                                    with _c_col:
                                        st.markdown(
                                            f"<div style='background:{_row_bg};border:{_row_bdr};"
                                            f"border-radius:8px;padding:8px 10px;margin-bottom:2px'>"
                                            f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                                            f"<span style='font-size:0.8rem;font-weight:700'>{_pick.get('name','')}</span>"
                                            f"<span style='font-size:0.68rem;color:{_urg_color2};font-weight:600'>"
                                            f"{_urg_icon2} {_urg2}</span>"
                                            f"</div>"
                                            f"<div style='display:flex;justify-content:space-between;margin-top:3px'>"
                                            f"<span style='font-size:0.65rem;color:#777'>"
                                            f"매수 ₩{int(_entry2):,} → +{_upside2}%</span>"
                                            f"<span style='font-size:0.68rem;color:{_cpct_c2};font-weight:600'>"
                                            f"{'▲' if _cpct2>=0 else '▼'}{abs(_cpct2):.1f}%</span>"
                                            f"</div></div>",
                                            unsafe_allow_html=True,
                                        )
                                    if st.button(
                                        "✓ 선택됨" if _is_sel else "▶ 상세보기",
                                        key=f"sel_pick_{_ci}",
                                        use_container_width=True,
                                        type="primary" if _is_sel else "secondary",
                                    ):
                                        st.session_state["kr_selected_pick_idx"] = _ci
                                        st.rerun()
                        else:
                            st.markdown(
                                "<div style='text-align:center;padding:50px 0;color:#555'>"
                                "<div style='font-size:2rem'>🎯</div>"
                                "<div style='margin-top:8px;font-size:0.85rem'>AI 분석을 실행하면<br>"
                                "종목 목록이 여기에 표시됩니다</div>"
                                "</div>",
                                unsafe_allow_html=True,
                            )

                # ── 우 패널: 선택 종목 상세 카드 ─────────────────────────
                with _pb_right:
                    with st.container(height=750):
                        if _pb_key not in st.session_state or not st.session_state[_pb_key].get("picks"):
                            st.markdown(
                                "<div style='display:flex;flex-direction:column;align-items:center;"
                                "justify-content:center;height:200px;color:#444'>"
                                "<div style='font-size:3rem'>📊</div>"
                                "<div style='margin-top:12px;font-size:0.88rem;text-align:center;line-height:1.6'>"
                                "좌측에서 AI 분석을 실행하면<br>선택 종목 상세가 여기에 표시됩니다</div>"
                                "</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            _res     = st.session_state[_pb_key]
                            _sel_idx = st.session_state.get("kr_selected_pick_idx", 0)
                            _sel_idx = min(_sel_idx, len(_res["picks"]) - 1)
                            _pick    = _res["picks"][_sel_idx]

                            _urg     = _pick.get("urgency", "")
                            _horizon = _pick.get("horizon", "")
                            _pattern = _pick.get("pattern", "")
                            _urg_icon  = "⚡" if "즉시" in _urg else ("🌙" if "내일" in _urg else "🕐")
                            _urg_color = "#ff9800" if "즉시" in _urg else ("#a78bfa" if "내일" in _urg else "#888")
                            _urg_bg    = ("rgba(255,152,0,0.15)" if "즉시" in _urg
                                          else "rgba(167,139,250,0.15)" if "내일" in _urg
                                          else "rgba(255,255,255,0.06)")
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
                            _pos       = _pick.get("position", "")
                            _pos_color = {"대장주": "#ff4b4b", "선도추종주": "#f5c518", "후발추종주": "#2b7cff"}.get(_pos, "#888")
                            _t_stage   = _pick.get("theme_stage", "")
                            _t_stage_c = {"초기 형성": "#4caf50", "확산": "#ff9800", "과열": "#ff4b4b", "냉각": "#2b7cff"}.get(_t_stage, "#888")
                            _leader    = _pick.get("leader_name", "")
                            _sup_sig   = _pick.get("supply_signal", "")
                            _sup_c     = "#00c853" if "유입" in _sup_sig or "매집" in _sup_sig else "#ff4b4b" if "이탈" in _sup_sig else "#f5c518"
                            _linkage   = _pick.get("theme_linkage", "")
                            _cpct_color = "#ff4b4b" if _cpct >= 0 else "#2b7cff"
                            _cpct_sign  = "▲" if _cpct >= 0 else "▼"

                            _cur_html = (
                                f"<div style='font-size:0.8rem;color:#aaa;margin-bottom:8px'>"
                                f"현재 <b style='color:#eee'>₩{int(_cur):,}</b>&nbsp;"
                                f"<span style='color:{_cpct_color};font-weight:700'>"
                                f"{_cpct_sign} {abs(_cpct):.2f}%</span></div>"
                            ) if _cur > 0 else ""

                            _pattern_html = (
                                f"<div style='font-size:0.62rem;color:#7dd3fc;"
                                f"background:rgba(125,211,252,0.08);border-radius:6px;"
                                f"padding:3px 8px;margin-bottom:6px;display:inline-block'>"
                                f"📊 {_pattern}</div>"
                            ) if _pattern else ""

                            _theme_pos_html = ""
                            if _pos or _t_stage:
                                _theme_pos_html = (
                                    f"<div style='display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px'>"
                                    + (f"<span style='background:rgba(255,255,255,0.07);border:1px solid {_pos_color};"
                                       f"border-radius:8px;padding:2px 7px;font-size:0.62rem;color:{_pos_color};font-weight:700'>"
                                       f"{_pos}</span>" if _pos else "")
                                    + (f"<span style='background:rgba(255,255,255,0.07);border:1px solid {_t_stage_c};"
                                       f"border-radius:8px;padding:2px 7px;font-size:0.62rem;color:{_t_stage_c}'>"
                                       f"{_t_stage}</span>" if _t_stage else "")
                                    + (f"<span style='font-size:0.62rem;color:{_sup_c};padding:2px 4px'>"
                                       f"📡 {_sup_sig}</span>" if _sup_sig else "")
                                    + "</div>"
                                )

                            _linkage_html = ""
                            if _leader or _linkage:
                                _linkage_html = (
                                    f"<div style='background:rgba(255,255,255,0.04);border-left:2px solid {_pos_color};"
                                    f"border-radius:0 6px 6px 0;padding:5px 8px;margin-bottom:8px;font-size:0.7rem'>"
                                    + (f"<span style='color:#888'>대장주: </span><span style='color:#eee'>{_leader}</span><br>" if _leader else "")
                                    + (f"<span style='color:#aaa'>{_linkage}</span>" if _linkage else "")
                                    + "</div>"
                                )

                            _theme_html = "".join(
                                f"<span style='background:rgba(255,255,255,0.08);"
                                f"border-radius:10px;padding:2px 7px;font-size:0.63rem;"
                                f"color:#aaa;margin-right:4px'>{th}</span>"
                                for th in _themes
                            )

                            _warn_html = (
                                "<div style='background:rgba(255,75,75,0.15);border:1px solid #ff4b4b;"
                                "border-radius:8px;padding:4px 8px;font-size:0.65rem;color:#ff4b4b;"
                                "margin-bottom:8px'>⚠️ 이미 많이 오른 종목 — 진입 신중</div>"
                            ) if _already_surged else ""

                            _border_color = "rgba(255,75,75,0.3)" if _already_surged else "rgba(255,255,255,0.1)"

                            _card_html = (
                                f"<div class='toss-card sc-card' style='"
                                f"border-color:{_border_color};padding:14px 14px 12px 14px'>"
                                f"<div style='display:flex;justify-content:space-between;"
                                f"align-items:flex-start;margin-bottom:6px'>"
                                f"<div>"
                                f"<span style='font-size:0.7rem;color:#888'>#{_pick.get('rank',_sel_idx+1)}</span>&nbsp;"
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
                                + _theme_pos_html
                                + _pattern_html
                                + _linkage_html
                                + _cur_html +
                                f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;"
                                f"gap:6px;margin-bottom:10px'>"
                                f"<div class='sc-card-sm' style='background:rgba(255,255,255,0.07);"
                                f"border:1px solid rgba(255,255,255,0.12);border-radius:8px;"
                                f"padding:6px;text-align:center'>"
                                f"<div style='font-size:0.6rem;color:var(--sc-text-muted,#888)'>매수 타점</div>"
                                f"<div style='font-size:0.85rem;font-weight:700'>₩{int(_entry):,}</div></div>"
                                f"<div class='sc-card-sm' style='background:rgba(0,200,83,0.12);"
                                f"border:1px solid rgba(0,200,83,0.25);border-radius:8px;"
                                f"padding:6px;text-align:center'>"
                                f"<div style='font-size:0.6rem;color:var(--sc-text-muted,#888)'>목표가</div>"
                                f"<div style='font-size:0.85rem;font-weight:700;color:#00c853'>"
                                f"₩{int(_target):,}</div>"
                                f"<div style='font-size:0.6rem;color:#00c853'>+{_upside}%</div></div>"
                                f"<div class='sc-card-sm' style='background:rgba(43,124,255,0.12);"
                                f"border:1px solid rgba(43,124,255,0.25);border-radius:8px;"
                                f"padding:6px;text-align:center'>"
                                f"<div style='font-size:0.6rem;color:var(--sc-text-muted,#888)'>손절가</div>"
                                f"<div style='font-size:0.85rem;font-weight:700;color:#2b7cff'>"
                                f"₩{int(_stop):,}</div></div>"
                                f"</div>"
                                f"<div style='font-size:0.72rem;color:var(--sc-text-muted,#bbb);line-height:1.6;"
                                f"margin-bottom:8px'>{_pick.get('reason','')}</div>"
                                + _theme_html
                                + "</div>"
                            )
                            st.markdown(_card_html, unsafe_allow_html=True)

                            _pk_btn_c1, _pk_btn_c2 = st.columns(2)
                            with _pk_btn_c1:
                                if st.button("상세 분석 →", key=f"pk_detail_{_pick.get('code',_sel_idx)}",
                                             use_container_width=True):
                                    st.session_state.kr_selected_code = _pick.get("code", "005930")
                                    st.session_state.kr_selected_name = _pick.get("name", "")
                                    st.session_state.kr_mode = "📊 일반 주식 검색"
                                    st.rerun()
                            with _pk_btn_c2:
                                if st.button("🔗 테마 연동", key=f"pk_theme_{_pick.get('code',_sel_idx)}",
                                             use_container_width=True):
                                    st.session_state[f"pk_thm_run_{_pick.get('code','')}"] = True
                                    st.rerun()

                            _pk_thm_run = f"pk_thm_run_{_pick.get('code','')}"
                            _pk_thm_res = f"pk_thm_res_{_pick.get('code','')}"
                            if st.session_state.get(_pk_thm_run) and _pk_thm_res not in st.session_state:
                                with st.spinner("🔗 테마 연동 분석 중..."):
                                    try:
                                        from ai_engine import analyze_stock_theme_position
                                        _pk_theme_name = _themes[0] if _themes else ""
                                        _pk_sec_stocks = []
                                        try:
                                            from data_kr import load_sector_map
                                            _sm = load_sector_map()
                                            for _sv in _sm.get(_pk_theme_name, {}).values():
                                                _pk_sec_stocks.extend([
                                                    {"name": s["name"], "code": s["code"], "change_pct": 0.0}
                                                    for s in _sv
                                                ])
                                        except Exception:
                                            pass
                                        _pk_price_d = {
                                            "price": _cur, "change_pct": _cpct,
                                            "volume": 0, "open": 0, "high": 0, "low": 0,
                                            "w52_high": 0, "w52_low": 0, "per": "-", "pbr": "-",
                                        }
                                        st.session_state[_pk_thm_res] = analyze_stock_theme_position(
                                            _pick.get("code", ""), _pick.get("name", ""),
                                            _pk_price_d, [], _pk_theme_name, _pk_sec_stocks,
                                        )
                                    except Exception as _pte:
                                        st.session_state[_pk_thm_res] = {"error": str(_pte)}
                                    st.session_state[_pk_thm_run] = False
                                st.rerun()

                            if _pk_thm_res in st.session_state:
                                _pktr = st.session_state[_pk_thm_res]
                                if "error" in _pktr:
                                    st.caption(f"⚠️ {str(_pktr['error'])[:80]}")
                                else:
                                    _pos2   = _pktr.get("position", "")
                                    _pos_c2 = {"대장주": "#ff4b4b", "선도추종주": "#f5c518", "후발추종주": "#2b7cff", "소외주": "#888"}.get(_pos2, "#888")
                                    _mstg  = _pktr.get("momentum_stage", "")
                                    _etim  = _pktr.get("entry_timing", "")
                                    _etim_c = "#00c853" if "즉시" in _etim else "#f5c518" if "대기" in _etim or "확인" in _etim else "#ff4b4b"
                                    st.markdown(
                                        f"<div class='sc-card-sm' style='background:rgba(255,255,255,0.04);border-radius:8px;"
                                        f"padding:8px 10px;margin-top:4px;font-size:0.72rem'>"
                                        f"<b style='color:{_pos_c2}'>{_pos2}</b>"
                                        f"<span style='color:#aaa;margin-left:6px'>{_mstg}</span><br>"
                                        f"<span style='color:{_etim_c}'>⏱ {_etim}</span>"
                                        f"<span style='color:#888;margin-left:6px'>{_pktr.get('entry_reason','')[:60]}</span>"
                                        f"</div>",
                                        unsafe_allow_html=True,
                                    )
            # ══════════════════════════════════════════════════════════════
            # 📊 종목검색 / 🔥 섹터분석 (상단 네비로 전환)
            # ══════════════════════════════════════════════════════════════
            if kr_mode in ("📊 일반 주식 검색", "🔥 오늘의 이슈 섹터"):
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
                    _chart_ctr = st.container(height=750)
                with col_right:
                    _right_ctr = st.container(height=750)
                with _chart_ctr:
                    # ── 이슈 섹터 모드 ──────────────────────────────────────
                    if kr_mode == "🔥 오늘의 이슈 섹터":

                        if st.session_state.kr_sector_view == "detail":
                            # 선택 종목 Plotly 차트
                            _dtv_code = st.session_state.kr_sector_detail_code
                            _dtv_name = st.session_state.kr_sector_detail_name
                            
                            # 이름 보정: 마스터 맵에서 실제 이름 조회
                            _c2n_d = get_kr_code_to_name_map()
                            _real_dtv_name = _c2n_d.get(_dtv_code, _dtv_name)
                            if _real_dtv_name == _dtv_code and price_kr and price_kr.get('name'):
                                _real_dtv_name = price_kr['name']
                            
                            if st.session_state.kr_sector_detail_name != _real_dtv_name:
                                st.session_state.kr_sector_detail_name = _real_dtv_name
                                
                            pct_color = "up-kr" if is_up else "down-kr" if is_dn else ""
                            if price_kr:
                                st.markdown(
                                    f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px'>"
                                    f"<span style='font-size:1.25rem;font-weight:700'>**{_real_dtv_name}**</span> "
                                    f"<span style='font-size:0.9rem;color:#888'>({_dtv_code})</span> &nbsp; "
                                    f"<span style='font-size:1.1rem;font-weight:600'>₩{price_kr['price']:,}</span> &nbsp; "
                                    f'<span class="{pct_color}" style="font-size:1rem;font-weight:600">{arrow} {price_kr["change_pct"]:+.2f}%</span>'
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.markdown(f"**{_real_dtv_name}** ({_dtv_code})")

                            _kr_plotly_chart(_dtv_code, interval="5", height=660)

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
                            # 이름 보정: 마스터 맵에서 먼저 찾고, 없으면 시세 데이터 사용
                            _c2n = get_kr_code_to_name_map()
                            _real_name = _c2n.get(selected_code_kr, price_kr.get('name') or selected_code_kr)
                            
                            # 세션 이름 업데이트 (코드로 박혀있는 경우 방지)
                            if st.session_state.kr_selected_name != _real_name:
                                st.session_state.kr_selected_name = _real_name
                            
                            pct_color = "up-kr" if is_up else "down-kr" if is_dn else ""
                            st.markdown(
                                f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px'>"
                                f"<span style='font-size:1.25rem;font-weight:700'>**{_real_name}**</span> "
                                f"<span style='font-size:0.9rem;color:#888'>({selected_code_kr})</span> &nbsp; "
                                f"<span style='font-size:1.1rem;font-weight:600'>₩{price_kr['price']:,}</span> &nbsp; "
                                f'<span class="{pct_color}" style="font-size:1rem;font-weight:600">{arrow} {price_kr["change_pct"]:+.2f}%</span>'
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                        # 차트 타입 토글: 일봉(기본) | 분봉(당일)
                        _ct_c1, _ct_c2, _ = st.columns([1, 1, 6])
                        for _ctcol, _ctn in [(_ct_c1, "일봉"), (_ct_c2, "분봉")]:
                            if _ctcol.button(
                                _ctn, key=f"chart_type_{_ctn}",
                                type="primary" if st.session_state.kr_chart_type == _ctn else "secondary",
                                use_container_width=True,
                            ):
                                st.session_state.kr_chart_type = _ctn
                                st.rerun()

                        _kr_tv_iv = "5" if st.session_state.kr_chart_type == "분봉" else "D"
                        _kr_plotly_chart(selected_code_kr, interval=_kr_tv_iv, height=660)

                with _right_ctr:
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
                                # 이름 찾기 시도
                                _c2n = get_kr_code_to_name_map()
                                new_name = _c2n.get(new_code, new_code)
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
                                    # 즐겨찾기 버튼 (상단 배치)
                                    _fav_btn_label = "⭐ 즐겨찾기 등록"
                                    if st.button(_fav_btn_label, use_container_width=True, key=f"fav_btn_kr_top_{selected_code_kr}"):
                                        from db import save_favorite
                                        _ok, _msg = save_favorite("국내", selected_code_kr, price_kr["name"])
                                        if _ok: st.success(_msg)
                                        else: st.error(_msg)

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

                                # ── 단기 / 중기 / 장기 추천 분석 ─────────────────
                                _chg  = price_kr.get("change_pct", 0) or 0
                                _vol  = price_kr.get("volume", 0) or 0
                                _cp   = price_kr.get("price", 0) or 0
                                _wl   = price_kr.get("w52_low",  0) or 0
                                _wh   = price_kr.get("w52_high", 0) or 0
                                _per  = price_kr.get("per", "-")
                                _pbr  = price_kr.get("pbr", "-")

                                # 52주 위치 계산
                                _band_pos = (_cp - _wl) / (_wh - _wl) * 100 if _wh > _wl > 0 else 50

                                # 극단타 판정 (분 단위~하루 이틀, 당일 모멘텀 기준)
                                if abs(_chg) < 0.5:
                                    _et_label = "⚪ 극단타 불가"
                                    _et_color = "#888"
                                    _et_desc  = "변동 없음 — 거래비용 감안 시 손익 기대 불가"
                                elif _chg >= 5.0:
                                    _et_label = "🟢 극단타 적극 대응"
                                    _et_color = "#00c853"
                                    _et_desc  = f"강 모멘텀 {_chg:+.2f}% — 눌림목 분봉 지지 확인 후 진입"
                                elif _chg >= 3.0:
                                    _et_label = "🟢 극단타 관심"
                                    _et_color = "#00c853"
                                    _et_desc  = f"상승 {_chg:+.2f}% — 직전 분봉 고점 돌파 시 추격"
                                elif _chg >= 1.0:
                                    _et_label = "🟡 극단타 관망"
                                    _et_color = "#ffd600"
                                    _et_desc  = f"소폭 {_chg:+.2f}% — 변동성 부족, 돌파 신호 대기"
                                elif _chg <= -5.0:
                                    _et_label = "🔵 반등 노림"
                                    _et_color = "#2b7cff"
                                    _et_desc  = f"급락 {_chg:+.2f}% — 분봉 반등 캔들+거래량 폭발 확인 후"
                                elif _chg <= -1.0:
                                    _et_label = "🔴 극단타 자제"
                                    _et_color = "#ff4b4b"
                                    _et_desc  = f"하락 {_chg:+.2f}% — 추세 꺾임, 섣부른 반매수 위험"
                                else:
                                    _et_label = "🟡 극단타 관망"
                                    _et_color = "#ffd600"
                                    _et_desc  = f"등락 {_chg:+.2f}% — 방향 미확정, 분봉 패턴 확인 필요"

                                # 단기 판정 (당일 등락률 + 거래량)
                                if abs(_chg) < 0.1:
                                    _st_label = "⚪ 관망"
                                    _st_color = "#888"
                                    _st_desc  = f"등락 미미({_chg:+.2f}%) — 장 마감·거래 없음 상태 가능"
                                elif _chg >= 5.0:
                                    _st_label = "🟢 강력 단기 추천"
                                    _st_color = "#00c853"
                                    _st_desc  = f"강한 모멘텀 {_chg:+.2f}% — 눌림목 진입 권장"
                                elif _chg >= 3.0:
                                    _st_label = "🟢 단기 추천"
                                    _st_color = "#00c853"
                                    _st_desc  = f"상승세 {_chg:+.2f}% — 손절: 당일 저점"
                                elif _chg >= 1.0:
                                    _st_label = "🟡 단기 관망"
                                    _st_color = "#ffd600"
                                    _st_desc  = f"소폭 상승 {_chg:+.2f}% — 3% 돌파 확인 후 진입"
                                elif _chg <= -5.0:
                                    _st_label = "🔵 반등 관찰"
                                    _st_color = "#2b7cff"
                                    _st_desc  = f"급락 {_chg:+.2f}% — 지지선·거래량 확인 필수"
                                elif _chg <= -2.0:
                                    _st_label = "🔴 단기 비추천"
                                    _st_color = "#ff4b4b"
                                    _st_desc  = f"하락세 {_chg:+.2f}% — 추가 하락 가능"
                                else:
                                    _st_label = "🔴 단기 비추천"
                                    _st_color = "#ff4b4b"
                                    _st_desc  = f"등락 {_chg:+.2f}% — 수수료 감안 시 실익 없음"

                                # 중기 판정 (52주 위치 + PBR)
                                try:
                                    _pbr_f = float(str(_pbr).replace(",",""))
                                except Exception:
                                    _pbr_f = 1.5
                                if _band_pos <= 30:
                                    _mt_label = "🟢 중기 매수 관심"
                                    _mt_color = "#00c853"
                                    _mt_desc  = f"52주 저점 근처({_band_pos:.0f}%) — 중기 분할 매수 고려"
                                elif _band_pos >= 80:
                                    _mt_label = "🔴 중기 고평가"
                                    _mt_color = "#ff4b4b"
                                    _mt_desc  = f"52주 고점 근처({_band_pos:.0f}%) — 신규 진입 부담"
                                elif _pbr_f < 1.0:
                                    _mt_label = "🟢 중기 저평가"
                                    _mt_color = "#00c853"
                                    _mt_desc  = f"PBR {_pbr_f:.2f} (자산가치 이하) — 중기 가치투자 유리"
                                else:
                                    _mt_label = "🟡 중기 중립"
                                    _mt_color = "#ffd600"
                                    _mt_desc  = f"52주 중간대({_band_pos:.0f}%) — 방향성 확인 후 대응"

                                # 장기 판정 (PER + 섹터 포지션)
                                try:
                                    _per_f = float(str(_per).replace(",",""))
                                except Exception:
                                    _per_f = 20.0
                                if _per_f <= 0:
                                    _lt_label = "🟡 장기 중립"
                                    _lt_color = "#ffd600"
                                    _lt_desc  = "PER 음수(적자) — 수익성 개선 추이 확인 필요"
                                elif _per_f < 10:
                                    _lt_label = "🟢 장기 저평가"
                                    _lt_color = "#00c853"
                                    _lt_desc  = f"PER {_per_f:.1f} — 업종 대비 저평가, 장기 보유 유리"
                                elif _per_f < 20:
                                    _lt_label = "🟢 장기 적정"
                                    _lt_color = "#00c853"
                                    _lt_desc  = f"PER {_per_f:.1f} — 적정 밸류에이션"
                                elif _per_f < 40:
                                    _lt_label = "🟡 장기 중립"
                                    _lt_color = "#ffd600"
                                    _lt_desc  = f"PER {_per_f:.1f} — 성장 프리미엄 반영, 모니터링 필요"
                                else:
                                    _lt_label = "🔴 장기 고평가"
                                    _lt_color = "#ff4b4b"
                                    _lt_desc  = f"PER {_per_f:.1f} — 고평가 구간, 장기 진입 신중"

                                _rc0, _rc1, _rc2, _rc3 = st.columns(4)
                                for _rcol, _rl, _rc_color, _rdesc, _rtitle in [
                                    (_rc0, _et_label, _et_color, _et_desc, "극단타"),
                                    (_rc1, _st_label, _st_color, _st_desc, "단기"),
                                    (_rc2, _mt_label, _mt_color, _mt_desc, "중기"),
                                    (_rc3, _lt_label, _lt_color, _lt_desc, "장기"),
                                ]:
                                    with _rcol:
                                        st.markdown(
                                            f"<div style='background:rgba(255,255,255,0.05);border-left:3px solid {_rc_color};"
                                            f"border-radius:6px;padding:8px 10px;margin:4px 0'>"
                                            f"<div style='font-size:0.65rem;color:#888;margin-bottom:2px'>{_rtitle}</div>"
                                            f"<div style='font-size:0.8rem;font-weight:700;color:{_rc_color}'>{_rl}</div>"
                                            f"<div style='font-size:0.68rem;color:#ccc;margin-top:3px'>{_rdesc}</div>"
                                            f"</div>",
                                            unsafe_allow_html=True,
                                        )

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
                                    _fc, _gc = _get_chart_colors()
                                    fig_inv.update_layout(
                                        barmode="group",
                                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                        font=dict(color=_fc), legend=dict(orientation="h"),
                                        xaxis=dict(gridcolor=_gc),
                                        yaxis=dict(gridcolor=_gc, title="순매수(주)"),
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
                                    if "long_term_rating" in rep_kr:
                                        t1, t2 = st.tabs(["⚡ 단기 트레이딩 관점", "📈 중장기 투자 관점"])
                                        with t1:
                                            rating_kr = rep_kr.get("rating", "")
                                            r_emoji = "🟢" if "강력" in rating_kr else "🟡" if "추천" in rating_kr else "🔴"
                                            st.markdown(f"##### {r_emoji} {rating_kr}")
                                            rk1, rk2, rk3 = st.columns(3)
                                            rk1.metric("분석 기간", rep_kr.get("short_term_period", "-"))
                                            rk2.metric("기대 수익", rep_kr.get("short_term_target_pct", "-"))
                                            rk3.metric("매수 타점", rep_kr.get("buy_target", "-"))
                                            
                                            rk4, rk5 = st.columns(2)
                                            rk4.metric("단기 목표가", rep_kr.get("sell_target", "-"))
                                            rk5.metric("손절가",     rep_kr.get("stop_loss", "-"))
                                            
                                            if st.button("🎒 포트폴리오에 담기", use_container_width=True, type="primary", key="kr_port_btn_short"):
                                                if "portfolio" not in st.session_state:
                                                    st.session_state.portfolio = []
                                                if not any(i["ticker"] == selected_code_kr for i in st.session_state.portfolio):
                                                    st.session_state.portfolio.append({
                                                        "ticker": selected_code_kr, "name": price_kr["name"],
                                                        "buy_price": price_kr["price"], "quantity": 10,
                                                        "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                    })
                                                    st.success(f"{price_kr['name']} 포트폴리오에 추가!")
                                                else:
                                                    st.warning("이미 포트폴리오에 있습니다.")
                                                    
                                            if rep_kr.get("세력분석"):
                                                st.info(f"**세력 분석:** {rep_kr['세력분석']}")
                                            if rep_kr.get("historical_pattern_analysis"):
                                                with st.expander("🕰️ 역사적 유사 패턴 분석 (프랙탈)", expanded=False):
                                                    st.markdown(rep_kr["historical_pattern_analysis"])
                                            if rep_kr.get("analysis"):
                                                with st.container(border=True):
                                                    st.markdown(rep_kr["analysis"])
                                        with t2:
                                            lt_rating = rep_kr.get("long_term_rating", "")
                                            lt_emoji = "🟢" if "매수" in lt_rating else "🟡" if "관망" in lt_rating else "🔴"
                                            st.markdown(f"##### {lt_emoji} {lt_rating}")
                                            
                                            lk1, lk2, lk3 = st.columns(3)
                                            lk1.metric("권장 기간", rep_kr.get("long_term_period", "-"))
                                            lk2.metric("목표 수익", rep_kr.get("long_term_target_pct", "-"))
                                            lk3.metric("중장기 목표가", rep_kr.get("long_term_target", "-"))
                                            
                                            if st.button("🎒 장기 포트폴리오에 담기", use_container_width=True, type="primary", key="kr_port_btn_long"):
                                                if "portfolio" not in st.session_state:
                                                    st.session_state.portfolio = []
                                                if not any(i["ticker"] == selected_code_kr for i in st.session_state.portfolio):
                                                    st.session_state.portfolio.append({
                                                        "ticker": selected_code_kr, "name": price_kr["name"],
                                                        "buy_price": price_kr["price"], "quantity": 10,
                                                        "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                    })
                                                    st.success(f"{price_kr['name']} 포트폴리오에 추가!")
                                                else:
                                                    st.warning("이미 포트폴리오에 있습니다.")
                                            
                                            if rep_kr.get("long_term_analysis"):
                                                with st.container(border=True):
                                                    st.markdown(rep_kr["long_term_analysis"])
                                    else:
                                        rating_kr = rep_kr.get("rating", "")
                                        r_emoji = "🟢" if "강력" in rating_kr else "🟡" if "추천" in rating_kr else "🔴"
                                        st.markdown(f"##### {r_emoji} {rating_kr}")
                                        rk1, rk2 = st.columns(2)
                                        rk1.metric("매수 타점", rep_kr.get("buy_target", "-"))
                                        rk2.metric("목표가",    rep_kr.get("sell_target", "-"))
                                        st.metric("손절가",     rep_kr.get("stop_loss", "-"))
                                        
                                        
                                        if st.button("🎒 포트폴리오에 담기", use_container_width=True, type="primary", key="kr_port_btn"):
                                            if "portfolio" not in st.session_state:
                                                st.session_state.portfolio = []
                                            if not any(i["ticker"] == selected_code_kr for i in st.session_state.portfolio):
                                                st.session_state.portfolio.append({
                                                    "ticker": selected_code_kr, "name": price_kr["name"],
                                                    "buy_price": price_kr["price"], "quantity": 10,
                                                    "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                })
                                                st.success(f"{price_kr['name']} 포트폴리오에 추가!")
                                            else:
                                                st.warning("이미 포트폴리오에 있습니다.")
                                                
                                        if rep_kr.get("세력분석"):
                                            st.info(f"**세력 분석:** {rep_kr['세력분석']}")
                                        if rep_kr.get("analysis"):
                                            with st.container(border=True):
                                                st.markdown(rep_kr["analysis"])
                                else:
                                    st.info("버튼을 눌러 AI 분석을 실행하세요.")

                                # ── 테마 연동 분석 ──────────────────────────────────
                                st.markdown("---")
                                st.markdown("#### 🔗 테마 연동 분석")
                                st.caption("이 종목의 테마 내 포지션·수급·세력·역사 패턴을 분석합니다")
                                _ktp_key     = f"kr_theme_pos_{selected_code_kr}"
                                _ktp_run_key = f"_ktp_run_{selected_code_kr}"
                                if st.button("🔗 테마 연동 분석 실행", key="kr_theme_btn",
                                             use_container_width=True):
                                    st.session_state[_ktp_run_key] = True
                                    st.session_state.pop(_ktp_key, None)
                                    st.rerun()
                                if st.session_state.get(_ktp_run_key) and _ktp_key not in st.session_state:
                                    with st.spinner("AI가 테마·수급·세력·역사 흐름 분석 중..."):
                                        try:
                                            from ai_engine import analyze_stock_theme_position
                                            from db import load_sector_map as _lsm_tp
                                            _tp_sm = _lsm_tp()
                                            # 이 종목이 속한 섹터 찾기
                                            _tp_sec = "기타"
                                            _tp_stk = []
                                            for _s, _subs in _tp_sm.items():
                                                for _sb, _sl in _subs.items():
                                                    for _st in _sl:
                                                        if _st.get("code") == selected_code_kr:
                                                            _tp_sec = _s
                                                        _tp_stk.append({**_st, "price":0,"change_pct":0})
                                                if _tp_sec != "기타":
                                                    break
                                            _ktp_inv = get_kr_investor_trend(selected_code_kr)
                                            _ktp_res = analyze_stock_theme_position(
                                                selected_code_kr, price_kr.get("name", ""),
                                                price_kr or {}, _ktp_inv,
                                                _tp_sec, _tp_stk
                                            )
                                        except Exception as _ktp_e:
                                            _ktp_res = {"error": str(_ktp_e)}
                                        st.session_state[_ktp_key]     = _ktp_res
                                        st.session_state[_ktp_run_key] = False
                                    st.rerun()
                                if _ktp_key in st.session_state:
                                    _ktr = st.session_state[_ktp_key]
                                    if _ktr.get("error"):
                                        st.error(f"분석 오류: {_ktr['error']}")
                                    else:
                                        _kpos = _ktr.get("position", "")
                                        _kpc = {"대장주":"#ff4b4b","선도추종주":"#f5c518","후발추종주":"#2b7cff","소외주":"#888"}.get(_kpos, "#aaa")
                                        st.markdown(
                                            f"<div style='display:inline-block;background:{_kpc}22;"
                                            f"border:1px solid {_kpc};border-radius:8px;"
                                            f"padding:4px 12px;font-size:0.82rem;font-weight:700;"
                                            f"color:{_kpc};margin-bottom:6px'>📍 {_kpos}</div>"
                                            + (f" <span style='font-size:0.72rem;color:#aaa'>{_tp_sec}</span>" if "_tp_sec" in dir() else ""),
                                            unsafe_allow_html=True,
                                        )
                                        if _ktr.get("position_reason"):
                                            st.caption(_ktr["position_reason"])
                                        _ktc1, _ktc2 = st.columns(2)
                                        _ktc1.markdown(
                                            f"<div style='font-size:0.68rem;color:#888'>섹터 대장주</div>"
                                            f"<div style='font-weight:700'>{_ktr.get('leader_name','?')}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        _kfd = _ktr.get("force_direction","")
                                        _kfdc = "#00c853" if "유입" in _kfd or "매집" in _kfd else "#ff4b4b" if "이탈" in _kfd else "#888"
                                        _ktc2.markdown(
                                            f"<div style='font-size:0.68rem;color:#888'>세력 방향</div>"
                                            f"<div style='font-weight:700;color:{_kfdc}'>{_kfd}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        if _ktr.get("momentum_stage") or _ktr.get("chart_pattern"):
                                            st.markdown(
                                                f"<div class='sc-card-sm' style='background:rgba(255,255,255,0.04);border-radius:8px;"
                                                f"padding:8px 12px;margin:6px 0;font-size:0.8rem'>"
                                                f"<b>📈 {_ktr.get('momentum_stage','')}</b>"
                                                + (f" · {_ktr.get('chart_pattern','')}" if _ktr.get('chart_pattern') else "")
                                                + "</div>",
                                                unsafe_allow_html=True,
                                            )
                                        if _ktr.get("leader_correlation"):
                                            st.info(f"🔗 **연동:** {_ktr['leader_correlation']}")
                                        if _ktr.get("supply_analysis"):
                                            with st.expander("💰 수급·세력 분석"):
                                                st.markdown(_ktr["supply_analysis"])
                                        if _ktr.get("historical_pattern"):
                                            with st.expander("📜 역사적 유사 패턴"):
                                                st.markdown(_ktr["historical_pattern"])
                                        _ket = _ktr.get("entry_timing","")
                                        _ketc = {"즉시 진입":"#00c853","눌림목 대기":"#f5c518","돌파 확인 후":"#f5c518","관망 권고":"#ff4b4b"}.get(_ket,"#888")
                                        if _ket:
                                            st.markdown(
                                                f"<div style='background:{_ketc}15;border:1px solid {_ketc}50;"
                                                f"border-radius:8px;padding:8px 12px;margin:4px 0'>"
                                                f"<span style='color:{_ketc};font-weight:700'>⏱ {_ket}</span>"
                                                + (f" — {_ktr.get('entry_reason','')}" if _ktr.get('entry_reason') else "")
                                                + "</div>",
                                                unsafe_allow_html=True,
                                            )
                                        _kta1, _kta2, _kta3 = st.columns(3)
                                        _kta1.metric("매수 타점", _ktr.get("buy_target", "-"))
                                        _kta2.metric("목표가",    _ktr.get("sell_target", "-"))
                                        _kta3.metric("손절가",    _ktr.get("stop_loss", "-"))
                                        if _ktr.get("risk_factors"):
                                            st.warning(f"⚠️ {_ktr['risk_factors']}")

                    else:  # 🔥 오늘의 이슈 섹터
                        from db import load_sector_map, init_sector_sheet
                        # duplicate import removed

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

                            # 이름 보정
                            _c2n_d = get_kr_code_to_name_map()
                            _real_detail_name = _c2n_d.get(detail_code, detail_name)
                            if _real_detail_name == detail_code and price_kr and price_kr.get('name'):
                                _real_detail_name = price_kr['name']
                            
                            if st.session_state.kr_sector_detail_name != _real_detail_name:
                                st.session_state.kr_sector_detail_name = _real_detail_name

                            st.markdown(
                                f"<h4 style='margin:4px 0 2px 0'>{_real_detail_name} <span style='font-size:0.9rem;color:#888;font-weight:400'>({detail_code})</span></h4>"
                                f"<p style='margin:0;font-size:0.78rem;color:#888'>"
                                f"{st.session_state.kr_selected_sector}</p>",
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
                                    _fc, _gc = _get_chart_colors()
                                    fig_inv_d.update_layout(
                                        barmode="group",
                                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                        font=dict(color=_fc), legend=dict(orientation="h"),
                                        xaxis=dict(gridcolor=_gc),
                                        yaxis=dict(gridcolor=_gc, title="순매수(주)"),
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
                                    if "long_term_rating" in _r:
                                        t1, t2 = st.tabs(["⚡ 단기 트레이딩 관점", "📈 중장기 투자 관점"])
                                        with t1:
                                            _rtg = _r.get("rating","")
                                            _re = "🟢" if "강력" in _rtg else "🟡" if "추천" in _rtg else "🔴"
                                            st.markdown(f"##### {_re} {_rtg}")
                                            
                                            _rk1, _rk2, _rk3 = st.columns(3)
                                            _rk1.metric("분석 기간", _r.get("short_term_period", "-"))
                                            _rk2.metric("기대 수익", _r.get("short_term_target_pct", "-"))
                                            _rk3.metric("매수 타점", _r.get("buy_target","-"))
                                            
                                            _rk4, _rk5 = st.columns(2)
                                            _rk4.metric("단기 목표가", _r.get("sell_target","-"))
                                            _rk5.metric("손절가", _r.get("stop_loss","-"))
                                            
                                            if st.button("🎒 포트폴리오에 담기", use_container_width=True, type="primary", key=f"kr_sec_port_btn_short_{detail_code}"):
                                                if "portfolio" not in st.session_state:
                                                    st.session_state.portfolio = []
                                                if not any(i["ticker"] == detail_code for i in st.session_state.portfolio):
                                                    st.session_state.portfolio.append({
                                                        "ticker": detail_code, "name": detail_name,
                                                        "buy_price": price_kr.get("price", 0) if price_kr else 0, "quantity": 10,
                                                        "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                    })
                                                    st.success(f"{detail_name} 포트폴리오에 추가!")
                                                else:
                                                    st.warning("이미 포트폴리오에 있습니다.")
                                                    
                                            if _r.get("세력분석"):
                                                st.info(f"**세력 분석:** {_r['세력분석']}")
                                            if _r.get("historical_pattern_analysis"):
                                                with st.expander("🕰️ 역사적 유사 패턴 분석 (프랙탈)", expanded=False):
                                                    st.markdown(_r["historical_pattern_analysis"])
                                            if _r.get("analysis"):
                                                st.markdown("---")
                                                with st.container(border=True):
                                                    st.markdown(_r["analysis"])
                                        with t2:
                                            lt_rating = _r.get("long_term_rating", "")
                                            lt_emoji = "🟢" if "매수" in lt_rating else "🟡" if "관망" in lt_rating else "🔴"
                                            st.markdown(f"##### {lt_emoji} {lt_rating}")
                                            
                                            _lk1, _lk2, _lk3 = st.columns(3)
                                            _lk1.metric("권장 기간", _r.get("long_term_period", "-"))
                                            _lk2.metric("목표 수익", _r.get("long_term_target_pct", "-"))
                                            _lk3.metric("중장기 목표가", _r.get("long_term_target", "-"))
                                            
                                            if st.button("🎒 장기 포트폴리오에 담기", use_container_width=True, type="primary", key=f"kr_sec_port_btn_long_{detail_code}"):
                                                if "portfolio" not in st.session_state:
                                                    st.session_state.portfolio = []
                                                if not any(i["ticker"] == detail_code for i in st.session_state.portfolio):
                                                    st.session_state.portfolio.append({
                                                        "ticker": detail_code, "name": detail_name,
                                                        "buy_price": price_kr.get("price", 0) if price_kr else 0, "quantity": 10,
                                                        "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                    })
                                                    st.success(f"{detail_name} 포트폴리오에 추가!")
                                                else:
                                                    st.warning("이미 포트폴리오에 있습니다.")
                                                    
                                            if _r.get("long_term_analysis"):
                                                with st.container(border=True):
                                                    st.markdown(_r["long_term_analysis"])
                                    else:
                                        _rtg = _r.get("rating","")
                                        _re = "🟢" if "강력" in _rtg else "🟡" if "추천" in _rtg else "🔴"
                                        st.markdown(f"##### {_re} {_rtg}")
                                        _rk1, _rk2 = st.columns(2)
                                        _rk1.metric("매수 타점", _r.get("buy_target","-"))
                                        _rk2.metric("목표가",    _r.get("sell_target","-"))
                                        st.metric("손절가", _r.get("stop_loss","-"))
                                        
                                        if st.button("🎒 포트폴리오에 담기", use_container_width=True, type="primary", key=f"kr_sec_port_btn_{detail_code}"):
                                            if "portfolio" not in st.session_state:
                                                st.session_state.portfolio = []
                                            if not any(i["ticker"] == detail_code for i in st.session_state.portfolio):
                                                st.session_state.portfolio.append({
                                                    "ticker": detail_code, "name": detail_name,
                                                    "buy_price": price_kr.get("price", 0) if price_kr else 0, "quantity": 10,
                                                    "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                })
                                                st.success(f"{detail_name} 포트폴리오에 추가!")
                                            else:
                                                st.warning("이미 포트폴리오에 있습니다.")
                                                
                                        if _r.get("세력분석"):
                                            st.info(f"**세력 분석:** {_r['세력분석']}")
                                        if _r.get("analysis"):
                                            st.markdown("---")
                                            with st.container(border=True):
                                                st.markdown(_r["analysis"])

                                # ── 테마 연동 분석 (대장주·추종주·수급·역사) ─────────
                                st.markdown("#### 🔗 테마 연동 분석")
                                st.caption("대장주·추종주 순서·수급·세력·역사 패턴을 종합 분석합니다")
                                _thm_key = f"theme_pos_{detail_code}"
                                _thm_run_key = f"_thm_run_{detail_code}"
                                if st.button("🔗 테마 연동 분석 실행", key="sec_theme_btn",
                                             use_container_width=True):
                                    st.session_state[_thm_run_key] = True
                                    st.session_state.pop(_thm_key, None)
                                    st.rerun()
                                if st.session_state.get(_thm_run_key) and _thm_key not in st.session_state:
                                    with st.spinner("AI가 테마 흐름·수급·역사 패턴을 분석 중..."):
                                        try:
                                            from ai_engine import analyze_stock_theme_position
                                            _cur_sec = st.session_state.kr_selected_sector
                                            _sec_stk_flat = [
                                                {**s, "price": 0, "change_pct": 0}
                                                for subs in sector_map.get(_cur_sec, {}).values()
                                                for s in subs
                                            ]
                                            _thm_inv = get_kr_investor_trend(detail_code)
                                            _thm_res = analyze_stock_theme_position(
                                                detail_code, detail_name,
                                                price_kr or {}, _thm_inv,
                                                _cur_sec, _sec_stk_flat
                                            )
                                        except Exception as _te:
                                            _thm_res = {"error": str(_te)}
                                        st.session_state[_thm_key] = _thm_res
                                        st.session_state[_thm_run_key] = False
                                    st.rerun()
                                if _thm_key in st.session_state:
                                    _tr = st.session_state[_thm_key]
                                    if _tr.get("error"):
                                        st.error(f"분석 오류: {_tr['error']}")
                                    else:
                                        _pos = _tr.get("position", "")
                                        _pos_c = {"대장주":"#ff4b4b","선도추종주":"#f5c518","후발추종주":"#2b7cff","소외주":"#888"}.get(_pos, "#aaa")
                                        st.markdown(
                                            f"<div style='display:inline-block;background:{_pos_c}22;"
                                            f"border:1px solid {_pos_c};border-radius:8px;"
                                            f"padding:4px 12px;font-size:0.82rem;font-weight:700;"
                                            f"color:{_pos_c};margin-bottom:6px'>📍 {_pos}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        if _tr.get("position_reason"):
                                            st.caption(_tr["position_reason"])
                                        _tc1, _tc2 = st.columns(2)
                                        _tc1.markdown(
                                            f"<div style='font-size:0.68rem;color:#888'>오늘의 대장주</div>"
                                            f"<div style='font-weight:700'>{_tr.get('leader_name','?')}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        _fd = _tr.get("force_direction", "")
                                        _fd_c = "#00c853" if "유입" in _fd or "매집" in _fd else "#ff4b4b" if "이탈" in _fd else "#888"
                                        _tc2.markdown(
                                            f"<div style='font-size:0.68rem;color:#888'>세력 방향</div>"
                                            f"<div style='font-weight:700;color:{_fd_c}'>{_fd}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        _ms = _tr.get("momentum_stage", "")
                                        _cp = _tr.get("chart_pattern", "")
                                        if _ms or _cp:
                                            st.markdown(
                                                f"<div class='sc-card-sm' style='background:rgba(255,255,255,0.04);border-radius:8px;"
                                                f"padding:8px 12px;margin:6px 0;font-size:0.8rem'>"
                                                f"<b>📈 {_ms}</b>"
                                                + (f" · {_cp}" if _cp else "") + "</div>",
                                                unsafe_allow_html=True,
                                            )
                                        if _tr.get("leader_correlation"):
                                            st.info(f"🔗 **연동:** {_tr['leader_correlation']}")
                                        if _tr.get("supply_analysis"):
                                            with st.expander("💰 수급·세력 분석 상세"):
                                                render_ai_content(_tr["supply_analysis"])
                                        if _tr.get("historical_pattern"):
                                            with st.expander("📜 역사적 유사 패턴"):
                                                render_ai_content(_tr["historical_pattern"])
                                        _et = _tr.get("entry_timing", "")
                                        _et_c = {"즉시 진입":"#00c853","눌림목 대기":"#f5c518","돌파 확인 후":"#f5c518","관망 권고":"#ff4b4b"}.get(_et, "#888")
                                        if _et:
                                            st.markdown(
                                                f"<div style='background:{_et_c}15;border:1px solid {_et_c}50;"
                                                f"border-radius:8px;padding:8px 12px;margin:4px 0'>"
                                                f"<span style='color:{_et_c};font-weight:700'>⏱ {_et}</span>"
                                                + (f" — {_tr.get('entry_reason','')}" if _tr.get('entry_reason') else "")
                                                + "</div>",
                                                unsafe_allow_html=True,
                                            )
                                        _ta1, _ta2, _ta3 = st.columns(3)
                                        _ta1.metric("매수 타점", _tr.get("buy_target", "-"))
                                        _ta2.metric("목표가",    _tr.get("sell_target", "-"))
                                        _ta3.metric("손절가",    _tr.get("stop_loss", "-"))
                                        if _tr.get("risk_factors"):
                                            st.warning(f"⚠️ {_tr['risk_factors']}")

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
                                # --- [추가] 통합 섹터 순환매 로드맵 (원클릭) ---
                                with st.container(border=True):
                                    st.markdown("##### 🚀 AI 섹터 순환매 로드맵 (Pathfinder)")
                                    st.caption("현재 자금의 위치와 다음 목적지, 추천 종목과 진입 타점까지 한 번에 분석합니다.")
                                    
                                    _kr_rot_key = "kr_sector_rotation_res"
                                    if st.button("🗺️ 차기 주도 섹터 & 추천주 로드맵 생성", key="btn_kr_rot_direct", use_container_width=True, type="primary"):
                                        with st.spinner("AI가 실시간 시장 데이터를 수집하여 로드맵을 작성 중..."):
                                            # duplicate import removed
                                            # duplicate import removed
                                            # 실시간 원시 데이터 수집
                                            _vol = get_kr_volume_ranking()
                                            _chg = get_kr_change_ranking()
                                            _idx = get_kr_market_index()
                                            _raw_data = {
                                                "indices": _idx,
                                                "volume_ranking": _vol[:15],
                                                "change_ranking": _chg[:15]
                                            }
                                            _rot_res = analyze_sector_rotation("국내", _raw_data)
                                            st.session_state[_kr_rot_key] = _rot_res
                                    
                                    if _kr_rot_key in st.session_state:
                                        render_ai_content(st.session_state[_kr_rot_key])
                                        if st.button("🗑️ 분석 결과 지우기", key="clear_kr_rot"):
                                            st.session_state.pop(_kr_rot_key, None)
                                            st.rerun()

                                st.markdown("---")
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
                                        
                                        st.markdown("---")
                                        st.markdown("#### 💎 AI 선정 핫 섹터 & 종목")

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

                                    st.markdown("<hr class='toss-divider' style='margin:8px 0'>", unsafe_allow_html=True)

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
                                                    _r1c0, _r1c1, _r1c2, _r1c3 = st.columns([0.6, 4, 2, 1.2])
                                                    with _r1c0:
                                                        render_star_toggle("국내", _cd, _nm, key_suffix=f"rise_{_cd}_{_si}")
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

                                    st.markdown("<hr class='toss-divider' style='margin:8px 0'>", unsafe_allow_html=True)

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
                                            st.markdown("<hr class='toss-divider' style='margin:6px 0'>", unsafe_allow_html=True)

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
                                                                '<hr class="toss-divider" style="margin:1px 0">',
                                                                unsafe_allow_html=True,
                                                            )
                                                        _pd  = _ai_prices.get(_stk["code"], {"price": 0, "change_pct": 0.0})
                                                        _pct = _pd["change_pct"]
                                                        _pv  = _pd["price"]
                                                        _pc  = "#ff4b4b" if _pct > 0 else "#2b7cff" if _pct < 0 else "#888"
                                                        _badge = "🔑 " if _stk.get("r") == "core" else ""
                                                        _bc_star, _bc0, _bc1, _bc2, _bc3, _bc4 = st.columns([0.45, 0.3, 2.6, 1.8, 1.4, 0.45])
                                                        with _bc_star:
                                                            render_star_toggle("국내", _stk["code"], _stk["name"], key_suffix=f"ai_hot_{_stk['code']}_{_si}")
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

                                                    _sbtn_c1, _sbtn_c2 = st.columns(2)
                                                    with _sbtn_c1:
                                                        if st.button("📊 역사적 패턴", key=f"pat_btn_{_asi}", help=f"{_kw} 섹터 과거 패턴 기반 미래 예측"):
                                                            st.session_state["ai_pattern_kw"] = _kw
                                                            st.rerun()
                                                    with _sbtn_c2:
                                                        if st.button("🔗 테마 연동", key=f"thm_btn_{_asi}", help=f"{_kw} 대장주·추종주·수급·역사 분석"):
                                                            st.session_state[f"thm_run_{_kw}"] = True
                                                            st.rerun()

                                                    _thm_run_key = f"thm_run_{_kw}"
                                                    _thm_res_key = f"thm_res_{_kw}"
                                                    if st.session_state.get(_thm_run_key) and _thm_res_key not in st.session_state:
                                                        with st.spinner(f"🔍 {_kw} 테마 연동 분석 중..."):
                                                            _stk_with_data = [
                                                                {
                                                                    "name": s["name"], "code": s["code"],
                                                                    "price": _ai_prices.get(s["code"], {}).get("price", 0),
                                                                    "change_pct": _ai_prices.get(s["code"], {}).get("change_pct", 0.0),
                                                                    "volume": 0,
                                                                }
                                                                for s in (_display or [])
                                                            ]
                                                            from ai_engine import analyze_sector_theme_linkage
                                                            st.session_state[_thm_res_key] = analyze_sector_theme_linkage(_kw, _stk_with_data)
                                                            st.session_state[_thm_run_key] = False
                                                        st.rerun()

                                                    if _thm_res_key in st.session_state:
                                                        _tl = st.session_state[_thm_res_key]
                                                        if "error" in _tl:
                                                            st.error(_tl.get("error", "분석 오류"))
                                                        else:
                                                            with st.expander("🔗 테마 연동 분석 결과", expanded=True):
                                                                _tl_c1, _tl_c2 = st.columns(2)
                                                                _tl_c1.markdown(
                                                                    f"**대장주:** {_tl.get('leader_name','?')}  \n"
                                                                    f"<span style='font-size:0.75rem;color:#aaa'>{_tl.get('leader_reason','')}</span>",
                                                                    unsafe_allow_html=True,
                                                                )
                                                                _stage = _tl.get("sector_stage", "")
                                                                _stage_color = {"초기 형성": "#4caf50", "확산": "#ff9800", "과열": "#ff4b4b", "냉각": "#2b7cff"}.get(_stage, "#888")
                                                                _tl_c2.markdown(
                                                                    f"**섹터 단계:** <span style='color:{_stage_color};font-weight:700'>{_stage}</span>  \n"
                                                                    f"<span style='font-size:0.75rem;color:#aaa'>{_tl.get('stage_reason','')}</span>",
                                                                    unsafe_allow_html=True,
                                                                )
                                                                _sup_sig = _tl.get("supply_signal", "")
                                                                _sup_color = "#00c853" if "유입" in _sup_sig or "매집" in _sup_sig else "#ff4b4b" if "이탈" in _sup_sig else "#f5c518"
                                                                st.markdown(
                                                                    f"<div style='background:rgba(255,255,255,0.04);border-left:3px solid {_sup_color};"
                                                                    f"border-radius:0 6px 6px 0;padding:6px 10px;margin:6px 0'>"
                                                                    f"<span style='font-size:0.72rem;font-weight:700;color:{_sup_color}'>📡 {_sup_sig}</span>"
                                                                    f"<span style='font-size:0.72rem;color:#aaa;margin-left:8px'>{_tl.get('supply_detail','')}</span>"
                                                                    f"</div>",
                                                                    unsafe_allow_html=True,
                                                                )
                                                                _followers = _tl.get("followers", [])
                                                                if _followers:
                                                                    st.markdown("**후속주:**")
                                                                    for _f in _followers:
                                                                        st.write(f"- {_f}")


                                # ── hot_score 맵 구성 (AI 시장분석 결과 재활용) ──
                                _hot_score_map: dict = {}  # {sector_name: {score, reason, news}}
                                try:
                                    from ai_engine import analyze_kr_hot_sectors
                                    _hs_res = analyze_kr_hot_sectors()
                                    if isinstance(_hs_res, dict) and _hs_res.get("sectors"):
                                        for _hs in _hs_res["sectors"]:
                                            _kw = _hs.get("keyword", "")
                                            if _kw in sector_names:
                                                _hot_score_map[_kw] = {
                                                    "score": _hs.get("hot_score", 0),
                                                    "reason": _hs.get("reason", ""),
                                                    "news": _hs.get("news_title", ""),
                                                }
                                except Exception:
                                    pass

                                def _sector_tier(name):
                                    sc = _hot_score_map.get(name, {}).get("score", 0)
                                    if sc >= 7: return 0
                                    if sc >= 4: return 1
                                    return 2

                                _sorted_sector_names = sorted(
                                    sector_names,
                                    key=lambda n: (_sector_tier(n), -_hot_score_map.get(n, {}).get("score", 0))
                                )

                                # ── 섹터 배지 목록 ─────────────────────────────────
                                st.markdown(
                                    "<p style='font-size:0.72rem;color:#888;margin:2px 0 6px 0'>"
                                    "섹터를 클릭해 종목을 탐색하세요 · 🔥 = 오늘의 이슈 섹터</p>",
                                    unsafe_allow_html=True,
                                )
                                with st.container(height=190):
                                    _prev_tier = -1
                                    for _sn in _sorted_sector_names:
                                        _tier = _sector_tier(_sn)
                                        _hs_info = _hot_score_map.get(_sn, {})
                                        _sc = _hs_info.get("score", 0)
                                        _reason_short = _hs_info.get("reason", "")[:40]
                                        _news_short   = _hs_info.get("news",   "")[:35]

                                        if _tier != _prev_tier:
                                            if _tier == 0:
                                                st.markdown(
                                                    "<p style='font-size:0.68rem;font-weight:700;color:#ff4b4b;"
                                                    "margin:4px 0 2px 0;letter-spacing:0.05em'>🔥 HOT 섹터</p>",
                                                    unsafe_allow_html=True,
                                                )
                                            elif _tier == 1:
                                                st.markdown(
                                                    "<p style='font-size:0.68rem;font-weight:700;color:#f5c518;"
                                                    "margin:6px 0 2px 0;letter-spacing:0.05em'>⭐ 관심 섹터</p>",
                                                    unsafe_allow_html=True,
                                                )
                                            else:
                                                st.markdown(
                                                    "<p style='font-size:0.68rem;color:#555;"
                                                    "margin:6px 0 2px 0;letter-spacing:0.05em'>일반 섹터</p>",
                                                    unsafe_allow_html=True,
                                                )
                                            _prev_tier = _tier

                                        _is_sel = st.session_state.kr_selected_sector == _sn
                                        if _tier == 0:
                                            _badge_html = (
                                                f"🔥 {_sn} <span style='font-size:0.65rem;color:#ff9800'>"
                                                f"[{_sc}점]</span>"
                                            )
                                            if _reason_short:
                                                _badge_html += (
                                                    f"<br><span style='font-size:0.63rem;color:#aaa'>"
                                                    f"{_reason_short}{'…' if len(_hs_info.get('reason',''))>40 else ''}</span>"
                                                )
                                            if _news_short:
                                                _badge_html += (
                                                    f"<span style='font-size:0.62rem;color:#666'>"
                                                    f" · {_news_short}</span>"
                                                )
                                            _bg = "rgba(255,75,75,0.12)" if _is_sel else "rgba(255,75,75,0.06)"
                                            _border = "#ff4b4b" if _is_sel else "rgba(255,75,75,0.35)"
                                        elif _tier == 1:
                                            _badge_html = (
                                                f"⭐ {_sn} <span style='font-size:0.65rem;color:#888'>"
                                                f"[{_sc}점]</span>"
                                            )
                                            if _reason_short:
                                                _badge_html += (
                                                    f"<br><span style='font-size:0.63rem;color:#888'>"
                                                    f"{_reason_short}{'…' if len(_hs_info.get('reason',''))>40 else ''}</span>"
                                                )
                                            _bg = "rgba(245,197,24,0.10)" if _is_sel else "rgba(245,197,24,0.04)"
                                            _border = "#f5c518" if _is_sel else "rgba(245,197,24,0.25)"
                                        else:
                                            _badge_html = f"{_sn}"
                                            _bg = "rgba(255,255,255,0.06)" if _is_sel else "transparent"
                                            _border = "rgba(255,255,255,0.2)" if _is_sel else "rgba(255,255,255,0.06)"

                                        _bc1, _bc2 = st.columns([5, 1])
                                        _bc1.markdown(
                                            f"<div style='border:1px solid {_border};background:{_bg};"
                                            f"border-radius:7px;padding:5px 10px;margin:2px 0'>"
                                            f"{_badge_html}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        if _bc2.button("▶", key=f"sec_btn_{_sn}", use_container_width=True):
                                            st.session_state.kr_selected_sector = _sn
                                            st.session_state["kr_sector_selectbox"] = _sn
                                            st.rerun()

                                # 선택된 섹터 표시 (드롭다운 폴백 + 확인용)
                                _cur_idx = _sorted_sector_names.index(st.session_state.kr_selected_sector) \
                                    if st.session_state.kr_selected_sector in _sorted_sector_names else 0
                                _sel_sector = st.selectbox(
                                    "섹터 선택 (직접 선택)",
                                    _sorted_sector_names,
                                    index=_cur_idx,
                                    key="kr_sector_selectbox",
                                    label_visibility="visible",
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
                                            st.markdown('<hr class="toss-divider" style="margin:2px 0">', unsafe_allow_html=True)
                                        pdata = prices.get(s["code"], {"price": 0, "change_pct": 0.0})
                                        pct   = pdata["change_pct"]
                                        pval  = pdata["price"]
                                        pct_color = "#ff4b4b" if pct > 0 else "#2b7cff" if pct < 0 else "#888"
                                        other_locs = [loc for loc in code_locations.get(s["code"], []) if loc != f"{selected_sector} › {sub_name}"]
                                        help_text = f"다중 섹터: {', '.join(other_locs)}" if other_locs else None
                                        c_star, c0, c1, c2, c3, c4 = st.columns([0.45, 0.35, 2.8, 1.8, 1.4, 0.45])
                                        with c_star:
                                            render_star_toggle("국내", s["code"], s["name"], key_suffix=f"sec_stk_{s['code']}_{i}")
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
                                                st.markdown('<hr class="toss-divider" style="margin:4px 0 6px 0">', unsafe_allow_html=True)
                                                _render_sector_stocks(sub_name, stocks, prices, code_locations, selected_sector)




        else:
            # ── 미국 시장 지수 배너 + 마켓 세션 ─────────────────────────────
            with st.spinner(""):
                us_indices = get_us_market_indices()
            _us_session = get_us_market_session()

            # 마켓 세션 배지
            _sess_col   = _us_session["color"]
            _sess_label = _us_session["label"]
            _sess_time  = _us_session["et_time"]
            _sess_id    = _us_session["session"]

            # 지수 배너
            _us_banner = []
            for _in, _key in [("S&P 500", "S&P 500"), ("NASDAQ", "NASDAQ"), ("DOW", "DOW"), ("VIX", "VIX")]:
                _id  = (us_indices or {}).get(_key, {})
                _iv  = _id.get("price", 0)
                _ic  = _id.get("change", 0)
                _ip  = _id.get("change_pct", 0)
                _col = "#00c853" if _ic >= 0 else "#ff4b4b"
                if _in == "VIX":
                    _col = "#f5c518" if _iv < 20 else "#ff4b4b"
                _sg  = "+" if _ic >= 0 else ""
                if _iv > 0:
                    _us_banner.append(
                        f"<div class='index-item'>"
                        f"<span class='index-name'>{_in}</span>"
                        f"<span class='index-val' style='color:{_col}'>{_iv:,.2f}</span>"
                        f"<span class='index-chg' style='color:{_col}'>{_sg}{_ic:.2f} ({_sg}{_ip:.2f}%)</span>"
                        f"</div>"
                    )

            _sess_html = (
                f"<div style='display:flex;flex-direction:column;align-items:center;"
                f"background:rgba(255,255,255,0.04);border:1px solid {_sess_col}40;"
                f"border-radius:8px;padding:4px 12px;margin-left:auto'>"
                f"<span style='font-size:0.82rem;font-weight:700;color:{_sess_col}'>{_sess_label}</span>"
                f"<span style='font-size:0.65rem;color:#888'>{_sess_time}</span>"
                f"</div>"
            )
            if _sess_id in ("pre", "after"):
                _sess_html += (
                    f"<div style='font-size:0.68rem;color:#888;margin-left:8px;align-self:flex-end;"
                    f"padding-bottom:4px'>연장 시간 — 유동성 낮음, 가격 급변 주의</div>"
                )

            if _us_banner:
                st.markdown(
                    f"<div class='index-banner' style='flex-wrap:wrap;gap:16px'>{''.join(_us_banner)}{_sess_html}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div style='display:flex'>{_sess_html}</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("<hr class='toss-divider'>", unsafe_allow_html=True)

            # ── 세션 상태 초기화 ──────────────────────────────────────────
            for _k, _v in [
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
                ("us_selected_pick_idx", 0),
                ("us_chart_type",    "일봉"),
                ("us_daily_period",  "3mo"),
            ]:
                if _k not in st.session_state:
                    st.session_state[_k] = _v

            us_mode = st.session_state.us_mode

            # ── US 신호 스캔 (모드 무관, 항상 실행 → 네비 배지용) ───────────
            if _HAVE_AUTOREFRESH:
                _st_autorefresh(interval=180_000, key="us_signal_autorefresh")

            def _us_quick_signal_scan() -> int:
                try:
                    from ai_engine import _compute_us_prebreakout_signals
                    from data_kr import get_us_volume_ranking, get_us_change_ranking
                    _qvol = get_us_volume_ranking() or []
                    _qchg = get_us_change_ranking() or []
                    _qpre, _ = _compute_us_prebreakout_signals(_qvol, _qchg)
                    return sum(1 for x in _qpre if x.get("_signal", {}).get("signal_score", 0) >= 3)
                except Exception:
                    return 0

            _us_sig_count_key = "_us_sig_count_last"
            _us_sig_ts_key    = "_us_sig_ts_last"
            _us_new_count = _us_quick_signal_scan()
            st.session_state[_us_sig_count_key] = _us_new_count
            st.session_state[_us_sig_ts_key] = (datetime.now() + timedelta(hours=9)).strftime("%H:%M")
            _us_sig_ts = st.session_state.get(_us_sig_ts_key, "")

            # ══════════════════════════════════════════════════════════════
            # 🎯 US AI 타점 보드
            # ══════════════════════════════════════════════════════════════
            if us_mode == "⭐ 즐겨찾기 관리":
                show_favorites_center()
            elif us_mode == "🎯 AI 타점 보드":
                _us_pb_key  = "us_picks_result"
                _us_run_key = "_us_picks_pending"

                # AI 호출 — 버튼 클릭 후 rerun 시 실행 (패널 렌더 전에 처리)
                if st.session_state.get(_us_run_key) and _us_pb_key not in st.session_state:
                    with st.spinner("AI가 US 시장·뉴스·옵션플로우를 분석 중입니다..."):
                        try:
                            from ai_engine import generate_us_realtime_picks
                            from data_kr import get_us_volume_ranking, get_us_change_ranking
                            _us_mkt  = get_us_market_indices() or {}
                            _us_vol  = get_us_volume_ranking() or []
                            _us_chg  = get_us_change_ranking() or []
                            _us_picks = generate_us_realtime_picks(_us_mkt, _us_vol, _us_chg)
                        except Exception as _upe:
                            _us_picks = {"error": str(_upe), "picks": []}
                        _us_picks["_ts"] = (datetime.now() + timedelta(hours=9)).strftime("%H:%M")
                        st.session_state[_us_pb_key] = _us_picks
                        st.session_state[_us_run_key] = False
                    st.rerun()

                # ── 좌/우 2패널 레이아웃 ─────────────────────────────────
                _us_pb_left, _us_pb_right = st.columns([4.5, 5.5], gap="small")

                # ── 좌 패널: 컨트롤 + 종목 목록 ─────────────────────────
                with _us_pb_left:
                    with st.container(height=750):
                        # 신호 배너
                        if _us_new_count > 0 and _us_pb_key not in st.session_state:
                            st.markdown(
                                f"""<div style='background:linear-gradient(90deg,rgba(0,200,83,0.15),rgba(0,150,60,0.08));
                                    border:1.5px solid #00c853;border-radius:10px;padding:8px 14px;margin-bottom:8px;
                                    display:flex;align-items:center;gap:8px;animation:pulse 1.5s ease-in-out infinite;'>
                                  <span style='font-size:1rem'>🚀</span>
                                  <span style='flex:1;font-size:0.75rem;font-weight:700;color:#00c853'>
                                    {_us_new_count}개 US 신호 감지 ({_us_sig_ts})</span>
                                </div>
                                <style>@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.6}}}}</style>""",
                                unsafe_allow_html=True,
                            )
                        elif _us_new_count == 0 and _us_sig_ts:
                            st.caption(f"🟢 스캔: {_us_sig_ts} — 신호 없음")

                        # 실행 / 초기화 버튼
                        _us_pb_c1, _us_pb_c2 = st.columns([3, 1])
                        with _us_pb_c1:
                            if st.button("🔄 US AI 타점 분석 실행", key="us_picks_btn",
                                         type="primary", use_container_width=True):
                                st.session_state[_us_run_key] = True
                                st.session_state.pop(_us_pb_key, None)
                                st.session_state["us_selected_pick_idx"] = 0
                                st.rerun()
                        with _us_pb_c2:
                            if st.button("🗑", key="us_picks_clear", use_container_width=True):
                                st.session_state.pop(_us_pb_key, None)
                                st.session_state["us_selected_pick_idx"] = 0
                                st.rerun()

                        if _us_pb_key in st.session_state:
                            _us_res  = st.session_state[_us_pb_key]
                            _us_cond = _us_res.get("market_condition", "")
                            _us_cond_color = "#00c853" if "상승" in _us_cond else "#ff4b4b" if "하락" in _us_cond else "#f5c518"
                            _us_cond_icon  = "🟢" if "상승" in _us_cond else "🔴" if "하락" in _us_cond else "🟡"
                            st.markdown(
                                f"<div style='font-size:0.7rem;padding:4px 8px;margin:6px 0;"
                                f"border-left:3px solid {_us_cond_color};border-radius:0 6px 6px 0'>"
                                f"{_us_cond_icon} <b style='color:{_us_cond_color}'>{_us_cond}</b>"
                                f"&nbsp;<span style='color:#666;font-size:0.62rem'>{_us_res.get('_ts','')}</span></div>",
                                unsafe_allow_html=True,
                            )
                            if _us_res.get("error") and not _us_res.get("picks"):
                                st.error(f"분석 오류: {_us_res['error']}")
                            elif not _us_res.get("picks"):
                                st.info("추천 종목이 없습니다.")
                            else:
                                _us_sel = st.session_state.get("us_selected_pick_idx", 0)
                                st.markdown(
                                    f"<div style='font-size:0.65rem;color:#666;margin-bottom:4px'>"
                                    f"총 {len(_us_res['picks'])}개 종목 — 클릭하여 상세 확인</div>",
                                    unsafe_allow_html=True,
                                )
                                for _uci, _up in enumerate(_us_res["picks"]):
                                    _up_ticker  = _up.get("ticker", "")
                                    _up_name    = _up.get("name", _up_ticker)
                                    _up_chg     = float(_up.get("change_pct", 0) or 0)
                                    _up_entry   = _up.get("entry", 0)
                                    _up_target  = _up.get("target", 0)
                                    _up_urg     = _up.get("urgency", "")
                                    _up_upside  = round((_up_target - _up_entry) / _up_entry * 100, 1) if _up_entry > 0 else 0
                                    _up_urg_icon  = "⚡" if "즉시" in _up_urg else ("🌙" if "내일" in _up_urg or "스윙" in _up_urg else "🕐")
                                    _up_urg_color = "#ff9800" if "즉시" in _up_urg else ("#a78bfa" if "스윙" in _up_urg else "#888")
                                    _up_chg_c   = "#ff4b4b" if _up_chg >= 0 else "#2b7cff"
                                    _up_is_sel  = (_uci == _us_sel)
                                    _up_row_bg  = "rgba(0,200,83,0.10)" if _up_is_sel else "rgba(255,255,255,0.03)"
                                    _up_row_bdr = "1px solid rgba(0,200,83,0.5)" if _up_is_sel else "1px solid rgba(255,255,255,0.07)"
                                    _u_star_col, _u_card_col = st.columns([0.15, 0.85])
                                    with _u_star_col:
                                        render_star_toggle("미국", _up_ticker, _up_name, f"us_pick_{_uci}")
                                    with _u_card_col:
                                        st.markdown(
                                            f"<div style='background:{_up_row_bg};border:{_up_row_bdr};"
                                            f"border-radius:8px;padding:8px 10px;margin-bottom:2px'>"
                                            f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                                            f"<span style='font-size:0.8rem;font-weight:700'>{_up_name} <span style='font-size:0.65rem;color:#666'>({_up_ticker})</span></span>"
                                            f"<span style='font-size:0.68rem;color:{_up_urg_color};font-weight:600'>"
                                            f"{_up_urg_icon} {_up_urg}</span>"
                                            f"</div>"
                                            f"<div style='display:flex;justify-content:space-between;margin-top:3px'>"
                                            f"<span style='font-size:0.65rem;color:#777'>"
                                            f"진입 ${_up_entry:,.2f} → +{_up_upside}%</span>"
                                            f"<span style='font-size:0.68rem;color:{_up_chg_c};font-weight:600'>"
                                            f"{'▲' if _up_chg>=0 else '▼'}{abs(_up_chg):.1f}%</span>"
                                            f"</div></div>",
                                            unsafe_allow_html=True,
                                        )
                                    if st.button(
                                        "✓ 선택됨" if _up_is_sel else "▶ 상세보기",
                                        key=f"us_sel_pick_{_uci}",
                                        use_container_width=True,
                                        type="primary" if _up_is_sel else "secondary",
                                    ):
                                        st.session_state["us_selected_pick_idx"] = _uci
                                        st.rerun()
                        else:
                            st.markdown(
                                "<div style='text-align:center;padding:50px 0;color:#555'>"
                                "<div style='font-size:2rem'>🎯</div>"
                                "<div style='margin-top:8px;font-size:0.85rem'>AI 분석을 실행하면<br>"
                                "종목 목록이 여기에 표시됩니다</div>"
                                "</div>",
                                unsafe_allow_html=True,
                            )

                # ── 우 패널: 선택 종목 상세 카드 ─────────────────────────
                with _us_pb_right:
                    with st.container(height=750):
                        if _us_pb_key not in st.session_state or not st.session_state[_us_pb_key].get("picks"):
                            st.markdown(
                                "<div style='display:flex;flex-direction:column;align-items:center;"
                                "justify-content:center;height:200px;color:#444'>"
                                "<div style='font-size:3rem'>📊</div>"
                                "<div style='margin-top:12px;font-size:0.88rem;text-align:center;line-height:1.6'>"
                                "좌측에서 AI 분석을 실행하면<br>선택 종목 상세가 여기에 표시됩니다</div>"
                                "</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            _us_res     = st.session_state[_us_pb_key]
                            _us_sel_idx = st.session_state.get("us_selected_pick_idx", 0)
                            _us_sel_idx = min(_us_sel_idx, len(_us_res["picks"]) - 1)
                            _up         = _us_res["picks"][_us_sel_idx]

                            _up_ticker  = _up.get("ticker", "")
                            _up_name    = _up.get("name", _up_ticker)
                            _up_chg     = float(_up.get("change_pct", 0) or 0)
                            _up_pat     = _up.get("pattern", "")
                            _up_hrz     = _up.get("horizon", "")
                            _up_urg     = _up.get("urgency", "")
                            _up_theme   = _up.get("theme", "")
                            _up_reason  = _up.get("reason", "")
                            _up_entry   = _up.get("entry", 0)
                            _up_target  = _up.get("target", 0)
                            _up_stop    = _up.get("stop", 0)
                            _up_cur     = _up.get("current_price", 0)
                            _up_rank    = _up.get("rank", _us_sel_idx + 1)
                            _up_upside  = round((_up_target - _up_entry) / _up_entry * 100, 1) if _up_entry > 0 else 0
                            _up_themes  = [t.strip() for t in str(_up_theme).split(",") if t.strip()]
                            _up_chg_col = "#ff4b4b" if _up_chg >= 0 else "#2b7cff"
                            _up_chg_sign = "▲" if _up_chg >= 0 else "▼"
                            _up_urg_icon  = "⚡" if "즉시" in _up_urg else ("🌙" if "스윙" in _up_urg else "🕐")
                            _up_urg_color = "#ff9800" if "즉시" in _up_urg else ("#a78bfa" if "스윙" in _up_urg else "#888")
                            _up_urg_bg    = ("rgba(255,152,0,0.15)" if "즉시" in _up_urg
                                             else "rgba(167,139,250,0.15)" if "스윙" in _up_urg
                                             else "rgba(255,255,255,0.06)")
                            _up_hz_color = "#00c853" if "당일" in _up_hrz or "스캘핑" in _up_hrz else "#f5c518"
                            _up_already_surged = _up_chg >= 12

                            _up_cur_html = (
                                f"<div style='font-size:0.8rem;color:#aaa;margin-bottom:8px'>"
                                f"현재 <b style='color:#eee'>${_up_cur:,.2f}</b>&nbsp;"
                                f"<span style='color:{_up_chg_col};font-weight:700'>"
                                f"{_up_chg_sign} {abs(_up_chg):.2f}%</span></div>"
                            ) if _up_cur > 0 else ""

                            _up_pattern_html = (
                                f"<div style='font-size:0.62rem;color:#7dd3fc;"
                                f"background:rgba(125,211,252,0.08);border-radius:6px;"
                                f"padding:3px 8px;margin-bottom:6px;display:inline-block'>"
                                f"📊 {_up_pat}</div>"
                            ) if _up_pat else ""

                            _up_theme_html = "".join(
                                f"<span style='background:rgba(255,255,255,0.08);"
                                f"border-radius:10px;padding:2px 7px;font-size:0.63rem;"
                                f"color:#aaa;margin-right:4px'>{th}</span>"
                                for th in _up_themes
                            )

                            _up_warn_html = (
                                "<div style='background:rgba(255,75,75,0.15);border:1px solid #ff4b4b;"
                                "border-radius:8px;padding:4px 8px;font-size:0.65rem;color:#ff4b4b;"
                                "margin-bottom:8px'>⚠️ 이미 많이 오른 종목 — 진입 신중</div>"
                            ) if _up_already_surged else ""

                            _up_border_color = "rgba(255,75,75,0.3)" if _up_already_surged else "rgba(255,255,255,0.1)"

                            _up_card_html = (
                                f"<div class='toss-card sc-card' style='"
                                f"border-color:{_up_border_color};padding:14px 14px 12px 14px'>"
                                f"<div style='display:flex;justify-content:space-between;"
                                f"align-items:flex-start;margin-bottom:6px'>"
                                f"<div>"
                                f"<span style='font-size:0.7rem;color:#888'>#{_up_rank}</span>&nbsp;"
                                f"<span style='font-size:1rem;font-weight:700'>{_up_name}</span><br>"
                                f"<span style='font-size:0.68rem;color:#666'>{_up_ticker}</span>"
                                f"</div>"
                                f"<div style='text-align:right'>"
                                f"<span style='background:{_up_urg_bg};color:{_up_urg_color};"
                                f"border-radius:10px;padding:2px 7px;font-size:0.65rem;font-weight:700;"
                                f"display:block;margin-bottom:3px'>{_up_urg_icon} {_up_urg}</span>"
                                f"<span style='color:{_up_hz_color};font-size:0.6rem;font-weight:600'>{_up_hrz}</span>"
                                f"</div></div>"
                                + _up_warn_html
                                + _up_pattern_html
                                + _up_cur_html +
                                f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;"
                                f"gap:6px;margin-bottom:10px'>"
                                f"<div style='background:rgba(255,255,255,0.07);"
                                f"border:1px solid rgba(255,255,255,0.12);border-radius:8px;"
                                f"padding:6px;text-align:center'>"
                                f"<div style='font-size:0.6rem;color:#888'>매수 타점</div>"
                                f"<div style='font-size:0.85rem;font-weight:700'>${_up_entry:,.2f}</div></div>"
                                f"<div style='background:rgba(0,200,83,0.12);"
                                f"border:1px solid rgba(0,200,83,0.25);border-radius:8px;"
                                f"padding:6px;text-align:center'>"
                                f"<div style='font-size:0.6rem;color:#888'>목표가</div>"
                                f"<div style='font-size:0.85rem;font-weight:700;color:#00c853'>"
                                f"${_up_target:,.2f}</div>"
                                f"<div style='font-size:0.6rem;color:#00c853'>+{_up_upside}%</div></div>"
                                f"<div style='background:rgba(43,124,255,0.12);"
                                f"border:1px solid rgba(43,124,255,0.25);border-radius:8px;"
                                f"padding:6px;text-align:center'>"
                                f"<div style='font-size:0.6rem;color:#888'>손절가</div>"
                                f"<div style='font-size:0.85rem;font-weight:700;color:#2b7cff'>"
                                f"${_up_stop:,.2f}</div></div>"
                                f"</div>"
                                f"<div style='font-size:0.72rem;color:#bbb;line-height:1.6;"
                                f"margin-bottom:8px'>{_up.get('reason','')}</div>"
                                + _up_theme_html
                                + "</div>"
                            )
                            st.markdown(_up_card_html, unsafe_allow_html=True)

                            _up_btn_c1, _up_btn_c2 = st.columns(2)
                            with _up_btn_c1:
                                if st.button("상세 분석 →", key=f"us_pk_detail_{_up_ticker}_{_us_sel_idx}",
                                             use_container_width=True):
                                    st.session_state.us_selected_ticker      = _up_ticker
                                    st.session_state.us_selected_name        = _up_name
                                    st.session_state.us_mode                 = "📊 일반 주식 검색"
                                    st.rerun()
                            with _up_btn_c2:
                                if st.button("▶ 차트 보기", key=f"us_pk_chart_{_up_ticker}_{_us_sel_idx}",
                                             use_container_width=True):
                                    st.session_state.us_selected_ticker      = _up_ticker
                                    st.session_state.us_selected_name        = _up_name
                                    st.session_state.us_sector_detail_ticker = _up_ticker
                                    st.session_state.us_sector_detail_name   = _up_name
                                    st.session_state.us_sector_view          = "detail"
                                    st.session_state.us_mode                 = "🔥 오늘의 이슈 섹터"
                                    st.rerun()

            # ══════════════════════════════════════════════════════════════
            # 📊 종목검색 / 🔥 섹터분석 (상단 네비로 전환)
            # ══════════════════════════════════════════════════════════════
            if us_mode in ("📊 일반 주식 검색", "🔥 오늘의 이슈 섹터"):
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

                col_us_chart, col_us_right = st.columns([5.5, 4.5])
                with col_us_chart:
                    _us_chart_ctr = st.container(height=750)
                with col_us_right:
                    _us_right_ctr = st.container(height=750)
                with _us_chart_ctr:
                    if us_mode == "🔥 오늘의 이슈 섹터":
                        if st.session_state.us_sector_view == "detail":
                            _us_dticker   = st.session_state.us_sector_detail_ticker
                            _us_dname     = st.session_state.us_sector_detail_name
                            _us_dexchange = st.session_state.get("us_sector_detail_exchange", "NASDAQ")
                            _us_tv_sym    = f"{_us_dexchange}:{_us_dticker}"

                            # 이름 보정
                            from data_kr import get_us_ticker_map as _get_us_tm_head
                            _us_tm_head = _get_us_tm_head()
                            _real_us_dname = _us_dname
                            if _us_tm_head and _us_dticker in _us_tm_head:
                                _real_us_dname = _us_tm_head[_us_dticker].get("name", _us_dname)
                            elif detail_us and detail_us.get('name') and detail_us['name'] != _us_dticker:
                                _real_us_dname = detail_us['name']
                            
                            if st.session_state.us_sector_detail_name != _real_us_dname:
                                st.session_state.us_sector_detail_name = _real_us_dname

                            if detail_us:
                                _chg_cur = detail_us["change_pct"]
                                _col_cur = "#00c853" if _chg_cur >= 0 else "#ff4b4b"
                                _ar_cur  = "▲" if _chg_cur >= 0 else "▼"
                                st.markdown(
                                    f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px'>"
                                    f"<span style='font-size:1.25rem;font-weight:700'>**{_real_us_dname}**</span> "
                                    f"<span style='font-size:0.9rem;color:#888'>({_us_dticker})</span> &nbsp; "
                                    f"<span style='font-size:1.1rem;font-weight:600'>${detail_us['price']:,.2f}</span> &nbsp; "
                                    f"<span style='color:{_col_cur};font-size:1rem;font-weight:600'>{_ar_cur} {_chg_cur:+.2f}%</span>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.markdown(f"**{_real_us_dname}** ({_us_dticker})")
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
                            # 이름 보정
                            from data_kr import get_us_ticker_map as _get_us_tm_head_g
                            _us_tm_head_g = _get_us_tm_head_g()
                            _real_us_name = _us_ticker_cur
                            if _us_tm_head_g and _us_ticker_cur in _us_tm_head_g:
                                _real_us_name = _us_tm_head_g[_us_ticker_cur].get("name", _us_ticker_cur)
                            elif detail_us.get('name') and detail_us['name'] != _us_ticker_cur:
                                _real_us_name = detail_us['name']
                            
                            if st.session_state.us_selected_name != _real_us_name:
                                st.session_state.us_selected_name = _real_us_name

                            _chg = detail_us.get("change_pct", 0)
                            _col = "#00c853" if _chg >= 0 else "#ff4b4b"
                            _ar  = "▲" if _chg >= 0 else "▼"
                            st.markdown(
                                f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px'>"
                                f"<span style='font-size:1.25rem;font-weight:700'>**{_real_us_name}**</span> "
                                f"<span style='font-size:0.9rem;color:#888'>({_us_ticker_cur})</span> &nbsp; "
                                f"<span style='font-size:1.1rem;font-weight:600'>${detail_us.get('price', 0):,.2f}</span> &nbsp; "
                                f"<span style='color:{_col};font-size:1rem;font-weight:600'>{_ar} {_chg:+.2f}%</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                        # 차트 타입 토글: 일봉 | 분봉
                        _us_ct_c1, _us_ct_c2, _ = st.columns([1, 1, 6])
                        for _us_ctcol, _us_ctn in [(_us_ct_c1, "일봉"), (_us_ct_c2, "분봉")]:
                            if _us_ctcol.button(
                                _us_ctn, key=f"us_chart_type_{_us_ctn}",
                                type="primary" if st.session_state.us_chart_type == _us_ctn else "secondary",
                                use_container_width=True,
                            ):
                                st.session_state.us_chart_type = _us_ctn
                                st.rerun()

                        _us_tv_iv = "5" if st.session_state.us_chart_type == "분봉" else "D"
                        _us_exch  = (detail_us.get("exchange", "NASDAQ") if detail_us else "NASDAQ").upper()
                        if _us_exch not in ("NASDAQ", "NYSE", "AMEX", "CBOE"):
                            _us_exch = "NASDAQ"
                        _tv_chart(f"{_us_exch}:{_us_ticker_cur}", interval=_us_tv_iv, height=660)

                with _us_right_ctr:
                    if us_mode == "📊 일반 주식 검색":
                        from data_kr import get_us_ticker_map as _get_us_tm
                        _us_tm = _get_us_tm()  # {ticker: {"name": name, "exchange": exch}}
                        _us_all_stk: dict = {}
                        if _us_tm:
                            for _tk, _ti in _us_tm.items():
                                _lbl = f"{_ti['name']} ({_tk})"
                                _us_all_stk[_lbl] = {"ticker": _tk, "exchange": _ti.get("exchange", "NASDAQ")}
                        else:
                            # 폴백: 섹터맵 + 인기 종목
                            from db import load_us_sector_map as _load_us_sm
                            _us_sm = _load_us_sm()
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
                            # 이름 찾기 시도
                            _new_name = _us_man
                            if _us_tm and _us_man in _us_tm:
                                _new_name = _us_tm[_us_man].get("name", _us_man)
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
                                    # 즐겨찾기 버튼 (US 상단)
                                    _u_fav_lbl = "⭐ 즐겨찾기 등록"
                                    if st.button(_u_fav_lbl, use_container_width=True, key=f"fav_btn_us_top_{st.session_state.us_selected_ticker}"):
                                        from db import save_favorite
                                        _ok, _msg = save_favorite("미국", st.session_state.us_selected_ticker, detail_us["name"])
                                        if _ok: st.success(_msg)
                                        else: st.error(_msg)

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
                                    _um1.metric("거래량",   f"{detail_us.get('volume', 0):,}")
                                    _um2.metric("시가",     f"${detail_us.get('open', 0):,.2f}")
                                    _um3.metric("시가총액", detail_us.get("market_cap", "-"))
                                    _um4, _um5, _um6 = st.columns(3)
                                    _um4.metric("고가", f"${detail_us.get('high', 0):,.2f}")
                                    _um5.metric("저가", f"${detail_us.get('low', 0):,.2f}")
                                    _um6.metric("PER",  str(detail_us.get("per", "-")))
                                    _um7, _um8, _um9 = st.columns(3)
                                    _um7.metric("52주 최고", f"${detail_us.get('w52_high', 0):,.2f}")
                                    _um8.metric("52주 최저", f"${detail_us.get('w52_low', 0):,.2f}")
                                    _um9.metric("베타",      str(detail_us.get("beta", "-")))
                                    _uwl = detail_us.get("w52_low",  0) or 0
                                    _uwh = detail_us.get("w52_high", 0) or 0
                                    _ucp = detail_us.get("price", 0)
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
                                # ── 연장 거래 시간 (프리/애프터마켓) ──
                                _pre_p  = detail_us.get("pre_price", 0) or 0
                                _pre_c  = detail_us.get("pre_pct", 0) or 0
                                _post_p = detail_us.get("post_price", 0) or 0
                                _post_c = detail_us.get("post_pct", 0) or 0
                                if _pre_p > 0 or _post_p > 0:
                                    st.markdown(
                                        "<div style='font-size:0.72rem;color:#888;margin:10px 0 4px 0;"
                                        "font-weight:600;letter-spacing:0.04em'>⏱ 연장 거래 시간</div>",
                                        unsafe_allow_html=True,
                                    )
                                    _ext_cols = st.columns(2)
                                    if _pre_p > 0:
                                        _pc = "#f5c518"
                                        _par = "▲" if _pre_c >= 0 else "▼"
                                        _ext_cols[0].markdown(
                                            f"<div style='background:rgba(245,197,24,0.08);border:1px solid"
                                            f" rgba(245,197,24,0.3);border-radius:8px;padding:8px 10px'>"
                                            f"<div style='font-size:0.65rem;color:#888;margin-bottom:2px'>🌅 프리마켓</div>"
                                            f"<div style='font-size:1rem;font-weight:700'>${_pre_p:,.2f}</div>"
                                            f"<div style='font-size:0.72rem;color:{_pc};font-weight:600'>"
                                            f"{_par} {_pre_c:+.2f}%</div></div>",
                                            unsafe_allow_html=True,
                                        )
                                    if _post_p > 0:
                                        _poc = "#7b61ff"
                                        _poar = "▲" if _post_c >= 0 else "▼"
                                        _ext_cols[1].markdown(
                                            f"<div style='background:rgba(123,97,255,0.08);border:1px solid"
                                            f" rgba(123,97,255,0.3);border-radius:8px;padding:8px 10px'>"
                                            f"<div style='font-size:0.65rem;color:#888;margin-bottom:2px'>🌙 애프터마켓</div>"
                                            f"<div style='font-size:1rem;font-weight:700'>${_post_p:,.2f}</div>"
                                            f"<div style='font-size:0.72rem;color:{_poc};font-weight:600'>"
                                            f"{_poar} {_post_c:+.2f}%</div></div>",
                                            unsafe_allow_html=True,
                                        )

                                # ── 단기 / 중기 / 장기 추천 분석 (US) ───────────
                                _us_chg2  = detail_us.get("change_pct", 0) or 0
                                _us_cp    = detail_us.get("price", 0) or 0
                                _us_wl    = detail_us.get("w52_low",  0) or 0
                                _us_wh    = detail_us.get("w52_high", 0) or 0
                                _us_per   = detail_us.get("per", "-")
                                _us_beta  = detail_us.get("beta", 1.0) or 1.0

                                _us_band  = (_us_cp - _us_wl) / (_us_wh - _us_wl) * 100 if _us_wh > _us_wl > 0 else 50

                                # 극단타 판정 (US)
                                if abs(_us_chg2) < 0.5:
                                    _uet_label = "⚪ 극단타 불가"
                                    _uet_color = "#888"
                                    _uet_desc  = "변동 없음 — 거래비용 감안 시 손익 기대 불가"
                                elif _us_chg2 >= 5.0:
                                    _uet_label = "🟢 극단타 적극 대응"
                                    _uet_color = "#00c853"
                                    _uet_desc  = f"강 모멘텀 {_us_chg2:+.2f}% — 눌림목 분봉 지지 확인 후 진입"
                                elif _us_chg2 >= 3.0:
                                    _uet_label = "🟢 극단타 관심"
                                    _uet_color = "#00c853"
                                    _uet_desc  = f"상승 {_us_chg2:+.2f}% — 직전 분봉 고점 돌파 시 추격"
                                elif _us_chg2 >= 1.0:
                                    _uet_label = "🟡 극단타 관망"
                                    _uet_color = "#ffd600"
                                    _uet_desc  = f"소폭 {_us_chg2:+.2f}% — 변동성 부족, 돌파 신호 대기"
                                elif _us_chg2 <= -5.0:
                                    _uet_label = "🔵 반등 노림"
                                    _uet_color = "#2b7cff"
                                    _uet_desc  = f"급락 {_us_chg2:+.2f}% — 분봉 반등 캔들+거래량 폭발 확인 후"
                                elif _us_chg2 <= -1.0:
                                    _uet_label = "🔴 극단타 자제"
                                    _uet_color = "#ff4b4b"
                                    _uet_desc  = f"하락 {_us_chg2:+.2f}% — 추세 꺾임, 섣부른 반매수 위험"
                                else:
                                    _uet_label = "🟡 극단타 관망"
                                    _uet_color = "#ffd600"
                                    _uet_desc  = f"등락 {_us_chg2:+.2f}% — 방향 미확정, 분봉 패턴 확인 필요"

                                if abs(_us_chg2) < 0.1:
                                    _ust_label = "⚪ 관망"
                                    _ust_color = "#888"
                                    _ust_desc  = f"등락 미미({_us_chg2:+.2f}%) — 장 마감·프리마켓 상태 가능"
                                elif _us_chg2 >= 5.0:
                                    _ust_label = "🟢 강력 단기 추천"
                                    _ust_color = "#00c853"
                                    _ust_desc  = f"강한 모멘텀 {_us_chg2:+.2f}% — 눌림목 진입 권장"
                                elif _us_chg2 >= 3.0:
                                    _ust_label = "🟢 단기 추천"
                                    _ust_color = "#00c853"
                                    _ust_desc  = f"상승세 {_us_chg2:+.2f}% — 손절: 당일 저점"
                                elif _us_chg2 >= 1.0:
                                    _ust_label = "🟡 단기 관망"
                                    _ust_color = "#ffd600"
                                    _ust_desc  = f"소폭 상승 {_us_chg2:+.2f}% — 3% 돌파 확인 후 진입"
                                elif _us_chg2 <= -5.0:
                                    _ust_label = "🔵 반등 관찰"
                                    _ust_color = "#2b7cff"
                                    _ust_desc  = f"급락 {_us_chg2:+.2f}% — 지지선·거래량 확인 필수"
                                elif _us_chg2 <= -2.0:
                                    _ust_label = "🔴 단기 비추천"
                                    _ust_color = "#ff4b4b"
                                    _ust_desc  = f"하락세 {_us_chg2:+.2f}% — 추가 하락 가능"
                                else:
                                    _ust_label = "🔴 단기 비추천"
                                    _ust_color = "#ff4b4b"
                                    _ust_desc  = f"등락 {_us_chg2:+.2f}% — 수수료 감안 시 실익 없음"

                                if _us_band <= 30:
                                    _usm_label = "🟢 중기 매수 관심"
                                    _usm_color = "#00c853"
                                    _usm_desc  = f"52주 저점 근처({_us_band:.0f}%) — 중기 분할 매수 고려"
                                elif _us_band >= 80:
                                    _usm_label = "🔴 중기 고평가"
                                    _usm_color = "#ff4b4b"
                                    _usm_desc  = f"52주 고점 근처({_us_band:.0f}%) — 신규 진입 부담"
                                else:
                                    _usm_label = "🟡 중기 중립"
                                    _usm_color = "#ffd600"
                                    _usm_desc  = f"52주 중간대({_us_band:.0f}%) — 방향성 확인 후 대응"

                                try:
                                    _us_per_f = float(str(_us_per).replace(",",""))
                                except Exception:
                                    _us_per_f = 25.0
                                _us_beta_f = float(_us_beta) if _us_beta else 1.0
                                if _us_per_f <= 0:
                                    _usl_label = "🟡 장기 중립"
                                    _usl_color = "#ffd600"
                                    _usl_desc  = f"PER 음수(적자) 베타{_us_beta_f:.1f} — 수익성 확인 필요"
                                elif _us_per_f < 15:
                                    _usl_label = "🟢 장기 저평가"
                                    _usl_color = "#00c853"
                                    _usl_desc  = f"PER {_us_per_f:.1f} — 저평가, 장기 보유 유리"
                                elif _us_per_f < 30:
                                    _usl_label = "🟢 장기 적정"
                                    _usl_color = "#00c853"
                                    _usl_desc  = f"PER {_us_per_f:.1f} — 적정 밸류에이션"
                                elif _us_per_f < 60:
                                    _usl_label = "🟡 장기 중립"
                                    _usl_color = "#ffd600"
                                    _usl_desc  = f"PER {_us_per_f:.1f} — 성장 프리미엄 구간"
                                else:
                                    _usl_label = "🔴 장기 고평가"
                                    _usl_color = "#ff4b4b"
                                    _usl_desc  = f"PER {_us_per_f:.1f} — 고평가, 장기 진입 신중"

                                _urc0, _urc1, _urc2, _urc3 = st.columns(4)
                                for _urcol, _url, _urc_c, _urd, _urt in [
                                    (_urc0, _uet_label, _uet_color, _uet_desc, "극단타"),
                                    (_urc1, _ust_label, _ust_color, _ust_desc, "단기"),
                                    (_urc2, _usm_label, _usm_color, _usm_desc, "중기"),
                                    (_urc3, _usl_label, _usl_color, _usl_desc, "장기"),
                                ]:
                                    with _urcol:
                                        st.markdown(
                                            f"<div style='background:rgba(255,255,255,0.05);border-left:3px solid {_urc_c};"
                                            f"border-radius:6px;padding:8px 10px;margin:4px 0'>"
                                            f"<div style='font-size:0.65rem;color:#888;margin-bottom:2px'>{_urt}</div>"
                                            f"<div style='font-size:0.8rem;font-weight:700;color:{_urc_c}'>{_url}</div>"
                                            f"<div style='font-size:0.68rem;color:#ccc;margin-top:3px'>{_urd}</div>"
                                            f"</div>",
                                            unsafe_allow_html=True,
                                        )

                            elif st.session_state.us_right_tab == _rp_tabs[1]:
                                _inst_pct   = detail_us.get("institutional_pct", 0) or 0
                                _insider_pct = detail_us.get("insider_pct", 0) or 0
                                if _inst_pct > 0 or _insider_pct > 0:
                                    st.markdown("#### 📊 기관/내부자 보유율")
                                    _retail_p = max(0.0, 100.0 - _inst_pct - _insider_pct)
                                    fig_own = go.Figure(go.Bar(
                                        x=["기관", "내부자", "기타"],
                                        y=[_inst_pct, _insider_pct, _retail_p],
                                        marker_color=["#2b7cff", "#ff4b4b", "#888"],
                                    ))
                                    _fc, _gc = _get_chart_colors()
                                    fig_own.update_layout(
                                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                        font=dict(color=_fc),
                                        yaxis=dict(gridcolor=_gc, title="%", range=[0, 100]),
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
                                    "<hr class='toss-divider' style='margin:8px 0'>",
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
                                                    "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                })
                                                st.toast(f"AI 자동 담기: {_us_ticker_cur}")
                                    st.rerun()
                                if _us_ai_key in st.session_state:
                                    _rep = st.session_state[_us_ai_key]
                                    if "long_term_rating" in _rep:
                                        t1, t2 = st.tabs(["⚡ 단기 트레이딩 관점", "📈 중장기 투자 관점"])
                                        with t1:
                                            _re  = ("🟢" if "강력 추천" in _rep.get("rating","")
                                                    else "🟡" if "추천" in _rep.get("rating","") else "🔴")
                                            st.markdown(f"##### {_re} {_rep.get('rating','')}")
                                            
                                            _rt1, _rt2, _rt3 = st.columns(3)
                                            _rt1.metric("분석 기간", _rep.get("short_term_period", "-"))
                                            _rt2.metric("기대 수익", _rep.get("short_term_target_pct", "-"))
                                            _rt3.metric("매수가", _rep.get("buy_target","-"))
                                            
                                            _rt4, _rt5 = st.columns(2)
                                            _rt4.metric("단기 목표가", _rep.get("sell_target","-"))
                                            _rt5.metric("손절", _rep.get("stop_loss","-"))
                                            
                                            if st.button("🎒 포트폴리오에 담기", use_container_width=True,
                                                         type="primary", key="us_port_btn_short"):
                                                if "portfolio" not in st.session_state:
                                                    st.session_state.portfolio = []
                                                if not any(i["ticker"] == _us_ticker_cur for i in st.session_state.portfolio):
                                                    st.session_state.portfolio.append({
                                                        "ticker": _us_ticker_cur, "name": detail_us["name"],
                                                        "buy_price": _cur_p, "quantity": 10,
                                                        "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                    })
                                                    st.success(f"{_us_ticker_cur} 포트폴리오에 추가!")
                                                else:
                                                    st.warning("이미 포트폴리오에 있습니다.")
                                            if _rep.get("historical_pattern_analysis"):
                                                with st.expander("🕰️ 역사적 유사 패턴 분석 (프랙탈)", expanded=False):
                                                    render_ai_content(_rep["historical_pattern_analysis"])
                                            if _rep.get("analysis"):
                                                with st.container(border=True):
                                                    render_ai_content(_rep["analysis"])
                                        with t2:
                                            lt_rating = _rep.get("long_term_rating", "")
                                            lt_emoji = "🟢" if "매수" in lt_rating else "🟡" if "관망" in lt_rating else "🔴"
                                            st.markdown(f"##### {lt_emoji} {lt_rating}")
                                            
                                            _lt1, _lt2, _lt3 = st.columns(3)
                                            _lt1.metric("권장 기간", _rep.get("long_term_period", "-"))
                                            _lt2.metric("목표 수익", _rep.get("long_term_target_pct", "-"))
                                            _lt3.metric("중장기 목표가", _rep.get("long_term_target", "-"))
                                            
                                            if st.button("🎒 장기 포트폴리오에 담기", use_container_width=True,
                                                         type="primary", key="us_port_btn_long"):
                                                if "portfolio" not in st.session_state:
                                                    st.session_state.portfolio = []
                                                if not any(i["ticker"] == _us_ticker_cur for i in st.session_state.portfolio):
                                                    st.session_state.portfolio.append({
                                                        "ticker": _us_ticker_cur, "name": detail_us["name"],
                                                        "buy_price": _cur_p, "quantity": 10,
                                                        "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                    })
                                                    st.success(f"{_us_ticker_cur} 포트폴리오에 추가!")
                                                else:
                                                    st.warning("이미 포트폴리오에 있습니다.")
                                            if _rep.get("long_term_analysis"):
                                                with st.container(border=True):
                                                    st.markdown(_rep["long_term_analysis"])
                                    else:
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
                                                    "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                })
                                                st.success(f"{_us_ticker_cur} 포트폴리오에 추가!")
                                            else:
                                                st.warning("이미 포트폴리오에 있습니다.")
                                        if _rep.get("historical_pattern_analysis"):
                                            with st.expander("🕰️ 역사적 유사 패턴 분석 (프랙탈)", expanded=False):
                                                st.markdown(_rep["historical_pattern_analysis"])
                                        if _rep.get("analysis"):
                                            with st.container(border=True):
                                                st.markdown(_rep["analysis"])
                                st.markdown(
                                    "<hr class='toss-divider' style='margin:8px 0'>",
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
                                        n6.metric("베타", str(us_detail.get("beta", "N/A")))
                                    # ── 연장 거래 시간 ──
                                    _d_pre_p  = us_detail.get("pre_price", 0) or 0
                                    _d_pre_c  = us_detail.get("pre_pct", 0) or 0
                                    _d_post_p = us_detail.get("post_price", 0) or 0
                                    _d_post_c = us_detail.get("post_pct", 0) or 0
                                    if _d_pre_p > 0 or _d_post_p > 0:
                                        st.markdown(
                                            "<div style='font-size:0.72rem;color:#888;margin:8px 0 4px 0;"
                                            "font-weight:600'>⏱ 연장 거래 시간</div>",
                                            unsafe_allow_html=True,
                                        )
                                        _dc1, _dc2 = st.columns(2)
                                        if _d_pre_p > 0:
                                            _dpar = "▲" if _d_pre_c >= 0 else "▼"
                                            _dc1.markdown(
                                                f"<div style='background:rgba(245,197,24,0.08);border:1px solid"
                                                f" rgba(245,197,24,0.3);border-radius:8px;padding:8px 10px'>"
                                                f"<div style='font-size:0.65rem;color:#888'>🌅 프리마켓</div>"
                                                f"<div style='font-size:0.95rem;font-weight:700'>${_d_pre_p:,.2f}</div>"
                                                f"<div style='font-size:0.72rem;color:#f5c518'>"
                                                f"{_dpar} {_d_pre_c:+.2f}%</div></div>",
                                                unsafe_allow_html=True,
                                            )
                                        if _d_post_p > 0:
                                            _dpoar = "▲" if _d_post_c >= 0 else "▼"
                                            _dc2.markdown(
                                                f"<div style='background:rgba(123,97,255,0.08);border:1px solid"
                                                f" rgba(123,97,255,0.3);border-radius:8px;padding:8px 10px'>"
                                                f"<div style='font-size:0.65rem;color:#888'>🌙 애프터마켓</div>"
                                                f"<div style='font-size:0.95rem;font-weight:700'>${_d_post_p:,.2f}</div>"
                                                f"<div style='font-size:0.72rem;color:#7b61ff'>"
                                                f"{_dpoar} {_d_post_c:+.2f}%</div></div>",
                                                unsafe_allow_html=True,
                                            )

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
                                    if us_detail.get("institutional_pct", 0) > 0 or us_detail.get("insider_pct", 0) > 0:
                                        st.markdown("#### 📊 기관/내부자 보유율")
                                        retail_p = max(0.0, 100.0 - us_detail["institutional_pct"] - us_detail["insider_pct"])
                                        fig_own2 = go.Figure(go.Bar(
                                            x=["기관", "내부자", "기타"],
                                            y=[us_detail["institutional_pct"], us_detail["insider_pct"], retail_p],
                                            marker_color=["#2b7cff", "#ff4b4b", "#888"]
                                        ))
                                        _fc, _gc = _get_chart_colors()
                                        fig_own2.update_layout(
                                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                            font=dict(color=_fc),
                                            yaxis=dict(gridcolor=_gc, title="%", range=[0, 100]),
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
                                        if "long_term_rating" in _ur:
                                            t1, t2 = st.tabs(["⚡ 단기 관점", "📈 중장기 관점"])
                                            with t1:
                                                _urtg = _ur.get("rating","")
                                                _ure  = "🟢" if "강력" in _urtg else "🟡" if "추천" in _urtg else "🔴"
                                                st.markdown(f"##### {_ure} {_urtg}")
                                                
                                                _urk1, _urk2, _urk3 = st.columns(3)
                                                _urk1.metric("분석 기간", _ur.get("short_term_period", "-"))
                                                _urk2.metric("기대 수익", _ur.get("short_term_target_pct", "-"))
                                                _urk3.metric("매수 타점", _ur.get("buy_target","-"))
                                                
                                                _urk4, _urk5 = st.columns(2)
                                                _urk4.metric("단기 목표가", _ur.get("sell_target","-"))
                                                _urk5.metric("손절가", _ur.get("stop_loss","-"))
                                                
                                                if _ur.get("historical_pattern_analysis"):
                                                    with st.expander("🕰️ 역사적 유사 패턴 분석 (프랙탈)", expanded=False):
                                                        st.markdown(_ur["historical_pattern_analysis"])
                                                if _ur.get("analysis"):
                                                    st.markdown("---")
                                                    with st.container(border=True):
                                                        st.markdown(_ur["analysis"])
                                                _fav_us_label = "⭐ 즐겨찾기 등록"
                                                if st.button(_fav_us_label, use_container_width=True, key=f"fav_btn_us_{_us_dticker}"):
                                                    from db import save_favorite
                                                    _ok, _msg = save_favorite("미국", _us_dticker, _us_dname)
                                                    if _ok: st.success(_msg)
                                                    else: st.error(_msg)

                                                if st.button("🎒 포트폴리오에 담기", use_container_width=True, type="primary", key=f"us_sec_port_btn_short_{_us_dticker}"):
                                                    if "portfolio" not in st.session_state:
                                                        st.session_state.portfolio = []
                                                    if not any(i["ticker"] == _us_dticker for i in st.session_state.portfolio):
                                                        st.session_state.portfolio.append({
                                                            "ticker": _us_dticker, "name": _us_dname,
                                                            "buy_price": us_detail["price"], "quantity": 10,
                                                            "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                        })
                                                        st.success(f"{_us_dname} 포트폴리오에 추가!")
                                                    else:
                                                        st.warning("이미 포트폴리오에 있습니다.")
                                            with t2:
                                                lt_rating = _ur.get("long_term_rating", "")
                                                lt_emoji = "🟢" if "매수" in lt_rating else "🟡" if "관망" in lt_rating else "🔴"
                                                st.markdown(f"##### {lt_emoji} {lt_rating}")
                                                
                                                _ulk1, _ulk2, _ulk3 = st.columns(3)
                                                _ulk1.metric("권장 기간", _ur.get("long_term_period", "-"))
                                                _ulk2.metric("목표 수익", _ur.get("long_term_target_pct", "-"))
                                                _ulk3.metric("중장기 목표가", _ur.get("long_term_target", "-"))
                                                
                                                if st.button("🎒 장기 포트폴리오에 담기", use_container_width=True, type="primary", key=f"us_sec_port_btn_long_{_us_dticker}"):
                                                    if "portfolio" not in st.session_state:
                                                        st.session_state.portfolio = []
                                                    if not any(i["ticker"] == _us_dticker for i in st.session_state.portfolio):
                                                        st.session_state.portfolio.append({
                                                            "ticker": _us_dticker, "name": _us_dname,
                                                            "buy_price": us_detail["price"], "quantity": 10,
                                                            "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                        })
                                                        st.success(f"{_us_dname} 포트폴리오에 추가!")
                                                    else:
                                                        st.warning("이미 포트폴리오에 있습니다.")
                                                if _ur.get("long_term_analysis"):
                                                    with st.container(border=True):
                                                        st.markdown(_ur["long_term_analysis"])
                                        else:
                                            _urtg = _ur.get("rating","")
                                            _ure  = "🟢" if "강력" in _urtg else "🟡" if "추천" in _urtg else "🔴"
                                            st.markdown(f"##### {_ure} {_urtg}")
                                            
                                            _urk1, _urk2, _urk3 = st.columns(3)
                                            _urk1.metric("분석 기간", _ur.get("short_term_period", "-"))
                                            _urk2.metric("기대 수익", _ur.get("short_term_target_pct", "-"))
                                            _urk3.metric("매수 타점", _ur.get("buy_target","-"))
                                            
                                            _urk4, _urk5 = st.columns(2)
                                            _urk4.metric("목표가",    _ur.get("sell_target","-"))
                                            _urk5.metric("손절가", _ur.get("stop_loss","-"))
                                            
                                            if st.button("🎒 포트폴리오에 담기", use_container_width=True, type="primary", key=f"us_sec_port_btn_{_us_dticker}"):
                                                if "portfolio" not in st.session_state:
                                                    st.session_state.portfolio = []
                                                if not any(i["ticker"] == _us_dticker for i in st.session_state.portfolio):
                                                    st.session_state.portfolio.append({
                                                        "ticker": _us_dticker, "name": _us_dname,
                                                        "buy_price": us_detail["price"], "quantity": 10,
                                                        "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                                                    })
                                                    st.success(f"{_us_dname} 포트폴리오에 추가!")
                                                else:
                                                    st.warning("이미 포트폴리오에 있습니다.")
                                            if _ur.get("historical_pattern_analysis"):
                                                with st.expander("🕰️ 역사적 유사 패턴 분석 (프랙탈)", expanded=False):
                                                    st.markdown(_ur["historical_pattern_analysis"])
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
                                # --- [추가] 통합 섹터 순환매 로드맵 (원클릭) ---
                                with st.container(border=True):
                                    st.markdown("##### 🚀 AI 글로벌 섹터 로드맵 (Pathfinder)")
                                    st.caption("글로벌 자금의 흐름과 차기 주도 섹터, 추천 종목 및 진입 타점을 분석합니다.")
                                    
                                    _us_rot_key = "us_sector_rotation_res"
                                    if st.button("🗺️ US 차기 주도주 & 로드맵 생성", key="btn_us_rot_direct", use_container_width=True, type="primary"):
                                        with st.spinner("AI가 글로벌 시장 데이터를 분석하여 로드맵을 작성 중..."):
                                            # duplicate import removed
                                            _idx = get_us_market_indices()
                                            try:
                                                # duplicate import removed
                                                _chg = get_us_change_ranking() or []
                                            except: _chg = []
                                            _raw_data = {
                                                "indices": _idx,
                                                "top_movers": _chg[:15]
                                            }
                                            _rot_res = analyze_sector_rotation("미국", _raw_data)
                                            st.session_state[_us_rot_key] = _rot_res
                                    
                                    if _us_rot_key in st.session_state:
                                        render_ai_content(st.session_state[_us_rot_key])
                                        if st.button("🗑️ 분석 결과 지우기", key="clear_us_rot"):
                                            st.session_state.pop(_us_rot_key, None)
                                            st.rerun()

                                st.markdown("---")
                                from ai_engine import analyze_us_today_market, analyze_us_hot_sectors
                                _us_am_hdr, _us_am_ref = st.columns([8, 1])
                                _us_am_hdr.markdown(
                                    "<p style='font-size:0.75rem;color:#888;margin:4px 0'>"
                                    "급등 종목 분석 · AI 핫 섹터 통합</p>",
                                    unsafe_allow_html=True,
                                )
                                if st.session_state.us_ai_market_run:
                                    if _us_am_ref.button("🔄", key="us_ai_mkt_refresh", help="전체 재분석"):
                                        try: analyze_us_today_market.clear()
                                        except: pass
                                        try: analyze_us_hot_sectors.clear()
                                        except: pass
                                        st.rerun()

                                if not st.session_state.us_ai_market_run:
                                    st.markdown(
                                        "<div style='text-align:center;padding:40px 20px'>"
                                        "<p style='color:#888;font-size:0.85rem;margin-bottom:16px'>"
                                        "US 급등 종목 이유 분석, AI 핫 섹터를 한번에 확인합니다</p>"
                                        "</div>",
                                        unsafe_allow_html=True,
                                    )
                                    if st.button("🤖 AI 시장분석 실행", use_container_width=True,
                                                 type="primary", key="us_run_ai_market"):
                                        st.session_state.us_ai_market_run = True
                                        st.rerun()
                                else:
                                    with st.spinner("US 시장 분석 중..."):
                                        _us_mkt_res = analyze_us_today_market()
                                        _us_ai_res  = analyze_us_hot_sectors()

                                    _us_quota_err = (
                                        isinstance(_us_mkt_res, dict) and _us_mkt_res.get("error") == "QUOTA"
                                    )
                                    if _us_quota_err:
                                        st.warning(_us_mkt_res.get("message", "API 할당량 초과"))
                                    else:
                                        # 시장 요약 배너
                                        if isinstance(_us_mkt_res, dict) and _us_mkt_res.get("market_summary"):
                                            st.markdown(
                                                f"<div style='background:rgba(0,200,83,0.06);border-left:3px solid #00c853;"
                                                f"padding:6px 12px;border-radius:4px;margin:4px 0'>"
                                                f"<span style='font-size:0.75rem;color:#aaa'>{_us_mkt_res['market_summary']}</span>"
                                                f"</div>",
                                                unsafe_allow_html=True,
                                            )
                                        # 주도 테마 태그
                                        _us_themes_lead = (_us_mkt_res or {}).get("leading_themes", [])
                                        if _us_themes_lead:
                                            _us_tag_html = " ".join(
                                                f"<span style='background:rgba(0,200,83,0.12);border:1px solid rgba(0,200,83,0.3);"
                                                f"border-radius:12px;padding:2px 8px;font-size:0.68rem;color:#00c853;margin:2px'>"
                                                f"{_t}</span>"
                                                for _t in _us_themes_lead
                                            )
                                            st.markdown(
                                                f"<div style='margin:4px 0'>{_us_tag_html}</div>",
                                                unsafe_allow_html=True,
                                            )

                                        st.markdown("---")
                                        st.markdown("#### 💎 AI 선정 US 핫 섹터")
                                        _us_stk_list = (_us_mkt_res or {}).get("stocks", [])
                                        if _us_stk_list:
                                            for _us_stk in _us_stk_list[:8]:
                                                _us_sc = _us_stk.get("change_pct", 0)
                                                _us_sc_col = "#00c853" if _us_sc >= 0 else "#ff4b4b"
                                                with st.container(border=True):
                                                    _usc_star, _usc1, _usc2 = st.columns([0.6, 5, 1])
                                                    with _usc_star:
                                                        render_star_toggle("미국", _us_stk.get('ticker',''), _us_stk.get('name',''), key_suffix=f"us_rise_{_us_stk.get('ticker','')}")
                                                    with _usc1:
                                                        st.markdown(
                                                            f"<span style='font-size:0.82rem;font-weight:700'>"
                                                            f"{_us_stk.get('ticker','')} · {_us_stk.get('name','')}</span>"
                                                            f"<span style='font-size:0.75rem;color:{_us_sc_col};margin-left:8px'>"
                                                            f"{_us_sc:+.1f}%</span>",
                                                            unsafe_allow_html=True,
                                                        )
                                                        if _us_stk.get("theme"):
                                                            st.markdown(
                                                                f"<span style='font-size:0.65rem;color:#888'>"
                                                                f"🏷 {_us_stk['theme']}</span>",
                                                                unsafe_allow_html=True,
                                                            )
                                                        if _us_stk.get("reason"):
                                                            st.markdown(
                                                                f"<p style='font-size:0.68rem;color:#bbb;margin:2px 0'>"
                                                                f"{_us_stk['reason']}</p>",
                                                                unsafe_allow_html=True,
                                                            )
                                                    _us_cd = _us_stk.get("ticker", "")
                                                    if _usc2.button("▶", key=f"us_mkt_stk_{_us_cd}",
                                                                    use_container_width=True):
                                                        st.session_state.us_selected_ticker      = _us_cd
                                                        st.session_state.us_selected_name        = _us_stk.get("name", _us_cd)
                                                        st.session_state.us_sector_detail_ticker = _us_cd
                                                        st.session_state.us_sector_detail_name   = _us_stk.get("name", _us_cd)
                                                        st.session_state.us_sector_view          = "detail"
                                                        st.rerun()
                                        elif not _us_quota_err:
                                            st.caption("급등 종목 데이터를 불러올 수 없습니다.")

                                        st.markdown(
                                            "<hr class='toss-divider' style='margin:8px 0'>",
                                            unsafe_allow_html=True,
                                        )

                                        # AI 핫 섹터
                                        st.markdown(
                                            "<p style='font-size:0.78rem;font-weight:700;color:#aaa;margin:4px 0'>"
                                            "🔥 AI 핫 섹터</p>",
                                            unsafe_allow_html=True,
                                        )
                                        _us_ai_sectors = []
                                        if isinstance(_us_ai_res, dict) and not _us_ai_res.get("error") and _us_ai_res.get("sectors"):
                                            _us_ai_sectors = sorted(
                                                _us_ai_res.get("sectors", []),
                                                key=lambda x: -x.get("hot_score", 0),
                                            )
                                        if _us_ai_sectors:
                                            with st.container(height=380):
                                                for _uas in _us_ai_sectors:
                                                    _ukw    = _uas.get("keyword", "")
                                                    _usc    = _uas.get("hot_score", 0)
                                                    _ursn   = _uas.get("reason", "")
                                                    _unews  = _uas.get("news_title", "")
                                                    _uhot_t = _uas.get("hot_tickers", [])
                                                    _ufire  = "🔥" * max(1, min(int(_usc / 2.5), 4))
                                                    _usc_col = "#ff4b4b" if _usc >= 7 else "#f5c518" if _usc >= 4 else "#888"
                                                    with st.container(border=True):
                                                        _uah1, _uah2 = st.columns([8, 2])
                                                        _uah1.markdown(
                                                            f"<span style='font-size:0.88rem;font-weight:700'>"
                                                            f"{_ufire} {_ukw}</span>"
                                                            f"<span style='font-size:0.72rem;color:{_usc_col};"
                                                            f"margin-left:8px'>HOT {_usc}/10</span>",
                                                            unsafe_allow_html=True,
                                                        )
                                                        if _ursn:
                                                            st.markdown(
                                                                f"<p style='font-size:0.72rem;color:#bbb;margin:3px 0'>"
                                                                f"{_ursn}</p>",
                                                                unsafe_allow_html=True,
                                                            )
                                                        if _unews:
                                                            st.markdown(
                                                                f"<p style='font-size:0.68rem;color:#666;margin:2px 0'>"
                                                                f"📰 {_unews}</p>",
                                                                unsafe_allow_html=True,
                                                            )
                                                        if _uhot_t:
                                                            st.markdown(
                                                                " ".join(
                                                                    f"<span style='font-size:0.65rem;border:1px solid rgba(0,200,83,0.3);"
                                                                    f"border-radius:4px;padding:1px 5px;color:#00c853'>{_t}</span>"
                                                                    for _t in _uhot_t[:6]
                                                                ),
                                                                unsafe_allow_html=True,
                                                            )
                                                        # 동적 서브섹터
                                                        for _uds in _uas.get("dynamic_subsectors", [])[:2]:
                                                            st.markdown(
                                                                f"<span style='font-size:0.68rem;color:#ff9800'>"
                                                                f"📡 {_uds.get('name','')} — {_uds.get('reason','')[:50]}</span>",
                                                                unsafe_allow_html=True,
                                                            )
                                                        # hot_tickers 중 섹터 DB에 있는 종목 클릭
                                                        if _uhot_t and _uah2.button(
                                                            "▶ 탐색", key=f"us_hot_sec_{_ukw}",
                                                            use_container_width=True,
                                                        ):
                                                            if _ukw in us_sector_names:
                                                                st.session_state.us_selected_sector_us = _ukw
                                                                st.session_state.us_sector_panel_tab = "📚 전체 섹터 탐색"
                                                                st.rerun()
                                        elif not _us_quota_err:
                                            st.caption("섹터 데이터를 불러올 수 없습니다.")

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

                                # ── hot_score 맵 구성 (AI 시장분석 결과 재활용) ──
                                _us_hot_score_map: dict = {}
                                try:
                                    from ai_engine import analyze_us_hot_sectors as _auh
                                    _uh_res = _auh()
                                    if isinstance(_uh_res, dict) and _uh_res.get("sectors"):
                                        for _uhs in _uh_res["sectors"]:
                                            _uhkw = _uhs.get("keyword", "")
                                            if _uhkw in us_sector_names:
                                                _us_hot_score_map[_uhkw] = {
                                                    "score": _uhs.get("hot_score", 0),
                                                    "reason": _uhs.get("reason", ""),
                                                }
                                except Exception:
                                    pass

                                def _us_sector_tier(name):
                                    sc = _us_hot_score_map.get(name, {}).get("score", 0)
                                    return 0 if sc >= 7 else 1 if sc >= 4 else 2

                                _us_sorted_sectors = sorted(
                                    us_sector_names,
                                    key=lambda n: (_us_sector_tier(n), -_us_hot_score_map.get(n, {}).get("score", 0))
                                )

                                st.markdown(
                                    "<p style='font-size:0.72rem;color:#888;margin:2px 0 6px 0'>"
                                    "섹터를 클릭해 종목을 탐색하세요 · 🔥 = 오늘의 이슈 섹터</p>",
                                    unsafe_allow_html=True,
                                )
                                with st.container(height=180):
                                    _us_prev_tier = -1
                                    for _usn in _us_sorted_sectors:
                                        _us_tier = _us_sector_tier(_usn)
                                        _us_hs_info = _us_hot_score_map.get(_usn, {})
                                        _us_sc = _us_hs_info.get("score", 0)
                                        _us_rsn = _us_hs_info.get("reason", "")[:40]
                                        if _us_tier != _us_prev_tier:
                                            if _us_tier == 0:
                                                st.markdown("<p style='font-size:0.68rem;font-weight:700;color:#00c853;margin:4px 0 2px 0'>🔥 HOT 섹터</p>", unsafe_allow_html=True)
                                            elif _us_tier == 1:
                                                st.markdown("<p style='font-size:0.68rem;font-weight:700;color:#f5c518;margin:6px 0 2px 0'>⭐ 관심 섹터</p>", unsafe_allow_html=True)
                                            else:
                                                st.markdown("<p style='font-size:0.68rem;color:#555;margin:6px 0 2px 0'>일반 섹터</p>", unsafe_allow_html=True)
                                            _us_prev_tier = _us_tier
                                        _us_is_sel = st.session_state.us_selected_sector_us == _usn
                                        if _us_tier == 0:
                                            _us_bh = f"🔥 {_usn} <span style='font-size:0.65rem;color:#ff9800'>[{_us_sc}점]</span>"
                                            if _us_rsn:
                                                _us_bh += f"<br><span style='font-size:0.63rem;color:#aaa'>{_us_rsn}{'…' if len(_us_hs_info.get('reason',''))>40 else ''}</span>"
                                            _us_bg = "rgba(0,200,83,0.12)" if _us_is_sel else "rgba(0,200,83,0.06)"
                                            _us_bd = "#00c853" if _us_is_sel else "rgba(0,200,83,0.35)"
                                        elif _us_tier == 1:
                                            _us_bh = f"⭐ {_usn} <span style='font-size:0.65rem;color:#888'>[{_us_sc}점]</span>"
                                            _us_bg = "rgba(245,197,24,0.10)" if _us_is_sel else "rgba(245,197,24,0.04)"
                                            _us_bd = "#f5c518" if _us_is_sel else "rgba(245,197,24,0.25)"
                                        else:
                                            _us_bh = _usn
                                            _us_bg = "rgba(255,255,255,0.06)" if _us_is_sel else "transparent"
                                            _us_bd = "rgba(255,255,255,0.2)" if _us_is_sel else "rgba(255,255,255,0.06)"
                                        _ubc1, _ubc2 = st.columns([5, 1])
                                        _ubc1.markdown(
                                            f"<div style='border:1px solid {_us_bd};background:{_us_bg};"
                                            f"border-radius:7px;padding:5px 10px;margin:2px 0'>{_us_bh}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        if _ubc2.button("▶", key=f"us_sec_btn_{_usn}", use_container_width=True):
                                            st.session_state.us_selected_sector_us = _usn
                                            st.session_state["us_sector_selectbox"] = _usn
                                            st.rerun()

                                _us_cur_si = (_us_sorted_sectors.index(st.session_state.us_selected_sector_us)
                                              if st.session_state.us_selected_sector_us in _us_sorted_sectors else 0)
                                _us_sel_sec = st.selectbox(
                                    "섹터 선택 (직접 선택)", _us_sorted_sectors, index=_us_cur_si,
                                    key="us_sector_selectbox", label_visibility="visible",
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
                                                    '<hr class="toss-divider" style="margin:4px 0 6px 0">',
                                                    unsafe_allow_html=True,
                                                )
                                                for _ui, _us in enumerate(us_stocks):
                                                    if _ui > 0:
                                                        st.markdown(
                                                            '<hr class="toss-divider" style="margin:2px 0">',
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
                                                    _uc_star, _uc0, _uc1, _uc2, _uc3, _uc4 = st.columns([0.45, 0.35, 2.8, 1.8, 1.4, 0.45])
                                                    with _uc_star:
                                                        render_star_toggle("미국", _us["ticker"], _us["name"], key_suffix=f"us_sec_stk_{_us['ticker']}_{_ui}")
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
                                "buy_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
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
                                    "sell_date": (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
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
                    _fc, _gc = _get_chart_colors()
                    fig.update_layout(
                        title="📈 누적 수익금 추이",
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color=_fc),
                        xaxis=dict(gridcolor=_gc),
                        yaxis=dict(gridcolor=_gc, tickprefix="$"),
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
