# 요구사항: 일일 인구 배치 (current_population 집계)

> **다음 단계 안내**: 이 문서는 PRD입니다. 다음 단계로 `tech-design`을 호출하세요. 기술 세부는 여기 박지 마세요.
> **북극성 정합:** `docs/architecture/user-ai-persona-north-star.md` §2 "인구 배치" 모듈.

## 1. 배경/목적

`population.py`에는 `current_population` set/get 훅만 있고 실제 집계 주체가 없어 항상 0 → 댓글 상한 Cap이 25로 고정돼 있다(`elastic_limit.compute_effective_cap`). 유저 인증 슬라이스로 `users` 테이블이 생겨 이제 전체 유저수를 셀 수 있다(PRD planned.md §3.4).

목적: **매일 새벽 4시(+서버 기동 즉시) 전체 가입 유저수를 집계해 `current_population`에 주입**한다. 실시간 DB 조회를 배제(하루 1회)하면서, 유저 규모가 커지면 Cap이 따라 커지게 한다(세계관 확장).

## 2. 사용자 스토리 / 시나리오

해당 없음 — 인프라/운영 배치라 외부 사용자 스토리 없음.

## 3. 기능 요구사항 (FR)

- **FR-1**: 전체 가입 유저수 `COUNT(users)`를 계산해 `population.set_current_population()`에 주입한다.
- **FR-2**: 집계는 **서버 기동 즉시 1회 + 매일 새벽 4시** 실행한다.
- **FR-3**: 스케줄러는 **APScheduler 인프로세스**로, FastAPI 기동 시 시작하고 종료 시 정리한다.
- **FR-4**: 집계 로직은 외부 스케줄러와 분리된 **테스트 가능한 함수**(`compute_population(db)` → 유저수)로 둔다.
- **FR-5**: population 값은 **raw `COUNT(users)`** (별도 가중치 공식 없음). `elastic_limit`의 `Cap=max(25, population)`이 이를 소비한다.

## 4. 비기능 요구사항 (NFR)

한 줄: **단일 프로세스 가정**(멀티워커 공유는 비범위). 실시간 조회 배제(하루 1회 + 기동 시). 집계 실패가 앱 기동/요청을 막지 않도록 안전 처리.

## 5. 범위 밖 (Out of Scope)

- 멀티프로세스/워커 간 `current_population` 공유(Redis 등) — planned.md는 Redis를 언급하나 이번엔 인프로세스
- 유저수 외 가중치 공식(스케일 계수 등)
- OLAP/ETL·B2B 통계 파이프라인 (PRD §3.5)
- 세계관 확장 스토리텔링 UI/알림

## 6. 수용 기준 (Acceptance Criteria)

- **AC-1**: 서버 기동 직후 `current_population`이 `COUNT(users)`로 설정된다.
- **AC-2**: 매일 새벽 4시 재집계되도록 스케줄이 등록된다(트리거 시 값 갱신).
- **AC-3**: `compute_population(db)`가 유저수를 정확히 반환한다(단위 테스트, 유저 N명 → N).
- **AC-4**: 유저 0명이면 population 0 → Cap 25 유지(회귀 없음).
- **AC-5**: 집계 중 예외가 나도 앱 기동/응답이 중단되지 않는다.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 12:45] [요구사항-수정]
- **id**: CH-20260617-001
- **이유**: 신규 피처 brainstorming 결과 (일일 인구 배치 — user-auth로 잠금 해제)
- **무엇이**: daily-population-batch-requirements.md 전체 (FR-1~5, AC-1~5)
- **영향범위**: 없음(최초). 후속에서 comea_backend(population_batch + main 기동 이벤트 + apscheduler). 북극성 §2 정합.
- **연관 항목**: 없음
