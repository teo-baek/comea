---
commit_policy: per-task
---

# 일일 인구 배치 구현계획서

> **다음 단계 안내**: `js-super-sub-driven`(권장) 또는 `executing-plans`로 task-by-task 실행.

**Goal:** 기동 즉시 + 매일 4시 `COUNT(users)`를 집계해 `current_population`에 주입(APScheduler 인프로세스). 집계 로직은 테스트 가능한 함수로 분리, 테스트 중엔 스케줄러 미기동.

**Architecture:** `population_batch.py`에 `compute_population(db)`(COUNT)·`run_population_update()`(세션+set+예외격리)·`start/shutdown_scheduler()`(APScheduler, env 가드). FastAPI 기동/종료 이벤트가 스케줄러를 관리.

**Tech Stack:** FastAPI, SQLAlchemy, APScheduler. 테스트 SQLite.

**Spec inputs:**
- `daily-population-batch-requirements.md` — FR-1~5, AC-1~5
- `daily-population-batch-tech-design.md` — D1(BackgroundScheduler) D2(기동+cron) D3(분리) D4(예외격리) D5(env 가드)
- `docs/architecture/user-ai-persona-north-star.md` — §2 인구 배치

---

## 1. 단계별 작업

### Task 1: `population_batch.py` + 유닛 테스트

**Files:**
- Modify: `pyproject.toml` (uv add)
- Create: `ulssu_backend/population_batch.py`
- Test: `ulssu_backend/tests/test_population_batch.py`

**Model**: sonnet

- [ ] **Step 1: 의존성 추가**

Run: `uv add apscheduler`
Expected: `pyproject.toml`에 `apscheduler` 추가 + `uv.lock` 갱신.

- [ ] **Step 2: 실패하는 테스트 작성**

**수정 후** (new file: `ulssu_backend/tests/test_population_batch.py`):
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import population
import population_batch
from database import UserModel


def _session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_compute_population_counts_users():
    Session = _session_factory()
    db = Session()
    try:
        assert population_batch.compute_population(db) == 0
        db.add(UserModel(email="a@x.com", password_hash="h"))
        db.add(UserModel(email="b@x.com", password_hash="h"))
        db.commit()
        assert population_batch.compute_population(db) == 2
    finally:
        db.close()


def test_run_population_update_sets_value(monkeypatch):
    Session = _session_factory()
    seed = Session()
    seed.add(UserModel(email="c@x.com", password_hash="h"))
    seed.commit()
    seed.close()

    # run_population_update 는 database.SessionLocal 을 사용 → 테스트 팩토리로 치환
    monkeypatch.setattr(database, "SessionLocal", Session)
    population.set_current_population(999)

    population_batch.run_population_update()

    assert population.get_current_population() == 1


def test_run_population_update_swallows_errors(monkeypatch):
    # 세션 생성에서 예외가 나도 전파되지 않아야 함 (AC-5)
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(database, "SessionLocal", boom)
    population_batch.run_population_update()  # 예외 없이 통과
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_population_batch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'population_batch'`

- [ ] **Step 4: 구현 작성**

**수정 후** (new file: `ulssu_backend/population_batch.py`):
```python
"""일일 인구 배치: COUNT(users) → current_population. APScheduler 인프로세스."""
import os

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

import database
import population
from database import UserModel

_scheduler = None


def compute_population(db: Session) -> int:
    """전체 가입 유저수."""
    return db.query(UserModel).count()


def run_population_update() -> None:
    """유저수를 집계해 current_population 에 주입. 실패해도 전파하지 않음(AC-5)."""
    try:
        db = database.SessionLocal()
        try:
            population.set_current_population(compute_population(db))
        finally:
            db.close()
    except Exception:
        pass


def start_scheduler() -> None:
    """기동 즉시 1회 집계 + 매일 4시 cron 등록. 테스트(DISABLE_SCHEDULER)면 미기동(D5)."""
    if os.getenv("DISABLE_SCHEDULER"):
        return
    global _scheduler
    run_population_update()  # 기동 즉시 1회 (0 방지, FR-2)
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(run_population_update, "cron", hour=4)
    _scheduler.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd ulssu_backend && uv run pytest tests/test_population_batch.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml uv.lock ulssu_backend/population_batch.py ulssu_backend/tests/test_population_batch.py
git commit -m "feat(backend): 일일 인구 배치(compute_population + APScheduler) + 유닛테스트"
```

---

### Task 2: 기동/종료 이벤트 연결 + 테스트 스케줄러 가드

**Files:**
- Modify: `ulssu_backend/main.py:16` (import), `ulssu_backend/main.py:35-36` (이벤트 핸들러 추가)
- Modify: `ulssu_backend/tests/conftest.py:5` (DISABLE_SCHEDULER env)

**Model**: sonnet

- [ ] **Step 1: conftest에 DISABLE_SCHEDULER 가드 추가**

**원본** (`ulssu_backend/tests/conftest.py:1-6`):
```python
import os

# main/database import 전에 반드시 먼저 세팅 (모듈 로드 시 엔진 생성 + create_all 실행됨)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["OPENAI_API_KEY"] = "test-dummy-key"
os.environ["JWT_SECRET"] = "test-secret"
```

**수정 후**:
```python
import os

# main/database import 전에 반드시 먼저 세팅 (모듈 로드 시 엔진 생성 + create_all 실행됨)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["OPENAI_API_KEY"] = "test-dummy-key"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["DISABLE_SCHEDULER"] = "1"  # 테스트 중 APScheduler 스레드 미기동 (D5)
```

- [ ] **Step 2: main.py에 population_batch import 추가**

**원본** (`ulssu_backend/main.py:16`):
```python
from auth import hash_password, verify_password, create_token, get_current_user
```

**수정 후**:
```python
from auth import hash_password, verify_password, create_token, get_current_user
from population_batch import start_scheduler, shutdown_scheduler
```

- [ ] **Step 3: 기동/종료 이벤트 핸들러 추가**

**원본** (`ulssu_backend/main.py:35-36`):
```python
# OPENAI_API_KEY 는 환경변수에서 읽는다(소스 하드코딩 금지 — 노출된 기존 키는 폐기/회전 필요).
client = OpenAI()
```

**수정 후**:
```python
# OPENAI_API_KEY 는 환경변수에서 읽는다(소스 하드코딩 금지 — 노출된 기존 키는 폐기/회전 필요).
client = OpenAI()


@app.on_event("startup")
def _on_startup():
    # 기동 즉시 인구 집계 + 매일 4시 cron 등록 (테스트는 DISABLE_SCHEDULER 가드로 미기동)
    start_scheduler()


@app.on_event("shutdown")
def _on_shutdown():
    shutdown_scheduler()
```

- [ ] **Step 4: 전체 백엔드 테스트 실행**

Run: `cd ulssu_backend && uv run pytest -q`
Expected: PASS (전체 green — 신규 batch + 기존, 스케줄러 가드로 부작용 없음)

- [ ] **Step 5: 커밋**

```bash
git add ulssu_backend/main.py ulssu_backend/tests/conftest.py
git commit -m "feat(backend): FastAPI 기동/종료 이벤트로 인구 배치 스케줄러 연결 + 테스트 가드"
```

---

## 2. 위험 코드 지점

- `ulssu_backend/population_batch.py:start_scheduler` — **side-effect**: 기동 시 APScheduler 스레드 + 즉시 DB 집계. (mitigation: `DISABLE_SCHEDULER` env 가드로 테스트 미기동(D5), `run_population_update` try/except 예외격리(AC-5), 종료 이벤트로 스레드 정리.)
- `ulssu_backend/population.py:current_population` (소비처) — **race**: 인메모리 전역이라 멀티워커 시 워커별 상이. (mitigation: 단일 프로세스 가정(NFR/범위 밖). 운영 멀티워커는 후속 Redis 공유로 별도 처리.)

## 3. 롤백 전략

- **Code:** Task별 커밋 역순 `git revert`. 스케줄러만 끄려면 `DISABLE_SCHEDULER=1` env 설정(코드 변경 없이 비기동).
- **Config:** cron 시각은 `population_batch.py`의 `hour=4` 한 곳.
- **신규 의존성:** apscheduler — 롤백 시 제거.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 12:55] [구현계획서-수정]
- **id**: CH-20260617-003
- **이유**: 신규 구현계획서 작성 (일일 인구 배치, 2 TDD task)
- **무엇이**: daily-population-batch-implementation-plan.md §1(Task 1~2), §2 위험, §3 롤백
- **영향범위**: ulssu_backend(population_batch 신설·main 이벤트·conftest 가드)·apscheduler 의존성.
- **연관 항목**: CH-20260617-001, CH-20260617-002

### [2026-06-17 13:05] [코드-수정] (batch: tasks 1..2)
- **id**: CH-20260617-004
- **이유**: 일일 인구 배치 구현(2 task). 기동 즉시 + 매일 4시 COUNT(users)→current_population, APScheduler 인프로세스.
- **무엇이**: `ulssu_backend/population_batch.py`(신설), `main.py`(기동/종료 이벤트), `tests/conftest.py`(DISABLE_SCHEDULER), `tests/test_population_batch.py`(신설), `pyproject.toml`/`uv.lock`(apscheduler)
- **영향범위**: FastAPI 기동 시 인구 집계 스케줄러 시작. current_population이 유저수로 채워져 Cap=max(25,users) 동작. 테스트는 DISABLE_SCHEDULER로 스레드 미기동.
- **위험 카테고리**: side-effect(스케줄러 스레드/즉시집계 → env가드+예외격리), race(인메모리 멀티워커 → 단일프로세스 가정) — §2 사전 식별
- **task별 세부 (2건)**:
  - DP1: `population_batch.py` — compute/run/start/shutdown + 유닛 3 (side-effect) — `b63b646`
  - DP2: `main.py`/`conftest.py` — 기동/종료 이벤트 + 가드 (side-effect) — `3e89c5d`
- **테스트 결과**: 백엔드 47 passed.
- **연관 commits**: `b63b646..3e89c5d`
- **변경 전/후 코드**: 생략 — `git show <SHA>`
- **연관 항목**: CH-20260617-003
