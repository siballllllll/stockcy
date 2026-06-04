"""
Turso 원격 백업/복원 (best-effort).

목적: Cloudtype 등 영구 디스크가 없는 환경에서 db.sqlite3 데이터를 보존한다.
- 시작 시: 로컬 DB가 비어있으면 Turso에서 복원
- 주기적으로: 로컬 db.sqlite3 스냅샷을 Turso에 백업

설계 원칙:
- **앱 안전 최우선**: 이 모듈의 모든 동작은 실패해도 예외를 삼키고 로그만 남긴다.
  Turso가 죽어도/느려도 앱은 로컬 sqlite3로 평소처럼 동작한다.
- 쿼리 코드(db.py)는 전혀 건드리지 않는다. 파일 단위 백업/복원만 한다.
- 외부 라이브러리 불필요: Turso HTTP(hrana v2 /pipeline) 를 requests 로 직접 호출.
- 세대(generation) 방식: 새 백업을 새 세대로 쓰고 meta를 마지막에 갱신.
  백업 도중 사고가 나도 이전 완성본은 보존된다(부분 백업은 복원에서 무시).

환경변수:
- TURSO_DATABASE_URL : libsql://... 또는 https://...
- TURSO_AUTH_TOKEN   : Turso 인증 토큰
둘 다 있어야 활성화. 없으면 모든 함수가 조용히 no-op → 로컬 단독 동작(기존과 동일).
"""
import os
import base64
import time
import threading
import sqlite3

import requests

# ── 설정 ──────────────────────────────────────────────────────────────────────
_BACKUP_TABLE = "db_file_backup"      # (gen, seq, chunk)
_META_TABLE = "db_file_meta"          # (k, v)
_CHUNK_CHARS = 200 * 1024             # base64 텍스트 청크 크기(행당)
_BATCH = 5                            # 한 HTTP 요청에 담을 INSERT 수
_BACKUP_INTERVAL = 600               # 백업 주기(초) = 10분
_HTTP_TIMEOUT = 60

_backup_thread_started = False
_thread_lock = threading.Lock()


# ── 연결 정보 ─────────────────────────────────────────────────────────────────
def _endpoint():
    url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    if not url:
        return None
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    elif url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    elif not url.startswith("https://"):
        url = "https://" + url
    return url.rstrip("/") + "/v2/pipeline"


def _token():
    return os.environ.get("TURSO_AUTH_TOKEN", "").strip()


def enabled():
    """Turso 백업 활성화 여부 (env 2개 모두 있을 때만)."""
    return bool(_endpoint() and _token())


# ── HTTP(hrana v2) ────────────────────────────────────────────────────────────
def _to_value(a):
    if a is None:
        return {"type": "null"}
    if isinstance(a, bool):
        return {"type": "integer", "value": str(int(a))}
    if isinstance(a, int):
        return {"type": "integer", "value": str(a)}
    if isinstance(a, float):
        return {"type": "float", "value": a}
    if isinstance(a, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(bytes(a)).decode()}
    return {"type": "text", "value": str(a)}


def _pipeline(statements):
    """statements: [(sql, args_list_or_None), ...]. 결과 result dict 리스트 반환."""
    reqs = []
    for sql, args in statements:
        stmt = {"sql": sql}
        if args is not None:
            stmt["args"] = [_to_value(a) for a in args]
        reqs.append({"type": "execute", "stmt": stmt})
    reqs.append({"type": "close"})

    r = requests.post(
        _endpoint(),
        headers={"Authorization": f"Bearer {_token()}",
                 "Content-Type": "application/json"},
        json={"requests": reqs},
        timeout=_HTTP_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    results = []
    for item in data.get("results", []):
        if item.get("type") == "error":
            raise RuntimeError(f"Turso error: {item.get('error')}")
        resp = item.get("response") or {}
        if resp.get("type") == "execute":
            results.append(resp.get("result", {}))
    return results


def _cell_text(cell):
    # hrana 값: {"type":"text","value":"..."} 등
    return cell.get("value", "") if isinstance(cell, dict) else str(cell)


def _ensure_tables():
    _pipeline([
        (f"CREATE TABLE IF NOT EXISTS {_BACKUP_TABLE} "
         f"(gen INTEGER NOT NULL, seq INTEGER NOT NULL, chunk TEXT NOT NULL, "
         f"PRIMARY KEY(gen, seq))", None),
        (f"CREATE TABLE IF NOT EXISTS {_META_TABLE} (k TEXT PRIMARY KEY, v TEXT)", None),
    ])


def _get_meta(key, default=None):
    res = _pipeline([(f"SELECT v FROM {_META_TABLE} WHERE k=?", [key])])
    rows = res[0].get("rows", []) if res else []
    if rows:
        return _cell_text(rows[0][0])
    return default


# ── 복원 ──────────────────────────────────────────────────────────────────────
def restore_to(db_path) -> bool:
    """Turso의 최신 완성 백업을 db_path로 복원. 성공 시 True. 실패/백업없음 시 False."""
    if not enabled():
        return False
    try:
        _ensure_tables()
        gen = _get_meta("current_gen")
        count = _get_meta("chunk_count")
        if gen is None or count is None:
            print("[turso] 복원할 백업이 없습니다(첫 실행).")
            return False
        gen, count = int(gen), int(count)
        res = _pipeline([(f"SELECT chunk FROM {_BACKUP_TABLE} WHERE gen=? ORDER BY seq", [gen])])
        rows = res[0].get("rows", []) if res else []
        if len(rows) != count:
            print(f"[turso] 백업 불완전(기대 {count}, 실제 {len(rows)}) → 복원 건너뜀")
            return False
        b64 = "".join(_cell_text(row[0]) for row in rows)
        raw = base64.b64decode(b64)
        tmp = db_path + ".restore.tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        # 오래된 WAL/SHM 사이드카 제거 후 원자적 교체
        for ext in ("-wal", "-shm"):
            try:
                os.remove(db_path + ext)
            except OSError:
                pass
        os.replace(tmp, db_path)
        print(f"[turso] 복원 완료: {len(raw):,} bytes (gen {gen}, {count} chunks)")
        return True
    except Exception as e:
        print(f"[turso] 복원 실패(무시, 로컬DB 사용): {e}")
        return False


# ── 백업 ──────────────────────────────────────────────────────────────────────
def backup_from(db_path) -> bool:
    """db_path의 일관 스냅샷을 Turso에 백업. 성공 시 True."""
    if not enabled():
        return False
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return False
    snap = db_path + ".backup.snap"
    try:
        # VACUUM INTO: 실행 중 DB의 일관된 스냅샷 파일 생성
        try:
            os.remove(snap)
        except OSError:
            pass
        con = sqlite3.connect(db_path, timeout=30.0)
        try:
            con.execute("VACUUM INTO ?", (snap,))
        finally:
            con.close()

        with open(snap, "rb") as f:
            raw = f.read()
        b64 = base64.b64encode(raw).decode()
        chunks = [b64[i:i + _CHUNK_CHARS] for i in range(0, len(b64), _CHUNK_CHARS)]

        _ensure_tables()
        prev_gen = _get_meta("current_gen")
        new_gen = (int(prev_gen) + 1) if prev_gen is not None else 1

        # 1) 새 세대 청크 적재
        batch = []
        for i, ch in enumerate(chunks):
            batch.append((f"INSERT INTO {_BACKUP_TABLE}(gen, seq, chunk) VALUES (?,?,?)",
                          [new_gen, i, ch]))
            if len(batch) >= _BATCH:
                _pipeline(batch)
                batch = []
        if batch:
            _pipeline(batch)

        # 2) meta 갱신(= 완성 표시). 이게 끝나야 복원에서 인정됨.
        _pipeline([
            (f"INSERT INTO {_META_TABLE}(k,v) VALUES('current_gen',?) "
             f"ON CONFLICT(k) DO UPDATE SET v=excluded.v", [str(new_gen)]),
            (f"INSERT INTO {_META_TABLE}(k,v) VALUES('chunk_count',?) "
             f"ON CONFLICT(k) DO UPDATE SET v=excluded.v", [str(len(chunks))]),
        ])

        # 3) 이전 세대 정리(이제 안전)
        _pipeline([(f"DELETE FROM {_BACKUP_TABLE} WHERE gen<>?", [new_gen])])

        print(f"[turso] 백업 완료: {len(raw):,} bytes (gen {new_gen}, {len(chunks)} chunks)")
        return True
    except Exception as e:
        print(f"[turso] 백업 실패(무시): {e}")
        return False
    finally:
        try:
            os.remove(snap)
        except OSError:
            pass


# ── 백그라운드 백업 루프 ──────────────────────────────────────────────────────
def start_backup_loop(db_path):
    """주기적 백업 데몬 스레드를 1회만 기동한다."""
    global _backup_thread_started
    if not enabled():
        return
    with _thread_lock:
        if _backup_thread_started:
            return
        _backup_thread_started = True

    def _loop():
        # 시작 직후엔 방금 복원했으므로 한 주기 쉬고 시작
        while True:
            time.sleep(_BACKUP_INTERVAL)
            try:
                backup_from(db_path)
            except Exception as e:
                print(f"[turso] 백업 루프 오류(무시): {e}")

    threading.Thread(target=_loop, daemon=True, name="turso-backup").start()
    print(f"[turso] 백업 루프 시작(주기 {_BACKUP_INTERVAL}s)")
