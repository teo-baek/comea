---
commit_policy: per-task
---

# 유저 인증 (최소) 구현계획서

> **다음 단계 안내**: 이 계획을 task-by-task 로 실행하려면 `js-super-sub-driven` (보조 에이전트 강제 모드, 권장) 또는 `executing-plans` (인라인 모드) 를 사용하세요.

**Goal:** 이메일+비번 가입/로그인/로그아웃(JWT) + 글·반응을 로그인 유저로 보호·연결. `users` 테이블 + `author_user_id`/`user_id` 이음새(북극성 §4). Flutter 로그인 흐름.

**Architecture:** 순수 인증 로직(bcrypt 해시 + PyJWT)을 `auth.py`로 분리(단위 테스트). `get_current_user` 의존성이 `Authorization: Bearer`를 검증해 보호 라우트에 유저 주입. Flutter는 SharedPreferences 토큰 + ApiService 헤더 주입.

**Tech Stack:** FastAPI, SQLAlchemy, PyJWT, bcrypt / Flutter, http, shared_preferences. 백엔드 테스트 SQLite, Flutter MockClient.

**Spec inputs:**
- `user-auth-requirements.md` — FR-1~6, AC-1~7
- `user-auth-tech-design.md` — D1(PyJWT+bcrypt) D2(get_current_user) D3(자동로그인) D4(SharedPreferences) D5(NULL 호환) D6(기존 테스트 전환)
- `docs/architecture/user-ai-persona-north-star.md` — §3 데이터모델, §4 전방호환

---

## 1. 단계별 작업

### Task 1: 인증 순수 로직 (`auth.py`) + 유닛 테스트

**Files:**
- Modify: `pyproject.toml` (uv add)
- Create: `ulssu_backend/auth.py`
- Test: `ulssu_backend/tests/test_auth.py`

**Model**: sonnet

- [ ] **Step 1: dev/런타임 의존성 추가**

Run: `uv add pyjwt bcrypt`
Expected: `pyproject.toml`에 `pyjwt`, `bcrypt` 추가 + `uv.lock` 갱신.

- [ ] **Step 2: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_auth.py`):
```python
import jwt
import pytest

from auth import create_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"            # 평문 아님
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False


def test_token_roundtrip():
    token = create_token(42)
    assert decode_token(token) == 42


def test_decode_forged_token_raises():
    bad = jwt.encode({"sub": "1"}, "WRONG-SECRET", algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        decode_token(bad)
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'auth'`

- [ ] **Step 4: 순수 로직 구현**

**수정 후** (new file: `ulssu_backend/auth.py`):
```python
"""인증 순수 로직: 비밀번호 해시(bcrypt) + JWT(PyJWT). get_current_user 는 Task 3에서 추가."""
import os
import datetime as dt

import bcrypt
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7  # 7일


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> int:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return int(payload["sub"])
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_auth.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml uv.lock ulssu_backend/auth.py ulssu_backend/tests/test_auth.py
git commit -m "feat(backend): 인증 순수 로직(bcrypt 해시 + PyJWT) + 유닛테스트"
```

---

### Task 2: 스키마 — `users` + author/user 이음새 + 마이그레이션

**Files:**
- Modify: `ulssu_backend/database.py:19-26` (PostModel), `ulssu_backend/database.py:37-44` (ReactionModel), `ulssu_backend/database.py:47` (get_db 위 UserModel 추가)
- Create: `ulssu_backend/migrations/002_add_users_and_authorship.sql`
- Test: `ulssu_backend/tests/test_user_schema.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_user_schema.py`):
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import PostModel, ReactionModel, UserModel


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_user_and_authorship_columns():
    db = _session()
    try:
        user = UserModel(email="a@b.com", password_hash="x")
        db.add(user)
        db.commit()
        db.refresh(user)

        post = PostModel(content="글", score=70, author_user_id=user.id)
        db.add(post)
        db.commit()
        db.refresh(post)
        assert post.author_user_id == user.id

        r = ReactionModel(post_id=post.id, reaction_type="like", user_id=user.id)
        db.add(r)
        db.commit()
        assert r.user_id == user.id

        # 익명 호환: author/user NULL 허용
        anon = PostModel(content="익명", score=40)
        db.add(anon)
        db.commit()
        db.refresh(anon)
        assert anon.author_user_id is None
    finally:
        db.close()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_user_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'UserModel'`

- [ ] **Step 3: PostModel에 author_user_id 추가**

**원본** (`ulssu_backend/database.py:19-26`):
```python
class PostModel(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    score = Column(Integer, nullable=False)
    is_locked = Column(Boolean, nullable=False, default=False, server_default="false")
    comments = relationship("CommentModel", back_populates="post", cascade="all, delete-orphan")
    # 주의: reactions 관계는 의도적으로 노출하지 않음(직렬화 시 카운트 유출 방지, FR-3).
```

**수정 후**:
```python
class PostModel(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    score = Column(Integer, nullable=False)
    is_locked = Column(Boolean, nullable=False, default=False, server_default="false")
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 익명 호환 NULL (북극성 §4)
    comments = relationship("CommentModel", back_populates="post", cascade="all, delete-orphan")
    # 주의: reactions 관계는 의도적으로 노출하지 않음(직렬화 시 카운트 유출 방지, FR-3).
```

- [ ] **Step 4: ReactionModel에 user_id 추가**

**원본** (`ulssu_backend/database.py:37-44`):
```python
class ReactionModel(Base):
    # 좋아요/싫어요를 카운터가 아니라 개별 레코드(스택)로 적재 → 동시 클릭 경합 제거(FR-9).
    # 총 반응 수는 COUNT 집계. reaction_type 은 B2B 분석용 저장(수식은 총량만 사용).
    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    reaction_type = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
```

**수정 후**:
```python
class ReactionModel(Base):
    # 좋아요/싫어요를 카운터가 아니라 개별 레코드(스택)로 적재 → 동시 클릭 경합 제거(FR-9).
    # 총 반응 수는 COUNT 집계. reaction_type 은 B2B 분석용 저장(수식은 총량만 사용).
    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    reaction_type = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 누가 눌렀나, 익명 호환 NULL (북극성 §4)
```

- [ ] **Step 5: UserModel 추가**

**원본** (`ulssu_backend/database.py:46-47`):
```python

def get_db():
```

**수정 후**:
```python

class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


def get_db():
```

- [ ] **Step 6: 운영 DB 마이그레이션 SQL 작성**

**수정 후** (new file: `ulssu_backend/migrations/002_add_users_and_authorship.sql`):
```sql
-- 002_add_users_and_authorship.sql
-- user-auth 슬라이스 스키마를 기존 운영 PostgreSQL 에 반영한다. 멱등.
-- 적용:  psql "$DATABASE_URL" -f migrations/002_add_users_and_authorship.sql

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE posts     ADD COLUMN IF NOT EXISTS author_user_id INTEGER REFERENCES users(id);
ALTER TABLE reactions ADD COLUMN IF NOT EXISTS user_id        INTEGER REFERENCES users(id);

-- 롤백 (down):
--   ALTER TABLE reactions DROP COLUMN IF EXISTS user_id;
--   ALTER TABLE posts     DROP COLUMN IF EXISTS author_user_id;
--   DROP TABLE IF EXISTS users;
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_user_schema.py -v`
Expected: PASS (1 passed)

- [ ] **Step 8: 커밋**

```bash
git add ulssu_backend/database.py ulssu_backend/migrations/002_add_users_and_authorship.sql ulssu_backend/tests/test_user_schema.py
git commit -m "feat(backend): users 테이블 + author_user_id/user_id 이음새 + 마이그레이션"
```

---

### Task 3: `get_current_user` + signup/login 엔드포인트 + conftest 인증 픽스처

**Files:**
- Modify: `ulssu_backend/auth.py` (get_current_user 추가)
- Modify: `ulssu_backend/main.py:37-42` (요청 모델), `ulssu_backend/main.py:115` 앞(인증 라우트)
- Modify: `ulssu_backend/tests/conftest.py` (JWT_SECRET env + auth_client 픽스처)
- Test: `ulssu_backend/tests/test_auth_api.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 통합 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_auth_api.py`):
```python
def test_signup_returns_token(client):
    resp = client.post("/api/auth/signup", json={"email": "u1@x.com", "password": "pw123456"})
    assert resp.status_code == 201
    assert "token" in resp.json()


def test_duplicate_email_rejected(client):
    client.post("/api/auth/signup", json={"email": "dup@x.com", "password": "pw123456"})
    resp = client.post("/api/auth/signup", json={"email": "dup@x.com", "password": "pw123456"})
    assert resp.status_code == 409


def test_login_success_and_failure(client):
    client.post("/api/auth/signup", json={"email": "u2@x.com", "password": "pw123456"})
    ok = client.post("/api/auth/login", json={"email": "u2@x.com", "password": "pw123456"})
    assert ok.status_code == 200 and "token" in ok.json()
    bad = client.post("/api/auth/login", json={"email": "u2@x.com", "password": "WRONG"})
    assert bad.status_code == 401
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_auth_api.py -v`
Expected: FAIL — `404` (auth 라우트 미존재)

- [ ] **Step 3: auth.py에 get_current_user 추가**

**원본** (`ulssu_backend/auth.py:1`):
```python
"""인증 순수 로직: 비밀번호 해시(bcrypt) + JWT(PyJWT). get_current_user 는 Task 3에서 추가."""
import os
import datetime as dt

import bcrypt
import jwt
```

**수정 후**:
```python
"""인증 로직: 비밀번호 해시(bcrypt) + JWT(PyJWT) + get_current_user 의존성."""
import os
import datetime as dt

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db, UserModel
```

- [ ] **Step 4: auth.py 끝에 get_current_user 추가**

**원본** (`ulssu_backend/auth.py:decode_token 끝`):
```python
def decode_token(token: str) -> int:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return int(payload["sub"])
```

**수정 후**:
```python
def decode_token(token: str) -> int:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return int(payload["sub"])


def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> UserModel:
    """Authorization: Bearer <jwt> 검증 → UserModel 반환. 실패 시 401."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[len("Bearer "):]
    try:
        user_id = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid token")
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    return user
```

- [ ] **Step 5: main.py 요청 모델 + import 보강**

**원본** (`ulssu_backend/main.py:37-42`):
```python
class PostRequest(BaseModel):
    content: str


class ReactionRequest(BaseModel):
    reaction: str  # "like" | "dislike"
```

**수정 후**:
```python
class PostRequest(BaseModel):
    content: str


class ReactionRequest(BaseModel):
    reaction: str  # "like" | "dislike"


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str
```

- [ ] **Step 6: main.py import에 auth + UserModel 추가**

**원본** (`ulssu_backend/main.py:15`):
```python
from database import get_db, PostModel, CommentModel, ReactionModel
```

**수정 후**:
```python
from database import get_db, PostModel, CommentModel, ReactionModel, UserModel
from auth import hash_password, verify_password, create_token, get_current_user
```

- [ ] **Step 7: signup/login 라우트 추가 (GET /api/posts 앞에)**

**원본** (`ulssu_backend/main.py:115-116`):
```python
# 📌 1. 과거에 저장된 모든 고민 글 + AI 댓글 리스트를 역순(최신순)으로 반환하는 API
@app.get("/api/posts")
```

**수정 후**:
```python
# 📌 0. 인증 — 가입(자동 로그인) / 로그인
@app.post("/api/auth/signup", status_code=201)
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    exists = db.query(UserModel).filter(UserModel.email == request.email).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    user = UserModel(email=request.email, password_hash=hash_password(request.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id)}


@app.post("/api/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == request.email).first()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return {"token": create_token(user.id)}


# 📌 1. 과거에 저장된 모든 고민 글 + AI 댓글 리스트를 역순(최신순)으로 반환하는 API
@app.get("/api/posts")
```

- [ ] **Step 8: conftest에 JWT_SECRET env + auth_client 픽스처 추가**

**원본** (`ulssu_backend/tests/conftest.py:1-5`):
```python
import os

# main/database import 전에 반드시 먼저 세팅 (모듈 로드 시 엔진 생성 + create_all 실행됨)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["OPENAI_API_KEY"] = "test-dummy-key"
```

**수정 후**:
```python
import os

# main/database import 전에 반드시 먼저 세팅 (모듈 로드 시 엔진 생성 + create_all 실행됨)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["OPENAI_API_KEY"] = "test-dummy-key"
os.environ["JWT_SECRET"] = "test-secret"
```

- [ ] **Step 9: conftest 끝에 auth_client 픽스처 추가**

**원본** (`ulssu_backend/tests/conftest.py` 끝 — `client` 픽스처의 마지막 두 줄):
```python
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
    population.set_current_population(0)
```

**수정 후**:
```python
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
    population.set_current_population(0)


@pytest.fixture
def auth_client(client):
    """가입해서 토큰을 받은 뒤 Authorization 헤더를 단 TestClient."""
    resp = client.post("/api/auth/signup", json={"email": "tester@x.com", "password": "pw123456"})
    token = resp.json()["token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
```

- [ ] **Step 10: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_auth_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 11: 커밋**

```bash
git add ulssu_backend/auth.py ulssu_backend/main.py ulssu_backend/tests/conftest.py ulssu_backend/tests/test_auth_api.py
git commit -m "feat(backend): signup/login 엔드포인트 + get_current_user + conftest 인증 픽스처"
```

---

### Task 4: 글·반응 라우트 인증 보호 + author 연결 + 기존 테스트 전환

**Files:**
- Modify: `ulssu_backend/main.py:122-148` (create_post), `ulssu_backend/main.py:152-181` (react_to_post)
- Modify: `ulssu_backend/tests/test_create_post.py`, `test_reaction_api.py`, `test_lock_and_scale.py` (auth_client로 전환)

**Model**: sonnet

- [ ] **Step 1: create_post 보호 + author 연결**

**원본** (`ulssu_backend/main.py:122-135`):
```python
@app.post("/api/posts")
async def create_post(request: PostRequest, db: Session = Depends(get_db)):
    user_post = request.content

    score = evaluate_post_quality(user_post)
    base_limit = compute_base_limit(score)
    # 반응 0 시점이므로 Final == Base. 초기 생성도 동일 수식 사용(FR-11). 잡담도 최소 10개(FR-1).
    final_limit = compute_final_limit(base_limit, 0, get_current_population())

    # 1. 원문 글 저장하여 고유 ID 확보
    db_post = PostModel(content=user_post, score=score)
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
```

**수정 후**:
```python
@app.post("/api/posts")
async def create_post(
    request: PostRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),  # 로그인 필수 (FR-4)
):
    user_post = request.content

    score = evaluate_post_quality(user_post)
    base_limit = compute_base_limit(score)
    # 반응 0 시점이므로 Final == Base. 초기 생성도 동일 수식 사용(FR-11). 잡담도 최소 10개(FR-1).
    final_limit = compute_final_limit(base_limit, 0, get_current_population())

    # 1. 원문 글 저장하여 고유 ID 확보 (작성자 연결 — 북극성 §4)
    db_post = PostModel(content=user_post, score=score, author_user_id=current_user.id)
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
```

- [ ] **Step 2: react_to_post 보호 + user 연결**

**원본** (`ulssu_backend/main.py:152-161`):
```python
@app.post("/api/posts/{post_id}/reaction")
def react_to_post(post_id: int, request: ReactionRequest, db: Session = Depends(get_db)):
    db_post = db.query(PostModel).filter(PostModel.id == post_id).first()
    if db_post is None:
        raise HTTPException(status_code=404, detail="post not found")
    if request.reaction not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="reaction must be 'like' or 'dislike'")

    # 카운터 증분이 아니라 개별 레코드(스택)로 적재 → 동시 클릭 경합 제거(FR-9)
    db.add(ReactionModel(post_id=post_id, reaction_type=request.reaction))
```

**수정 후**:
```python
@app.post("/api/posts/{post_id}/reaction")
def react_to_post(
    post_id: int,
    request: ReactionRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),  # 로그인 필수 (FR-4)
):
    db_post = db.query(PostModel).filter(PostModel.id == post_id).first()
    if db_post is None:
        raise HTTPException(status_code=404, detail="post not found")
    if request.reaction not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="reaction must be 'like' or 'dislike'")

    # 카운터 증분이 아니라 개별 레코드(스택)로 적재 → 동시 클릭 경합 제거(FR-9). 반응자 연결(북극성 §4).
    db.add(ReactionModel(post_id=post_id, reaction_type=request.reaction, user_id=current_user.id))
```

- [ ] **Step 3: 인증 401 회귀 테스트 추가 (test_auth_api.py에 append)**

**원본** (`ulssu_backend/tests/test_auth_api.py` 끝):
```python
    bad = client.post("/api/auth/login", json={"email": "u2@x.com", "password": "WRONG"})
    assert bad.status_code == 401
```

**수정 후**:
```python
    bad = client.post("/api/auth/login", json={"email": "u2@x.com", "password": "WRONG"})
    assert bad.status_code == 401


def test_protected_write_requires_token(client):
    # 토큰 없이 글 작성/반응 → 401 (FR-4)
    assert client.post("/api/posts", json={"content": "x"}).status_code == 401
    assert client.post("/api/posts/1/reaction", json={"reaction": "like"}).status_code == 401


def test_authed_post_sets_author(auth_client, monkeypatch):
    import main
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 40)
    body = auth_client.post("/api/posts", json={"content": "내 글"}).json()
    assert body["author_user_id"] is not None  # 작성자 연결됨 (AC-4)
```

- [ ] **Step 4: 기존 통합 테스트를 auth_client로 전환**

기존 `test_create_post.py` / `test_reaction_api.py` / `test_lock_and_scale.py`는 `client` 픽스처로 보호 라우트(POST)를 호출하므로 이제 401이 난다. **각 파일에서 보호 POST를 호출하는 테스트 함수의 픽스처 인자를 `client` → `auth_client`로 바꾼다.** (GET만 쓰는 test_smoke는 그대로.)

예시 — `test_create_post.py`의 각 테스트 시그니처:

**원본** (`ulssu_backend/tests/test_create_post.py` — 함수 시그니처들):
```python
def test_create_post_chitchat_still_gets_ten_comments(client, monkeypatch):
```

**수정 후**:
```python
def test_create_post_chitchat_still_gets_ten_comments(auth_client, monkeypatch):
```

> 동일 규칙으로 `test_create_post.py`(5개 함수), `test_reaction_api.py`(3개 함수의 `client`→`auth_client`; `_create` 헬퍼 인자도), `test_lock_and_scale.py`(3개 함수의 `client`→`auth_client`)의 **`client` 파라미터·본문 내 `client.` 호출을 모두 `auth_client`로 치환**한다. (본문에서 `client.post(...)`로 보호 라우트를 호출하던 부분이 토큰 헤더를 갖게 됨.)

- [ ] **Step 5: 전체 백엔드 테스트 실행**

Run: `cd ulssu_backend && uv run pytest -v`
Expected: PASS (전체 green — 신규 auth + 전환된 기존 테스트)

- [ ] **Step 6: 커밋**

```bash
git add ulssu_backend/main.py ulssu_backend/tests/test_create_post.py ulssu_backend/tests/test_reaction_api.py ulssu_backend/tests/test_lock_and_scale.py ulssu_backend/tests/test_auth_api.py
git commit -m "feat(backend): 글·반응 라우트 로그인 보호 + 작성자 연결 + 기존 테스트 인증 전환"
```

---

### Task 5: Flutter ApiService 인증 (signup/login/logout + 토큰 주입)

**Files:**
- Modify: `ulssu/pubspec.yaml` (shared_preferences), `ulssu/lib/services/api.dart`
- Test: `ulssu/test/services/api_auth_test.dart`

**Model**: sonnet

- [ ] **Step 1: shared_preferences 추가**

Run: `cd ulssu && flutter pub add shared_preferences`
Expected: `pubspec.yaml` dependencies에 `shared_preferences` 추가.

- [ ] **Step 2: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu/test/services/api_auth_test.dart`):
```dart
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ulssu/services/api.dart';

void main() {
  test('login: 토큰을 반환하고 ApiService에 보관된다', () async {
    final mock = MockClient((req) async {
      expect(req.url.path, '/api/auth/login');
      return http.Response(jsonEncode({'token': 'T123'}), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    });
    final api = ApiService(client: mock);

    final token = await api.login('a@b.com', 'pw');

    expect(token, 'T123');
    expect(api.token, 'T123');
  });

  test('보호 요청에 Authorization 헤더가 붙는다', () async {
    String? seen;
    final mock = MockClient((req) async {
      seen = req.headers['Authorization'];
      return http.Response(jsonEncode({'id': 1, 'comments': []}), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    });
    final api = ApiService(client: mock)..token = 'T999';

    await api.createPost('hi');

    expect(seen, 'Bearer T999');
  });
}
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd ulssu && flutter test test/services/api_auth_test.dart`
Expected: FAIL — `login`/`token` 미존재로 컴파일 실패

- [ ] **Step 4: ApiService에 인증 추가**

**원본** (`ulssu/lib/services/api.dart:1-31`):
```dart
import 'dart:convert';

import 'package:http/http.dart' as http;

/// ulssu 백엔드 HTTP 호출을 한곳에 모은 서비스.
/// baseUrl 단일화 + http.Client 주입(테스트 시 MockClient 사용).
class ApiService {
  static const String baseUrl = 'http://172.28.0.1:8000/api';

  final http.Client _client;

  ApiService({http.Client? client}) : _client = client ?? http.Client();

  Future<List<Map<String, dynamic>>> getPosts() async {
    final resp = await _client.get(Uri.parse('$baseUrl/posts'));
    if (resp.statusCode != 200) {
      throw Exception('글 목록을 불러오지 못했습니다 (${resp.statusCode})');
    }
    final List<dynamic> data = jsonDecode(utf8.decode(resp.bodyBytes));
    return List<Map<String, dynamic>>.from(data);
  }

  Future<Map<String, dynamic>> createPost(String content) async {
    final resp = await _client.post(
      Uri.parse('$baseUrl/posts'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'content': content}),
    );
    if (resp.statusCode != 200) {
      throw Exception('글 등록에 실패했습니다 (${resp.statusCode})');
    }
    return Map<String, dynamic>.from(jsonDecode(utf8.decode(resp.bodyBytes)));
  }
```

**수정 후**:
```dart
import 'dart:convert';

import 'package:http/http.dart' as http;

/// ulssu 백엔드 HTTP 호출을 한곳에 모은 서비스.
/// baseUrl 단일화 + http.Client 주입(테스트 시 MockClient 사용).
class ApiService {
  static const String baseUrl = 'http://172.28.0.1:8000/api';

  final http.Client _client;
  String? token; // 로그인 후 JWT (보호 요청에 첨부)

  ApiService({http.Client? client}) : _client = client ?? http.Client();

  Map<String, String> _headers({bool auth = false}) {
    final h = {'Content-Type': 'application/json'};
    if (auth && token != null) h['Authorization'] = 'Bearer $token';
    return h;
  }

  Future<String> signup(String email, String password) async {
    final resp = await _client.post(
      Uri.parse('$baseUrl/auth/signup'),
      headers: _headers(),
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (resp.statusCode != 201) {
      throw Exception('가입에 실패했습니다 (${resp.statusCode})');
    }
    token = Map<String, dynamic>.from(jsonDecode(utf8.decode(resp.bodyBytes)))['token'] as String;
    return token!;
  }

  Future<String> login(String email, String password) async {
    final resp = await _client.post(
      Uri.parse('$baseUrl/auth/login'),
      headers: _headers(),
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (resp.statusCode != 200) {
      throw Exception('로그인에 실패했습니다 (${resp.statusCode})');
    }
    token = Map<String, dynamic>.from(jsonDecode(utf8.decode(resp.bodyBytes)))['token'] as String;
    return token!;
  }

  void logout() {
    token = null;
  }

  Future<List<Map<String, dynamic>>> getPosts() async {
    final resp = await _client.get(Uri.parse('$baseUrl/posts'));
    if (resp.statusCode != 200) {
      throw Exception('글 목록을 불러오지 못했습니다 (${resp.statusCode})');
    }
    final List<dynamic> data = jsonDecode(utf8.decode(resp.bodyBytes));
    return List<Map<String, dynamic>>.from(data);
  }

  Future<Map<String, dynamic>> createPost(String content) async {
    final resp = await _client.post(
      Uri.parse('$baseUrl/posts'),
      headers: _headers(auth: true),
      body: jsonEncode({'content': content}),
    );
    if (resp.statusCode != 200) {
      throw Exception('글 등록에 실패했습니다 (${resp.statusCode})');
    }
    return Map<String, dynamic>.from(jsonDecode(utf8.decode(resp.bodyBytes)));
  }
```

- [ ] **Step 5: reactToPost에도 auth 헤더 적용**

**원본** (`ulssu/lib/services/api.dart:reactToPost 내부 headers`):
```dart
  Future<Map<String, dynamic>> reactToPost(int postId, String reaction) async {
    final resp = await _client.post(
      Uri.parse('$baseUrl/posts/$postId/reaction'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'reaction': reaction}),
    );
```

**수정 후**:
```dart
  Future<Map<String, dynamic>> reactToPost(int postId, String reaction) async {
    final resp = await _client.post(
      Uri.parse('$baseUrl/posts/$postId/reaction'),
      headers: _headers(auth: true),
      body: jsonEncode({'reaction': reaction}),
    );
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd ulssu && flutter test test/services/api_auth_test.dart`
Expected: PASS (2 tests)

- [ ] **Step 7: 커밋**

```bash
git add ulssu/pubspec.yaml ulssu/pubspec.lock ulssu/lib/services/api.dart ulssu/test/services/api_auth_test.dart
git commit -m "feat(flutter): ApiService 인증(signup/login/logout + 토큰 헤더 주입)"
```

---

### Task 6: Flutter 로그인/가입 화면 + 라우팅

**Files:**
- Create: `ulssu/lib/screens/login_screen.dart`
- Modify: `ulssu/lib/main.dart` (토큰 유무 분기 + 토큰 영속화)
- Test: `ulssu/test/screens/login_test.dart`

**Model**: sonnet

- [ ] **Step 1: 실패하는 위젯 테스트 작성**

**수정 후** (new file: `ulssu/test/screens/login_test.dart`):
```dart
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ulssu/screens/login_screen.dart';
import 'package:ulssu/services/api.dart';

void main() {
  testWidgets('이메일/비번 입력 후 로그인 탭 → onAuthed 콜백', (tester) async {
    final api = ApiService(client: MockClient((req) async => http.Response(
        jsonEncode({'token': 'T1'}), 200,
        headers: {'content-type': 'application/json; charset=utf-8'})));
    var authed = false;

    await tester.pumpWidget(MaterialApp(
      home: LoginScreen(api: api, onAuthed: () => authed = true),
    ));

    await tester.enterText(find.byKey(const Key('email-field')), 'a@b.com');
    await tester.enterText(find.byKey(const Key('password-field')), 'pw123456');
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pump();
    await tester.pump();

    expect(authed, isTrue);
    expect(api.token, 'T1');
  });
}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu && flutter test test/screens/login_test.dart`
Expected: FAIL — `LoginScreen` 미존재

- [ ] **Step 3: login_screen.dart 생성**

**수정 후** (new file: `ulssu/lib/screens/login_screen.dart`):
```dart
import 'package:flutter/material.dart';

import '../services/api.dart';

/// 로그인/가입 화면. 성공 시 onAuthed() 호출(상위가 홈으로 전환 + 토큰 영속화).
class LoginScreen extends StatefulWidget {
  final ApiService api;
  final VoidCallback onAuthed;

  const LoginScreen({super.key, required this.api, required this.onAuthed});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _isSignup = false;
  bool _busy = false;

  Future<void> _submit() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      if (_isSignup) {
        await widget.api.signup(_email.text.trim(), _password.text);
      } else {
        await widget.api.login(_email.text.trim(), _password.text);
      }
      widget.onAuthed();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_isSignup ? '가입 실패' : '로그인 실패'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isSignup ? '가입' : '로그인')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TextField(
              key: const Key('email-field'),
              controller: _email,
              decoration: const InputDecoration(labelText: '이메일', border: OutlineInputBorder()),
              keyboardType: TextInputType.emailAddress,
            ),
            const SizedBox(height: 12),
            TextField(
              key: const Key('password-field'),
              controller: _password,
              decoration: const InputDecoration(labelText: '비밀번호', border: OutlineInputBorder()),
              obscureText: true,
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                key: const Key('login-button'),
                onPressed: _busy ? null : _submit,
                child: Text(_isSignup ? '가입하기' : '로그인'),
              ),
            ),
            TextButton(
              onPressed: _busy ? null : () => setState(() => _isSignup = !_isSignup),
              child: Text(_isSignup ? '이미 계정이 있어요 (로그인)' : '계정이 없어요 (가입)'),
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: main.dart 라우팅 + 토큰 영속화**

**원본** (`ulssu/lib/main.dart:1-28`):
```dart
import 'package:flutter/material.dart';
import 'screens/home_screen.dart'; // 방금 만든 홈 화면 임포트

void main() {
  runApp(const AiSquareApp());
}

class AiSquareApp extends StatelessWidget {
  const AiSquareApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Square',
      theme: ThemeData(
        // 트렌디하고 깨끗한 Material 3 가이드라인 적용
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.deepPurple,
          brightness: Brightness.light,
        ),
      ),
      // 앱이 켜졌을 때 첫 화면을 게시판(HomeScreen)으로 설정
      home: const HomeScreen(),
      debugShowCheckedModeBanner: false, // 우상단 디버그 띠 숨기기
    );
  }
}
```

**수정 후**:
```dart
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'services/api.dart';

void main() {
  runApp(const AiSquareApp());
}

class AiSquareApp extends StatelessWidget {
  const AiSquareApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Square',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.deepPurple,
          brightness: Brightness.light,
        ),
      ),
      home: const AuthGate(),
      debugShowCheckedModeBanner: false,
    );
  }
}

/// 토큰 유무로 로그인/홈을 분기하고, 토큰을 SharedPreferences에 영속화한다.
class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  final ApiService _api = ApiService();
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    final prefs = await SharedPreferences.getInstance();
    _api.token = prefs.getString('token');
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _onAuthed() async {
    final prefs = await SharedPreferences.getInstance();
    if (_api.token != null) await prefs.setString('token', _api.token!);
    if (mounted) setState(() {});
  }

  Future<void> _onLogout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('token');
    _api.logout();
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_api.token == null) {
      return LoginScreen(api: _api, onAuthed: _onAuthed);
    }
    return HomeScreen(api: _api, onLogout: _onLogout);
  }
}
```

> 주의: `HomeScreen`은 현재 `api`/`onLogout` 파라미터가 없다. 이 Step에서 `HomeScreen` 생성자에 `final ApiService api;`(기본 ApiService())와 `final VoidCallback? onLogout;`를 추가하고, 내부 `_api` 필드를 `widget.api`로 대체 + 앱바에 로그아웃 IconButton(`onLogout` 호출)을 추가한다. (home_screen.dart도 이 Task의 Modify 대상에 포함.)

- [ ] **Step 5: home_screen.dart에 api 주입 + 로그아웃 버튼**

**원본** (`ulssu/lib/screens/home_screen.dart:6-16`):
```dart
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ApiService _api = ApiService();
  List<Map<String, dynamic>> _posts = [];
  final TextEditingController _textController = TextEditingController();
  bool _isLoading = false;
```

**수정 후**:
```dart
class HomeScreen extends StatefulWidget {
  final ApiService api;
  final VoidCallback? onLogout;

  HomeScreen({super.key, ApiService? api, this.onLogout}) : api = api ?? ApiService();

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  ApiService get _api => widget.api;
  List<Map<String, dynamic>> _posts = [];
  final TextEditingController _textController = TextEditingController();
  bool _isLoading = false;
```

- [ ] **Step 6: home_screen 앱바에 로그아웃 버튼 추가**

**원본** (`ulssu/lib/screens/home_screen.dart` — 앱바 actions의 새로고침 IconButton):
```dart
        actions: [
          // 새로고침 버튼 추가
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _isLoading ? null : _fetchPostsFromDatabase,
          )
        ],
```

**수정 후**:
```dart
        actions: [
          // 새로고침 버튼 추가
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _isLoading ? null : _fetchPostsFromDatabase,
          ),
          if (widget.onLogout != null)
            IconButton(
              icon: const Icon(Icons.logout),
              onPressed: widget.onLogout,
            ),
        ],
```

- [ ] **Step 7: 위젯 테스트 통과 + 전체 + analyze**

Run: `cd ulssu && flutter test && flutter analyze`
Expected: 모든 테스트 PASS + `No issues found!`

- [ ] **Step 8: 커밋**

```bash
git add ulssu/lib/main.dart ulssu/lib/screens/login_screen.dart ulssu/lib/screens/home_screen.dart ulssu/test/screens/login_test.dart
git commit -m "feat(flutter): 로그인/가입 화면 + 토큰 영속화 라우팅(AuthGate) + 로그아웃"
```

---

## 2. 위험 코드 지점

- `ulssu_backend/main.py:create_post,react_to_post` — **breaking**: 인증 강제로 기존 무인증 호출(테스트·Flutter)이 401. (mitigation: 같은 슬라이스에서 conftest `auth_client` + 기존 테스트 전환(Task 4) + Flutter 헤더 주입(Task 5). e2e로 확인.)
- `ulssu_backend/database.py:users/FK` — **breaking**: users 테이블 + FK 컬럼 추가. 운영 DB `create_all` 미반영. (mitigation: `migrations/002_*.sql` 멱등 SQL + 런북. dev는 재생성.)
- `ulssu_backend/auth.py` — **side-effect(security)**: 비번 해시·JWT 시크릿 취급. (mitigation: bcrypt 해시·평문 미저장, `JWT_SECRET` env(기본값은 dev용 — 운영은 반드시 교체), 토큰 만료 7일. password_hash 응답 비노출.)

## 3. 롤백 전략

- **Code:** Task별 커밋 역순 `git revert`. 인증만 끄려면 Task 4 revert(라우트 보호 해제) — 단 Flutter는 헤더를 보내도 무해.
- **DB:** `migrations/002_*.sql` 하단 down SQL 역순 실행. dev는 테이블 재생성.
- **Config:** `JWT_SECRET`/만료는 `auth.py` 상수+env. 토큰 정책 변경은 여기서.
- **신규 의존성:** pyjwt·bcrypt·shared_preferences — 롤백 시 제거.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 12:10] [구현계획서-수정]
- **id**: CH-20260617-003
- **이유**: 신규 구현계획서 작성 (유저 인증 최소, 6 TDD task — 백엔드 인증/스키마 + 기존 테스트 전환 + Flutter 로그인)
- **무엇이**: user-auth-implementation-plan.md §1(Task 1~6), §2 위험, §3 롤백
- **영향범위**: ulssu_backend(auth/database/main/conftest/기존 테스트)·migrations/002·ulssu(api/screens/main)·신규 의존성 3. 북극성 §4 정합.
- **연관 항목**: CH-20260617-001, CH-20260617-002

### [2026-06-17 12:30] [코드-수정] (batch: tasks 1..6)
- **id**: CH-20260617-004
- **이유**: 유저 인증 최소 슬라이스 전체 구현(6 TDD task). 이메일+비번 가입/로그인/로그아웃(JWT) + 글·반응 로그인 보호·작성자 연결 + users/이음새 + Flutter 로그인 흐름. 북극성 identity-only.
- **무엇이**: `ulssu_backend/auth.py`(신설)·`database.py`·`main.py`·`tests/conftest.py`·기존 테스트 3파일(전환)·`tests/test_auth*.py`·`tests/test_user_schema.py`(신설)·`migrations/002_*.sql`(신설), `ulssu/lib/services/api.dart`·`screens/login_screen.dart`(신설)·`screens/home_screen.dart`·`main.dart`·`test/*`(신설), `pyproject.toml`/`pubspec.yaml`
- **영향범위**: 글·반응 라우트 인증 강제(기존 무인증 테스트 → auth_client 전환). users 테이블 + posts.author_user_id/reactions.user_id(NULL 호환). Flutter 앱이 토큰 없으면 로그인 유도. 신규 의존성 pyjwt·bcrypt·shared_preferences.
- **위험 카테고리**: breaking(인증 강제 → 기존 테스트 전환으로 완화), breaking(스키마 → migrations/002), security(비번 해시·JWT 시크릿) — 모두 §2 사전 식별
- **task별 세부 (6건)**:
  - UA1: `auth.py` — bcrypt/PyJWT 순수 로직 + 유닛 3 (security) — `861133b`
  - UA2: `database.py`+`migrations/002` — users/이음새 (breaking) — `b728261`
  - UA3: `auth.py`/`main.py`/`conftest.py` — get_current_user+signup/login+auth_client (security) — `17e84ce`
  - UA4: `main.py`+기존 테스트 3 — 라우트 보호+author 연결+전환 (breaking) — `a62e902`
  - UA5: `ulssu/lib/services/api.dart` — Flutter 인증 메서드+헤더 (none) — `49e324a`
  - UA6: `main.dart`/`login_screen.dart`/`home_screen.dart` — AuthGate+로그인 UI+로그아웃 (none) — `10701b7`
- **테스트 결과**: 백엔드 44 passed, Flutter 9 passed, flutter analyze No issues.
- **연관 commits**: `861133b..10701b7` (6 커밋)
- **변경 전/후 코드**: 생략 — `git show <SHA>` 로 조회 (git-fast 모드)
- **운영 주의**: `JWT_SECRET` 환경변수 반드시 교체. Flutter 빌드/실행엔 Windows Developer Mode 필요(shared_preferences 플러그인).
- **연관 항목**: CH-20260617-003
