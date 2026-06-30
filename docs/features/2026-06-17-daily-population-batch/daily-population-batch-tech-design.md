---
slug: daily-population-batch
source: daily-population-batch-requirements.md
north_star: docs/architecture/user-ai-persona-north-star.md
---

# 기술설계: 일일 인구 배치

> 입력 PRD: `daily-population-batch-requirements.md`. 다음 단계: `/write-plan`.

## 1. 아키텍처 개요

집계 로직(외부 의존 적은 `compute_population(db)`)과 스케줄링(APScheduler)을 `population_batch.py`로 분리한다. `compute_population`은 `COUNT(users)`만 하는 테스트 가능한 함수, `run_population_update`는 세션을 열어 그 값을 `population.set_current_population`에 주입(예외 격리). FastAPI 기동 이벤트가 `start_scheduler()`를 호출해 **기동 즉시 1회 실행 + 매일 4시 cron**을 등록하고, 종료 이벤트가 정리한다. 테스트에서는 env 가드로 스케줄러 스레드를 띄우지 않고 job 함수만 직접 검증한다.

## 2. 영향받는 컴포넌트

| 파일 | 작업 | 책임 |
|---|---|---|
| `comea_backend/population_batch.py` | **생성** | `compute_population(db)`, `run_population_update()`(세션+set+예외격리), `start_scheduler()`/`shutdown_scheduler()`(APScheduler, env 가드). |
| `comea_backend/main.py` | **수정** | `@app.on_event("startup")`/`("shutdown")`에서 스케줄러 start/stop. |
| `comea_backend/tests/conftest.py` | **수정** | `DISABLE_SCHEDULER=1` env (테스트 중 스케줄러 스레드 미기동). |
| `comea_backend/tests/test_population_batch.py` | **생성** | compute_population(N명→N) + run_population_update 주입 검증. |
| `pyproject.toml` | **수정** | `apscheduler` 추가. |

## 3. 데이터 모델

변경 없음. 읽기 전용 `COUNT(users)`. population은 기존 인메모리 훅(`population.py`).

## 4. 외부 인터페이스

신규 API 없음(내부 배치). `population_batch.run_population_update()`가 `population.set_current_population(COUNT(users))` 호출. `elastic_limit.compute_effective_cap`이 그 값을 소비(기존).

## 5. 핵심 결정 (대안 비교)

- **D1. APScheduler BackgroundScheduler(동기)** (대안: AsyncIOScheduler / asyncio 루프 / 외부 cron). BackgroundScheduler 채택 — job이 동기 DB 작업, 설정 단순. cron 트리거 `hour=4`.
- **D2. 기동 즉시 1회 + cron** — `start_scheduler()`가 `run_population_update()` 1회 직접 호출 후 cron 등록(0 방지, FR-2).
- **D3. compute_population/run_population_update를 스케줄러와 분리** — 스케줄러 없이 직접 호출해 단위 테스트(FR-4).
- **D4. 예외 격리** — `run_population_update`는 try/except로 감싸 집계 실패가 기동/요청을 막지 않음(NFR, AC-5).
- **D5. 테스트 env 가드** — `start_scheduler()`는 `os.getenv("DISABLE_SCHEDULER")` 시 즉시 return. conftest가 설정 → 테스트에서 스레드 미기동(부작용 차단).

## 6. 예비 위험 (→ 구현계획서 §2로 매핑)

- **side-effect**: 기동 시 스케줄러 스레드 + DB 세션. (완화: env 가드로 테스트 차단, 예외 격리, 종료 이벤트로 스레드 정리.)
- **race**: `current_population`은 인메모리 전역 — 멀티워커 시 워커별 상이. (완화: 단일 프로세스 가정(NFR/범위 밖). 운영 멀티워커는 후속 Redis 공유.)

## 7. 테스트 전략

- **단위**(`test_population_batch.py`): sqlite 세션에 유저 N명 → `compute_population(db) == N`. `run_population_update`(세션 팩토리 주입)가 `population.get_current_population() == N`로 설정. 유저 0명 → 0.
- 스케줄러 자체(cron 발화)는 단위 테스트하지 않음(env 가드로 미기동). 등록 코드는 수동/기동 확인.
- 기존 스위트: `DISABLE_SCHEDULER` 가드로 회귀 없음 확인(전체 green).

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 12:45] [개발방향-수정]
- **id**: CH-20260617-002
- **이유**: 신규 기술설계 (일일 인구 배치) — requirements 승인 후 작성
- **무엇이**: daily-population-batch-tech-design.md 전체 (§1~7, 결정 D1~D5)
- **영향범위**: comea_backend(population_batch 신설 + main 기동 이벤트 + conftest 가드)·apscheduler. verifying-spec 4축 green.
- **연관 항목**: CH-20260617-001
