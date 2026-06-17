---
commit_policy: per-task
---

# 페르소나 진화 엔진 구현계획서

> **다음 단계 안내**: `js-super-sub-driven`(권장) 또는 `executing-plans`로 task-by-task 실행.

**Goal:** 유저별 `comment_reactions ⋈ comments.name`을 +1/−1 합산 → `ai_personas.trait_params={prefs,hint}` 갱신. 일일 배치 연동. 저장만(출동은 다음).

**Architecture:** `persona_evolution.py`(compute/build_hint/run) + `population_batch` 스케줄러에 evolution job 추가. 마이그레이션 없음(trait_params JSON 기존).

**Tech Stack:** FastAPI, SQLAlchemy, APScheduler. 테스트 SQLite.

**Spec inputs:**
- `persona-evolution-engine-requirements.md` — FR-1~6, AC-1~6
- `persona-evolution-engine-tech-design.md` — D1(합산) D2(trait_params) D3(힌트) D4(일일배치) D5(저장만)

---

## 1. 단계별 작업

### Task 1: `persona_evolution.py` + 유닛 테스트

**Files:**
- Create: `ulssu_backend/persona_evolution.py`
- Test: `ulssu_backend/tests/test_persona_evolution.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_persona_evolution.py`):
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import persona_evolution
from database import (
    AiPersonaModel,
    CommentModel,
    CommentReactionModel,
    PostModel,
    UserModel,
)


def _factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _seed_user_reactions(db):
    u = UserModel(email="e@x.com", password_hash="h")
    db.add(u)
    db.commit()
    db.refresh(u)
    post = PostModel(content="x", score=40)
    db.add(post)
    db.commit()
    db.refresh(post)
    c1 = CommentModel(post_id=post.id, name="냉철 김박사", comment="a")
    c2 = CommentModel(post_id=post.id, name="공감 요정 웅이", comment="b")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)
    db.add(CommentReactionModel(user_id=u.id, comment_id=c1.id, reaction_type="like"))
    db.add(CommentReactionModel(user_id=u.id, comment_id=c2.id, reaction_type="dislike"))
    db.commit()
    return u


def test_compute_preferences_sums_plus_minus():
    db = _factory()()
    try:
        u = _seed_user_reactions(db)
        prefs = persona_evolution.compute_persona_preferences(db, u.id)
        assert prefs == {"냉철 김박사": 1, "공감 요정 웅이": -1}
    finally:
        db.close()


def test_build_prompt_hint():
    assert "냉철 김박사" in persona_evolution.build_prompt_hint({"냉철 김박사": 2, "공감 요정 웅이": -1})
    assert persona_evolution.build_prompt_hint({}) == ""
    assert persona_evolution.build_prompt_hint({"x": -1}) == ""  # 양수 없으면 빈 힌트


def test_run_persona_evolution_updates_trait_params(monkeypatch):
    Session = _factory()
    seed = Session()
    u = _seed_user_reactions(seed)
    seed.add(AiPersonaModel(user_id=u.id, display_name="x", persona_prompt="p"))
    seed.commit()
    seed.close()

    monkeypatch.setattr(database, "SessionLocal", Session)
    persona_evolution.run_persona_evolution()

    check = Session()
    try:
        p = check.query(AiPersonaModel).filter(AiPersonaModel.user_id == u.id).first()
        assert p.trait_params["prefs"]["냉철 김박사"] == 1
        assert "냉철 김박사" in p.trait_params["hint"]
    finally:
        check.close()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_persona_evolution.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'persona_evolution'`

- [ ] **Step 3: 구현 작성**

**수정 후** (new file: `ulssu_backend/persona_evolution.py`):
```python
"""페르소나 진화 엔진: comment_reactions ⋈ comments.name 합산 → ai_personas.trait_params 갱신.

planned.md 팁대로 단순 합산(+1 like / −1 dislike). 저장만(댓글 생성 사용은 다음 슬라이스).
"""
import database
from database import AiPersonaModel, CommentModel, CommentReactionModel


def compute_persona_preferences(db, user_id: int) -> dict:
    """유저의 댓글 반응을 페르소나(comments.name)별 +1/−1 합산한 선호 맵."""
    rows = (
        db.query(CommentModel.name, CommentReactionModel.reaction_type)
        .join(CommentReactionModel, CommentReactionModel.comment_id == CommentModel.id)
        .filter(CommentReactionModel.user_id == user_id)
        .all()
    )
    prefs: dict = {}
    for name, rtype in rows:
        prefs[name] = prefs.get(name, 0) + (1 if rtype == "like" else -1)
    return prefs


def build_prompt_hint(prefs: dict) -> str:
    """최고 양수 선호 페르소나로 프롬프트 힌트 문장. 양수 없으면 빈 문자열."""
    if not prefs:
        return ""
    top_name, top_score = max(prefs.items(), key=lambda kv: kv[1])
    if top_score <= 0:
        return ""
    return f"당신의 주인은 현재 '{top_name}' 같은 답변을 선호합니다."


def run_persona_evolution() -> None:
    """모든 페르소나를 유저 행동으로 진화(trait_params 갱신). 유저 단위 예외 격리(AC-5)."""
    try:
        db = database.SessionLocal()
    except Exception:
        return
    try:
        for persona in db.query(AiPersonaModel).all():
            try:
                prefs = compute_persona_preferences(db, persona.user_id)
                persona.trait_params = {"prefs": prefs, "hint": build_prompt_hint(prefs)}
                db.commit()
            except Exception:
                db.rollback()
    finally:
        db.close()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_persona_evolution.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add ulssu_backend/persona_evolution.py ulssu_backend/tests/test_persona_evolution.py
git commit -m "feat(backend): 페르소나 진화 엔진(선호 합산 + 힌트 → trait_params) + 유닛테스트"
```

---

### Task 2: 일일 배치에 진화 job 연동

**Files:**
- Modify: `ulssu_backend/population_batch.py` (import + start_scheduler)

**Model**: sonnet

> 검증: 스케줄러 배선이라 별도 테스트 대신 전체 스위트 green(가드로 미기동) + import 무오류로 확인. 진화 로직은 Task 1 유닛이 커버.

- [ ] **Step 1: import 추가**

**원본** (`ulssu_backend/population_batch.py:7-9`):
```python
import database
import population
from database import UserModel
```

**수정 후**:
```python
import database
import population
from database import UserModel
from persona_evolution import run_persona_evolution
```

- [ ] **Step 2: start_scheduler에 진화 실행/등록 추가**

**원본** (`ulssu_backend/population_batch.py:start_scheduler`):
```python
def start_scheduler() -> None:
    """기동 즉시 1회 집계 + 매일 4시 cron 등록. 테스트(DISABLE_SCHEDULER)면 미기동(D5)."""
    if os.getenv("DISABLE_SCHEDULER"):
        return
    global _scheduler
    run_population_update()  # 기동 즉시 1회 (0 방지, FR-2)
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(run_population_update, "cron", hour=4)
    _scheduler.start()
```

**수정 후**:
```python
def start_scheduler() -> None:
    """기동 즉시 1회(인구+진화) + 매일 4시 cron 등록. 테스트(DISABLE_SCHEDULER)면 미기동(D5)."""
    if os.getenv("DISABLE_SCHEDULER"):
        return
    global _scheduler
    run_population_update()    # 기동 즉시 1회 (0 방지, FR-2)
    run_persona_evolution()    # 기동 즉시 페르소나 진화 1회
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(run_population_update, "cron", hour=4)
    _scheduler.add_job(run_persona_evolution, "cron", hour=4)
    _scheduler.start()
```

- [ ] **Step 3: 전체 백엔드 테스트 실행**

Run: `cd ulssu_backend && uv run pytest -q`
Expected: PASS (전체 green — 진화 단위 + 기존 회귀 없음, 스케줄러 미기동)

- [ ] **Step 4: 커밋**

```bash
git add ulssu_backend/population_batch.py
git commit -m "feat(backend): 일일 배치에 페르소나 진화 job 연동(기동+4시)"
```

---

## 2. 위험 코드 지점

- `ulssu_backend/persona_evolution.py:run_persona_evolution` — **side-effect**: 배치가 모든 페르소나 순회 + 반응 쿼리. (mitigation: 일일 1회, 유저 단위 try/except 격리, 세션 생성 실패 시 조용히 return. 기동 시 best-effort.)
- `ulssu_backend/persona_evolution.py` (스냅샷) — **race**: 진화 중 동시 comment_reaction 변경. (mitigation: 일별 스냅샷 — 다음 배치에 반영, 무해.)

## 3. 롤백 전략

- **Code:** Task별 커밋 역순 `git revert`. 진화만 끄려면 Task 2 revert(배치에서 진화 job 제거) — trait_params는 남아도 무해.
- **Config:** cron 시각은 `population_batch.py`의 `hour=4`. `DISABLE_SCHEDULER=1`로 전체 스케줄러 비기동.
- **신규 의존성·마이그레이션:** 없음.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 14:40] [구현계획서-수정]
- **id**: CH-20260617-003
- **이유**: 신규 구현계획서 작성 (페르소나 진화 엔진, 2 TDD task)
- **무엇이**: persona-evolution-engine-implementation-plan.md §1(Task 1~2), §2 위험, §3 롤백
- **영향범위**: ulssu_backend(persona_evolution 신설 + population_batch 연동). 마이그레이션 없음.
- **연관 항목**: CH-20260617-001, CH-20260617-002

### [2026-06-17 14:50] [코드-수정] (batch: tasks 1..2)
- **id**: CH-20260617-004
- **이유**: 페르소나 진화 엔진 구현(2 task). comment_reactions⋈comments.name +1/−1 합산 → trait_params{prefs,hint} 갱신, 일일 배치 연동. Phase 3 데이터 루프 완성.
- **무엇이**: `ulssu_backend/persona_evolution.py`(신설), `population_batch.py`(스케줄러 연동), `tests/test_persona_evolution.py`(신설)
- **영향범위**: 일일 배치(기동+4시)가 모든 ai_personas의 trait_params를 유저 댓글 반응으로 갱신. 댓글 생성/한계선 불변(저장만). 마이그레이션 없음.
- **위험 카테고리**: side-effect(배치 순회→유저 단위 격리), race(일별 스냅샷) — §2 사전 식별
- **task별 세부 (2건)**:
  - PE1: `persona_evolution.py` — compute/build_hint/run + 유닛 3 (side-effect) — commits: `6efc7fe`, `77554c0`(테스트 detached 픽스)
  - PE2: `population_batch.py` — start_scheduler에 진화 job (side-effect) — `30b5964`
- **테스트 결과**: 백엔드 57 passed.
- **비고**: PE1 첫 커밋(6efc7fe)에 테스트 detached 버그 → 즉시 77554c0로 수정(파이프 exit code 가림 회고).
- **연관 commits**: `6efc7fe..30b5964`
- **변경 전/후 코드**: 생략 — `git show <SHA>`
- **연관 항목**: CH-20260617-003
