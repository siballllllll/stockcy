"""v4.0 자동 승격 (v3.207.0).

ML 게이트(db.check_v4_gate)를 연속으로 통과하면 version.py와 frontend/package.json을
4.0.0으로 바꾸고 그 두 파일만 커밋·푸시한다. 작업 트리에 다른 변경이 있어도 건드리지 않는다.
이미 4 이상이면 아무것도 하지 않는다 — 승격은 한 번뿐이다.
"""
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
TARGET = "4.0.0"
# 하루 반짝 통과로 영구 승격되는 것을 막는다. AUC는 표본이 들어올 때마다 흔들린다.
STREAK_DAYS = 3


def current_version(root: str = ROOT) -> str:
    with open(os.path.join(root, "version.py"), encoding="utf-8") as f:
        m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', f.read())
    return m.group(1) if m else ""


def _replace(path: str, pattern: str, repl: str) -> None:
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    new, n = re.subn(pattern, repl, text, count=1)
    if n != 1:
        raise RuntimeError(f"버전 문자열을 못 찾음: {path}")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def promote_to_v4(gate: dict, root: str = ROOT, push: bool = True) -> dict:
    """버전 파일을 4.0.0으로 바꾸고 커밋(·푸시)한다. 반환: {promoted, from, pushed, error}."""
    cur = current_version(root)
    try:
        if int(cur.split(".")[0]) >= 4:
            return {"promoted": False, "from": cur, "reason": "already_v4"}
    except ValueError:
        return {"promoted": False, "from": cur, "error": "버전 파싱 실패"}

    files = ["version.py", "frontend/package.json"]
    _replace(os.path.join(root, "version.py"),
             r'APP_VERSION\s*=\s*"[^"]+"', f'APP_VERSION = "{TARGET}"')
    pkg = os.path.join(root, "frontend", "package.json")
    if os.path.exists(pkg):
        _replace(pkg, r'"version"\s*:\s*"[^"]+"', f'"version": "{TARGET}"')
    else:
        files.remove("frontend/package.json")

    hz = ", ".join(gate.get("passed_horizons", []))
    detail = "\n".join(
        f"- {h}: 표본 {v['n']} · 실전 AUC {v['live_auc']} · 55%+ 구간 {v['high_win']}% ({v['high_n']}건)"
        for h, v in gate.get("horizons", {}).items())
    msg = (f"release: 스톡시 v{TARGET} — ML 승격 게이트 {STREAK_DAYS}일 연속 통과 ({hz})\n\n"
           f"{detail}\n\n백엔드 일일 잡이 자동으로 승격함 (이전 v{cur}).")
    out = {"promoted": True, "from": cur, "pushed": False}
    _git(root, "add", "--", *files)
    c = _git(root, "commit", "-m", msg, "--", *files)
    if c.returncode != 0:
        # 파일만 4.0.0으로 남으면 다음 날 '이미 v4'로 보고 다시 시도하지 않는다 — 되돌린다.
        _git(root, "reset", "-q", "--", *files)
        _git(root, "checkout", "--", *files)
        err = [l for l in (c.stderr or c.stdout).splitlines() if l.strip() and not l.startswith("warning:")]
        return {"promoted": False, "from": cur, "error": f"commit 실패: {' / '.join(err)[-300:]}"}
    if push:
        p = _git(root, "push")
        out["pushed"] = p.returncode == 0
        if p.returncode != 0:
            out["error"] = f"push 실패: {p.stderr.strip()[:300]}"
    return out
