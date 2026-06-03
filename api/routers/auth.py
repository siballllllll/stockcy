"""
인증 라우터 (Phase 1a) — /api/auth/*

- POST /login            : 로그인 → 세션 토큰 발급 (HttpOnly 쿠키 + 응답 본문)
- POST /logout           : 쿠키 제거
- GET  /me               : 현재 로그인 사용자 정보
- POST /change-password  : 본인 비밀번호 변경
- 관리자 전용 (require_admin):
  - GET  /users                    : 유저 목록
  - POST /users                    : 계정 생성
  - POST /users/{username}/toggle  : 활성/비활성 토글 (사이트 사용 on/off)
"""
from fastapi import APIRouter, Depends, Response, HTTPException
from pydantic import BaseModel

from api.auth import (
    authenticate, create_token, get_current_user, require_admin,
    create_user, list_users, set_active, change_password, get_user,
    COOKIE_NAME, TOKEN_TTL_SEC,
    create_access_request, get_my_pending_request, list_access_requests,
    decide_access_request, list_users_with_usage, add_credits,
)

router = APIRouter()


# ── 모델 ──────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"          # 'user' | 'admin'
    ai_credits: int = 0


class ToggleUserRequest(BaseModel):
    is_active: bool


class AiAccessRequest(BaseModel):
    reason: str = ""


class DecideRequest(BaseModel):
    approve: bool
    count: int = 5          # 승인 시 부여할 횟수


class CreditsAdjust(BaseModel):
    delta: int              # 가감할 횟수(음수 가능)


# ── 인증 ──────────────────────────────────────────────────────────────────────
@router.post("/login")
async def login(req: LoginRequest, response: Response):
    user = authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401,
                            detail="아이디 또는 비밀번호가 올바르지 않거나, 비활성화된 계정입니다.")
    token = create_token(user["username"])
    # HttpOnly 쿠키 (동일 사이트). 크로스 사이트(ngrok 등)에서는 응답 본문의 token을
    # localStorage에 저장해 Authorization: Bearer 로 보내면 origin 무관하게 동작한다.
    response.set_cookie(
        key=COOKIE_NAME, value=token, max_age=TOKEN_TTL_SEC,
        httponly=True, samesite="lax", secure=False, path="/",
    )
    return {
        "username": user["username"],
        "role": user["role"],
        "ai_credits": user["ai_credits"],
        "token": token,
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"success": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {
        "username": user["username"],
        "role": user["role"],
        "is_active": bool(user["is_active"]),
        "ai_credits": user["ai_credits"],
        "telegram_chat_id": user.get("telegram_chat_id") or "",
    }


@router.post("/change-password")
async def change_my_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    # 현재 비밀번호 확인
    if not authenticate(user["username"], req.current_password):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")
    ok, msg = change_password(user["username"], req.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


# ── 관리자: 유저 관리 ─────────────────────────────────────────────────────────
@router.get("/users")
async def admin_list_users(_admin: dict = Depends(require_admin)):
    return {"users": list_users()}


@router.post("/users")
async def admin_create_user(req: CreateUserRequest, _admin: dict = Depends(require_admin)):
    ok, msg = create_user(req.username, req.password, req.role, req.ai_credits)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


@router.post("/users/{username}/toggle")
async def admin_toggle_user(username: str, req: ToggleUserRequest,
                            admin: dict = Depends(require_admin)):
    target = get_user(username)
    if not target:
        raise HTTPException(status_code=404, detail="존재하지 않는 계정")
    # 관리자가 자기 자신을 비활성화하는 사고 방지
    if username == admin["username"] and not req.is_active:
        raise HTTPException(status_code=400, detail="자기 자신은 비활성화할 수 없습니다.")
    ok, msg = set_active(username, req.is_active)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


# ── AI 사용 승인제 (Phase 4) ──────────────────────────────────────────────────
@router.post("/ai-request")
async def submit_ai_request(req: AiAccessRequest, user: dict = Depends(get_current_user)):
    """일반 유저가 AI 사용 권한(횟수)을 신청한다."""
    ok, msg = create_access_request(user["username"], req.reason)
    return {"success": ok, "message": msg}


@router.get("/ai-status")
async def my_ai_status(user: dict = Depends(get_current_user)):
    """현재 유저의 AI 잔여 횟수 + 대기 중 신청 여부."""
    pending = get_my_pending_request(user["username"])
    return {
        "ai_credits": user["ai_credits"],
        "is_admin": user["role"] == "admin",
        "pending": bool(pending),
        "pending_since": pending["requested_at"] if pending else None,
    }


@router.get("/admin/ai-requests")
async def admin_list_ai_requests(status: str = "pending", _admin: dict = Depends(require_admin)):
    return {"requests": list_access_requests(status or None)}


@router.post("/admin/ai-requests/{req_id}/decide")
async def admin_decide_ai_request(req_id: int, body: DecideRequest, admin: dict = Depends(require_admin)):
    ok, msg = decide_access_request(req_id, body.approve, body.count, admin["username"])
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


@router.get("/admin/users-usage")
async def admin_users_usage(_admin: dict = Depends(require_admin)):
    """유저별 잔여 크레딧 + 사용량 + 대기 신청 여부."""
    return {"users": list_users_with_usage()}


@router.post("/users/{username}/credits")
async def admin_adjust_credits(username: str, body: CreditsAdjust, _admin: dict = Depends(require_admin)):
    if not get_user(username):
        raise HTTPException(status_code=404, detail="존재하지 않는 계정")
    new_bal = add_credits(username, body.delta)
    return {"success": True, "ai_credits": new_bal, "message": f"{username} 잔여 {new_bal}회"}
