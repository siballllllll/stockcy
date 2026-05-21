"""
Streamlit 모의 모듈
FastAPI 환경에서 st.secrets / st.cache_data / st.cache_resource 를
환경변수 + TTL 인메모리 캐시로 투명하게 대체합니다.

api/main.py 에서 가장 먼저 import 해야 합니다.
(sys.modules['streamlit'] 을 이 모듈로 교체하는 사이드 이펙트)
"""
import os
import sys
import json
import time
import threading
import functools


# ── st.secrets 대체 ─────────────────────────────────────────────────────────

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

    def __contains__(self, key):
        return super().__contains__(key)


def _build_secrets() -> _AttrDict:
    """환경변수로부터 st.secrets 구조를 재구성합니다."""
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


# ── @st.cache_data 대체 ──────────────────────────────────────────────────────

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
    - ttl=None → lru_cache (프로세스 수명 내 영구)
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

            with _lock:
                now = time.monotonic()
                if key in _store:
                    if ttl is None or (now - _times[key]) < ttl:
                        return _store[key]
                result = fn(*args, **kwargs)
                _store[key] = result
                _times[key] = now
                return result

        def clear():
            with _lock:
                _store.clear()
                _times.clear()

        _wrapper.clear = clear
        return _wrapper

    # @st.cache_data        → func 는 callable
    # @st.cache_data(ttl=N) → func 는 None
    if callable(func):
        return _decorator(func)
    return _decorator


# ── @st.cache_resource 대체 ──────────────────────────────────────────────────

def cache_resource(func=None, **_kw):
    """
    @st.cache_resource 대체.
    프로세스 수명 동안 단일 인스턴스를 유지합니다.
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


# ── UI 호출 무시 (NoOp) ──────────────────────────────────────────────────────

class _NoOp:
    """st.write, st.spinner 등 모든 UI 호출을 조용히 무시합니다."""

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


# ── 모의 streamlit 모듈 ──────────────────────────────────────────────────────

class _StreamlitMock:
    cache_data     = staticmethod(cache_data)
    cache_resource = staticmethod(cache_resource)

    def __init__(self):
        self.secrets = _build_secrets()
        self.session_state: dict = {}
        self.query_params:  dict = {}

        _noop = _NoOp()
        for _attr in (
            "write", "error", "warning", "info", "success",
            "spinner", "progress", "empty", "expander",
            "sidebar", "columns", "tabs", "container",
            "button", "selectbox", "text_input", "number_input",
            "checkbox", "radio", "slider", "multiselect",
            "dataframe", "table", "metric", "json",
            "plotly_chart", "image", "markdown", "caption",
            "title", "header", "subheader", "code",
            "rerun", "stop", "set_page_config",
            "toast", "balloons", "snow", "form",
        ):
            setattr(self, _attr, _noop)

    def reload_secrets(self):
        """환경변수 변경 후 secrets 재구성."""
        self.secrets = _build_secrets()


# sys.modules 교체 (이 모듈이 import 되는 순간 적용)
sys.modules["streamlit"] = _StreamlitMock()  # type: ignore
