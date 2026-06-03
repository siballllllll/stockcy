# 스톡시 멀티유저 전환 구현 계획서

> 목표: "관리자(나)는 리딩방·AI 도구를 풀로 쓰고, 일반 유저는 자기 실매매만 하며 제한적으로 AI를 쓰되, 그들의 거래 데이터는 전부 AI 학습에 흡수된다."

작성일: 2026-06-03 / 대상 규모: 지인 소수(5~20명), 확장 가능 구조

---

## 0. 한눈에 보는 접근 권한 매트릭스

| 기능 | 일반 유저 | 관리자(나) |
|---|:---:|:---:|
| 로그인 / 내 계정 | ✅ | ✅ |
| 내 매수·매도 기록·조회 (무료 데이터 입력) | ✅ | ✅ |
| 리딩방 뷰 (리더 픽/패턴) | ❌ 아예 안 보임 | ✅ |
| AI 분석·시나리오 등 **비용 발생 기능 실행** | ❌ 평소 차단 → **승인받은 횟수만큼만** | ✅ 무제한 |
| AI 사용 **승인 요청** | ✅ 신청 가능 | — |
| 승인 / 부여 횟수 결정 | ❌ | ✅ |
| 위에서 생성된 결과 보기 | 👁️ 읽기 전용 | ✅ |
| 텔레그램 알림 | ✅ 공유봇 + 본인 챗ID | ✅ |
| 유저 사용량 조회 / 계정 on·off / 한도 설정 | ❌ | ✅ |
| (백그라운드) 전 유저 거래데이터 AI 학습 | 데이터 공급만 | 학습 결과 소비 |

**핵심 원칙**
1. `owner`는 **로그인 세션에서 강제** — 클라이언트가 보내는 파라미터를 절대 신뢰하지 않음. (현재 최대 취약점)
2. 비용 발생 기능(Gemini 호출)은 **기본 차단**. 유저가 **승인 요청** → 관리자가 **횟수를 부여**해야만 사용 가능. 호출 1건마다 잔여 횟수 차감 + 로깅.
3. 관리자가 **계정 활성/비활성 + 승인/부여 횟수**를 컨트롤. 잔여 0이면 다시 읽기 전용으로 복귀.

---

## 1. 현재 상태 (코드 실측)

| 항목 | 현황 | 멀티유저 영향 |
|---|---|---|
| 인증 | **없음.** owner는 그냥 API 파라미터 (`portfolio.py` `owner="USER"` 기본값) | 신규 구축 필요 (1순위) |
| admin 권한 | `admin.py`는 라우트 묶음일 뿐, 인증 0 | 게이트 필요 |
| DB | SQLite + WAL (`db.py:25`). `portfolio`/`trade_history`/`virtual_balances`에 `owner` 컬럼 존재 | 격리 토대 완비, 마이그레이션 거의 불필요 |
| 텔레그램 | `telegram_config(key,token,chat_id)` 단일 전역 설정. `_get_credentials()` → 전역 1개 | `key=owner`로 유저별 챗ID 확장 |
| AI 사용 로깅 | `ai_recommendations` 테이블에 호출 기록(시각/유형) | 여기에 `user` 컬럼 추가하면 사용량 측정 |
| 학습 | `build_pattern_profile(source)` — leading/personal/all 지원 (`ai.py:1472`) | `all`로 전 유저 통합 → 학습 자동 |

---

## 2. 단계별 구현 (의존 순서대로)

### Phase 1 — 인증 & 유저 계정 (모든 것의 전제)
- **`users` 테이블 신설**
  - `username`(PK), `password_hash`, `role`('admin'|'user'), `is_active`(0/1),
    `ai_credits`(INT, 기본 **0** = 평소 AI 차단), `telegram_chat_id`, `created_at`.
  - 최초 1명(=나)을 `role='admin'`으로 시드.
- **비밀번호 해싱**: `passlib[bcrypt]` (requirements 추가).
- **로그인 엔드포인트** `POST /api/auth/login` → JWT 발급(또는 서버 세션 쿠키).
  - 소수 인원이라 JWT(HttpOnly 쿠키) 추천 — 간단·무상태.
- **계정 생성 방식**: 관리자가 직접 생성하거나 **초대코드** 방식. (소수면 관리자 직접 생성이 가장 단순)
- **FastAPI 의존성** `get_current_user()` → 모든 보호 라우트에 주입.
- **🔑 owner 일원화**: `owner`를 클라가 보내던 곳 전부 → `current_user.username`에서 가져오도록 교체.
  - 대상: `portfolio.py`(load/save portfolio, save_trade_record), 거래내역 조회 등.
  - 이 작업 끝나면 "남이 owner 바꿔서 내 데이터 조회" 불가능.

### Phase 2 — 권한(역할) 게이트
- **`require_admin` 의존성** 신설 → 아래에 부착:
  - `admin.py` 전체 라우트
  - 리딩방 관련: `/leading-room-patterns`, `entry-timing?source=leading`, 패턴 리빌드(`ai.py:1472,1527`)
  - 비용 발생 트리거 중 "관리자 전용"으로 둘 것들
- **프론트(Next.js)**: 로그인 유저 role에 따라
  - 일반 유저: 리딩방/시나리오 관리 메뉴 **렌더 자체를 제거** (숨김).
  - 관리자: 풀 메뉴.
  - ※ 프론트 숨김은 UX용일 뿐, **실제 차단은 반드시 백엔드 `require_admin`** 으로 (프론트만 숨기면 API 직접 호출로 뚫림).

### Phase 3 — 데이터 격리 검증
- 모든 portfolio/trade 쿼리가 `current_user` 기준인지 점검.
- 관리자만 `owner=다른유저` 조회 가능(사용량/디버깅용), 일반 유저는 본인 고정.
- 회귀 테스트: 유저 A 토큰으로 유저 B 데이터 접근 → 403/빈 결과 확인.

### Phase 4 — AI 사용 승인제 + 사용량 측정 + 계정 컨트롤 (★ 신규 요구)

**모델: 승인제(grant 기반).** 평소엔 `ai_credits=0` → AI 완전 차단(읽기 전용). 유저가 신청하면 내가 횟수를 부여하고, 그만큼만 쓰고 소진되면 다시 차단.

- **`ai_access_requests` 테이블 신설**
  - `id`, `user`, `requested_at`, `reason`(선택), `status`('pending'|'approved'|'denied'),
    `granted_count`(관리자가 부여한 횟수), `decided_at`, `decided_by`.
- **`usage_log` 테이블 신설**
  - `id`, `user`, `feature`('ai_us_analysis'|'ai_kr_analysis'|'scenario'|...), `called_at`.
- **유저 흐름**
  1. 평소 AI 버튼은 비활성/잠금 표시 + "AI 사용 신청" 버튼.
  2. 신청 → `ai_access_requests`에 `pending` 1건 생성. (관리자에게 텔레그램 알림 가능)
  3. 승인 전까지 실행 불가.
- **관리자 흐름** (전부 `require_admin`)
  - `GET /api/admin/ai-requests?status=pending` — 대기 중 신청 목록.
  - `POST /api/admin/ai-requests/{id}/approve` — body에 `count`(부여 횟수). → 해당 유저 `ai_credits += count`, status=approved.
  - `POST /api/admin/ai-requests/{id}/deny` — 거부.
- **호출 시 차감 의존성** `consume_ai_credit()`:
  - 비용 기능 호출 직전 → `ai_credits <= 0` 이면 `403 (승인 필요)`.
  - 통과 시 `ai_credits -= 1` + `usage_log` 1줄 기록.
  - 관리자는 면제(무제한).
- **계정 컨트롤 API** (전부 `require_admin`)
  - `GET /api/admin/users` — 유저 목록 + 잔여 ai_credits + 누적 사용수 + is_active.
  - `POST /api/admin/users/{username}/toggle` — 활성/비활성 (★ 사이트 사용 on/off).
  - `POST /api/admin/users/{username}/credits` — 횟수 직접 가감(신청 없이 부여/회수).
- **비활성 처리**: `is_active=0` → 로그인 거부 + 기존 토큰도 `get_current_user`에서 차단.
- **프론트**
  - 유저 화면: AI 버튼 잠금 + 신청 버튼 + 잔여 횟수 표시.
  - 관리자 화면: ① 대기 신청 목록(승인 시 횟수 입력) ② 유저 테이블(이름/잔여/누적/[차단]/[횟수 가감]).

### Phase 5 — 텔레그램 유저별 알림 (방식 A: 공유봇 + 본인 챗ID)
- **봇은 내 봇 1개 유지.** 유저는 본인 챗ID만 등록.
- **챗ID 확보 흐름**:
  1. 유저가 텔레그램에서 내 봇에게 `/start` 전송.
  2. (선택) `getUpdates` 폴링 또는 webhook로 chat_id 자동 캡처 → 계정에 매핑.
  3. 또는 가장 단순하게: 봇이 안내한 chat_id를 유저가 설정 화면에 붙여넣기.
- **저장**: 기존 `telegram_config`를 `key=username`으로 활용하거나 `users.telegram_chat_id`에 저장.
- **발송 함수 시그니처 변경**: `send_message(text, chat_id)` (또는 owner) — 전역 단일 → 대상 지정.
  - 영향: `telegram_bot.py`, `watchlist_alerts.py`, `daily_brief.py`, `research_watcher.py`.
- **알림 디스패치**: "이 알림은 누구 것" → 해당 유저 챗ID로. (개인 가격알림 = 본인에게만)

### Phase 6 — 학습 통합 (대부분 이미 됨)
- `build_pattern_profile`를 **전 유저(all owner) 통합**으로 정기 실행.
  - 승률 좋은 케이스 / 특정 이슈+패턴 조합이 학습 풀에 자동 유입.
- 학습 결과(리딩방 패턴)는 **관리자만** 소비 (Phase 2 게이트 적용).
- 배치: 기존 `api/background.py` 스케줄러에 야간 1회 리빌드 추가.

### Phase 7 — 호스팅 (나중에 결정, 보류)
- 현재 "내 PC + ngrok(5일째)"는 외부 유저에게 부적합.
- 옵션 비교는 별도 논의 (상시 서버 + 고정 도메인 + HTTPS 필요).

---

## 3. 신규/변경 산출물 요약

**DB 테이블 신설**: `users`, `usage_log`
**DB 컬럼 추가**: (선택) `telegram_config`를 유저별로 사용
**백엔드 신규**: `api/routers/auth.py`(로그인), `api/auth_deps.py`(get_current_user/require_admin/enforce_ai_quota), `api/routers/admin.py`에 유저관리 엔드포인트 추가
**백엔드 변경**: `portfolio.py`(owner 일원화), `ai.py`(계측+게이트), `telegram_bot.py`(대상 지정 발송)
**프론트 신규**: 로그인 페이지, 관리자 유저관리 화면, role 기반 메뉴 가드
**의존성 추가**: `passlib[bcrypt]`, `python-jose`(JWT) 또는 세션 라이브러리

---

## 4. 리스크 / 결정 필요 사항

- **법적 한 줄(확정)**: ✅ 가입 약관/개인정보처리방침에 "거래 데이터를 서비스 개선·AI 학습에 활용" 고지 포함. (한국 PIPA 대응)
- **계정 생성(확정)**: ✅ 관리자가 직접 생성.
- **AI 사용(확정)**: ✅ 승인제. 평소 차단, 신청→관리자 승인 시 부여 횟수만큼만.
- **JWT vs 세션쿠키**: 소수면 JWT(HttpOnly) 추천. 즉시 강제 로그아웃이 중요하면 서버세션. (미결)
- **승인 시 기본 부여 횟수**: 승인 화면에서 매번 입력. 편의용 기본값(예: 5회) 둘지? (미결, 선택)
- **SQLite 유지**: 5~20명이면 WAL로 충분. 수백 명 가면 Postgres 검토.

---

## 5. 추천 진행 순서

1. **Phase 1** (인증 + owner 일원화) — 보안상 가장 시급, 나머지의 전제.
2. **Phase 2 + 3** (게이트 + 격리) — 함께.
3. **Phase 4** (사용량/계정 컨트롤) — 비용 방어.
4. **Phase 5** (텔레그램 유저별).
5. **Phase 6** (학습 통합) — 마무리, 대부분 기존 코드 재사용.
6. **Phase 7** (호스팅) — 별도 논의.
