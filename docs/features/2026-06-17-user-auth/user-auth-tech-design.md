---
slug: user-auth
source: user-auth-requirements.md
north_star: docs/architecture/user-ai-persona-north-star.md
---

# 기술설계: 유저 인증 (최소)

> 입력 PRD: `user-auth-requirements.md`. 북극성: `docs/architecture/user-ai-persona-north-star.md`. 다음 단계: `/write-plan`.

## 1. 아키텍처 개요

백엔드(FastAPI)에 **이메일+비번 인증 + JWT(stateless)** 를 추가한다. 비번은 bcrypt 해시, 토큰은 PyJWT로 발급/검증. `get_current_user` FastAPI 의존성이 `Authorization: Bearer <jwt>`를 검증해 보호 라우트에 유저를 주입한다. 스키마에 `users` 테이블 + `posts.author_user_id`·`reactions.user_id`(NULL 허용 FK)를 더한다(북극성 §4 이음새). Flutter는 가입/로그인 화면 + SharedPreferences 토큰 + `ApiService`가 보호 요청에 Authorization 헤더를 첨부한다.

순수 로직(해시/JWT)은 `auth.py`로 분리해 단위 테스트하고, 인증 의존성·라우트는 `main.py`가 오케스트레이션한다.

## 2. 영향받는 컴포넌트

| 파일 | 작업 | 책임 |
|---|---|---|
| `comea_backend/auth.py` | **생성** | `hash_password`/`verify_password`(bcrypt), `create_token`/`decode_token`(PyJWT), `get_current_user`(Depends, 401). JWT_SECRET/만료 env. |
| `comea_backend/database.py` | **수정** | `UserModel`(email unique, password_hash, created_at) 신설 + `PostModel.author_user_id`·`ReactionModel.user_id`(NULL FK) 추가. |
| `comea_backend/main.py` | **수정** | `POST /api/auth/signup`·`/login` 추가, `create_post`·`react_to_post`에 `Depends(get_current_user)` + author/user 연결. |
| `comea_backend/migrations/002_add_users_and_authorship.sql` | **생성** | 운영 DB용 멱등 SQL(users 생성 + author_user_id/user_id 컬럼). |
| `comea_backend/tests/conftest.py` | **수정** | 인증된 TestClient 픽스처(가입+토큰 헤더 주입) + JWT_SECRET 테스트 env. |
| `comea_backend/tests/*` (기존) | **수정** | 보호된 write 호출하는 기존 테스트(create_post/reaction/lock_and_scale)를 인증 클라이언트로 전환. |
| `comea_backend/tests/test_auth.py` | **생성** | 해시/JWT 단위 + signup/login/401 통합. |
| `comea/lib/services/api.dart` | **수정** | `signup`/`login`(토큰 반환), 토큰 보관, 보호 요청에 Authorization 헤더, `logout`. |
| `comea/lib/screens/login_screen.dart`·`signup_screen.dart` | **생성** | 로그인/가입 화면. |
| `comea/lib/main.dart` | **수정** | 토큰 유무로 로그인/홈 분기. |
| `comea/test/*` | **생성/수정** | ApiService 인증 메서드 MockClient 테스트 + 로그인 화면 위젯 테스트. |
| `pyproject.toml` / `comea/pubspec.yaml` | **수정** | `pyjwt`·`bcrypt` / `shared_preferences` 추가. |

## 3. 데이터 모델 변경

```
users
  id            SERIAL PK
  email         VARCHAR UNIQUE NOT NULL
  password_hash VARCHAR NOT NULL
  created_at    TIMESTAMP NOT NULL DEFAULT now()

posts.author_user_id   INTEGER NULL REFERENCES users(id)   -- 신규 추가, 익명 호환 NULL
reactions.user_id      INTEGER NULL REFERENCES users(id)   -- 신규 추가, 익명 호환 NULL
```

응답에 `password_hash`는 **절대 노출 안 함**. 토큰 payload는 최소(user id, exp).

## 4. 외부 인터페이스 (API)

- `POST /api/auth/signup` `{email, password}` → 201 + `{token}` (가입 즉시 자동 로그인). 중복 이메일 409.
- `POST /api/auth/login` `{email, password}` → 200 `{token}` / 401(불일치).
- `POST /api/posts` (보호): `Authorization: Bearer` 필수, 없으면 401. 성공 시 `author_user_id`=토큰 유저.
- `POST /api/posts/{id}/reaction` (보호): 동일. `user_id`=토큰 유저.
- `GET /api/posts`: 비보호 유지(읽기는 이번 범위 비강제).

## 5. 핵심 결정 (대안 비교)

- **D1. PyJWT + bcrypt** (대안: passlib / authlib / fastapi-users). 경량 직접 채택 — 의존성 최소·통제 쉬움. fastapi-users는 과한 추상화.
- **D2. `get_current_user` 의존성으로 라우트 보호** (대안: 미들웨어 전역). 의존성 채택 — 보호 라우트만 선택 적용(GET 열어둠), 테스트 주입 쉬움.
- **D3. 가입 시 토큰 즉시 발급(자동 로그인)** (대안: 가입 후 별도 로그인). 자동 로그인 채택 — UX 매끄럽고 한 번 왕복 절약.
- **D4. Flutter 토큰 = SharedPreferences + ApiService가 보관·주입** (대안: secure storage / 상태관리 패키지). SharedPreferences 채택(결정됨) — MVP 단순.
- **D5. 기존 익명 데이터 = NULL 유지 + 신규부터 author 채움** (북극성 §4-2). 소급 마이그레이션 안 함.
- **D6. 기존 백엔드 테스트는 인증 클라이언트로 전환** — write 보호로 기존 무인증 테스트가 401나므로, conftest에 인증 픽스처 추가 후 해당 테스트들 갱신(회귀 유지).

## 6. 예비 위험 (→ 구현계획서 §2로 매핑)

- **breaking**: `create_post`·`react_to_post`에 인증 강제 → **기존 무인증 테스트/클라이언트가 401**. (완화: conftest 인증 픽스처 + 기존 테스트 일괄 전환, 같은 슬라이스에서 처리. Flutter도 헤더 첨부로 전환.)
- **breaking**: 스키마에 users 테이블 + FK 컬럼 → 운영 DB는 `create_all` 미반영 가능. (완화: `migrations/002_*.sql` 멱등 SQL + 런북, 북극성 §4-2.)
- **side-effect/security**: 비번 해시·JWT 시크릿 취급. (완화: bcrypt 해시·평문 미저장·미로그, JWT_SECRET은 .env, 토큰 만료. 시크릿 누락 시 기동 실패하도록.)

## 7. 테스트 전략

- **순수 단위**(`test_auth.py`): `hash_password`/`verify_password` 라운드트립, 틀린 비번 거부, `create_token`/`decode_token` 라운드트립·만료/위조 거부.
- **통합**(TestClient + sqlite): signup(중복 409), login(성공 토큰/실패 401), 보호 라우트 무토큰 401·유토큰 author 연결. conftest에 `auth_client`(가입+헤더) 픽스처.
- **기존 테스트 전환**: create_post/reaction/lock_and_scale을 `auth_client` 사용으로 갱신(회귀 green 유지).
- **Flutter**: ApiService signup/login MockClient 단위 + 로그인 화면 위젯(입력→login 호출→토큰 저장 경로) 테스트.
- **수동**: flutter run 으로 가입→로그인→글작성→로그아웃 e2e.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 11:50] [개발방향-수정]
- **id**: CH-20260617-002
- **이유**: 신규 기술설계 (유저 인증 최소) — requirements 승인 후 작성
- **무엇이**: user-auth-tech-design.md 전체 (§1~7, 결정 D1~D6)
- **영향범위**: comea_backend(auth/JWT/스키마/기존 테스트 전환)·migrations/002·comea(Flutter 로그인 UI)·신규 의존성(pyjwt·bcrypt·shared_preferences). 북극성 §4 정합. verifying-spec 4축 green.
- **연관 항목**: CH-20260617-001
