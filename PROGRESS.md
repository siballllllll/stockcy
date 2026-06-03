# 멀티유저 전환 — 진행 체크리스트

> 이 파일은 "어디까지 했고 다음에 뭘 할지"의 단일 출처입니다. VSCode/터미널이 꺼져도
> 새 세션에서 이 파일 + `plan_multiuser.md` + `git log` 를 읽으면 그대로 이어서 작업할 수 있습니다.
> (Claude는 추가로 `~/.claude` 메모리의 `멀티유저 전환 진행상황`을 매 세션 자동으로 읽습니다.)

**전체 설계:** `plan_multiuser.md` 참조
**마지막 갱신:** 2026-06-03

---

## ✅ Phase 1 — 인증 + owner 일원화  (완료·커밋됨, v3.16.0)
- [x] 백엔드 인증 인프라 (`api/auth.py`, `api/routers/auth.py`)
- [x] 프론트 로그인 (`lib/auth-context.tsx`, `components/auth/LoginForm.tsx`, `Providers.tsx` 게이트+토큰주입)
- [x] owner 세션 강제 (portfolio/trades/trading/postmortem) + db.py owner 스코핑
- [x] 레거시 `USER` → `admin` 데이터 이전 (포폴6·거래20·잔고1)
- [x] 브라우저 로그인 E2E 검증 (Playwright)
- 관리자 계정: `admin` (비번은 backend.log 최초 출력 / 변경됨)

## ✅ Phase 2 — 리딩방 관리자 전용화  (완료·커밋됨, v3.17.0)
- [x] 백엔드: ai.py 4개 엔드포인트에 `require_admin`
      (leading-room-patterns, screener-feedback-stats, entry-timing, pattern-profile/build)
- [x] 프론트 대시보드: 리딩방검증·시간대분석 탭 + 리딩점수 뱃지 숨김 (`app/page.tsx`)
- [x] 프론트 포트폴리오: 리딩방 패턴분석 버튼/패널 + 출처·유형(리딩방/테스트) 토글·필터 숨김 (`app/favorites/page.tsx`)
- [x] 비관리자 403 검증 통과 (admin 200 / user 403), tsc 통과

## ✅ Phase 3 — favorites·price_alerts·trade_analysis 유저별 격리  (완료·커밋됨, v3.18.0)
- [x] favorites/price_alerts에 owner 컬럼 + PK 재생성(마이그레이션), trade_analysis 키 `owner::` 네임스페이스
- [x] db 함수 owner 스코핑(내부 호출용 owner=None=전체 유지), portfolio.py 엔드포인트가 세션 owner 전달
- [x] 기존 데이터 owner='admin' 귀속, 신규유저 격리 검증(p3user TSLA가 admin에 안 보임)
- 참고: 에이전트/워처/가격체크 루프는 owner 미지정 → 전체 favorites/alerts 스캔(의도된 동작)
- 참고: AI 자동 알림(auto_register_ai_alerts)은 owner 기본 'admin' (Phase 4에서 AI 게이팅 시 정교화)

## 🔄 Phase 4 — AI 승인제 + 사용량/계정 컨트롤  (4a 백엔드 완료, 4b 프론트 진행 중)
- [x] **4a 백엔드:** `ai_access_requests`/`usage_log` 테이블, credit 함수 + `consume_ai_credit` 의존성
- [x] **4a:** ai.py 비용 엔드포인트 21종에 `consume_ai_credit`(관리자 무제한/유저 1차감, 0이면 403 NEED_AI_CREDIT)
- [x] **4a:** 엔드포인트 — POST /auth/ai-request, GET /auth/ai-status, GET /auth/admin/ai-requests,
      POST /auth/admin/ai-requests/{id}/decide, GET /auth/admin/users-usage, POST /auth/users/{u}/credits
- [x] **4a:** 검증 — 0크레딧 403 → 신청 → 승인2회 → credits=2 → 차감 2→1→0
- [ ] **4b 프론트 (다음):** AuthContext에 ai_credits/신청, 비용버튼 잠금+신청 UX(403 NEED_AI_CREDIT 핸들),
      관리자 화면(대기 신청 승인·유저별 크레딧/사용량/on·off/가감)

## ⬜ Phase 5 — 텔레그램 유저별 (공유봇 + 본인 챗ID)
- [ ] `_get_credentials(owner)` + 유저별 챗ID 저장, send_message(text, chat_id)

## ⬜ Phase 6 — 학습 통합
- [ ] build_pattern_profile를 전 유저(all owner) 정기 실행 (background.py)

## ⬜ Phase 7 — 호스팅 (ngrok 탈피)
- [ ] Cloudflare Tunnel(임시) 또는 VPS 이전 + 쿠키 secure/도메인/env

---

## 이어서 작업하는 법 (새 세션에서)
1. 이 파일과 `plan_multiuser.md` 를 읽는다.
2. `git log --oneline -5` 로 마지막 커밋 확인.
3. 위 체크리스트에서 `[ ]` 인 첫 항목부터 진행.
4. 백엔드 가동: `uvicorn api.main:app --port 8000` / 프론트: `cd frontend && npm run dev`
5. 한 단계 끝낼 때마다 이 파일의 체크박스를 갱신하고 커밋한다.
