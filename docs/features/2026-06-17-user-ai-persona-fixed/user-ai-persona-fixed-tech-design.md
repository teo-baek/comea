---
slug: user-ai-persona-fixed
source: user-ai-persona-fixed-requirements.md
north_star: docs/architecture/user-ai-persona-north-star.md
---

# 기술설계: 유저별 AI 페르소나 (중간 — 고정, 내부)

> 입력 PRD: `user-ai-persona-fixed-requirements.md`. 다음 단계: `/write-plan`.

## 1. 아키텍처 개요

`ai_personas` 테이블(유저 1:1)을 추가하고, 가입(`signup`) 시 기존 페르소나 풀에서 랜덤 1개를 골라 그 유저의 페르소나 레코드를 생성한다. 사용자에게 노출하지 않으며(API/UI 없음), 댓글 생성에도 연동하지 않는다(저장만). `trait_params`(JSON)는 풀 단계 진화 엔진이 채울 자리로 비워 둔다. 페르소나 생성은 **best-effort**(유저 commit 후 별도 시도)라 실패해도 가입은 유지된다.

## 2. 영향받는 컴포넌트

| 파일 | 작업 | 책임 |
|---|---|---|
| `comea_backend/database.py` | **수정** | `AiPersonaModel`(user_id 1:1, display_name, persona_prompt, trait_params JSON, updated_at) 신설 + JSON import. |
| `comea_backend/personas.py` | **수정** | `random_persona(rng=None)` — 풀에서 (이름, 프롬프트) 랜덤 반환(시드 주입 가능). |
| `comea_backend/main.py` | **수정** | `signup`에서 유저 생성 후 AI 페르소나 best-effort 생성. `AiPersonaModel` import. |
| `comea_backend/migrations/003_add_ai_personas.sql` | **생성** | 운영 DB용 멱등 SQL. |
| `comea_backend/tests/test_persona.py` | **생성** | random_persona 풀 멤버·결정성 + signup이 페르소나 생성 + 1:1. |

## 3. 데이터 모델 변경

```
ai_personas
  id            SERIAL PK
  user_id       INTEGER UNIQUE NOT NULL REFERENCES users(id)   -- 1유저:1페르소나
  display_name  VARCHAR NOT NULL
  persona_prompt TEXT NOT NULL
  trait_params  JSON NULL          -- 풀 단계 진화 엔진이 채움(지금 NULL)
  updated_at    TIMESTAMP NOT NULL DEFAULT now()
```

응답 비노출(직렬화 대상 아님). PostModel 등에 관계 매핑 추가하지 않음.

## 4. 외부 인터페이스

신규 사용자용 API 없음(내부 데이터, FR-3). `signup`이 내부적으로 1건 생성. 진화 엔진(다음 슬라이스)이 이 레코드 + 행동(posts.author_user_id/reactions.user_id)을 읽어 갱신할 예정.

## 5. 핵심 결정 (대안 비교)

- **D1. 가입 시 풀에서 랜덤 배정** (`random_persona`) — 행동 데이터 없는 출발점. 설문/생성은 비범위.
- **D2. best-effort 생성** — 유저 commit 후 try/except로 페르소나 생성(실패해도 가입 유지, NFR/AC). 단 정상 경로에선 항상 생성(AC-1).
- **D3. 미노출 + 댓글 미연동** — API/UI 없음, 댓글은 기존 공용 풀(FR-3/4).
- **D4. trait_params=JSON, 지금 NULL** — 북극성 §3 구조 선반영(전방 호환), 진화 엔진이 채움.

## 6. 예비 위험 (→ 구현계획서 §2로 매핑)

- **breaking**: `ai_personas` 테이블 신설. 운영 DB `create_all` 미반영 가능. (완화: `migrations/003_*.sql` 멱등 SQL.)
- **side-effect**: `signup`이 추가 write(페르소나) 수행. (완화: 유저 commit 선행 + 페르소나 try/except best-effort로 가입 흐름 보호.)

## 7. 테스트 전략

- **단위**(`test_persona.py`): `random_persona(Random(seed))`가 `PERSONA_POOL` 멤버 반환·동일 시드 동일 결과. 
- **통합**: signup 후 해당 user_id의 `ai_personas` 1건 존재 + display_name이 풀 이름 중 하나 + 같은 유저 재호출 없음(1:1). 사용자용 조회 API 부재(라우트 없음) 확인.
- 기존 스위트: 회귀 없음(댓글/인증 로직 불변) 전체 green.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->
