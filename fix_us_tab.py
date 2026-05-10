# -*- coding: utf-8 -*-
"""
US 탭 구조를 KR 탭과 동일하게 수정:
  - 3-mode radio → us_mode = st.session_state.us_mode
  - AI 타점 보드: if True: (항상 표시)
  - 종목 탐색: st.expander + 2-button toggle (KR과 동일)
  - col_us_chart / col_us_right의 pass 케이스 제거
"""

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"[시작] 총 {len(lines)}줄")

# Step 1: us_mode 기본값 변경 (idx 2040, line 2041)
assert '가 AI 타점 보드' in lines[2040] or '🎯 AI 타점 보드' in lines[2040], \
    f"Step1 실패: {repr(lines[2040][:80])}"
lines[2040] = lines[2040].replace('"🎯 AI 타점 보드"', '"📊 일반 주식 검색"')
print("Step 1 완료: us_mode 기본값 변경")

# Step 2: AI 타점 보드 조건 변경 (idx 2071, line 2072)
assert '🎯 AI 타점 보드' in lines[2071], f"Step2 실패: {repr(lines[2071][:80])}"
lines[2071] = lines[2071].replace('if us_mode == "🎯 AI 타점 보드":', 'if True:')
print("Step 2 완료: AI 타점 보드 if True:")

# Step 3: col_us_chart 내부 pass 케이스 제거
# idx 2258: if us_mode == "🎯 AI 타점 보드":
# idx 2259: pass  # ...
# idx 2260: elif us_mode == "🔥..." → if us_mode == "🔥..."
assert '🎯 AI 타점 보드' in lines[2258], f"Step3a 실패: {repr(lines[2258][:80])}"
assert 'pass' in lines[2259], f"Step3b 실패: {repr(lines[2259][:80])}"
assert 'elif us_mode ==' in lines[2260], f"Step3c 실패: {repr(lines[2260][:80])}"
lines[2260] = lines[2260].replace('elif us_mode ==', 'if us_mode ==')
del lines[2258:2260]   # 2줄 삭제 → 이후 인덱스 -2
print("Step 3 완료: col_us_chart pass 제거 및 elif→if")

# Step 4: col_us_right 내부 pass 케이스 제거 (Step3로 -2 적용)
# 원본 2386→2384, 2387→2385, 2388→2386
assert '🎯 AI 타점 보드' in lines[2384], f"Step4a 실패: {repr(lines[2384][:80])}"
assert 'pass' in lines[2385], f"Step4b 실패: {repr(lines[2385][:80])}"
assert 'elif us_mode ==' in lines[2386], f"Step4c 실패: {repr(lines[2386][:80])}"
lines[2386] = lines[2386].replace('elif us_mode ==', 'if us_mode ==')
del lines[2384:2386]   # 2줄 삭제 → 이후 인덱스 -2
print("Step 4 완료: col_us_right pass 제거 및 elif→if")

# Step 5: _us_need_price 조건 수정 (idx 2247, Steps 3-4 영향 없음 since 2247<2258)
assert 'us_mode != ' in lines[2247] and '_us_need_price' in lines[2247], \
    f"Step5 실패: {repr(lines[2247][:80])}"
lines[2247] = lines[2247].replace(
    'if us_mode != "🎯 AI 타점 보드" and _us_need_price:',
    'if _us_need_price:'
)
print("Step 5 완료: _us_need_price 조건 수정")

# Step 6: 3-mode radio 블록 → us_mode = st.session_state.us_mode (1줄, net -9)
assert '모드 토글' in lines[2057], f"Step6 시작 실패: {repr(lines[2057][:80])}"
radio_line = '            us_mode = st.session_state.us_mode\n'
lines = lines[:2057] + [radio_line] + lines[2067:]
print(f"Step 6 완료: radio→session_state ({len(lines)}줄)")

# Step 7: 재들여쓰기 (+4 spaces)
# 원본 2239(2-col comment) -9(radio) = 2230
# 원본 3238(tab2) -2(step3) -2(step4) -9(step6) = 3225
COL_START = 2230
TAB2_IDX  = 3225
assert '2-컬럼 레이아웃 변수' in lines[COL_START], \
    f"Step7 시작점 실패: {repr(lines[COL_START][:80])}"
assert 'with tab2:' in lines[TAB2_IDX], \
    f"Step7 끝점 실패: {repr(lines[TAB2_IDX][:80])}"
for i in range(COL_START, TAB2_IDX):
    if lines[i].strip():
        lines[i] = '    ' + lines[i]
print(f"Step 7 완료: [{COL_START}:{TAB2_IDX}) 재들여쓰기 +4")

# Step 8: expander + 2-button toggle 삽입
expander_lines = [
    '            with st.expander("📊 종목 탐색", expanded=False):\n',
    '                _un1, _un2 = st.columns(2)\n',
    '                with _un1:\n',
    '                    if st.button("📊 일반 주식 검색", key="us_nav2_search",\n',
    '                                 type="primary" if us_mode == "📊 일반 주식 검색" else "secondary",\n',
    '                                 use_container_width=True):\n',
    '                        st.session_state.us_mode = "📊 일반 주식 검색"\n',
    '                        st.rerun()\n',
    '                with _un2:\n',
    '                    if st.button("🔥 오늘의 이슈 섹터", key="us_nav2_sector",\n',
    '                                 type="primary" if us_mode == "🔥 오늘의 이슈 섹터" else "secondary",\n',
    '                                 use_container_width=True):\n',
    '                        st.session_state.us_mode = "🔥 오늘의 이슈 섹터"\n',
    '                        st.rerun()\n',
]
lines = lines[:COL_START] + expander_lines + lines[COL_START:]
print(f"Step 8 완료: expander 삽입 (총 {len(lines)}줄)")

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("\n=== 완료 ===")
