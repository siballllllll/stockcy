"""
네이티브 런타임 호환 모듈 (구 Streamlit 대체)

과거 Streamlit 앱에서 쓰던 `st.secrets` / `@st.cache_data` / `@st.cache_resource` /
UI 호출(`st.write` 등)을 FastAPI 환경에서 그대로 쓸 수 있도록 대체한다.
환경변수 기반 secrets + TTL 인메모리 캐시 + UI NoOp 으로 구성.

사용법:  import st_compat as st   →   st.secrets["gemini"]["api_key"], @st.cache_data(ttl=60) ...

(v3.0.0: sys.modules["streamlit"] 을 가로채던 streamlit_mock 을 폐기하고,
 각 모듈이 이 네이티브 모듈을 직접 import 하도록 전환했다.)
"""
import os
import json
import time
import threading
import functools


# ── secrets 대체 ─────────────────────────────────────────────────────────────

class _AttrDict(dict):
    """딕셔너리 + .속성 접근 지원 (st.secrets 동작 모방)."""

    def __getattr__(self, key: str):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __getitem__(self, key: str):
        val = super().__getitem__(key)
        if isinstance(val, dict) and not isinstance(val, _AttrDict):
            return _AttrDict(val)
        return val


def _build_secrets() -> _AttrDict:
    """환경변수로부터 secrets 구조를 재구성한다."""
    raw_creds = os.environ.get("GSPREAD_CREDENTIALS", "{}")
    try:
        gspread_creds = json.loads(raw_creds)
    except Exception:
        gspread_creds = {}

    return _AttrDict({
        "gemini": {
            "api_key": os.environ.get("GEMINI_API_KEY", ""),
        },
        "kis": {
            "app_key":    os.environ.get("KIS_APP_KEY",    ""),
            "app_secret": os.environ.get("KIS_APP_SECRET", ""),
        },
        "gspread": {
            "credentials":      gspread_creds,
            "spreadsheet_id":   os.environ.get("GSPREAD_SPREADSHEET_ID", ""),
        },
        "telegram": {
            "bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            "chat_id":   os.environ.get("TELEGRAM_CHAT_ID",   ""),
        },
    })


secrets = _build_secrets()


def reload_secrets():
    """환경변수 변경 후 secrets 재구성."""
    global secrets
    secrets = _build_secrets()


# ── @cache_data 대체 ─────────────────────────────────────────────────────────

def _make_cache_key(args, kwargs):
    """인자를 hashable 캐시 키로 변환 (리스트/딕트 등 처리)."""
    def _to_hashable(v):
        try:
            hash(v)
            return v
        except TypeError:
            return json.dumps(v, sort_keys=True, default=str)

    return (
        tuple(_to_hashable(a) for a in args),
        tuple((k, _to_hashable(v)) for k, v in sorted(kwargs.items())),
    )


def cache_data(func=None, *, ttl=None, show_spinner=True, hash_funcs=None, **_kw):
    """
    @st.cache_data(ttl=N) 대체.
    - ttl=None → 프로세스 수명 내 영구 캐시
    - ttl=N    → TTL 기반 인메모리 캐시 (N초)
    decorated 함수에는 .clear() 메서드 추가.
    """
    def _decorator(fn):
        _store: dict = {}   # key → result
        _times: dict = {}   # key → timestamp
        _lock = threading.Lock()

        @functools.wraps(fn)
        def _wrapper(*args, **kwargs):
            try:
                key = _make_cache_key(args, kwargs)
            except Exception:
                return fn(*args, **kwargs)

            # 캐시 hit 체크만 lock 안에서 (빠른 경로)
            with _lock:
                now = time.monotonic()
                if key in _store:
                    if ttl is None or (now - _times[key]) < ttl:
                        return _store[key]

            # 무거운 계산은 lock 밖에서 실행 (동시 호출 시 중복 계산될 수 있으나 블로킹 방지)
            result = fn(*args, **kwargs)

            with _lock:
                _store[key] = result
                _times[key] = time.monotonic()
            return result

        def clear():
            with _lock:
                _store.clear()
                _times.clear()

        _wrapper.clear = clear
        return _wrapper

    # @cache_data        → func 는 callable
    # @cache_data(ttl=N) → func 는 None
    if callable(func):
        return _decorator(func)
    return _decorator


# ── @cache_resource 대체 ─────────────────────────────────────────────────────

def cache_resource(func=None, **_kw):
    """
    @st.cache_resource 대체.
    프로세스 수명 동안 단일 인스턴스를 유지한다.
    """
    def _decorator(fn):
        _instance: dict = {}
        _lock = threading.Lock()

        @functools.wraps(fn)
        def _wrapper(*args, **kwargs):
            try:
                key = _make_cache_key(args, kwargs)
            except Exception:
                key = id(fn)
            with _lock:
                if key not in _instance:
                    _instance[key] = fn(*args, **kwargs)
            return _instance[key]

        def clear():
            with _lock:
                _instance.clear()

        _wrapper.clear = clear
        return _wrapper

    if callable(func):
        return _decorator(func)
    return _decorator


# ── UI 호출 무시 (NoOp) ───────────────────────────────────────────────────────

class _NoOp:
    """st.write, st.spinner 등 모든 UI 호출을 조용히 무시한다."""

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def __getattr__(self, name):
        return self

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False


_noop = _NoOp()

# 과거 UI 호출 이름들을 모듈 전역에 NoOp 으로 노출
write = error = warning = info = success = _noop
spinner = progress = empty = expander = _noop
sidebar = columns = tabs = container = _noop
button = selectbox = text_input = number_input = _noop
checkbox = radio = slider = multiselect = _noop
dataframe = table = metric = json_ = _noop
plotly_chart = image = markdown = caption = _noop
title = header = subheader = code = _noop
rerun = stop = set_page_config = _noop
toast = balloons = snow = form = _noop

session_state: dict = {}
query_params: dict = {}


def __getattr__(name):
    """정의되지 않은 st.<무엇이든> 접근 시 조용히 NoOp 반환 (PEP 562)."""
    return _noop
