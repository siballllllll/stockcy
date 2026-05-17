"""
Tab2 코드를 @st.fragment 함수로 교체하는 패치 스크립트.

실행: python scratch/patch_frag.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

APP = r"C:\Users\user\.gemini\스톡시\app.py"

with open(APP, encoding="utf-8") as f:
    lines = f.readlines()

# ── 삽입할 fragment 함수 (들여쓰기 없음, 모듈 수준) ───────────────
FRAGMENT = """\
@st.fragment
def _render_ci_tab_fragment():
    \"\"\"커스텀 이슈 스나이퍼 탭 — fragment로 감싸 칩 클릭 시 dialog 유지.\"\"\"
    # ── 최근 검색어 히스토리 로드 (세션당 1회) ───────────────────────
    if "_ci_history_loaded" not in st.session_state:
        try:
            from db import load_ai_cache as _lhi
            _h = _lhi("custom_issue_history")
            st.session_state["_ci_history"] = _h.get("keywords", []) if _h else []
        except Exception:
            st.session_state["_ci_history"] = []
        st.session_state["_ci_history_loaded"] = True

    # ── 검색 폼 ──────────────────────────────────────────────────────
    with st.form(key="ci_form", border=False):
        _ci_col_inp, _ci_col_btn = st.columns([4, 1])
        with _ci_col_inp:
            _ci_keyword = st.text_input(
                "이슈 키워드",
                placeholder="예: 우크라이나 재건, 반도체 관세, 달러 약세, AI 버블...",
                key="ci_keyword_input",
                label_visibility="collapsed",
            )
        with _ci_col_btn:
            _ci_run = st.form_submit_button("🔍 분析", use_container_width=True, type="primary")

    # ── 최근 검색어 버튼 표시 ────────────────────────────────────────
    _ci_history = st.session_state.get("_ci_history", [])
    if _ci_history:
        st.markdown(
            "<div style='font-size:0.75rem;color:#888;margin:2px 0 4px'>🕐 최근 검색</div>",
            unsafe_allow_html=True,
        )
        for _ci_hi, _ci_hkw in enumerate(_ci_history[:8]):
            _c_kw, _c_del = st.columns([10, 1])
            with _c_kw:
                if st.button(
                    _ci_hkw, key=f"ci_hist_{_ci_hi}",
                    use_container_width=True, help=f"'{_ci_hkw}' 재검색",
                ):
                    st.session_state["_ci_chip_kw"] = _ci_hkw
                    st.rerun()          # fragment 만 재실행 — dialog 닫히지 않음
            with _c_del:
                if st.button("✕", key=f"ci_del_{_ci_hi}", help="검색기록 삭제"):
                    _cur = st.session_state.get("_ci_history", [])
                    _new_h = [h for h in _cur if h != _ci_hkw]
                    st.session_state["_ci_history"] = _new_h
                    def _del_save(_h=_new_h):
                        try:
                            from db import save_ai_cache as _sac
                            _sac("custom_issue_history", {"keywords": _h}, ttl_hours=24 * 30)
                        except Exception:
                            pass
                    threading.Thread(target=_del_save, daemon=True).start()
                    st.rerun()

    # ── 클릭 / 제출 처리 ─────────────────────────────────────────────
    _ci_chip_kw   = st.session_state.pop("_ci_chip_kw", None)
    _ci_kw        = _ci_chip_kw or _ci_keyword.strip()
    _ci_triggered = bool(_ci_chip_kw) or (_ci_run and bool(_ci_keyword.strip()))

    # ── 백그라운드 완료 결과 세션 반영 ───────────────────────────────
    for _ci_tid in [k for k in list(_SCENARIO_TASKS) if k.startswith("_ci_")]:
        with _SCENARIO_LOCK:
            _ci_t = _SCENARIO_TASKS.get(_ci_tid)
        if _ci_t and _ci_t["status"] in ("done", "error"):
            _res     = _ci_t.get("result")
            _kw_done = _ci_tid[4:]
            st.session_state["_ci_result"]        = _res
            st.session_state["_ci_last_kw"]       = _kw_done
            st.session_state["_ci_cache_checked"] = True
            st.session_state.pop("_ci_dialog_suppress", None)
            # 세션 캐시 저장 → 재클릭 시 즉시 복원
            if _res and "error" not in _res:
                _sc = st.session_state.get("_ci_result_cache", {})
                _sc[_kw_done] = _res
                if len(_sc) > 8:
                    _sc.pop(next(iter(_sc)))
                st.session_state["_ci_result_cache"] = _sc
            with _SCENARIO_LOCK:
                _SCENARIO_TASKS.pop(_ci_tid, None)
            break

    # ── 분析 시작 ─────────────────────────────────────────────────────
    if _ci_triggered and _ci_kw:
        _sess_cache = st.session_state.get("_ci_result_cache", {})
        if _ci_kw in _sess_cache:
            # 세션 캐시 히트 → 즉시 표시 (재분析 없음)
            st.session_state["_ci_result"]        = _sess_cache[_ci_kw]
            st.session_state["_ci_last_kw"]       = _ci_kw
            st.session_state["_ci_cache_checked"] = True
            _new_hist = [_ci_kw] + [h for h in _ci_history if h != _ci_kw]
            st.session_state["_ci_history"]       = _new_hist[:8]
            st.rerun()
        else:
            # 새 분析 시작
            st.session_state.pop("_ci_result", None)
            st.session_state.pop("_ci_dialog_suppress", None)
            st.session_state["_ci_last_kw"]       = _ci_kw
            st.session_state["_ci_cache_checked"] = False
            _new_hist = [_ci_kw] + [h for h in _ci_history if h != _ci_kw]
            _new_hist = _new_hist[:8]
            st.session_state["_ci_history"] = _new_hist
            def _save_hist(_h=_new_hist):
                try:
                    from db import save_ai_cache
                    save_ai_cache("custom_issue_history", {"keywords": _h}, ttl_hours=24 * 30)
                except Exception:
                    pass
            threading.Thread(target=_save_hist, daemon=True).start()
            _ci_new_tid = f"_ci_{_ci_kw}"
            with _SCENARIO_LOCK:
                _SCENARIO_TASKS[_ci_new_tid] = {"status": "running", "result": None}
            threading.Thread(
                target=_run_custom_issue_bg, args=(_ci_new_tid, _ci_kw), daemon=True
            ).start()
            st.rerun()
    elif _ci_run and not _ci_keyword.strip():
        st.warning("이슈 키워드를 입력해주세요.")

    # ── 진행 중 표시 ──────────────────────────────────────────────────
    _ci_running_kw = next(
        (_tid[4:] for _tid, _tv in _SCENARIO_TASKS.items()
         if _tid.startswith("_ci_") and _tv.get("status") == "running"),
        None
    )
    if _ci_running_kw:
        st.markdown(
            f"<div style='background:#1a2a1a;border:1px solid #2d5a2d;border-radius:8px;"
            f"padding:16px 18px;margin:8px 0'>"
            f"<div style='font-size:1.05rem;font-weight:700;color:#4caf50;margin-bottom:6px'>"
            f"🔄 분析 중...</div>"
            f"<div style='color:#ccc;font-size:0.9rem'>"
            f"<b style='color:#fff'>'{_ci_running_kw}'</b> 이슈를 AI가 분析하고 있습니다.<br>"
            f"<span style='color:#888;font-size:0.82rem'>"
            f"완료되면 이 창에 자동으로 결과가 표시됩니다. (최대 120초)</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
        if st.button(
            "✕ 닫기  (백그라운드에서 계속 실행됩니다)",
            key="ci_close_suppress",
            use_container_width=True,
        ):
            st.session_state["_ci_dialog_suppress"] = True
            st.rerun(scope="app")   # 전체 앱 재실행으로 dialog 닫기

    # ── 결과 로드: 세션 → Google Sheets 캐시 (새로고침 후 복원) ────────
    _ci_stored    = st.session_state.get("_ci_result")
    _ci_active_kw = st.session_state.get("_ci_last_kw", "")

    if _ci_stored is None and not st.session_state.get("_ci_cache_checked", False):
        try:
            from db import load_ai_cache as _lci
            _ci_from_cache = _lci("custom_issue_latest")
            if _ci_from_cache:
                _cached_kw = _ci_from_cache.get("keyword", "")
                if not _ci_active_kw or _cached_kw == _ci_active_kw:
                    _ci_stored    = _ci_from_cache.get("result")
                    _ci_active_kw = _cached_kw
                    if _ci_stored:
                        st.session_state["_ci_result"]  = _ci_stored
                        st.session_state["_ci_last_kw"] = _ci_active_kw
                        if "error" not in _ci_stored:
                            _sc = st.session_state.get("_ci_result_cache", {})
                            _sc[_ci_active_kw] = _ci_stored
                            st.session_state["_ci_result_cache"] = _sc
        except Exception:
            pass
        st.session_state["_ci_cache_checked"] = True

    # ── 결과 표시 ─────────────────────────────────────────────────────
    if _ci_stored:
        _col_title, _col_del = st.columns([5, 1])
        with _col_title:
            st.markdown(
                f"<h4 style='margin:10px 0 4px;color:#ffd740'>"
                f"📌 {_ci_stored.get('title', _ci_active_kw)}</h4>",
                unsafe_allow_html=True,
            )
        with _col_del:
            if st.button("🗑️ 삭제", key="ci_delete_btn", help="결과를 삭제합니다"):
                st.session_state.pop("_ci_result", None)
                st.session_state.pop("_ci_last_kw", None)
                st.session_state["_ci_cache_checked"] = False
                try:
                    from db import delete_ai_cache
                    delete_ai_cache("custom_issue_latest")
                except Exception:
                    pass
                st.rerun()
        _render_custom_issue_result(_ci_stored, key_prefix=f"ci_{_ci_active_kw[:20]}")


"""

FRAGMENT_LINES = [l + "\n" for l in FRAGMENT.split("\n")]

# ── 교체 범위 찾기 ─────────────────────────────────────────────────
# 탭2 시작: "    # ── 탭 2: 커스텀 이슈 스나이퍼" (0-indexed 1653)
# 탭1 시작: "    # ── 탭 1: AI 자동 시나리오"    (0-indexed 1813)
tab2_start = None
tab1_start = None
for i, l in enumerate(lines):
    if "# ── 탭 2: 커스텀 이슈 스나이퍼" in l and tab2_start is None:
        tab2_start = i
    if "# ── 탭 1: AI 자동 시나리오" in l and tab1_start is None:
        tab1_start = i

print(f"tab2_start (0-idx): {tab2_start}  tab1_start (0-idx): {tab1_start}")

# dialog 데코레이터 위치 (fragment 함수 삽입 위치)
dialog_idx = None
for i, l in enumerate(lines):
    if "@st.dialog" in l and "시나리오" in l:
        dialog_idx = i
        break
print(f"dialog_idx (0-idx): {dialog_idx}")

# ── 교체 실행 ──────────────────────────────────────────────────────
# 1) tab2 블록 내용을 fragment 호출 한 줄로 교체
new_tab2_block = "    # ── 탭 2: 커스텀 이슈 스나이퍼 ──────────────────────────────────────\n    with _tab_custom:\n        _render_ci_tab_fragment()\n\n"
lines[tab2_start:tab1_start] = [new_tab2_block]

# tab1 위치는 변경됐으므로 재탐색
new_tab1_start = None
for i, l in enumerate(lines):
    if "# ── 탭 1: AI 자동 시나리오" in l:
        new_tab1_start = i
        break
print(f"new_tab1_start (0-idx): {new_tab1_start}")

# 2) fragment 함수를 @st.dialog 바로 앞에 삽입 (dialog_idx는 이제 이전 위치 기준)
# tab2_start ~ tab1_start 사이를 1줄로 줄였으므로 dialog_idx 위치도 조정됨
# dialog_idx는 tab2_start보다 이전이므로 변경 없음 (tab2_start > dialog_idx)
print(f"dialog_idx unchanged: {dialog_idx}")

lines[dialog_idx:dialog_idx] = FRAGMENT_LINES
print(f"Inserted {len(FRAGMENT_LINES)} fragment lines before line {dialog_idx+1}")

with open(APP, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Done.")
