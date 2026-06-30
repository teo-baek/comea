---
slug: persona-deployment
source: persona-deployment-requirements.md
north_star: docs/architecture/user-ai-persona-north-star.md
---

# 기술설계: 내 AI 출동

> 입력 PRD: `persona-deployment-requirements.md`. 다음: `/write-plan`. 북극성 §3 풀 응용.

## 1. 아키텍처 개요

`persona_deployment.py`에 `select_deployed_personas(db, exclude_user_id, k, rng)`를 둔다 — 작성자 제외 `ai_personas`에서 랜덤 k명을 골라 `(display_name, persona_prompt + 진화 hint)` 리스트를 반환(시드 주입 결정적). `create_post`의 댓글 생성 루프가 Final Limit 슬롯 중 앞쪽 최대 k개를 이 출동 페르소나로, 나머지는 기존 공용 풀(`get_personas`)로 채운다. 총 댓글 수 불변, 다른 유저 없으면 전부 풀(회귀). 마이그레이션/의존성 없음.

## 2. 영향받는 컴포넌트

| 파일 | 작업 | 책임 |
|---|---|---|
| `comea_backend/persona_deployment.py` | **생성** | `select_deployed_personas(db, exclude_user_id, k=2, rng=None)` → `[(name, prompt+hint)]`. |
| `comea_backend/main.py` | **수정** | `create_post` 댓글 루프: 출동 k + 공용 풀 (final_limit−출동수). import 추가. |
| `comea_backend/tests/test_persona_deployment.py` | **생성** | select 단위(제외/한도/hint) + create_post 통합(타유저 프롬프트 사용·자기 글 제외). |

신규 의존성·마이그레이션 없음.

## 3. 데이터 모델

변경 없음. 읽기: `ai_personas`(display_name, persona_prompt, trait_params.hint). 출동 댓글도 기존 `comments`(name=display_name)로 저장.

## 4. 외부 인터페이스

신규 API 없음. `create_post` 내부 동작만 변경(댓글 구성). 응답 형태 동일.

## 5. 핵심 결정 (대안 비교)

- **D1. 출동 k=2 기본(상수)** — Final Limit 내 앞 슬롯 최대 2개를 출동, 나머지 풀. 작게 시작.
- **D2. 프롬프트 = persona_prompt + hint** — `trait_params.hint`(있으면) `\n[성향 힌트] ...`로 덧붙임. 진화 반영(FR-2).
- **D3. 작성자 제외 + 없으면 전부 풀** — `user_id != author` 필터, 결과 0이면 풀만(기존 회귀, FR-3/6).
- **D4. 표시명 = display_name(풀 이름)** — 유저 신원 비노출(FR-4). comment_reactions 매핑(comments.name)과도 일관.
- **D5. create_post 한정** — 반응 성장 경로(`_generate_more_comments`)는 이번 범위 밖(풀 유지).
- **D6. rng 주입** — `random.sample`에 rng 주입 가능 → 테스트 결정성(AC-6).

## 6. 예비 위험 (→ 구현계획서 §2)

- **side-effect**: 글 등록이 추가로 `ai_personas` 조회 + 출동 댓글 생성. (완화: k 작게 상한, 총 댓글 수 불변(슬롯 대체), 조회 1회.)
- **breaking(약)**: `create_post` 댓글 구성 변경 → 기존 create_post 테스트(댓글 수)는 불변(수 동일)이라 회귀 없음. 출동은 다른 유저 페르소나 존재 시에만 활성(테스트 환경엔 보통 없음 → 전부 풀).

## 7. 테스트 전략

- **단위**(`test_persona_deployment.py`): 유저 B 페르소나 시드 후 `select_deployed_personas(db, exclude_user_id=A, k=2, rng=seed)` → B 포함·A 제외·≤k·프롬프트에 hint 포함. 페르소나 없으면 빈 리스트.
- **통합**: 유저 B(페르소나+hint) 존재 상태에서 A가 create_post → `generate_ai_comment` 호출 프롬프트 중 하나에 B의 persona_prompt/hint 포함(monkeypatch 캡처). 자기 글에 자기(A) 페르소나 미출동. 총 댓글 수 = Final Limit 불변.
- 기존 스위트: 다른 유저 페르소나 없는 기존 테스트는 전부 풀 → 회귀 없음 green.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->

### [2026-06-17 15:05] [개발방향-수정]
- **id**: CH-20260617-002
- **이유**: 신규 기술설계 (내 AI 출동) — requirements 승인 후 작성
- **무엇이**: persona-deployment-tech-design.md 전체 (§1~7, 결정 D1~D6)
- **영향범위**: comea_backend(persona_deployment 신설 + create_post 연동). 마이그레이션 없음. verifying-spec 4축 green.
- **연관 항목**: CH-20260617-001
