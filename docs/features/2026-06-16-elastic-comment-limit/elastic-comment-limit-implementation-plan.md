---
commit_policy: per-task
---

# 가변적 한계선 + 실시간 반응 구현계획서

> **다음 단계 안내**: 이 계획을 task-by-task 로 실행하려면 `js-super-sub-driven` (보조 에이전트 강제 모드, 권장) 또는 `executing-plans` (인라인 모드) 를 사용하세요. 각 step 은 체크박스 (`- [ ]`) 형식이라 진행 상황 추적이 가능합니다.

**Goal:** 모든 글이 유형별 최소 10개 이상의 댓글을 받고(소외 금지), 반응(좋아요/싫어요 무관)이 쌓일수록 토론이 커지며, 전체 유저수가 25를 넘으면 상한이 유저수에 비례해 확장된다. 각 댓글의 분량은 짧게~길게 랜덤 변주하고, 상한 도달 시 중재자 없이 조용히 종료한다.

**Architecture:** FastAPI + SQLAlchemy 위에 순수 모듈 — 수식(`elastic_limit.py`), 인구 상태 훅(`population.py`), 페르소나(`personas.py`), 댓글 분량 스타일(`comment_style.py`) — 을 분리한다. 반응은 카운터 증분이 아니라 타임스탬프 개별 레코드(스택)로 적재해 동시 클릭 경합을 제거하고, 총 반응 수는 COUNT로 집계한다. 반응 카운트는 응답에 노출하지 않는다.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, OpenAI SDK, pytest + httpx(TestClient), 테스트 DB는 SQLite in-memory.

**Spec inputs:**
- `elastic-comment-limit-requirements.md` — §0 서비스 핵심(관심/소외 금지), FR-1~FR-13
- `elastic-comment-limit-tech-design.md` — D1~D7 결정, §3 데이터 모델, §4 API, §6 위험, §7 테스트 전략

---

## 1. 단계별 작업

### Task 1: 의존성 추가 + `elastic_limit` 순수 로직

**Files:**
- Modify: `pyproject.toml` (uv 명령으로 dev deps 추가)
- Create: `ulssu_backend/elastic_limit.py`
- Test: `ulssu_backend/tests/test_elastic_limit.py`

**Model**: sonnet

- [ ] **Step 1: dev 의존성 추가**

Run: `uv add --dev pytest httpx`
Expected: `pyproject.toml` dev 그룹에 `pytest`, `httpx` 추가 + `uv.lock` 갱신.

- [ ] **Step 2: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_elastic_limit.py`):
```python
from elastic_limit import (
    BASE_HARD_CAP,
    compute_base_limit,
    compute_effective_cap,
    compute_final_limit,
    should_lock,
)


def test_base_limit_all_tiers_at_least_ten():
    # 소외 금지: 모든 유형 10개 이상
    assert compute_base_limit(40) == 10   # 잡담
    assert compute_base_limit(59) == 10
    assert compute_base_limit(60) == 15   # 일반
    assert compute_base_limit(89) == 15
    assert compute_base_limit(90) == 20   # 명글
    assert compute_base_limit(100) == 20


def test_effective_cap_fixed_then_scales_with_population():
    assert BASE_HARD_CAP == 25
    assert compute_effective_cap(0) == 25     # 유저 없음 -> 고정 상한
    assert compute_effective_cap(25) == 25
    assert compute_effective_cap(100) == 100  # 유저>25 -> 유저수에 비례


def test_final_limit_neutral_equals_base():
    assert compute_final_limit(10, 0, 0) == 10
    assert compute_final_limit(15, 0, 0) == 15
    assert compute_final_limit(20, 0, 0) == 20


def test_final_limit_grows_with_total_reactions():
    # 10 * (1 + 5*0.1) = 15.0 -> 15
    assert compute_final_limit(10, 5, 0) == 15
    # 20 * (1 + 1*0.1) = 22.0 -> 22
    assert compute_final_limit(20, 1, 0) == 22


def test_final_limit_clamped_to_fixed_cap_when_population_small():
    # 20 * (1 + 3*0.1) = 26.0 -> clamp 25 (population 0)
    assert compute_final_limit(20, 3, 0) == 25


def test_final_limit_can_exceed_25_when_population_large():
    # population 100 -> cap 100, 20 * 1.5 = 30 (clamp 안 됨)
    assert compute_final_limit(20, 5, 100) == 30


def test_final_limit_never_below_base():
    assert compute_final_limit(15, 0, 0) == 15


def test_should_lock_only_at_cap():
    assert should_lock(current_comment_count=24, effective_cap=25) is False
    assert should_lock(current_comment_count=25, effective_cap=25) is True
    assert should_lock(current_comment_count=20, effective_cap=100) is False
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_elastic_limit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'elastic_limit'`

- [ ] **Step 4: 최소 구현 작성**

**수정 후** (new file: `ulssu_backend/elastic_limit.py`):
```python
"""글 점수 + 반응 총량 + 전체 유저수 기반 가변적 댓글 한계선 순수 로직.

외부 의존(DB/OpenAI) 없는 순수 함수만 둔다. PRD §3.3 수식의 단일 출처.
서비스 핵심(소외 금지): 모든 유형의 Base Limit 은 10 이상.
"""

# --- 설정 상수 ---
BASE_HARD_CAP = 25  # 유저가 적을 때의 고정 상한. 유저수가 이를 넘으면 상한도 확장.
ADJUST_STEP = 0.1   # 반응 1건(좋아요/싫어요 무관)당 증감률


def compute_base_limit(score: int) -> int:
    """채점 점수 → 유형별 기본 한계선. 0개 유형 없음(소외 금지)."""
    if score >= 90:
        return 20
    if score >= 60:
        return 15
    return 10


def compute_effective_cap(current_population: int) -> int:
    """유저 적을 땐 고정 25, 유저수가 25를 넘으면 유저수에 비례해 상한 확장."""
    return max(BASE_HARD_CAP, current_population)


def compute_final_limit(base_limit: int, total_reactions: int, current_population: int) -> int:
    """Final Limit = round( base × (1 + 총반응수 × STEP) ), [base, effective_cap] 클램프.

    round 는 round-half-up(`int(x + 0.5)`)로 고정. 좋아요/싫어요 구분 없이 총량만 사용.
    """
    cap = compute_effective_cap(current_population)
    adjust_rate = total_reactions * ADJUST_STEP
    final = int(base_limit * (1 + adjust_rate) + 0.5)
    if final < base_limit:
        final = base_limit
    if final > cap:
        final = cap
    return final


def should_lock(current_comment_count: int, effective_cap: int) -> bool:
    """현재 댓글 수가 상한(Cap)에 도달하면 잠근다. 중재자 요약 없이 조용히 종료."""
    return current_comment_count >= effective_cap
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_elastic_limit.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml uv.lock ulssu_backend/elastic_limit.py ulssu_backend/tests/test_elastic_limit.py
git commit -m "feat(backend): elastic limit 순수 수식(소외 금지 base10+ / 유저수 상한) + 테스트 의존성"
```

---

### Task 2: 인구 상태 훅 (`population.py`)

**Files:**
- Create: `ulssu_backend/population.py`
- Test: `ulssu_backend/tests/test_population.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_population.py`):
```python
import pytest

import population


def test_default_population_is_zero():
    population.set_current_population(0)
    assert population.get_current_population() == 0


def test_set_and_get_population():
    population.set_current_population(100)
    assert population.get_current_population() == 100
    population.set_current_population(0)  # 테스트 격리 위해 원복


def test_negative_population_rejected():
    with pytest.raises(ValueError):
        population.set_current_population(-1)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_population.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'population'`

- [ ] **Step 3: 최소 구현 작성**

**수정 후** (new file: `ulssu_backend/population.py`):
```python
"""전체 유저수(current_population) 인메모리 상태 훅.

이 슬라이스는 값을 읽고 쓰는 인터페이스만 제공한다. 실제 일일 새벽 배치 집계는
별도 슬라이스(PRD §3.4)가 set_current_population 으로 주입한다.
"""

_current_population = 0


def get_current_population() -> int:
    return _current_population


def set_current_population(value: int) -> None:
    if value < 0:
        raise ValueError("population must be non-negative")
    global _current_population
    _current_population = value
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_population.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add ulssu_backend/population.py ulssu_backend/tests/test_population.py
git commit -m "feat(backend): current_population 인메모리 훅(일일배치 주입용)"
```

---

### Task 3: 페르소나 풀 + 순환 선택

**Files:**
- Create: `ulssu_backend/personas.py`
- Test: `ulssu_backend/tests/test_personas.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_personas.py`):
```python
from personas import PERSONA_POOL, get_personas


def test_pool_has_at_least_16_unique_personas():
    assert len(PERSONA_POOL) >= 16
    names = [name for name, _ in PERSONA_POOL]
    assert len(set(names)) == len(names)  # 이름 중복 없음


def test_each_persona_is_name_prompt_pair():
    for name, prompt in PERSONA_POOL:
        assert isinstance(name, str) and name
        assert isinstance(prompt, str) and prompt


def test_get_personas_returns_requested_count():
    assert get_personas(3) == PERSONA_POOL[:3]
    assert len(get_personas(5)) == 5


def test_get_personas_cycles_when_exceeding_pool():
    n = len(PERSONA_POOL) + 2
    result = get_personas(n)
    assert len(result) == n
    assert result[len(PERSONA_POOL)] == PERSONA_POOL[0]  # 순환 복귀


def test_get_personas_start_offset():
    assert get_personas(2, start=1) == PERSONA_POOL[1:3]


def test_get_personas_zero_or_negative():
    assert get_personas(0) == []
    assert get_personas(-3) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_personas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'personas'`

- [ ] **Step 3: 최소 구현 작성**

**수정 후** (new file: `ulssu_backend/personas.py`):
```python
"""'AI 광장' 시민 페르소나 풀 + 순환 선택기.

상한(Cap)이 유저수만큼 커질 수 있으므로 16종을 정의하고, 요청 수가 풀을 넘으면
순환 재사용한다. 각 항목은 (이름, 페르소나 프롬프트) 튜플.
"""

PERSONA_POOL: list[tuple[str, str]] = [
    ("냉철 김박사", "T 성향 100%. 팩트와 현실적 해결책만 제시. 딱딱하지만 예의 바름."),
    ("공감 요정 웅이", "F 성향 100%. 따뜻한 위로. 차갑게 말하는 AI가 있으면 닉네임을 콕 집어 따진다."),
    ("삐딱 키보드워리어", "냉소적이고 비꼬는 성향. 다른 AI의 위선·논리 오류를 비웃고 딴지 건다."),
    ("동네 꼰대 어르신", "허허 웃으며 '라떼는 말이야'를 시전하고 뜬금없는 훈수를 둔다."),
    ("팩트체커 리나", "근거와 출처를 따지며 과장된 주장에 침착하게 제동을 건다."),
    ("스토아 현자", "감정에 휘둘리지 말라며 통제 가능한 것에 집중하라고 조언한다."),
    ("긍정 에너자이저", "무조건 잘 될 거라며 과하게 밝은 응원을 쏟아낸다."),
    ("음모론자 박씨", "모든 일에 숨은 배후가 있다고 의심하며 엉뚱한 가설을 던진다."),
    ("MZ 인턴 지우", "유행어와 줄임말을 섞어 가볍고 빠르게 반응한다."),
    ("경제 분석가 한실장", "숫자·확률·기대값으로 상황을 건조하게 분석한다."),
    ("감성 시인 노을", "은유와 비유로 마음을 어루만지는 문학적 댓글을 단다."),
    ("독설 평론가 최가시", "날카롭게 핵심을 찌르되 결국 도움이 되는 쓴소리를 한다."),
    ("중립 관망러", "양쪽 입장을 정리하며 어느 편도 들지 않고 균형을 맞춘다."),
    ("실전 행동파 강대리", "분석은 그만하고 당장 할 수 있는 행동 한 가지를 제시한다."),
    ("따뜻한 상담사 윤", "판단 없이 경청하고 감정을 이름 붙여 정리해 준다."),
    ("장난꾸러기 트롤", "진지한 흐름에 가벼운 농담으로 분위기를 환기한다."),
]


def get_personas(count: int, start: int = 0) -> list[tuple[str, str]]:
    """`start` 오프셋부터 `count`개의 페르소나를 풀을 순환하며 반환."""
    if count <= 0:
        return []
    pool = PERSONA_POOL
    return [pool[(start + i) % len(pool)] for i in range(count)]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_personas.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add ulssu_backend/personas.py ulssu_backend/tests/test_personas.py
git commit -m "feat(backend): 페르소나 풀 16종 + 순환 선택기"
```

---

### Task 4: 댓글 분량 스타일 (`comment_style.py`)

**Files:**
- Create: `ulssu_backend/comment_style.py`
- Test: `ulssu_backend/tests/test_comment_style.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_comment_style.py`):
```python
import random

from comment_style import LENGTH_STYLES, pick_length_style


def test_has_at_least_three_varied_styles():
    assert len(LENGTH_STYLES) >= 3
    assert len(set(LENGTH_STYLES)) == len(LENGTH_STYLES)  # 중복 없음


def test_pick_returns_a_pool_member():
    assert pick_length_style(random.Random(0)) in LENGTH_STYLES


def test_pick_is_deterministic_with_same_seed():
    assert pick_length_style(random.Random(7)) == pick_length_style(random.Random(7))


def test_pick_varies_across_seeds():
    picks = {pick_length_style(random.Random(s)) for s in range(50)}
    assert len(picks) >= 2  # 시드별로 분량이 갈린다(다양성)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_comment_style.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'comment_style'`

- [ ] **Step 3: 최소 구현 작성**

**수정 후** (new file: `ulssu_backend/comment_style.py`):
```python
"""댓글 분량(길이) 변주 스타일.

긴 글/짧은 글이 섞여 실제 게시판처럼 보이도록(FR-13), 댓글마다 길이 지침을 랜덤 선택한다.
선택 함수는 random.Random 주입을 허용해 테스트 결정성을 확보한다.
"""

import random

LENGTH_STYLES: list[str] = [
    "한 줄 이내로 짧고 강렬하게",
    "2~3줄 정도로 적당히",
    "5~6줄로 길고 자세하게 풀어서",
]


def pick_length_style(rng: random.Random | None = None) -> str:
    """분량 후보군에서 하나를 랜덤 선택. rng 주입 시 결정적."""
    chooser = rng if rng is not None else random
    return chooser.choice(LENGTH_STYLES)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_comment_style.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add ulssu_backend/comment_style.py ulssu_backend/tests/test_comment_style.py
git commit -m "feat(backend): 댓글 분량 랜덤 스타일(짧게/보통/길게) 모듈"
```

---

### Task 5: DB 스키마 (`is_locked` + `ReactionModel` 스택 + SQLite 호환)

**Files:**
- Modify: `ulssu_backend/database.py:2`, `ulssu_backend/database.py:12`, `ulssu_backend/database.py:17-22`, `ulssu_backend/database.py:24-30`
- Test: `ulssu_backend/tests/test_schema.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_schema.py`):
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import PostModel, ReactionModel


def _sqlite_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_post_has_is_locked_default_false():
    db = _sqlite_session()
    try:
        post = PostModel(content="테스트 글", score=95)
        db.add(post)
        db.commit()
        db.refresh(post)
        assert post.is_locked is False
    finally:
        db.close()


def test_reaction_row_stacks_with_timestamp():
    db = _sqlite_session()
    try:
        post = PostModel(content="테스트 글", score=70)
        db.add(post)
        db.commit()
        db.refresh(post)
        db.add(ReactionModel(post_id=post.id, reaction_type="like"))
        db.add(ReactionModel(post_id=post.id, reaction_type="dislike"))
        db.commit()
        rows = db.query(ReactionModel).filter(ReactionModel.post_id == post.id).all()
        assert len(rows) == 2  # 스택 적재
        assert all(r.created_at is not None for r in rows)  # 타임스탬프 부여
    finally:
        db.close()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'ReactionModel'`

- [ ] **Step 3: import 보강 (Boolean, DateTime, func)**

**원본** (`ulssu_backend/database.py:2`):
```python
from sqlalchemy import create_engine, Column, Integer, Text, String, ForeignKey
```

**수정 후**:
```python
from sqlalchemy import (
    create_engine, Column, Integer, Text, String,
    ForeignKey, Boolean, DateTime, func,
)
```

- [ ] **Step 4: 엔진에 SQLite connect_args 분기 추가**

**원본** (`ulssu_backend/database.py:12`):
```python
engine = create_engine(DATABASE_URL)
```

**수정 후**:
```python
# SQLite(테스트)일 때만 단일 커넥션/스레드 옵션을 적용. PostgreSQL(운영)은 기본값.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
```

- [ ] **Step 5: PostModel에 `is_locked` 추가**

**원본** (`ulssu_backend/database.py:17-22`):
```python
class PostModel(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    score = Column(Integer, nullable=False)
    comments = relationship("CommentModel", back_populates="post", cascade="all, delete-orphan")
```

**수정 후**:
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

- [ ] **Step 6: ReactionModel 신설 (타임스탬프 스택)**

`CommentModel` 정의 바로 아래(`get_db` 정의 위)에 추가한다.

**원본** (`ulssu_backend/database.py:24-30`):
```python
class CommentModel(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"))
    name = Column(String, nullable=False)
    comment = Column(Text, nullable=False)
    post = relationship("PostModel", back_populates="comments")
```

**수정 후**:
```python
class CommentModel(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"))
    name = Column(String, nullable=False)
    comment = Column(Text, nullable=False)
    post = relationship("PostModel", back_populates="comments")


class ReactionModel(Base):
    # 좋아요/싫어요를 카운터가 아니라 개별 레코드(스택)로 적재 → 동시 클릭 경합 제거(FR-9).
    # 총 반응 수는 COUNT 집계. reaction_type 은 B2B 분석용 저장(수식은 총량만 사용).
    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    reaction_type = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_schema.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: 커밋**

```bash
git add ulssu_backend/database.py ulssu_backend/tests/test_schema.py
git commit -m "feat(backend): posts.is_locked + reactions 스택 테이블 + sqlite 테스트 호환"
```

---

### Task 6: 테스트 인프라(conftest) + OpenAI 키 env화

**Files:**
- Modify: `ulssu_backend/main.py:25-26`
- Create: `ulssu_backend/tests/conftest.py`
- Test: `ulssu_backend/tests/test_smoke.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 스모크 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_smoke.py`):
```python
def test_get_posts_empty(client):
    resp = client.get("/api/posts")
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 2: 테스트 실패 확인 (fixture 부재)**

Run: `cd ulssu_backend && uv run pytest tests/test_smoke.py -v`
Expected: FAIL — `fixture 'client' not found`

- [ ] **Step 3: 하드코딩된 OpenAI 키 제거 (env 사용)**

**원본** (`ulssu_backend/main.py:25-26`):
```python
os.environ["OPENAI_API_KEY"] = "sk-proj-REDACTED"
client = OpenAI()
```

**수정 후**:
```python
# OPENAI_API_KEY 는 환경변수에서 읽는다(소스 하드코딩 금지 — 노출된 기존 키는 폐기/회전 필요).
client = OpenAI()
```

- [ ] **Step 4: conftest 작성 (import 전 env 세팅 + DB override + AI 모킹 + population 격리)**

**수정 후** (new file: `ulssu_backend/tests/conftest.py`):
```python
import os

# main/database import 전에 반드시 먼저 세팅 (모듈 로드 시 엔진 생성 + create_all 실행됨)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["OPENAI_API_KEY"] = "test-dummy-key"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import main
import population


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    database.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[database.get_db] = override_get_db

    # 인메모리 전역 상태 격리: 각 테스트 시작 시 0으로 리셋
    population.set_current_population(0)

    # OpenAI 호출 함수 결정적 더미로 치환 (실제 네트워크 호출 차단).
    # generate_ai_comment 는 length_hint 까지 4개 인자를 받는다(Task 7에서 시그니처 확정).
    monkeypatch.setattr(main, "evaluate_post_quality", lambda user_post: 95, raising=False)
    monkeypatch.setattr(
        main,
        "generate_ai_comment",
        lambda persona_prompt, user_post, previous, length_hint: "AI 댓글",
        raising=False,
    )

    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
    population.set_current_population(0)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: 커밋**

```bash
git add ulssu_backend/main.py ulssu_backend/tests/conftest.py ulssu_backend/tests/test_smoke.py
git commit -m "test(backend): conftest(sqlite override+AI 모킹+population 격리) + OpenAI 키 env화"
```

---

### Task 7: `create_post` 리팩터 + `generate_ai_comment` 분량 주입

**Files:**
- Modify: `ulssu_backend/main.py:9-10` (imports), `ulssu_backend/main.py:57-68` (generate_ai_comment), `ulssu_backend/main.py:77-113` (create_post)
- Test: `ulssu_backend/tests/test_create_post.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 통합 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_create_post.py`):
```python
import main


def test_create_post_chitchat_still_gets_ten_comments(client, monkeypatch):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 40)  # 잡담 base 10
    resp = client.post("/api/posts", json={"content": "돈까스 땡긴다"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 40
    assert body["is_locked"] is False
    assert len(body["comments"]) == 10  # 소외 금지: 잡담도 10개


def test_create_post_normal_gets_fifteen(client, monkeypatch):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 70)  # 일반 base 15
    body = client.post("/api/posts", json={"content": "이직 고민"}).json()
    assert len(body["comments"]) == 15


def test_create_post_hot_gets_twenty(client, monkeypatch):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 95)  # 명글 base 20
    body = client.post("/api/posts", json={"content": "영끌 주식 마이너스 20%"}).json()
    assert len(body["comments"]) == 20


def test_create_post_response_hides_reaction_counts(client, monkeypatch):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 70)
    body = client.post("/api/posts", json={"content": "테스트"}).json()
    assert "like_count" not in body
    assert "dislike_count" not in body
    assert "reactions" not in body  # 반응 카운트/목록 비노출 (FR-3)


def test_create_post_comments_use_length_styles(client, monkeypatch):
    import comment_style
    captured = []

    def fake_comment(persona_prompt, user_post, previous, length_hint):
        captured.append(length_hint)
        return "AI 댓글"

    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 40)  # 10개
    monkeypatch.setattr(main, "generate_ai_comment", fake_comment)
    client.post("/api/posts", json={"content": "테스트"})
    assert len(captured) == 10
    assert all(h in comment_style.LENGTH_STYLES for h in captured)  # 분량 변주 주입(FR-13)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_create_post.py -v`
Expected: FAIL — 잡담 댓글 수가 2로 나옴(`assert 2 == 10`) + `KeyError: 'is_locked'`

- [ ] **Step 3: import 추가 (elastic_limit, personas, population, comment_style)**

**원본** (`ulssu_backend/main.py:9-10`):
```python
import database
from database import get_db, PostModel, CommentModel
```

**수정 후**:
```python
import database
from database import get_db, PostModel, CommentModel, ReactionModel
from elastic_limit import (
    compute_base_limit, compute_final_limit, compute_effective_cap, should_lock,
)
from personas import get_personas
from population import get_current_population
from comment_style import pick_length_style
```

- [ ] **Step 4: generate_ai_comment 에 length_hint 주입**

**원본** (`ulssu_backend/main.py:57-68`):
```python
def generate_ai_comment(persona_prompt: str, user_post: str, previous_comments: str) -> str:
    system_instruction = f"너는 'AI 광장'이라는 커뮤니티의 시민이야. 아래 페르소나에 맞춰 2~3줄 내외의 댓글을 달아줘.\n[너의 페르소나]\n{persona_prompt}"
    user_content = f"유저의 게시글: '{user_post}'\n\n[현재 댓글 상황]\n{previous_comments}\n\n의견을 달아줘."
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ],
        temperature=0.8
    )
    return response.choices[0].message.content
```

**수정 후**:
```python
def generate_ai_comment(persona_prompt: str, user_post: str, previous_comments: str, length_hint: str) -> str:
    system_instruction = (
        "너는 'AI 광장'이라는 커뮤니티의 시민이야. 아래 페르소나에 맞춰 댓글을 달아줘.\n"
        f"[너의 페르소나]\n{persona_prompt}\n"
        f"[분량] {length_hint}"
    )
    user_content = f"유저의 게시글: '{user_post}'\n\n[현재 댓글 상황]\n{previous_comments}\n\n의견을 달아줘."
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ],
        temperature=0.8
    )
    return response.choices[0].message.content
```

- [ ] **Step 5: create_post 리팩터**

**원본** (`ulssu_backend/main.py:77-113`):
```python
@app.post("/api/posts")
async def create_post(request: PostRequest, db: Session = Depends(get_db)):
    user_post = request.content
    
    score = evaluate_post_quality(user_post)
    max_comments = 4 if score >= 90 else (2 if score >= 60 else 2)

    # 1. 원문 글 저장하여 고유 ID 확보
    db_post = PostModel(content=user_post, score=score)
    db.add(db_post)
    db.commit()
    db.refresh(db_post)

    persona_pool = [
        ("냉철 김박사", "T 성향 100%. 팩트 폭행 위주."),
        ("공감 요정 웅이", "F 성향 100%. 위로와 다른 AI 저격 위주."),
        ("삐딱 키보드워리어", "냉소적이고 비꼬는 성향. 시비 걸기 좋아함."),
        ("동네 꼰대 어르신", "허허 웃으며 '라떼는 말이야'를 시전하고 뜬금없는 훈수를 두며 참견함.")
    ]
    
    chat_history = ""
    
    # 2. AI 배틀을 진행하며 생성되는 댓글을 순차적으로 DB 레코드로 박아넣기
    for name, prompt in persona_pool:
        if db.query(CommentModel).filter(CommentModel.post_id == db_post.id).count() >= max_comments:
            break
            
        comment_text = generate_ai_comment(prompt, user_post, chat_history)
        
        db_comment = CommentModel(post_id=db_post.id, name=name, comment=comment_text)
        db.add(db_comment)
        chat_history += f"{name}: {comment_text}\n"
        
    db.commit() # 트랜잭션 최종 확정
    db.refresh(db_post) # 자식 레코드(comments) 상태 동기화

    return db_post
```

**수정 후**:
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

    # 2. Final Limit 만큼 페르소나를 순환 선택해 생성. 분량은 매번 랜덤 변주(FR-13).
    chat_history = ""
    for name, prompt in get_personas(final_limit):
        comment_text = generate_ai_comment(prompt, user_post, chat_history, pick_length_style())
        db.add(CommentModel(post_id=db_post.id, name=name, comment=comment_text))
        chat_history += f"{name}: {comment_text}\n"

    db.commit()       # 트랜잭션 최종 확정
    db.refresh(db_post)  # 자식 레코드(comments) 상태 동기화

    return db_post
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_create_post.py -v`
Expected: PASS (5 passed)

- [ ] **Step 7: 커밋**

```bash
git add ulssu_backend/main.py ulssu_backend/tests/test_create_post.py
git commit -m "feat(backend): create_post 리팩터(소외 금지 base10+, 카운트 비노출) + 댓글 분량 랜덤 주입"
```

---

### Task 8: 반응 엔드포인트 (`POST /api/posts/{id}/reaction`) — 스택 적재 + 성장

**Files:**
- Modify: `ulssu_backend/main.py:3` (HTTPException), `ulssu_backend/main.py:28-29` (ReactionRequest), generate_ai_comment 아래(헬퍼), 파일 끝(라우트)
- Test: `ulssu_backend/tests/test_reaction_api.py`

**Model**: sonnet

- [ ] **Step 1: 실패하는 통합 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_reaction_api.py`):
```python
import main


def _create(client, monkeypatch, score):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: score)
    return client.post("/api/posts", json={"content": "테스트 고민 글"}).json()


def test_reaction_stacks_and_grows_comments(client, monkeypatch):
    post = _create(client, monkeypatch, 70)  # base 15 -> 댓글 15
    assert len(post["comments"]) == 15
    # 15 * (1 + 1*0.1) = 16.5 -> 17 : 좋아요든 싫어요든 토론이 커짐
    resp = client.post(f"/api/posts/{post['id']}/reaction", json={"reaction": "dislike"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["comments"]) == 17
    assert body["is_locked"] is False
    # 응답에 반응 카운트 비노출(FR-3)
    assert "like_count" not in body and "dislike_count" not in body


def test_invalid_reaction_returns_400(client, monkeypatch):
    post = _create(client, monkeypatch, 70)
    resp = client.post(f"/api/posts/{post['id']}/reaction", json={"reaction": "love"})
    assert resp.status_code == 400


def test_reaction_on_missing_post_returns_404(client):
    resp = client.post("/api/posts/99999/reaction", json={"reaction": "like"})
    assert resp.status_code == 404
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_reaction_api.py -v`
Expected: FAIL — `405`/`404` (라우트 미존재)

- [ ] **Step 3: HTTPException import 보강**

**원본** (`ulssu_backend/main.py:3`):
```python
from fastapi import FastAPI, Depends
```

**수정 후**:
```python
from fastapi import FastAPI, Depends, HTTPException
```

- [ ] **Step 4: ReactionRequest 모델 추가**

**원본** (`ulssu_backend/main.py:28-29`):
```python
class PostRequest(BaseModel):
    content: str
```

**수정 후**:
```python
class PostRequest(BaseModel):
    content: str


class ReactionRequest(BaseModel):
    reaction: str  # "like" | "dislike"
```

- [ ] **Step 5: 댓글 추가 생성 헬퍼 추가**

Task 7에서 length_hint 가 추가된 `generate_ai_comment` 정의 바로 아래에 헬퍼를 추가한다.

**원본** (`ulssu_backend/main.py` — Task 7 적용 후의 generate_ai_comment):
```python
def generate_ai_comment(persona_prompt: str, user_post: str, previous_comments: str, length_hint: str) -> str:
    system_instruction = (
        "너는 'AI 광장'이라는 커뮤니티의 시민이야. 아래 페르소나에 맞춰 댓글을 달아줘.\n"
        f"[너의 페르소나]\n{persona_prompt}\n"
        f"[분량] {length_hint}"
    )
    user_content = f"유저의 게시글: '{user_post}'\n\n[현재 댓글 상황]\n{previous_comments}\n\n의견을 달아줘."
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ],
        temperature=0.8
    )
    return response.choices[0].message.content
```

**수정 후**:
```python
def generate_ai_comment(persona_prompt: str, user_post: str, previous_comments: str, length_hint: str) -> str:
    system_instruction = (
        "너는 'AI 광장'이라는 커뮤니티의 시민이야. 아래 페르소나에 맞춰 댓글을 달아줘.\n"
        f"[너의 페르소나]\n{persona_prompt}\n"
        f"[분량] {length_hint}"
    )
    user_content = f"유저의 게시글: '{user_post}'\n\n[현재 댓글 상황]\n{previous_comments}\n\n의견을 달아줘."
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ],
        temperature=0.8
    )
    return response.choices[0].message.content


def _count_comments(db: Session, post_id: int) -> int:
    return db.query(CommentModel).filter(CommentModel.post_id == post_id).count()


def _count_reactions(db: Session, post_id: int) -> int:
    return db.query(ReactionModel).filter(ReactionModel.post_id == post_id).count()


def _build_chat_history(db: Session, post_id: int) -> str:
    rows = (
        db.query(CommentModel)
        .filter(CommentModel.post_id == post_id)
        .order_by(CommentModel.id.asc())
        .all()
    )
    return "".join(f"{r.name}: {r.comment}\n" for r in rows)


def _generate_more_comments(db: Session, db_post: PostModel, count: int) -> None:
    """현재 댓글 수를 start 오프셋으로 페르소나를 순환 선택해 count개를 생성. 분량은 랜덤(FR-13)."""
    start = _count_comments(db, db_post.id)
    chat_history = _build_chat_history(db, db_post.id)
    for name, prompt in get_personas(count, start=start):
        comment_text = generate_ai_comment(prompt, db_post.content, chat_history, pick_length_style())
        db.add(CommentModel(post_id=db_post.id, name=name, comment=comment_text))
        chat_history += f"{name}: {comment_text}\n"
```

- [ ] **Step 6: 반응 라우트 추가 (파일 끝에 append)**

**수정 후** (append to `ulssu_backend/main.py`):
```python
# 📌 3. 반응 등록 → 스택 적재 → Final 재계산 → 부족분 생성 → Cap 도달 시 조용히 종료
@app.post("/api/posts/{post_id}/reaction")
def react_to_post(post_id: int, request: ReactionRequest, db: Session = Depends(get_db)):
    db_post = db.query(PostModel).filter(PostModel.id == post_id).first()
    if db_post is None:
        raise HTTPException(status_code=404, detail="post not found")
    if request.reaction not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="reaction must be 'like' or 'dislike'")

    # 카운터 증분이 아니라 개별 레코드(스택)로 적재 → 동시 클릭 경합 제거(FR-9)
    db.add(ReactionModel(post_id=post_id, reaction_type=request.reaction))
    db.commit()
    db.refresh(db_post)

    # 잠긴 스레드는 반응만 기록하고 생성/종료 없음 (FR-8)
    if not db_post.is_locked:
        base = compute_base_limit(db_post.score)
        population = get_current_population()
        total_reactions = _count_reactions(db, post_id)
        final = compute_final_limit(base, total_reactions, population)
        current = _count_comments(db, post_id)
        if current < final:
            _generate_more_comments(db, db_post, final - current)
            db.commit()
        if should_lock(_count_comments(db, post_id), compute_effective_cap(population)):
            db_post.is_locked = True  # Cap 도달 → 중재자 없이 조용히 종료(FR-7)
            db.commit()

    db.refresh(db_post)
    return db_post
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_reaction_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 8: 커밋**

```bash
git add ulssu_backend/main.py ulssu_backend/tests/test_reaction_api.py
git commit -m "feat(backend): reaction 엔드포인트(스택 적재+총량 기반 성장, 카운트 비노출)"
```

---

### Task 9: Cap 종료 / 유저수 확장 / 멱등 회귀 검증

**Files:**
- Test: `ulssu_backend/tests/test_lock_and_scale.py`
- (구현은 Task 7·8에서 완료 — 종료/확장/멱등 시나리오를 회귀로 고정)

**Model**: sonnet

- [ ] **Step 1: 시나리오 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_lock_and_scale.py`):
```python
import main
import population


def _create(client, monkeypatch, score):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: score)
    return client.post("/api/posts", json={"content": "테스트 고민 글"}).json()


def test_reaches_cap_and_locks_without_moderator(client, monkeypatch):
    # population 0 -> cap 25. 명글 base 20.
    post = _create(client, monkeypatch, 95)
    pid = post["id"]
    assert len(post["comments"]) == 20

    body = None
    for _ in range(5):
        body = client.post(f"/api/posts/{pid}/reaction", json={"reaction": "like"}).json()
        if body["is_locked"]:
            break
    assert body["is_locked"] is True
    assert len(body["comments"]) == 25  # Cap 25 도달
    # 중재자 댓글 없음(FR-7)
    assert all(c["name"] != "중재자 AI" for c in body["comments"])


def test_locked_thread_is_idempotent(client, monkeypatch):
    post = _create(client, monkeypatch, 95)
    pid = post["id"]
    body = None
    for _ in range(5):
        body = client.post(f"/api/posts/{pid}/reaction", json={"reaction": "like"}).json()
        if body["is_locked"]:
            break
    locked_count = len(body["comments"])
    # 잠긴 뒤 추가 반응: 댓글 수 불변 (FR-8)
    body2 = client.post(f"/api/posts/{pid}/reaction", json={"reaction": "dislike"}).json()
    assert body2["is_locked"] is True
    assert len(body2["comments"]) == locked_count


def test_large_population_allows_more_than_25_comments(client, monkeypatch):
    population.set_current_population(100)  # cap 100 (AC-4)
    post = _create(client, monkeypatch, 95)  # base 20
    pid = post["id"]
    body = None
    for _ in range(4):
        body = client.post(f"/api/posts/{pid}/reaction", json={"reaction": "like"}).json()
    # 20 * (1 + 4*0.1) = 28 -> 28, cap 100이라 25 초과 허용
    assert len(body["comments"]) == 28
    assert body["is_locked"] is False
```

- [ ] **Step 2: 테스트 실행 (Task 7·8 구현이 충족하는지 확인)**

Run: `cd ulssu_backend && uv run pytest tests/test_lock_and_scale.py -v`
Expected: PASS (3 passed). FAIL이면 Task 8의 `react_to_post` 종료/생성 분기 또는 `population` 사용을 점검.

- [ ] **Step 3: 전체 테스트 스위트 실행**

Run: `cd ulssu_backend && uv run pytest -v`
Expected: PASS (전체 green — 단위 + 통합)

- [ ] **Step 4: 커밋**

```bash
git add ulssu_backend/tests/test_lock_and_scale.py
git commit -m "test(backend): Cap 종료(중재자 없음)+유저수 확장+멱등 회귀 고정"
```

---

## 2. 위험 코드 지점

- `ulssu_backend/main.py:react_to_post` / `_generate_more_comments` — **side-effect**: 반응 처리 중 동기 OpenAI 호출로 댓글을 생성. 속도는 비요구(FR-10)라 지연 자체는 허용이나, 유저수가 큰 글(Cap이 수백+)에서 한 번에 다량 생성 시 API 비용이 급증. (mitigation: `compute_final_limit`이 증감률을 반응 1건당 +0.1로 점증시켜 요청당 델타를 작게 유지. 비용 상한이 필요하면 요청당 생성 델타 cap 추가 — 후속 TODO.)
- `ulssu_backend/database.py:17-30` — **breaking**: `posts.is_locked` 추가 + `reactions` 테이블 신설. 기존 운영 PostgreSQL은 `Base.metadata.create_all`이 컬럼 ALTER/테이블 신설을 보장하지 않아 누락 가능. 응답에 `is_locked` 가산. (mitigation: dev DB는 재생성으로 충분. 운영은 수동 `ALTER TABLE posts ADD COLUMN is_locked ...` + `CREATE TABLE reactions ...` 또는 Alembic — §3 롤백 참조.)
- `ulssu_backend/main.py:react_to_post` (생성 경로) — **race**: 반응 적재는 스택 INSERT로 경합이 없으나(FR-9), 두 반응 요청이 거의 동시에 "부족분 생성"을 계산하면 Cap을 일시 초과해 생성할 수 있음. (mitigation: 생성 후 `should_lock` 재집계로 Cap 도달 시 잠금. 엄밀한 상한 보장이 필요하면 글 행 `SELECT ... FOR UPDATE`로 생성 구간 직렬화 — 후속.)

## 3. 롤백 전략

- **Code:** Task별 커밋이므로 `git revert <SHA>` 역순(Task 9→1). 또는 `git reset --hard <Task1 직전 SHA>`.
- **DB:** 운영 적용분 되돌릴 때 `ALTER TABLE posts DROP COLUMN is_locked;` + `DROP TABLE reactions;`. dev는 테이블 재생성(drop & create_all).
- **Config:** 한계선 동작은 `elastic_limit.py` 상수(`BASE_HARD_CAP`, `ADJUST_STEP`) + `comment_style.LENGTH_STYLES`로 제어 — 되돌리지 않고 값 조정으로 영향 축소 가능. 유저수 효과는 `population.set_current_population(0)`으로 고정 25 회귀. 신규 라우트 비활성화는 `react_to_post` 데코레이터 제거.
- **Secret:** Task 6에서 제거한 하드코딩 OpenAI 키는 **즉시 폐기/회전**(OpenAI 대시보드 revoke). `battle_arena.py`·`battle_arena_v2.py`에도 동일 키가 남아 있으니 함께 제거 — 롤백으로 복구 금지.

---
## 변경이력

### [2026-06-16 20:54] [구현계획서-수정]
- **id**: CH-20260616-001
- **이유**: 신규 구현계획서 작성 + 사용자 2차 피드백(소외 금지/총 반응 기반 성장/카운트 비노출/중재자 제거/유저수 상한/스택 반응/댓글 분량 랜덤) 반영 후 승인
- **무엇이**: `elastic-comment-limit-implementation-plan.md` §1 단계별 작업(9 Task), §2 위험 코드 지점, §3 롤백 전략 신규 작성
- **영향범위**: 동일 폴더 `elastic-comment-limit-requirements.md`(FR-1~13 + AC-1~8), `elastic-comment-limit-tech-design.md`(D1~7) 동기 개정. 구현 대상 코드: `ulssu_backend/`(elastic_limit·population·personas·comment_style 신규, database·main 수정)
- **연관 항목**: 없음 (최초 엔트리)

### [2026-06-17 01:03] [코드-수정] (batch: tasks 1..9)
- **id**: CH-20260617-001
- **이유**: 가변적 한계선 + 실시간 반응 슬라이스 전체 구현(9 Task TDD 완료). 소외 금지(전원 댓글 base10+)·총 반응 기반 성장·유저수 상한·스택 반응·중재자 없는 조용한 종료·댓글 분량 랜덤·반응 카운트 비노출.
- **무엇이**: `ulssu_backend/elastic_limit.py`, `population.py`, `personas.py`, `comment_style.py`, `database.py`, `main.py`, `conftest.py`, `tests/*`(8 파일), `pyproject.toml`, `uv.lock`
- **영향범위**: `create_post` 응답에 `is_locked` 가산(Flutter는 content/score/comments만 읽어 비파괴), 신규 `POST /api/posts/{id}/reaction`, `reactions` 테이블 신설 + `posts.is_locked` 컬럼. 운영 PostgreSQL은 수동 마이그레이션 필요.
- **위험 카테고리**: side-effect(동기 OpenAI 생성), breaking(스키마+응답 가산), race(동시 생성 Cap 일시초과) — 모두 §2에 사전 식별·완화 기재
- **task별 세부 (9건)**:
  - Task 1: `elastic_limit.py` + 의존성 — base/cap/final/should_lock 순수 수식 (none) — commits: `cb4f923`
  - Task 2: `population.py` — current_population 훅 (none) — commits: `6676035`
  - Task 3: `personas.py` — 16종 + 순환 (none) — commits: `c397457`
  - Task 4: `comment_style.py` — 분량 랜덤 스타일 (none) — commits: `c5216d8`
  - Task 5: `database.py` — is_locked + reactions 스택 + sqlite (breaking) — commits: `ab8f99b`
  - Task 6: `main.py`/`conftest.py` — 키 env화 + 테스트 인프라 (none) — commits: `994a615`
  - Task 7: `main.py` — create_post 리팩터 + generate_ai_comment length_hint (breaking, side-effect) — commits: `b7dd687`
  - Task 8: `main.py` — reaction 엔드포인트 + 스택/성장 (race, side-effect) — commits: `3cab552`
  - Task 9: `tests/test_lock_and_scale.py` — 종료/확장/멱등 회귀 (none) — commits: `1cd73d2`
- **계획 대비 보정 2건** (실행 중 발견):
  - `ulssu_backend/conftest.py`(루트, 빈 파일) 추가 — 평면 import 모듈을 tests/에서 import 가능하게 sys.path 보장 (Task 1)
  - `create_post`/`react_to_post`에 `_ = db_post.comments` 한 줄 추가 — `db.refresh` 후 lazy 관계가 직렬화에 누락되어 응답에 `comments`가 빠지는 문제 해결 (Task 7·8)
- **테스트 결과**: 전체 35 passed (단위 21 + 통합 14)
- **연관 commits**: `cb4f923..1cd73d2` (9 커밋)
- **변경 전/후 코드**: 생략 — `git show <SHA>` 로 조회 (git-fast 모드)
- **연관 항목**: CH-20260616-001
