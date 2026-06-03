"""
인증·인가 인프라 (Phase 1a)

설계 메모:
- 외부 의존성 0 — 비밀번호 해싱(pbkdf2)·세션 토큰(HMAC 서명)을 파이썬 표준
  라이브러리만으로 구현한다. (Windows venv 설치 마찰 회피)
- 토큰은 JWT와 동일한 원리(payload + HMAC 서명)지만 자체 포맷이다.
- DB는 기존 SQLite(db.get_db_conn)를 그대로 사용. 테이블은 import 시 보장 생성.
- 이 모듈은 "추가만" — 기존 엔드포인트 동작에는 영향이 없다.
  실제 owner 강제는 Phase 1c에서 각 라우터에 의존성을 붙일 때 적용된다.
"""
import os
import time
import json
import hmac
import base64
import hashlib
import sqlite3
import secrets as _secrets
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Request

from db import get_db_conn

# ── 상수 ──────────────────────────────────────────────────────────────────────
TOKEN_TTL_SEC = 60 * 60 * 24 * 14   # 14일
COOKIE_NAME = "stockcy_session"
_PBKDF2_ITERS = 200_000


# ── 테이블 보장 ───────────────────────────────────────────────────────────────
def ensure_auth_tables() -> None:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username         TEXT PRIMARY KEY,
            password_hash    TEXT NOT NULL,
            role             TEXT NOT NULL DEFAULT 'user',   -- 'admin' | 'user'
            is_active        INTEGER NOT NULL DEFAULT 1,
            ai_credits       INTEGER NOT NULL DEFAULT 0,      -- Phase 4 승인제용 잔여 횟수
            telegram_chat_id TEXT,                            -- Phase 5 유저별 알림용
            created_at       TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # AI 사용 승인 요청 (Phase 4)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_access_requests (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL,
            requested_at  TEXT,
            reason        TEXT,
            status        TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | denied
            granted_count INTEGER DEFAULT 0,
            decided_at    TEXT,
            decided_by    TEXT
        )
    """)
    # AI 사용량 로그 (Phase 4)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT NOT NULL,
            feature   TEXT,
            called_at TEXT
        )
    """)
    conn.commit()
    conn.close()


# ── 서명 비밀키 (env 우선, 없으면 DB에 생성·영속) ────────────────────────────
def _get_secret() -> bytes:
    env = os.environ.get("AUTH_SECRET", "").strip()
    if env:
        return env.encode()
    conn = get_db_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT value FROM auth_meta WHERE key='secret'").fetchone()
    if row and row["value"]:
        conn.close()
        return row["value"].encode()
    new = _secrets.token_hex(32)
    cur.execute("INSERT OR REPLACE INTO auth_meta(key, value) VALUES('secret', ?)", (new,))
    conn.commit()
    conn.close()
    return new.encode()


# ── 비밀번호 해싱 (pbkdf2_sha256) ─────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = _secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
    return (f"pbkdf2_sha256${_PBKDF2_ITERS}$"
            f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}")


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iters, salt_b64, hash_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ── 세션 토큰 (payload.signature) ─────────────────────────────────────────────
def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(username: str) -> str:
    payload = {"u": username, "exp": int(time.time()) + TOKEN_TTL_SEC}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(_get_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str) -> Optional[str]:
    """유효하면 username, 아니면 None."""
    try:
        body, sig = token.split(".")
        expected = _b64e(hmac.new(_get_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload.get("u")
    except Exception:
        return None


# ── 유저 CRUD ─────────────────────────────────────────────────────────────────
def get_user(username: str) -> Optional[dict]:
    conn = get_db_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_users() -> list[dict]:
    conn = get_db_conn()
    rows = conn.execute(
        "SELECT username, role, is_active, ai_credits, telegram_chat_id, created_at "
        "FROM users ORDER BY created_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_user(username: str, password: str, role: str = "user",
                ai_credits: int = 0) -> tuple[bool, str]:
    username = (username or "").strip()
    if not username or not password:
        return False, "사용자명과 비밀번호는 필수입니다."
    if role not in ("admin", "user"):
        role = "user"
    conn = get_db_conn()
    try:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, is_active, ai_credits, created_at) "
            "VALUES(?,?,?,1,?,?)",
            (username, hash_password(password), role, ai_credits,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        return True, "계정 생성 완료"
    except sqlite3.IntegrityError:
        return False, "이미 존재하는 사용자명입니다."
    except Exception as e:
        return False, f"생성 실패: {e}"
    finally:
        conn.close()


def set_active(username: str, active: bool) -> tuple[bool, str]:
    conn = get_db_conn()
    cur = conn.execute("UPDATE users SET is_active = ? WHERE username = ?",
                       (1 if active else 0, username))
    conn.commit()
    n = cur.rowcount
    conn.close()
    if n == 0:
        return False, "존재하지 않는 계정"
    return True, ("활성화" if active else "비활성화") + " 완료"


def change_password(username: str, new_password: str) -> tuple[bool, str]:
    if not new_password:
        return False, "새 비밀번호를 입력하세요."
    conn = get_db_conn()
    cur = conn.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                       (hash_password(new_password), username))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return (n > 0), ("비밀번호 변경 완료" if n else "존재하지 않는 계정")


def authenticate(username: str, password: str) -> Optional[dict]:
    user = get_user((username or "").strip())
    if not user:
        return None
    if not user.get("is_active"):
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


# ── 관리자 시드 ───────────────────────────────────────────────────────────────
def seed_admin() -> None:
    """유저가 한 명도 없으면 관리자 1명을 생성한다.
    ADMIN_USERNAME / ADMIN_PASSWORD 환경변수가 있으면 사용, 없으면 임의 생성 후
    backend.log에 1회 출력한다 (로그인 후 변경 권장)."""
    ensure_auth_tables()
    conn = get_db_conn()
    n = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    conn.close()
    if n > 0:
        return
    uname = (os.environ.get("ADMIN_USERNAME", "").strip() or "admin")
    pw = os.environ.get("ADMIN_PASSWORD", "").strip()
    generated = False
    if not pw:
        pw = _secrets.token_urlsafe(9)
        generated = True
    ok, msg = create_user(uname, pw, role="admin")
    if not ok:
        print(f"[auth] 관리자 시드 실패: {msg}")
        return
    if generated:
        print("=" * 60)
        print(f"[auth] 관리자 계정 자동 생성됨")
        print(f"[auth]   username = {uname!r}")
        print(f"[auth]   password = {pw!r}   ← 이 비밀번호는 지금만 표시됩니다. 로그인 후 변경하세요.")
        print("=" * 60)
    else:
        print(f"[auth] 관리자 계정 생성됨: username={uname!r} (ADMIN_PASSWORD 사용)")


# ── FastAPI 의존성 ────────────────────────────────────────────────────────────
def _extract_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE_NAME)


async def get_current_user(request: Request) -> dict:
    token = _extract_token(request)
    username = verify_token(token) if token else None
    if not username:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user = get_user(username)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="비활성화되었거나 존재하지 않는 계정입니다.")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user


async def get_optional_user(request: Request) -> Optional[dict]:
    """로그인 안 했어도 통과 (None 반환). 점진적 전환 중 하위호환용."""
    token = _extract_token(request)
    username = verify_token(token) if token else None
    if not username:
        return None
    user = get_user(username)
    if not user or not user.get("is_active"):
        return None
    return user


# ── AI 사용 승인제 / 사용량 / 크레딧 (Phase 4) ────────────────────────────────
def get_credits(username: str) -> int:
    conn = get_db_conn()
    row = conn.execute("SELECT ai_credits FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return int(row["ai_credits"]) if row else 0


def add_credits(username: str, delta: int) -> int:
    """크레딧 증감(음수 가능). 0 미만으로는 안 내려감. 새 잔액 반환."""
    conn = get_db_conn()
    conn.execute(
        "UPDATE users SET ai_credits = MAX(0, ai_credits + ?) WHERE username = ?",
        (int(delta), username),
    )
    conn.commit()
    row = conn.execute("SELECT ai_credits FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return int(row["ai_credits"]) if row else 0


def consume_one_credit(username: str) -> bool:
    """잔여 크레딧이 있으면 1 차감(원자적). 성공 여부 반환."""
    conn = get_db_conn()
    cur = conn.execute(
        "UPDATE users SET ai_credits = ai_credits - 1 WHERE username = ? AND ai_credits > 0",
        (username,),
    )
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n > 0


def log_usage(username: str, feature: str) -> None:
    try:
        conn = get_db_conn()
        conn.execute(
            "INSERT INTO usage_log(username, feature, called_at) VALUES(?,?,?)",
            (username, feature, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def create_access_request(username: str, reason: str = "") -> tuple[bool, str]:
    """AI 사용 신청. 이미 대기 중이면 중복 생성하지 않음."""
    conn = get_db_conn()
    existing = conn.execute(
        "SELECT id FROM ai_access_requests WHERE username = ? AND status = 'pending'",
        (username,),
    ).fetchone()
    if existing:
        conn.close()
        return True, "이미 승인 대기 중인 신청이 있습니다."
    conn.execute(
        "INSERT INTO ai_access_requests(username, requested_at, reason, status) VALUES(?,?,?,'pending')",
        (username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reason or ""),
    )
    conn.commit()
    conn.close()
    return True, "AI 사용 신청이 접수되었습니다. 관리자 승인을 기다려 주세요."


def get_my_pending_request(username: str) -> Optional[dict]:
    conn = get_db_conn()
    row = conn.execute(
        "SELECT * FROM ai_access_requests WHERE username = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
        (username,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_access_requests(status: Optional[str] = None) -> list[dict]:
    conn = get_db_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM ai_access_requests WHERE status = ? ORDER BY id DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM ai_access_requests ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def decide_access_request(req_id: int, approve: bool, count: int, admin_name: str) -> tuple[bool, str]:
    conn = get_db_conn()
    row = conn.execute("SELECT * FROM ai_access_requests WHERE id = ?", (req_id,)).fetchone()
    if not row:
        conn.close()
        return False, "존재하지 않는 신청"
    if row["status"] != "pending":
        conn.close()
        return False, "이미 처리된 신청입니다."
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if approve:
        conn.execute(
            "UPDATE ai_access_requests SET status='approved', granted_count=?, decided_at=?, decided_by=? WHERE id=?",
            (int(count), now, admin_name, req_id),
        )
        conn.execute(
            "UPDATE users SET ai_credits = ai_credits + ? WHERE username = ?",
            (int(count), row["username"]),
        )
        msg = f"{row['username']} 에게 {count}회 부여했습니다."
    else:
        conn.execute(
            "UPDATE ai_access_requests SET status='denied', decided_at=?, decided_by=? WHERE id=?",
            (now, admin_name, req_id),
        )
        msg = f"{row['username']} 신청을 거부했습니다."
    conn.commit()
    conn.close()
    return True, msg


def list_users_with_usage() -> list[dict]:
    """유저 목록 + 잔여 크레딧 + 누적/오늘 사용량 + 대기 신청 여부."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db_conn()
    users = conn.execute(
        "SELECT username, role, is_active, ai_credits, created_at FROM users ORDER BY created_at"
    ).fetchall()
    result = []
    for u in users:
        d = dict(u)
        uname = d["username"]
        total = conn.execute("SELECT COUNT(*) c FROM usage_log WHERE username=?", (uname,)).fetchone()["c"]
        tod = conn.execute(
            "SELECT COUNT(*) c FROM usage_log WHERE username=? AND called_at LIKE ?", (uname, today + "%")
        ).fetchone()["c"]
        pend = conn.execute(
            "SELECT COUNT(*) c FROM ai_access_requests WHERE username=? AND status='pending'", (uname,)
        ).fetchone()["c"]
        d["usage_total"] = total
        d["usage_today"] = tod
        d["has_pending"] = pend > 0
        result.append(d)
    conn.close()
    return result


async def consume_ai_credit(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """비용 발생 AI 엔드포인트용 의존성. 관리자는 무제한, 일반 유저는 크레딧 1 차감.
    크레딧이 없으면 403(NEED_AI_CREDIT)."""
    if user.get("role") == "admin":
        return user
    if not consume_one_credit(user["username"]):
        raise HTTPException(
            status_code=403,
            detail="AI 사용 횟수가 없습니다. 관리자 승인이 필요합니다. (NEED_AI_CREDIT)",
        )
    log_usage(user["username"], request.url.path)
    return user


# ── import 시 1회: 테이블 보장 + 관리자 시드 ─────────────────────────────────
try:
    seed_admin()
except Exception as _e:
    print(f"[auth] 초기화 경고: {_e}")
