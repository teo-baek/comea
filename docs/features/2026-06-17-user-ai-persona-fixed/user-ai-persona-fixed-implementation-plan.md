---
commit_policy: per-task
---

# 유저별 AI 페르소나 (중간) 구현계획서

> **다음 단계 안내**: `js-super-sub-driven`(권장) 또는 `executing-plans`로 task-by-task 실행.

**Goal:** `ai_personas` 테이블(유저 1:1) + 가입 시 풀에서 랜덤 페르소나 1개 내부 생성. 미노출·댓글 미연동. 진화 엔진(다음 슬라이스)의 대상 레코드 마련.

**Architecture:** `AiPersonaModel`(database) + `random_persona`(personas) + signup best-effort 생성(main). trait_params는 풀 진화용 빈 자리.

**Tech Stack:** FastAPI, SQLAlchemy(JSON). 테스트 SQLite.

**Spec inputs:**
- `user-ai-persona-fixed-requirements.md` — FR-1~5, AC-1~5
- `user-ai-persona-fixed-tech-design.md` — D1(랜덤배정) D2(best-effort) D3(미노출/미연동) D4(trait_params JSON)
- 북극성 §3 중간

---

## 1. 단계별 작업

### Task 1: `ai_personas` 스키마 + `random_persona` + 마이그레이션

**Files:**
- Modify: `comea_backend/database.py:2` (JSON import), `comea_backend/database.py:15` (UserModel 아래 AiPersonaModel)
- Modify: `comea_backend/personas.py` (random_persona 추가)
- Create: `comea_backend/migrations/003_add_ai_personas.sql`
- Test: `comea_backend/tests/test_persona.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `comea_backend/tests/test_persona.py`):
```python
import random

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import AiPersonaModel, UserModel
from personas import PERSONA_POOL, random_persona


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_random_persona_returns_pool_member_deterministic():
    name, prompt = random_persona(random.Random(0))
    assert (name, prompt) in PERSONA_POOL
    assert random_persona(random.Random(3)) == random_persona(random.Random(3))


def test_ai_persona_record_one_to_one():
    db = _session()
    try:
        user = UserModel(email="p@x.com", password_hash="h")
        db.add(user)
        db.commit()
        db.refresh(user)
        name, prompt = random_persona(random.Random(1))
        db.add(AiPersonaModel(user_id=user.id, display_name=name, persona_prompt=prompt))
        db.commit()
        rows = db.query(AiPersonaModel).filter(AiPersonaModel.user_id == user.id).all()
        assert len(rows) == 1
        assert rows[0].display_name == name
        assert rows[0].trait_params is None  # 풀 단계 진화 엔진이 채움
    finally:
        db.close()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd comea_backend && uv run pytest tests/test_persona.py -v`
Expected: FAIL — `ImportError: cannot import name 'AiPersonaModel'`

- [ ] **Step 3: database.py import에 JSON 추가**

**원본** (`comea_backend/database.py:2`):
```python
from sqlalchemy import create_engine, Column, Integer, Text, String, ForeignKey, Boolean, DateTime, func
```

**수정 후**:
```python
from sqlalchemy import create_engine, Column, Integer, Text, String, ForeignKey, Boolean, DateTime, func, JSON
```

- [ ] **Step 4: AiPersonaModel 추가 (UserModel 아래, get_db 위)**

**원본** (`comea_backend/database.py:13-16`):
```python
    created_at = Column(DateTime, nullable=False, server_default=func.now())


def get_db():
```

**수정 후**:
```python
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class AiPersonaModel(Base):
    # 유저별 1:1 AI 페르소나(내부). 가입 시 풀에서 랜덤 배정. 진화 엔진(풀 단계)이 trait_params 채움.
    __tablename__ = "ai_personas"
    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    display_name   = Column(String, nullable=False)
    persona_prompt = Column(Text, nullable=False)
    trait_params   = Column(JSON, nullable=True)
    updated_at     = Column(DateTime, nullable=False, server_default=func.now())


def get_db():
```

- [ ] **Step 5: personas.py에 random_persona 추가**

**원본** (`comea_backend/personas.py:1`):
```python
"""'AI 광장' 시민 페르소나 풀 + 순환 선택기.
```

**수정 후**:
```python
"""'AI 광장' 시민 페르소나 풀 + 순환 선택기 + 랜덤 1개 선택.
```

- [ ] **Step 6: random_persona 함수 추가 (파일 끝)**

**수정 후** (append to `comea_backend/personas.py`):
```python


def random_persona(rng=None):
    """풀에서 (이름, 프롬프트) 1개를 랜덤 반환. rng 주입 시 결정적."""
    import random as _random
    chooser = rng if rng is not None else _random
    return chooser.choice(PERSONA_POOL)
```

- [ ] **Step 7: 마이그레이션 SQL 작성**

**수정 후** (new file: `comea_backend/migrations/003_add_ai_personas.sql`):
```sql
-- 003_add_ai_personas.sql
-- user-ai-persona-fixed 슬라이스 스키마를 기존 운영 PostgreSQL 에 반영한다. 멱등.
-- 적용:  psql "$DATABASE_URL" -f migrations/003_add_ai_personas.sql

CREATE TABLE IF NOT EXISTS ai_personas (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER UNIQUE NOT NULL REFERENCES users(id),
    display_name   VARCHAR NOT NULL,
    persona_prompt TEXT NOT NULL,
    trait_params   JSONB,
    updated_at     TIMESTAMP NOT NULL DEFAULT now()
);

-- 롤백 (down):
--   DROP TABLE IF EXISTS ai_personas;
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `cd comea_backend && uv run pytest tests/test_persona.py -v`
Expected: PASS (2 passed)

- [ ] **Step 9: 커밋**

```bash
git add comea_backend/database.py comea_backend/personas.py comea_backend/migrations/003_add_ai_personas.sql comea_backend/tests/test_persona.py
git commit -m "feat(backend): ai_personas 테이블 + random_persona + 마이그레이션"
```

---

### Task 2: 가입 시 페르소나 best-effort 생성

**Files:**
- Modify: `comea_backend/main.py:15-16` (import), `comea_backend/main.py:139-148` (signup)
- Test: `comea_backend/tests/test_persona_signup.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 통합 테스트 작성**

**수정 후** (new file: `comea_backend/tests/test_persona_signup.py`):
```python
import database
import main
from database import AiPersonaModel, UserModel


def test_signup_creates_internal_persona(client):
    resp = client.post("/api/auth/signup", json={"email": "pp@x.com", "password": "pw123456"})
    assert resp.status_code == 201

    # 내부 페르소나가 1건 생성됐는지 DB로 직접 확인 (사용자에겐 노출 안 됨).
    # conftest 가 get_db 를 오버라이드했으므로 같은 엔진 세션을 얻어 조회.
    db = next(main.app.dependency_overrides[database.get_db]())
    try:
        user = db.query(UserModel).filter(UserModel.email == "pp@x.com").first()
        personas = db.query(AiPersonaModel).filter(AiPersonaModel.user_id == user.id).all()
        assert len(personas) == 1  # 1:1
        assert personas[0].display_name  # 이름 채워짐
    finally:
        db.close()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd comea_backend && uv run pytest tests/test_persona_signup.py -v`
Expected: FAIL — 페르소나 미생성으로 `assert len(personas) == 1` 실패(0)

- [ ] **Step 3: main.py import에 AiPersonaModel + random_persona 추가**

**원본** (`comea_backend/main.py:15-16`):
```python
from database import get_db, PostModel, CommentModel, ReactionModel, UserModel
from auth import hash_password, verify_password, create_token, get_current_user
```

**수정 후**:
```python
from database import get_db, PostModel, CommentModel, ReactionModel, UserModel, AiPersonaModel
from auth import hash_password, verify_password, create_token, get_current_user
from personas import random_persona
```

- [ ] **Step 4: signup에 페르소나 best-effort 생성 추가**

**원본** (`comea_backend/main.py:140-148`):
```python
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    exists = db.query(UserModel).filter(UserModel.email == request.email).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    user = UserModel(email=request.email, password_hash=hash_password(request.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id)}
```

**수정 후**:
```python
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    exists = db.query(UserModel).filter(UserModel.email == request.email).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    user = UserModel(email=request.email, password_hash=hash_password(request.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    # 내부 AI 페르소나 1개 생성 (풀에서 랜덤). best-effort — 실패해도 가입은 유지(NFR).
    try:
        name, prompt = random_persona()
        db.add(AiPersonaModel(user_id=user.id, display_name=name, persona_prompt=prompt))
        db.commit()
    except Exception:
        db.rollback()

    return {"token": create_token(user.id)}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd comea_backend && uv run pytest tests/test_persona_signup.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: 전체 백엔드 테스트 실행**

Run: `cd comea_backend && uv run pytest -q`
Expected: PASS (전체 green — 신규 페르소나 + 기존 회귀 없음)

- [ ] **Step 7: 커밋**

```bash
git add comea_backend/main.py comea_backend/tests/test_persona_signup.py
git commit -m "feat(backend): 가입 시 내부 AI 페르소나 best-effort 생성"
```

---

## 2. 위험 코드 지점

- `comea_backend/database.py:AiPersonaModel` — **breaking**: `ai_personas` 테이블 신설. 운영 DB `create_all` 미반영 가능. (mitigation: `migrations/003_*.sql` 멱등 SQL. dev는 재생성.)
- `comea_backend/main.py:signup` — **side-effect**: 가입이 추가 write(페르소나) 수행. (mitigation: 유저 commit 선행 + 페르소나 try/except best-effort로 가입 흐름 보호. 실패 시 rollback.)

## 3. 롤백 전략

- **Code:** Task별 커밋 역순 `git revert`. 페르소나 생성만 끄려면 signup의 try 블록 제거(나머지 영향 없음).
- **DB:** `migrations/003_*.sql` 하단 down SQL. dev는 재생성.
- **신규 의존성:** 없음 (SQLAlchemy JSON 내장).

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 13:25] [구현계획서-수정]
- **id**: CH-20260617-002
- **이유**: 신규 구현계획서 작성 (유저별 AI 페르소나 중간, 2 TDD task)
- **무엇이**: user-ai-persona-fixed-implementation-plan.md §1(Task 1~2), §2 위험, §3 롤백
- **영향범위**: comea_backend(database AiPersonaModel·personas·main signup·migration 003).
- **연관 항목**: CH-20260617-001

### [2026-06-17 13:35] [코드-수정] (batch: tasks 1..2)
- **id**: CH-20260617-003
- **이유**: 유저별 AI 페르소나(중간=고정·내부) 구현(2 task). 가입 시 풀 랜덤 페르소나 1개 내부 생성·저장.
- **무엇이**: `comea_backend/database.py`(AiPersonaModel+JSON), `personas.py`(random_persona), `main.py`(signup 훅), `migrations/003_add_ai_personas.sql`(신설), `tests/test_persona.py`·`test_persona_signup.py`(신설)
- **영향범위**: 가입이 ai_personas 1건 best-effort 생성(1:1). 미노출·댓글 미연동. 진화 엔진(다음)이 이 레코드+행동(author_user_id/user_id)을 읽을 예정.
- **위험 카테고리**: breaking(스키마→migration 003), side-effect(signup 추가 write→best-effort) — §2 사전 식별
- **task별 세부 (2건)**:
  - PA1: `database.py`/`personas.py`/`migrations/003` — 스키마+random_persona (breaking) — `e332eab`
  - PA2: `main.py` signup — best-effort 페르소나 생성 (side-effect) — `4747351`
- **테스트 결과**: 백엔드 50 passed.
- **연관 commits**: `e332eab..4747351`
- **변경 전/후 코드**: 생략 — `git show <SHA>`
- **연관 항목**: CH-20260617-002
