---
commit_policy: per-task
---

# 내 AI 출동 구현계획서

> **다음 단계 안내**: `js-super-sub-driven`(권장) 또는 `executing-plans`로 task-by-task 실행.

**Goal:** 글 등록 시 작성자 제외 다른 유저 페르소나 최대 2명을 Final Limit 슬롯에 끼워 댓글 생성(persona_prompt+hint), 나머지 공용 풀. 총 댓글 수 불변, 다른 유저 없으면 전부 풀.

**Architecture:** `persona_deployment.select_deployed_personas(db, exclude_user_id, k, rng)` + `create_post` 댓글 루프 연동. 마이그레이션/의존성 없음.

**Tech Stack:** FastAPI, SQLAlchemy. 테스트 SQLite.

**Spec inputs:**
- `persona-deployment-requirements.md` — FR-1~6, AC-1~6
- `persona-deployment-tech-design.md` — D1(k=2) D2(prompt+hint) D3(작성자 제외/없으면 풀) D4(display_name) D5(create_post 한정) D6(rng)

---

## 1. 단계별 작업

### Task 1: `persona_deployment.py` + 유닛 테스트

**Files:**
- Create: `comea_backend/persona_deployment.py`
- Test: `comea_backend/tests/test_persona_deployment.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `comea_backend/tests/test_persona_deployment.py`):
```python
import random

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import persona_deployment
from database import AiPersonaModel, UserModel


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _user_with_persona(db, email, name, hint):
    u = UserModel(email=email, password_hash="h")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(AiPersonaModel(
        user_id=u.id, display_name=name, persona_prompt=f"PROMPT_{name}",
        trait_params={"hint": hint} if hint else None,
    ))
    db.commit()
    return u


def test_excludes_author_and_injects_hint():
    db = _session()
    try:
        a = _user_with_persona(db, "a@x.com", "A페르소나", "")
        _user_with_persona(db, "b@x.com", "B페르소나", "HINT_B")
        result = persona_deployment.select_deployed_personas(db, exclude_user_id=a.id, k=2, rng=random.Random(0))
        names = [n for n, _ in result]
        assert "A페르소나" not in names           # 작성자 제외
        assert "B페르소나" in names                # 타 유저 포함
        prompt_b = dict(result)["B페르소나"]
        assert "PROMPT_B페르소나" in prompt_b and "HINT_B" in prompt_b  # prompt + hint
    finally:
        db.close()


def test_respects_k_limit():
    db = _session()
    try:
        author = _user_with_persona(db, "au@x.com", "작성자", "")
        for i in range(5):
            _user_with_persona(db, f"u{i}@x.com", f"P{i}", "")
        result = persona_deployment.select_deployed_personas(db, exclude_user_id=author.id, k=2, rng=random.Random(1))
        assert len(result) == 2
    finally:
        db.close()


def test_empty_when_no_other_personas():
    db = _session()
    try:
        a = _user_with_persona(db, "solo@x.com", "혼자", "")
        assert persona_deployment.select_deployed_personas(db, exclude_user_id=a.id, k=2) == []
    finally:
        db.close()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd comea_backend && uv run pytest tests/test_persona_deployment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'persona_deployment'`

- [ ] **Step 3: 구현 작성**

**수정 후** (new file: `comea_backend/persona_deployment.py`):
```python
"""내 AI 출동: 작성자 제외 유저 페르소나를 댓글 생성에 일부 참여시킨다.

각 출동 페르소나의 persona_prompt + 진화 hint(trait_params.hint)로 댓글을 생성한다.
"""
import random

from database import AiPersonaModel


def select_deployed_personas(db, exclude_user_id: int, k: int = 2, rng=None):
    """작성자(exclude_user_id) 제외 유저 페르소나 중 랜덤 k명 → [(display_name, prompt+hint)]."""
    personas = (
        db.query(AiPersonaModel)
        .filter(AiPersonaModel.user_id != exclude_user_id)
        .all()
    )
    if not personas:
        return []
    chooser = rng if rng is not None else random
    chosen = chooser.sample(personas, min(k, len(personas)))
    result = []
    for p in chosen:
        hint = ""
        if isinstance(p.trait_params, dict):
            hint = p.trait_params.get("hint") or ""
        prompt = p.persona_prompt + (f"\n[성향 힌트] {hint}" if hint else "")
        result.append((p.display_name, prompt))
    return result
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd comea_backend && uv run pytest tests/test_persona_deployment.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add comea_backend/persona_deployment.py comea_backend/tests/test_persona_deployment.py
git commit -m "feat(backend): 내 AI 출동 선발(select_deployed_personas) + 유닛테스트"
```

---

### Task 2: `create_post` 댓글 루프에 출동 연동

**Files:**
- Modify: `comea_backend/main.py:15-16` (import), `comea_backend/main.py:create_post` (댓글 루프)
- Test: `comea_backend/tests/test_persona_deployment_signup.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 통합 테스트 작성**

**수정 후** (new file: `comea_backend/tests/test_persona_deployment_signup.py`):
```python
import database
import main
from database import AiPersonaModel, UserModel


def test_create_post_deploys_other_user_persona(auth_client, monkeypatch):
    # 다른 유저 B + 페르소나(hint) 시드 (auth_client 의 유저 A 와 별개)
    db = next(main.app.dependency_overrides[database.get_db]())
    try:
        b = UserModel(email="b@x.com", password_hash="h")
        db.add(b)
        db.commit()
        db.refresh(b)
        db.add(AiPersonaModel(
            user_id=b.id, display_name="냉철 김박사",
            persona_prompt="PROMPT_B", trait_params={"hint": "HINT_B"},
        ))
        db.commit()
    finally:
        db.close()

    captured = []

    def fake_comment(persona_prompt, user_post, previous, length_hint):
        captured.append(persona_prompt)
        return "댓글"

    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 40)  # base 10
    monkeypatch.setattr(main, "generate_ai_comment", fake_comment)

    body = auth_client.post("/api/posts", json={"content": "x"}).json()

    # 총 댓글 수 불변(Final == base 10)
    assert len(body["comments"]) == 10
    # B 페르소나(타 유저)가 출동해 prompt+hint 로 생성됨 (AC-1/2)
    assert any("PROMPT_B" in p and "HINT_B" in p for p in captured)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd comea_backend && uv run pytest tests/test_persona_deployment_signup.py -v`
Expected: FAIL — 출동 미연동으로 captured에 B 프롬프트 없음(`assert any(...)` 실패)

- [ ] **Step 3: main.py import에 select_deployed_personas 추가**

**원본** (`comea_backend/main.py:15-16`):
```python
from database import get_db, PostModel, CommentModel, ReactionModel, UserModel, AiPersonaModel, CommentReactionModel
from auth import hash_password, verify_password, create_token, get_current_user
```

**수정 후**:
```python
from database import get_db, PostModel, CommentModel, ReactionModel, UserModel, AiPersonaModel, CommentReactionModel
from auth import hash_password, verify_password, create_token, get_current_user
from persona_deployment import select_deployed_personas
```

- [ ] **Step 4: create_post 댓글 루프에 출동 슬롯 반영**

**원본** (`comea_backend/main.py`):
```python
    # 2. Final Limit 만큼 페르소나를 순환 선택해 생성. 분량은 매번 랜덤 변주(FR-13).
    chat_history = ""
    for name, prompt in get_personas(final_limit):
        comment_text = generate_ai_comment(prompt, user_post, chat_history, pick_length_style())
        db.add(CommentModel(post_id=db_post.id, name=name, comment=comment_text))
        chat_history += f"{name}: {comment_text}\n"
```

**수정 후**:
```python
    # 2. Final Limit 슬롯 = 타 유저 페르소나 출동(최대 2) + 공용 풀. 총 수 불변. 분량 랜덤(FR-13).
    deployed = select_deployed_personas(db, exclude_user_id=current_user.id, k=2)
    pool = get_personas(max(final_limit - len(deployed), 0))
    commenters = (deployed + pool)[:final_limit]
    chat_history = ""
    for name, prompt in commenters:
        comment_text = generate_ai_comment(prompt, user_post, chat_history, pick_length_style())
        db.add(CommentModel(post_id=db_post.id, name=name, comment=comment_text))
        chat_history += f"{name}: {comment_text}\n"
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd comea_backend && uv run pytest tests/test_persona_deployment_signup.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: 전체 백엔드 테스트 실행**

Run: `cd comea_backend && uv run pytest -q`
Expected: PASS (전체 green — 출동 + 기존 회귀 없음. 다른 유저 페르소나 없는 기존 테스트는 전부 풀.)

- [ ] **Step 7: 커밋**

```bash
git add comea_backend/main.py comea_backend/tests/test_persona_deployment_signup.py
git commit -m "feat(backend): create_post에 타 유저 페르소나 출동 연동(슬롯 일부)"
```

---

## 2. 위험 코드 지점

- `comea_backend/main.py:create_post` — **side-effect**: 글 등록이 추가로 `ai_personas` 조회 + 출동 댓글 생성. (mitigation: k=2 상한, 총 댓글 수 불변(슬롯 대체), 조회 1회.)
- `comea_backend/main.py:create_post` (댓글 구성 변경) — **breaking(약)**: 댓글 commenter 구성이 풀→출동+풀로 변경. (mitigation: 다른 유저 페르소나 없으면 전부 풀(기존 동작 동일), 총 수 불변 → 기존 create_post 테스트 회귀 없음.)

## 3. 롤백 전략

- **Code:** Task별 커밋 역순 `git revert`. 출동만 끄려면 create_post 루프를 `get_personas(final_limit)`로 되돌림(Task 2 revert).
- **Config:** 출동 인원 k는 `create_post`의 `k=2` 한 곳.
- **신규 의존성·마이그레이션:** 없음.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 15:15] [구현계획서-수정]
- **id**: CH-20260617-003
- **이유**: 신규 구현계획서 작성 (내 AI 출동, 2 TDD task)
- **무엇이**: persona-deployment-implementation-plan.md §1(Task 1~2), §2 위험, §3 롤백
- **영향범위**: comea_backend(persona_deployment 신설 + create_post 연동). 마이그레이션 없음.
- **연관 항목**: CH-20260617-001, CH-20260617-002

### [2026-06-17 15:25] [코드-수정] (batch: tasks 1..2)
- **id**: CH-20260617-004
- **이유**: 내 AI 출동 구현(2 task). 글 등록 시 타 유저 페르소나 일부가 persona_prompt+진화 hint로 댓글 참여.
- **무엇이**: `comea_backend/persona_deployment.py`(신설), `main.py`(create_post 댓글 루프+import), `tests/test_persona_deployment.py`·`test_persona_deployment_signup.py`(신설)
- **영향범위**: create_post 댓글 구성 = 출동(≤2)+풀. 총 댓글 수 불변. 다른 유저 페르소나 없으면 전부 풀(회귀). 마이그레이션 없음.
- **위험 카테고리**: side-effect(조회+생성), breaking(약, 댓글 구성 변경하나 수 불변·회귀 없음) — §2 사전 식별
- **task별 세부 (2건)**:
  - PD1: `persona_deployment.py` — select_deployed_personas + 유닛 3 (none) — `d9fe4d1`
  - PD2: `main.py` create_post — 출동 연동 + 통합 1 (side-effect) — `944171d`
- **테스트 결과**: 백엔드 61 passed.
- **연관 commits**: `d9fe4d1..944171d`
- **변경 전/후 코드**: 생략 — `git show <SHA>`
- **연관 항목**: CH-20260617-003
