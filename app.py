import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from data import get_us_stock_data, get_us_market_indices, get_us_stock_detail

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
        /* 기본적으로 Streamlit 테마 설정(Settings)에서 Dark를 선택해야 완벽히 적용됩니다. */
        /* 여기서는 추가적인 커스텀 스타일만 정의합니다. */
        .up-kr { color: #ff4b4b; font-weight: bold; }
        .down-kr { color: #2b7cff; font-weight: bold; }
        .up-us { color: #00c853; font-weight: bold; }
        .down-us { color: #ff4b4b; font-weight: bold; }
        .disclaimer { 
            font-size: 0.8rem; 
            color: #888; 
            text-align: center; 
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #444;
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
    init_session_state()
    inject_custom_css()
    
    # --- 상단 영역 ---
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        st.markdown("## 📈 Stockcy")
        
    with col2:
        # 시장 선택 토글 (가운데 정렬 효과를 위해 여백 컬럼 활용 가능하나 간단히 구현)
        selected_market = st.radio(
            "시장 선택",
            ["국내 주식 🇰🇷", "미국 주식 🇺🇸"],
            horizontal=True,
            label_visibility="collapsed"
        )
        if selected_market != st.session_state.market:
            st.session_state.market = selected_market
            st.rerun()
            
    with col3:
        # 우측 상단 브리핑 버튼
        if st.button("📰 데일리 브리핑 보기", use_container_width=True):
            show_daily_briefing()

    st.markdown("---")
    
    # --- 🚀 [무료 라이브 위젯] TradingView 실시간 티커 테이프 ---
    import streamlit.components.v1 as components
    ticker_html = """
    <!-- TradingView Widget BEGIN -->
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
      {
      "symbols": [
        {"description": "엔비디아", "proName": "NASDAQ:NVDA"},
        {"description": "애플", "proName": "NASDAQ:AAPL"},
        {"description": "테슬라", "proName": "NASDAQ:TSLA"},
        {"description": "마이크로소프트", "proName": "NASDAQ:MSFT"},
        {"description": "나스닥 100", "proName": "FOREXCOM:NSXUSD"},
        {"description": "비트코인", "proName": "CRYPTO:BTCUSD"}
      ],
      "showSymbolLogo": true,
      "isTransparent": true,
      "displayMode": "adaptive",
      "colorTheme": "dark",
      "locale": "kr"
    }
      </script>
    </div>
    <!-- TradingView Widget END -->
    """
    # HTML 컴포넌트를 화면에 렌더링 (높이 75px 지정, 잘림 방지)
    components.html(ticker_html, height=75)
    
    # --- 메인 탭 구성 ---
    tab1, tab2 = st.tabs(["📊 실시간 타점 보드", "📈 성과 트래킹"])
    
    with tab1:
        if "국내" in st.session_state.market:
            from data_kr import (get_kr_market_index, get_kr_stock_price,
                                 get_kr_investor_trend, get_kr_volume_ranking)

            # KIS API 키 설정 확인
            try:
                _ = st.secrets["kis"]["app_key"]
            except Exception:
                st.error("KIS API 키가 설정되지 않았습니다. Streamlit Cloud → Settings → Secrets에 아래 내용을 추가해주세요.")
                st.code("[kis]\napp_key = \"발급받은_앱키\"\napp_secret = \"발급받은_앱시크릿\"", language="toml")
                st.stop()

            # KOSPI / KOSDAQ 지수
            st.markdown("### 📊 국내 시장 지수")
            with st.spinner("지수 조회 중..."):
                indices = get_kr_market_index()

            if indices:
                col_k, col_q = st.columns(2)
                for col, idx_name in [(col_k, "KOSPI"), (col_q, "KOSDAQ")]:
                    if idx_name in indices:
                        idx = indices[idx_name]
                        col.metric(
                            f"{'📈' if idx['change'] >= 0 else '📉'} {idx_name}",
                            f"{idx['index']:,.2f}",
                            f"{idx['change']:+.2f}p ({idx['change_pct']:+.2f}%)",
                            delta_color="normal" if idx["change"] >= 0 else "inverse"
                        )

            st.markdown("---")

            # 종목 선택
            st.markdown("### 🔍 종목 선택")
            POPULAR_KR = {
                "삼성전자 (005930)": "005930",
                "SK하이닉스 (000660)": "000660",
                "현대차 (005380)": "005380",
                "NAVER (035420)": "035420",
                "카카오 (035720)": "035720",
                "LG에너지솔루션 (373220)": "373220",
                "삼성바이오로직스 (207940)": "207940",
                "POSCO홀딩스 (005490)": "005490",
                "삼성전자우 (005935)": "005935",
                "기아 (000270)": "000270",
            }
            col_sel, col_manual = st.columns([3, 1])
            with col_sel:
                selected_label = st.selectbox("인기 종목 빠른 선택", list(POPULAR_KR.keys()))
                selected_code_kr = POPULAR_KR[selected_label]
            with col_manual:
                manual_code_kr = st.text_input("직접 입력 (6자리 코드)", "").strip()
            if manual_code_kr and len(manual_code_kr) == 6 and manual_code_kr.isdigit():
                selected_code_kr = manual_code_kr

            # 실시간 시세 카드
            with st.spinner(f"{selected_code_kr} 실시간 시세 조회 중..."):
                price_kr = get_kr_stock_price(selected_code_kr)

            if price_kr:
                is_up = price_kr["sign"] in ("1", "2")
                is_dn = price_kr["sign"] in ("4", "5")
                arrow = "▲" if is_up else "▼" if is_dn else "-"
                d_color = "normal" if is_up else "inverse" if is_dn else "off"

                with st.container(border=True):
                    st.markdown(f"#### {price_kr['name']} ({selected_code_kr})")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("현재가",
                              f"₩{price_kr['price']:,}",
                              f"{arrow} {abs(price_kr['change']):,}원 ({price_kr['change_pct']:+.2f}%)",
                              delta_color=d_color)
                    c2.metric("거래량", f"{price_kr['volume']:,}주")
                    c3.metric("거래대금", f"₩{price_kr['amount'] // 100000000:,}억")

                    oc1, oc2, oc3, oc4, oc5, oc6 = st.columns(6)
                    oc1.metric("시가", f"₩{price_kr['open']:,}")
                    oc2.metric("고가", f"₩{price_kr['high']:,}")
                    oc3.metric("저가", f"₩{price_kr['low']:,}")
                    oc4.metric("52주 최고", f"₩{price_kr['w52_high']:,}")
                    oc5.metric("PER", price_kr['per'])
                    oc6.metric("PBR", price_kr['pbr'])

                # TradingView 차트 (국내주식)
                tv_kr_html = f"""
                <div class="tradingview-widget-container" style="height:420px;width:100%">
                  <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
                  <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
                  {{
                  "autosize": true,
                  "symbol": "KRX:{selected_code_kr}",
                  "interval": "15",
                  "timezone": "Asia/Seoul",
                  "theme": "dark",
                  "style": "1",
                  "locale": "kr",
                  "allow_symbol_change": false,
                  "backgroundColor": "rgba(0, 0, 0, 1)"
                  }}
                  </script>
                </div>
                """
                components.html(tv_kr_html, height=420)

                st.markdown("---")

                # 외국인/기관 수급 + AI 분석
                col_inv_kr, col_ai_kr = st.columns([3, 2])

                with col_inv_kr:
                    st.markdown("### 💰 외국인/기관 수급 분석")
                    with st.spinner("수급 데이터 조회 중..."):
                        investor_kr = get_kr_investor_trend(selected_code_kr)

                    if investor_kr:
                        df_inv = pd.DataFrame(investor_kr)
                        fig_inv = go.Figure()
                        for col_name, color in [("외국인", "#ff4b4b"), ("기관", "#2b7cff"), ("개인", "#888")]:
                            fig_inv.add_trace(go.Bar(
                                name=col_name, x=df_inv["날짜"], y=df_inv[col_name],
                                marker_color=color
                            ))
                        fig_inv.update_layout(
                            barmode="group",
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(color="white"), legend=dict(orientation="h"),
                            xaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
                            yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="순매수(주)"),
                            margin=dict(l=10, r=10, t=10, b=10), height=280
                        )
                        st.plotly_chart(fig_inv, use_container_width=True)

                        latest_kr = investor_kr[0]
                        st.markdown(
                            f"**오늘({latest_kr['날짜']}) 수급:** "
                            f"외국인 {'🔴' if latest_kr['외국인'] > 0 else '🔵'} {latest_kr['외국인']:+,}주 | "
                            f"기관 {'🔴' if latest_kr['기관'] > 0 else '🔵'} {latest_kr['기관']:+,}주"
                        )
                    else:
                        st.info("수급 데이터를 불러올 수 없습니다.")

                with col_ai_kr:
                    st.markdown("### 🧠 AI 단타 분석")
                    if st.button("🎯 AI 수급 & 타점 분석", key="kr_ai_btn",
                                 use_container_width=True, type="primary"):
                        with st.spinner("AI가 수급과 뉴스를 융합 분석 중..."):
                            from ai_engine import generate_kr_stock_report
                            inv_for_ai = get_kr_investor_trend(selected_code_kr)
                            kr_rep = generate_kr_stock_report(
                                selected_code_kr, price_kr["name"], price_kr, inv_for_ai
                            )
                            st.session_state[f"kr_report_{selected_code_kr}"] = kr_rep

                    if f"kr_report_{selected_code_kr}" in st.session_state:
                        rep_kr = st.session_state[f"kr_report_{selected_code_kr}"]
                        rating_kr = rep_kr.get("rating", "")
                        r_emoji = "🟢" if "강력" in rating_kr else "🟡" if "추천" in rating_kr else "🔴"
                        st.markdown(f"#### {r_emoji} {rating_kr}")

                        rk1, rk2 = st.columns(2)
                        rk1.metric("매수 타점", rep_kr.get("buy_target", "-"))
                        rk2.metric("목표가", rep_kr.get("sell_target", "-"))
                        st.metric("손절가", rep_kr.get("stop_loss", "-"))
                        if rep_kr.get("세력분석"):
                            st.info(f"**세력 분석:** {rep_kr['세력분석']}")

                if f"kr_report_{selected_code_kr}" in st.session_state:
                    st.markdown("---")
                    st.markdown("### 📝 AI 종합 분석 리포트")
                    with st.container(border=True):
                        st.markdown(
                            st.session_state[f"kr_report_{selected_code_kr}"].get("analysis", "")
                        )
            else:
                st.error(f"종목코드 {selected_code_kr}의 시세를 불러올 수 없습니다. KIS API 키를 확인해주세요.")

            st.markdown("---")

            # 거래량 상위 TOP 10
            st.markdown("### 🔥 거래량 상위 TOP 10")
            col_ref_kr, _ = st.columns([1, 5])
            with col_ref_kr:
                if st.button("🔄 새로고침", key="refresh_vol_kr"):
                    get_kr_volume_ranking.clear()
                    st.rerun()

            with st.spinner("거래량 순위 조회 중..."):
                vol_rank = get_kr_volume_ranking()

            if vol_rank:
                df_vol = pd.DataFrame(vol_rank)

                def color_kr(val):
                    if isinstance(val, (int, float)):
                        if val > 0: return "color: #ff4b4b; font-weight: bold"
                        if val < 0: return "color: #2b7cff; font-weight: bold"
                    return ""

                st.dataframe(
                    df_vol.style.map(color_kr, subset=["등락률(%)"]),
                    use_container_width=True, hide_index=True
                )
            else:
                st.info("거래량 순위 데이터를 불러올 수 없습니다.")
        else:
            # --- 미국 시장 지수 ---
            st.markdown("### 📊 미국 시장 지수")
            with st.spinner("지수 조회 중..."):
                us_indices = get_us_market_indices()
            if us_indices:
                idx_cols = st.columns(4)
                for i, (idx_name, idx_data) in enumerate(us_indices.items()):
                    arrow = "📈" if idx_data["change"] >= 0 else "📉"
                    delta_color = "normal" if idx_data["change"] >= 0 else "inverse"
                    if idx_name == "VIX":
                        idx_cols[i].metric("😱 VIX 공포지수", f"{idx_data['price']:.2f}",
                                           f"{idx_data['change']:+.2f} ({idx_data['change_pct']:+.2f}%)",
                                           delta_color="inverse" if idx_data["change"] >= 0 else "normal")
                    else:
                        idx_cols[i].metric(f"{arrow} {idx_name}", f"{idx_data['price']:,.2f}",
                                           f"{idx_data['change']:+.2f} ({idx_data['change_pct']:+.2f}%)",
                                           delta_color=delta_color)
            st.markdown("---")

            # --- 토스형 마인드맵 다이얼로그 ---
            @st.dialog("🌌 토스형 실시간 급등락 마인드맵", width="large")
            def show_mindmap():
                st.markdown("현재 미국 주식 시장의 주요 이슈와 그로 인해 움직이는 종목들의 인과관계를 보여줍니다.")
                with st.spinner("AI가 시장 전체 자금 흐름을 분석하여 맵을 그리는 중..."):
                    from ai_engine import generate_mindmap_data
                    mermaid_code = generate_mindmap_data()
                    html = f"""
                    <script type="module">
                      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                      mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});
                    </script>
                    <div class="mermaid" style="display:flex; justify-content:center; background-color:#111; padding:20px; border-radius:10px;">
                    {mermaid_code}
                    </div>
                    """
                    components.html(html, height=500, scrolling=True)

            if st.button("🚀 실시간 시장 자금 흐름 마인드맵 보기", use_container_width=True):
                show_mindmap()
                
            st.markdown("---")
            
            # --- AI 단타 종목 발굴 ---
            st.markdown("### 🎯 AI 실시간 단타 종목 발굴기")
            st.caption("실시간 구글 검색을 통해 오늘 당장 진입하기 가장 좋은 모멘텀 주식을 딱 하나 발굴합니다.")
            if st.button("✨ 오늘의 단타 핫종목 발굴하기", type="primary", use_container_width=True):
                with st.spinner("구글 검색망을 통해 세력 수급과 호재가 터진 종목을 탐색 중입니다..."):
                    from ai_engine import discover_hot_day_trading_stock
                    context_data = st.session_state.get("daily_briefing_data", "")
                    hot_stock = discover_hot_day_trading_stock(str(context_data))
                    
                    if hot_stock.get("ticker") != "N/A":
                        st.session_state.discovered_ticker = hot_stock.get("ticker")
                        st.session_state.discovered_name = hot_stock.get("name_kr")
                        st.session_state.discovered_buy = hot_stock.get("buy_target", "-")
                        st.session_state.discovered_sell = hot_stock.get("sell_target", "-")
                        st.session_state.discovered_stop = hot_stock.get("stop_loss", "-")
                        st.session_state.discovered_reasoning = hot_stock.get("reasoning")
                        st.success(f"🔥 발굴 완료: {st.session_state.discovered_name} ({st.session_state.discovered_ticker})")
                    else:
                        st.error(hot_stock.get("reasoning"))
                        
            if "discovered_ticker" in st.session_state:
                with st.container(border=True):
                    st.markdown(f"#### 🔥 AI 강력 추천 단타 종목: **{st.session_state.discovered_name} ({st.session_state.discovered_ticker})**")
                    col_h1, col_h2, col_h3 = st.columns(3)
                    col_h1.metric("권장 매수가", st.session_state.discovered_buy)
                    col_h2.metric("목표 매도가", st.session_state.discovered_sell)
                    col_h3.metric("손절 라인", st.session_state.discovered_stop)
                    st.markdown("---")
                    st.markdown(st.session_state.discovered_reasoning)
                
            st.markdown("---")
            
            # --- 관심 섹터 및 종목 선택 (하이브리드 지원) ---
            st.markdown("### 🔍 AI 동적 테마 & 종목 탐색 (전 종목 스캔)")
            st.caption("AI가 지금 당장 미국 시장 전체를 스캔하여 핫한 테마를 분류하고 대장주를 뽑아냅니다.")
            
            col_retry, _ = st.columns([1, 4])
            with col_retry:
                if st.button("🔄 테마 새로고침", help="캐시를 초기화하고 AI에게 다시 요청합니다"):
                    from ai_engine import generate_dynamic_themes
                    generate_dynamic_themes.clear()
                    st.rerun()

            with st.spinner("AI가 구글 검색을 통해 현재 가장 핫한 5대 테마를 발굴 중입니다..."):
                from ai_engine import generate_dynamic_themes
                theme_data = generate_dynamic_themes()
                
            themes = theme_data.get("themes", [])
            if not themes:
                actual_error = theme_data.get("error", "알 수 없는 오류")
                st.error(f"⚠️ 테마 데이터를 불러오지 못했습니다.\n\n**원인:** `{actual_error}`")
                st.info("💡 위의 [🔄 테마 새로고침] 버튼을 눌러 다시 시도하거나, 잠시 후 새로고침 해주세요.")
                selected_ticker = "NVDA"
                selected_stock_name = "엔비디아"
            else:
                theme_names = [t["theme_name"] for t in themes]
                
                col_t_left, col_t_right = st.columns([1, 2])
                with col_t_left:
                    selected_theme_name = st.radio("📂 발굴된 핫 테마 (클릭)", theme_names)
                    st.markdown("---")
                    if "us_input_ticker" not in st.session_state:
                        st.session_state.us_input_ticker = ""
                    input_ticker = st.text_input("⌨️ 수동 직접 검색 (예: TSLA)", key="us_input_ticker").upper().strip()
                    
                selected_theme = next((t for t in themes if t["theme_name"] == selected_theme_name), themes[0])
                leader = selected_theme.get("leader_stock", {})
                related = selected_theme.get("related_stocks", [])
                
                with col_t_right:
                    with st.container(border=True):
                        st.markdown(f"#### 👑 대장주: {leader.get('name_kr')} ({leader.get('ticker')})")
                        
                        # TradingView Mini Widget으로 방화벽을 우회하여 대장주 실시간 시세 표시
                        tv_leader = f"""
                        <div class="tradingview-widget-container">
                          <div class="tradingview-widget-container__widget"></div>
                          <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-single-quote.js" async>
                          {{
                          "symbol": "{leader.get('ticker')}",
                          "width": "100%",
                          "colorTheme": "dark",
                          "isTransparent": true,
                          "locale": "kr"
                        }}
                          </script>
                        </div>
                        """
                        components.html(tv_leader, height=130)
                        
                        st.info(f"**🔗 테마 연관성:**\n{selected_theme.get('correlation', '')}")
                        
                        st.markdown("**🔽 관련주 (동조화 종목)**")
                        rel_text = " | ".join([f"{r.get('name_kr')} ({r.get('ticker')})" for r in related])
                        st.markdown(f"`{rel_text}`")
                
                st.markdown("---")
                
                all_options = {f"👑 대장주: {leader.get('name_kr')} ({leader.get('ticker')})": leader.get("ticker")}
                for r in related:
                    all_options[f"관련주: {r.get('name_kr')} ({r.get('ticker')})"] = r.get("ticker")
                    
                if input_ticker:
                    selected_ticker = input_ticker
                    selected_stock_name = input_ticker
                else:
                    selected_stock_name = st.selectbox("🎯 위 테마에서 단타 분석을 진행할 종목을 선택하세요", list(all_options.keys()))
                    selected_ticker = all_options[selected_stock_name]
            
            # TradingView용 거래소 심볼 매핑 (없으면 티커 그대로)
            tv_symbols = {
                "NVDA": "NASDAQ:NVDA", "AMD": "NASDAQ:AMD", "TSM": "NYSE:TSM", "AVGO": "NASDAQ:AVGO", "MU": "NASDAQ:MU", "PLTR": "NYSE:PLTR",
                "AAPL": "NASDAQ:AAPL", "MSFT": "NASDAQ:MSFT", "GOOGL": "NASDAQ:GOOGL", "META": "NASDAQ:META", "AMZN": "NASDAQ:AMZN",
                "TSLA": "NASDAQ:TSLA"
            }
            tv_symbol = tv_symbols.get(selected_ticker, selected_ticker)
            
            # --- 3분할 대시보드 (상단 좌/우, 하단 전체) ---
            col_left, col_right = st.columns([5, 3])
            
            with col_left:
                st.markdown(f"### 📈 {selected_stock_name} 실시간 차트")
                # TradingView Advanced Chart (실시간 캔들 차트)
                tv_chart_html = f"""
                <div class="tradingview-widget-container" style="height:450px;width:100%">
                  <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
                  <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
                  {{
                  "autosize": true,
                  "symbol": "{tv_symbol}",
                  "interval": "15",
                  "timezone": "Asia/Seoul",
                  "theme": "dark",
                  "style": "1",
                  "locale": "kr",
                  "allow_symbol_change": false,
                  "hide_top_toolbar": false,
                  "hide_legend": false,
                  "save_image": false,
                  "backgroundColor": "rgba(0, 0, 0, 1)"
                }}
                  </script>
                </div>
                """
                components.html(tv_chart_html, height=450)
                
            with col_right:
                st.markdown("### ⚡ 실시간 시세 & 수급")
                with st.spinner("데이터 조회 중..."):
                    detail_us = get_us_stock_detail(selected_ticker)

                if detail_us:
                    cur_price = detail_us["price"]
                    change_pct = detail_us["change_pct"]
                    delta_color = "normal" if change_pct >= 0 else "inverse"

                    with st.container(border=True):
                        st.metric(
                            f"{detail_us['name']} ({selected_ticker})",
                            f"${cur_price:,.2f}",
                            f"{detail_us['change']:+.2f} ({change_pct:+.2f}%)",
                            delta_color=delta_color
                        )
                        dc1, dc2 = st.columns(2)
                        dc1.metric("시가", f"${detail_us['open']:,.2f}")
                        dc2.metric("거래량", f"{detail_us['volume']:,}")
                        dc3, dc4 = st.columns(2)
                        dc3.metric("고가", f"${detail_us['high']:,.2f}")
                        dc4.metric("저가", f"${detail_us['low']:,.2f}")
                        dc5, dc6 = st.columns(2)
                        dc5.metric("52주 최고", f"${detail_us['w52_high']:,.2f}")
                        dc6.metric("52주 최저", f"${detail_us['w52_low']:,.2f}")
                        dc7, dc8 = st.columns(2)
                        dc7.metric("PER", str(detail_us['per']))
                        dc8.metric("시가총액", detail_us['market_cap'])

                    own_col, rel_col = st.columns([3, 2])
                    with own_col:
                        if detail_us['institutional_pct'] > 0 or detail_us['insider_pct'] > 0:
                            st.markdown("#### 📊 기관/내부자 보유율")
                            retail_pct = max(0.0, 100.0 - detail_us['institutional_pct'] - detail_us['insider_pct'])
                            fig_own = go.Figure(go.Bar(
                                x=["기관", "내부자", "기타"],
                                y=[detail_us['institutional_pct'], detail_us['insider_pct'], retail_pct],
                                marker_color=["#2b7cff", "#ff4b4b", "#888"]
                            ))
                            fig_own.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                font=dict(color="white"),
                                yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="%", range=[0, 100]),
                                margin=dict(l=10, r=10, t=30, b=10), height=220
                            )
                            st.plotly_chart(fig_own, use_container_width=True)

                    with rel_col:
                        st.markdown("#### 🔗 AI 관련주")
                        if st.button("🔍 관련주 발굴", use_container_width=True, key="us_related_btn"):
                            with st.spinner("관련주 분석 중..."):
                                from ai_engine import generate_related_stocks
                                rel_result = generate_related_stocks(selected_ticker, detail_us.get("sector", ""))
                                st.session_state[f"us_related_{selected_ticker}"] = rel_result

                        if f"us_related_{selected_ticker}" in st.session_state:
                            for r in st.session_state[f"us_related_{selected_ticker}"]:
                                r_ticker = r.get("ticker", "")
                                r_name = r.get("name", r_ticker)
                                r_reason = r.get("reason", "")
                                if st.button(
                                    f"{r_name} ({r_ticker})",
                                    key=f"goto_{r_ticker}_{selected_ticker}",
                                    use_container_width=True,
                                    help=r_reason
                                ):
                                    st.session_state.us_input_ticker = r_ticker
                                    st.rerun()

                    st.markdown("---")

                    if st.button("🧠 세력 수급 및 AI 타점 분석", use_container_width=True):
                        with st.spinner("차트와 수급 데이터를 융합 분석 중입니다..."):
                            from ai_engine import generate_stock_report
                            report_json = generate_stock_report(selected_ticker, cur_price, change_pct)
                            st.session_state[f"report_{selected_ticker}"] = report_json

                            if "추천" in report_json.get("rating", "") and "비추천" not in report_json.get("rating", ""):
                                if "ai_portfolio" not in st.session_state:
                                    st.session_state.ai_portfolio = []
                                if not any(item["ticker"] == selected_ticker for item in st.session_state.ai_portfolio):
                                    st.session_state.ai_portfolio.append({
                                        "ticker": selected_ticker,
                                        "name": detail_us["name"],
                                        "buy_price": cur_price,
                                        "quantity": 10,
                                        "buy_date": datetime.now().strftime("%Y-%m-%d %H:%M")
                                    })
                                    st.toast(f"🤖 AI 자동 담기 완료: {selected_ticker}")

                    if f"report_{selected_ticker}" in st.session_state:
                        rep = st.session_state[f"report_{selected_ticker}"]
                        rating_color = "🟢" if "강력 추천" in rep.get("rating", "") else "🟡" if "추천" in rep.get("rating", "") else "🔴"

                        st.markdown(f"#### {rating_color} {rep.get('rating', '')}")
                        col_t1, col_t2 = st.columns(2)
                        col_t1.metric("권장 매수가", rep.get("buy_target", "-"))
                        col_t2.metric("목표 매도가", rep.get("sell_target", "-"))
                        st.metric("손절 라인", rep.get("stop_loss", "-"))

                        if st.button("🎒 내 포트폴리오에 직접 담기", use_container_width=True, type="primary"):
                            if "portfolio" not in st.session_state:
                                st.session_state.portfolio = []
                            if not any(item["ticker"] == selected_ticker for item in st.session_state.portfolio):
                                st.session_state.portfolio.append({
                                    "ticker": selected_ticker,
                                    "name": detail_us["name"],
                                    "buy_price": cur_price,
                                    "quantity": 10,
                                    "buy_date": datetime.now().strftime("%Y-%m-%d %H:%M")
                                })
                                st.success(f"나의 포트폴리오에 {selected_ticker}가 추가되었습니다!")
                            else:
                                st.warning("이미 포트폴리오에 있는 종목입니다.")
                else:
                    st.warning("데이터를 불러오지 못했습니다.")

            st.markdown("---")
            # --- 하단 전체: 상세 분석 ---
            st.markdown("### 📝 AI 상세 근거 및 수급 동향")
            if f"report_{selected_ticker}" in st.session_state:
                with st.container(border=True):
                    st.markdown(st.session_state[f"report_{selected_ticker}"].get("analysis", "상세 내용 없음"))
            else:
                st.info("우측 상단의 '🧠 분석' 버튼을 눌러 AI 등급 및 리포트를 받아보세요.")

    with tab2:
        st.subheader("📊 성과 트래킹 보드")

        if "trade_history" not in st.session_state:
            st.session_state.trade_history = []
        if "portfolio" not in st.session_state:
            st.session_state.portfolio = []
        if "ai_portfolio" not in st.session_state:
            st.session_state.ai_portfolio = []

        tab_holding, tab_history, tab_sheets = st.tabs([
            "📈 보유 종목",
            "📋 거래 성과",
            "☁️ 구글 시트 연동"
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

        with tab_sheets:
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

    # --- 하단 면책 조항 ---
    st.markdown("""
    <div class="disclaimer">
        <b>면책 조항 (Disclaimer):</b> 스톡시(Stockcy)에서 제공하는 모든 정보(종목 추천, 타점, AI 리포트 등)는 투자 참고용일 뿐이며, 
        실제 투자에 대한 결정 및 책임은 전적으로 사용자 본인에게 있습니다.
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
