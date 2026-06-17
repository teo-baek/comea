---
slug: persona-evolution-engine
source: persona-evolution-engine-requirements.md
north_star: docs/architecture/user-ai-persona-north-star.md
---

# 기술설계: 페르소나 진화 엔진 (풀)

> 입력 PRD: `persona-evolution-engine-requirements.md`. 다음: `/write-plan`. 북극성 §3 풀.

## 1. 아키텍처 개요

`persona_evolution.py`에 집계/진화 로직을 둔다: `compute_persona_preferences(db, user_id)`가 `comment_reactions ⋈ comments.name`을 +1(like)/−1(dislike) 합산해 페르소나별 선호 점수 맵을 만들고, `build_prompt_hint(prefs)`가 최고 양수 페르소나로 힌트 문장을 만든다. `run_persona_evolution()`이 모든 `ai_personas`를 돌며 그 유저의 선호를 계산해 `trait_params = {"prefs": {...}, "hint": "..."}` + `updated_at`을 갱신(유저 단위 예외 격리). 기존 daily 배치(`population_batch` 스케줄러)에 evolution job을 추가하고 기동 시 1회 실행한다. **마이그레이션 없음**(trait_params JSON 컬럼 기존 존재). 진화는 저장만 — 댓글 생성/한계선 무영향.

## 2. 영향받는 컴포넌트

| 파일 | 작업 | 책임 |
|---|---|---|
| `ulssu_backend/persona_evolution.py` | **생성** | `compute_persona_preferences`, `build_prompt_hint`, `run_persona_evolution`. |
| `ulssu_backend/population_batch.py` | **수정** | `start_scheduler`에서 기동 즉시 + 매일 4시 `run_persona_evolution`도 실행/등록. |
| `ulssu_backend/tests/test_persona_evolution.py` | **생성** | 합산/힌트/진화 단위. |

신규 의존성·마이그레이션 없음.

## 3. 데이터 모델

스키마 변경 없음. `ai_personas.trait_params`(JSON)에 `{"prefs": {persona_name: net_score}, "hint": str}` 저장. 입력은 `comment_reactions`(user_id, comment_id, reaction_type) ⋈ `comments`(id→name).

## 4. 외부 인터페이스

신규 API 없음(내부 배치). `run_persona_evolution()`이 daily 배치에서 실행.

## 5. 핵심 결정 (대안 비교)

- **D1. 합산 = comment_reactions ⋈ comments.name, +1/−1** (planned.md 팁: 단순 합산). 임베딩은 비범위.
- **D2. 저장 = trait_params JSON {prefs, hint}** — 마이그레이션 회피(컬럼 기존). updated_at 갱신.
- **D3. hint = 최고 양수 페르소나 문장** ("당신의 주인은 현재 '{name}' 같은 답변을 선호합니다"). 양수 없으면 빈 문자열.
- **D4. daily 배치 연동** — `population_batch.start_scheduler`가 population + evolution 두 job을 기동 시 1회 + 매일 4시 실행. 유저 단위 try/except(AC-5). 테스트는 기존 `DISABLE_SCHEDULER` 가드로 미기동.
- **D5. 저장만(출동 X)** — 진화된 trait_params를 댓글 생성에 쓰는 건 다음 슬라이스.

## 6. 예비 위험 (→ 구현계획서 §2)

- **side-effect**: 배치가 모든 페르소나 순회 + 쿼리. (완화: 일일 1회, 유저 단위 try/except, 기동 시 best-effort.)
- **race**: 진화 중 동시 comment_reaction 변경 — 일별 스냅샷이라 무해(다음 배치에 반영).

## 7. 테스트 전략

- **단위**(`test_persona_evolution.py`): sqlite에 user/comment(name)/comment_reaction 시드 → `compute_persona_preferences`가 정확한 net 맵(AC-1). `build_prompt_hint`: 양수 최고 → 문장, 빈/음수만 → 빈 문자열(AC-3). `run_persona_evolution`(세션 주입)이 ai_persona.trait_params 갱신(AC-2).
- 기존 스위트: 댓글 생성/한계선/배치 회귀 없음(DISABLE_SCHEDULER 가드) 전체 green.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 14:30] [개발방향-수정]
- **id**: CH-20260617-002
- **이유**: 신규 기술설계 (페르소나 진화 엔진) — requirements 승인 후 작성
- **무엇이**: persona-evolution-engine-tech-design.md 전체 (§1~7, 결정 D1~D5)
- **영향범위**: ulssu_backend(persona_evolution 신설 + population_batch 스케줄러 연동). 마이그레이션 없음. verifying-spec 4축 green.
- **연관 항목**: CH-20260617-001
