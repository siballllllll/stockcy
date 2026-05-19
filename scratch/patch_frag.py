import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

def robust_replace(content, target_pattern, replacement_str):
    match = re.search(target_pattern, content, flags=re.DOTALL)
    if match:
        print("Found match!")
        return content[:match.start()] + replacement_str + content[match.end():]
    else:
        print("Pattern not found:", target_pattern[:50])
        return content

pattern_kr = r"with st\.container\(height=600\):\s+for sub_name, stocks in subsectors\.items\(\):\s+avg_pct = _sub_avg_pct\(stocks, prices\).*?_render_sector_stocks\(sub_name, stocks, prices, code_locations, selected_sector\)"

replace_kr = """                                @st.fragment
                                def _render_kr_subsector_card(sub_name, stocks, prices, code_locations, selected_sector):
                                    avg_pct = _sub_avg_pct(stocks, prices)
                                    pct_color = "#ff4b4b" if avg_pct > 0 else "#2b7cff" if avg_pct < 0 else "#888"
                                    tok = f"_sub_open_{selected_sector}__{sub_name}"
                                    if tok not in st.session_state:
                                        st.session_state[tok] = False
                                    is_open = st.session_state[tok]

                                    with st.container(border=True):
                                        h0, h1, h2, h3, h4 = st.columns([0.35, 2.8, 1.8, 1.4, 0.45])
                                        tog_label = "▼" if is_open else "▶"
                                        if h0.button(tog_label, key=f"tog_{sub_name}", use_container_width=True):
                                            st.session_state[tok] = not is_open
                                            st.rerun(scope="fragment")
                                        
                                        h1.markdown(
                                            f"<span style='font-size:1.10rem;font-weight:600'>📌 {sub_name}</span>"
                                            f"<span style='font-size:0.98rem;color:#888'>　{len(stocks)}개</span>",
                                            unsafe_allow_html=True,
                                        )
                                        h3.markdown(
                                            f"<span style='font-size:1.20rem;font-weight:700;color:{pct_color}'>{avg_pct:+.2f}%</span>",
                                            unsafe_allow_html=True,
                                        )
                                        ai_key = f"_sub_ai_{selected_sector}__{sub_name}"
                                        if h4.button("AI", key=f"ai_btn_{sub_name}", help="AI 섹터 분석"):
                                            with st.spinner("AI 분석 중..."):
                                                st.session_state[ai_key] = _sub_ai_summary(selected_sector, sub_name, avg_pct, stocks, prices)
                                            st.rerun(scope="fragment")

                                        if is_open:
                                            if ai_key in st.session_state:
                                                st.markdown(
                                                    f"<div style='background:rgba(255,255,255,0.05);border-left:3px solid {pct_color};"
                                                    f"border-radius:6px;padding:8px 12px;margin:4px 0 8px 0;"
                                                    f"font-size:1.07rem;line-height:1.55;color:#ddd'>"
                                                    f"{st.session_state[ai_key]}</div>",
                                                    unsafe_allow_html=True,
                                                )
                                            st.markdown('<hr class="toss-divider" style="margin:4px 0 6px 0">', unsafe_allow_html=True)
                                            _render_sector_stocks(sub_name, stocks, prices, code_locations, selected_sector)

                                with st.container(height=600):
                                    for sub_name, stocks in subsectors.items():
                                        _render_kr_subsector_card(sub_name, stocks, prices, code_locations, selected_sector)"""


pattern_us = r"with st\.container\(height=600\):\s+for sub_name, stocks in subsectors\.items\(\):\s+avg_pct = _us_sub_avg_pct\(stocks, prices\).*?_render_us_sector_stocks\(sub_name, stocks, prices, code_locations, selected_sector\)"

replace_us = """                                @st.fragment
                                def _render_us_subsector_card(sub_name, stocks, prices, code_locations, selected_sector):
                                    avg_pct = _us_sub_avg_pct(stocks, prices)
                                    pct_color = "#00c853" if avg_pct > 0 else "#ff4b4b" if avg_pct < 0 else "#888"
                                    tok = f"_us_sub_open_{selected_sector}__{sub_name}"
                                    if tok not in st.session_state:
                                        st.session_state[tok] = False
                                    is_open = st.session_state[tok]

                                    with st.container(border=True):
                                        h0, h1, h2, h3, h4 = st.columns([0.35, 2.8, 1.8, 1.4, 0.45])
                                        tog_label = "▼" if is_open else "▶"
                                        if h0.button(tog_label, key=f"us_tog_{sub_name}", use_container_width=True):
                                            st.session_state[tok] = not is_open
                                            st.rerun(scope="fragment")
                                        
                                        h1.markdown(
                                            f"<span style='font-size:1.10rem;font-weight:600'>📌 {sub_name}</span>"
                                            f"<span style='font-size:0.98rem;color:#888'>　{len(stocks)}개</span>",
                                            unsafe_allow_html=True,
                                        )
                                        h3.markdown(
                                            f"<span style='font-size:1.20rem;font-weight:700;color:{pct_color}'>{avg_pct:+.2f}%</span>",
                                            unsafe_allow_html=True,
                                        )
                                        ai_key = f"_us_sub_ai_{selected_sector}__{sub_name}"
                                        if h4.button("AI", key=f"us_ai_btn_{sub_name}", help="AI 섹터 분석"):
                                            with st.spinner("AI 분석 중..."):
                                                st.session_state[ai_key] = _us_sub_ai_summary(selected_sector, sub_name, avg_pct, stocks, prices)
                                            st.rerun(scope="fragment")

                                        if is_open:
                                            if ai_key in st.session_state:
                                                st.markdown(
                                                    f"<div style='background:rgba(255,255,255,0.05);border-left:3px solid {pct_color};"
                                                    f"border-radius:6px;padding:8px 12px;margin:4px 0 8px 0;"
                                                    f"font-size:1.07rem;line-height:1.55;color:#ddd'>"
                                                    f"{st.session_state[ai_key]}</div>",
                                                    unsafe_allow_html=True,
                                                )
                                            st.markdown('<hr class="toss-divider" style="margin:4px 0 6px 0">', unsafe_allow_html=True)
                                            _render_us_sector_stocks(sub_name, stocks, prices, code_locations, selected_sector)

                                with st.container(height=600):
                                    for sub_name, stocks in subsectors.items():
                                        _render_us_subsector_card(sub_name, stocks, prices, code_locations, selected_sector)"""

content = robust_replace(content, pattern_kr, replace_kr)
content = robust_replace(content, pattern_us, replace_us)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("done")
