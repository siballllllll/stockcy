import streamlit as st
import pandas as pd
from data import get_us_stock_data

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
            st.warning("국내 주식 실시간 시세는 아직 준비 중입니다. 우측 상단 토글에서 '미국 주식'을 선택해주세요.")
        else:
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
            st.markdown("### 🔍 트레이딩 종목 탐색")
            
            sectors_db = {
                "🔥 반도체 및 AI": {"엔비디아 (NVDA)": "NVDA", "AMD (AMD)": "AMD", "TSMC (TSM)": "TSM", "브로드컴 (AVGO)": "AVGO", "마이크론 (MU)": "MU", "팔란티어 (PLTR)": "PLTR"},
                "💻 빅테크 및 소프트웨어": {"애플 (AAPL)": "AAPL", "마이크로소프트 (MSFT)": "MSFT", "알파벳 (GOOGL)": "GOOGL", "메타 (META)": "META", "아마존 (AMZN)": "AMZN"},
                "🚗 전기차 및 배터리": {"테슬라 (TSLA)": "TSLA", "리비안 (RIVN)": "RIVN", "루시드 (LCID)": "LCID"},
                "💊 바이오 및 헬스케어": {"일라이릴리 (LLY)": "LLY", "노보노디스크 (NVO)": "NVO", "존슨앤존슨 (JNJ)": "JNJ"},
                "💸 금융 및 핀테크": {"JP모건 (JPM)": "JPM", "비자 (V)": "V", "마스터카드 (MA)": "MA", "페이팔 (PYPL)": "PYPL"},
                "⌨️ 직접 검색 (전 종목)": {"수동 입력": "MANUAL"}
            }
            
            col_sel1, col_sel2 = st.columns(2)
            with col_sel1:
                selected_sector = st.selectbox("📂 분석할 섹터(영역)를 선택하세요", list(sectors_db.keys()))
                
            with col_sel2:
                if selected_sector == "⌨️ 직접 검색 (전 종목)":
                    input_ticker = st.text_input("미국 주식 티커를 직접 입력하세요 (예: GME, SOXL)", "NVDA").upper().strip()
                    selected_ticker = input_ticker if input_ticker else "NVDA"
                    selected_stock_name = selected_ticker
                else:
                    stock_options = sectors_db[selected_sector]
                    selected_stock_name = st.selectbox("🎯 트레이딩을 진행할 종목을 선택하세요", list(stock_options.keys()))
                    selected_ticker = stock_options[selected_stock_name]
            
            # TradingView용 거래소 심볼 매핑 (주요 종목은 거래소를 명시하고, 그 외 사용자는 직접 입력값 사용)
            tv_symbols = {
                "NVDA": "NASDAQ:NVDA", "AMD": "NASDAQ:AMD", "TSM": "NYSE:TSM", "AVGO": "NASDAQ:AVGO", "MU": "NASDAQ:MU", "PLTR": "NYSE:PLTR",
                "AAPL": "NASDAQ:AAPL", "MSFT": "NASDAQ:MSFT", "GOOGL": "NASDAQ:GOOGL", "META": "NASDAQ:META", "AMZN": "NASDAQ:AMZN",
                "TSLA": "NASDAQ:TSLA", "RIVN": "NASDAQ:RIVN", "LCID": "NASDAQ:LCID",
                "LLY": "NYSE:LLY", "NVO": "NYSE:NVO", "JNJ": "NYSE:JNJ",
                "JPM": "NYSE:JPM", "V": "NYSE:V", "MA": "NYSE:MA", "PYPL": "NASDAQ:PYPL"
            }
            tv_symbol = tv_symbols.get(selected_ticker, selected_ticker) # 매핑 안 된 티커는 입력값 그대로 전달
            
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
                st.markdown("### ⚡ 실시간 수급 및 타점")
                from data import get_us_stock_data
                df_us = get_us_stock_data([selected_ticker])
                
                if not df_us.empty:
                    row = df_us.iloc[0]
                    cur_price = row["현재가($)"]
                    change_pct = row["등락률(%)"]
                    
                    # 실시간 등락률 표시
                    delta_color = "normal" if change_pct >= 0 else "inverse"
                    st.metric(label=f"{selected_stock_name} 현재가", value=f"${cur_price}", delta=f"{change_pct}%", delta_color=delta_color)
                    
                    st.markdown("---")
                    
                    if st.button("🧠 세력 수급 및 AI 타점 분석", use_container_width=True):
                        with st.spinner("차트와 수급 데이터를 융합 분석 중입니다..."):
                            from ai_engine import generate_stock_report
                            report_json = generate_stock_report(selected_ticker, cur_price, change_pct)
                            st.session_state[f"report_{selected_ticker}"] = report_json
                            
                            # AI 추천 자동 담기 로직
                            if "추천" in report_json.get("rating", "") and "비추천" not in report_json.get("rating", ""):
                                if "ai_portfolio" not in st.session_state:
                                    st.session_state.ai_portfolio = []
                                # 중복 방지
                                if not any(item["ticker"] == selected_ticker for item in st.session_state.ai_portfolio):
                                    st.session_state.ai_portfolio.append({
                                        "ticker": selected_ticker,
                                        "buy_price": cur_price,
                                        "quantity": 10 # 기본 10주
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
                                    "buy_price": cur_price,
                                    "quantity": 10
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
        st.subheader("성과 트래킹 보드")
        
        tab_ai, tab_my = st.tabs(["🤖 AI 자동 추천 종목", "👤 내가 직접 담은 포트폴리오"])
        
        def render_portfolio(portfolio_state_key):
            port_list = st.session_state.get(portfolio_state_key, [])
            if not port_list:
                st.info("현재 등록된 종목이 없습니다.")
                return
                
            portfolio_tickers = list(set([item["ticker"] for item in port_list]))
            from data import get_us_stock_data
            
            with st.spinner("실시간 수익률을 계산 중입니다..."):
                pf_df = get_us_stock_data(portfolio_tickers)
            
            total_invested = 0
            total_current = 0
            results = []
            
            for item in port_list:
                ticker = item["ticker"]
                buy_p = item["buy_price"]
                qty = item["quantity"]
                invested = buy_p * qty
                
                if not pf_df.empty and ticker in pf_df["심볼"].values:
                    cur_p = pf_df[pf_df["심볼"] == ticker].iloc[0]["현재가($)"]
                    current_val = cur_p * qty
                    profit = current_val - invested
                    profit_pct = (profit / invested) * 100 if invested > 0 else 0
                else:
                    cur_p = buy_p 
                    current_val = invested
                    profit = 0
                    profit_pct = 0
                    
                total_invested += invested
                total_current += current_val
                
                results.append({
                    "종목": ticker,
                    "수량": qty,
                    "매수가": f"${buy_p:,.2f}",
                    "현재가": f"${cur_p:,.2f}",
                    "수익금": f"${profit:,.2f}",
                    "수익률(%)": f"{profit_pct:.2f}%"
                })
                
            total_profit = total_current - total_invested
            total_profit_pct = (total_profit / total_invested * 100) if total_invested > 0 else 0
            
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("총 매수 금액", f"${total_invested:,.2f}")
            col_m2.metric("총 평가 금액", f"${total_current:,.2f}")
            
            delta_color = "normal" if total_profit >= 0 else "inverse"
            col_m3.metric("총 수익률", f"${total_profit:,.2f}", f"{total_profit_pct:.2f}%", delta_color=delta_color)
            
            st.dataframe(results, use_container_width=True)
            
            if st.button("🗑️ 초기화", key=f"clear_{portfolio_state_key}", type="secondary"):
                st.session_state[portfolio_state_key] = []
                st.rerun()

        with tab_ai:
            st.markdown("**AI가 '추천' 등급 이상을 매긴 종목들이 자동으로 기록되는 공간입니다.**")
            render_portfolio("ai_portfolio")
            
        with tab_my:
            st.markdown("**내가 종목 카드에서 '내 포트폴리오에 직접 담기'를 눌러 수집한 종목들입니다.**")
            render_portfolio("portfolio")
            
            st.markdown("---")
            st.markdown("### 🛠️ 데이터베이스 연동 (Google Sheets)")
            if st.button("현재 나의 포트폴리오를 구글 시트에 백업하기 🚀"):
                from db import test_connection_and_write
                with st.spinner("구글 서버와 통신 중..."):
                    success, msg = test_connection_and_write()
                    if success:
                        st.success("데이터베이스 백업 성공! " + msg)
                    else:
                        st.error(msg)

    # --- 하단 면책 조항 ---
    st.markdown("""
    <div class="disclaimer">
        <b>면책 조항 (Disclaimer):</b> 스톡시(Stockcy)에서 제공하는 모든 정보(종목 추천, 타점, AI 리포트 등)는 투자 참고용일 뿐이며, 
        실제 투자에 대한 결정 및 책임은 전적으로 사용자 본인에게 있습니다.
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
