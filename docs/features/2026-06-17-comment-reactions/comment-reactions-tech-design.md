---
slug: comment-reactions
source: comment-reactions-requirements.md
north_star: docs/architecture/user-ai-persona-north-star.md
---

# 기술설계: 댓글 단위 반응

> 입력 PRD: `comment-reactions-requirements.md`. 다음: `/write-plan`. 북극성 §3 풀 선행(진화 신호 수집).

## 1. 아키텍처 개요

`comment_reactions` 테이블(유저·댓글당 1개)을 신설하고, `POST /api/comments/{id}/reaction`(로그인 필수)에서 **upsert**(있으면 갱신, 없으면 삽입)한다. 글 단위 반응(`reactions`, elastic limit)과 댓글 생성 로직은 건드리지 않는다(별도 경로). Flutter는 각 댓글 타일에 좋아요/싫어요 버튼을 추가해 `ApiService.reactToComment`를 호출하고 누른 상태를 시각 피드백한다. 댓글 반응 개수는 비노출.

## 2. 영향받는 컴포넌트

| 파일 | 작업 | 책임 |
|---|---|---|
| `comea_backend/database.py` | **수정** | `CommentReactionModel`(user_id, comment_id, reaction_type, created_at, unique(user_id,comment_id)) 신설. |
| `comea_backend/main.py` | **수정** | `POST /api/comments/{comment_id}/reaction` (Depends get_current_user, upsert). |
| `comea_backend/migrations/004_add_comment_reactions.sql` | **생성** | 운영 DB용 멱등 SQL. |
| `comea_backend/tests/test_comment_reaction.py` | **생성** | upsert/401/404/400 통합. |
| `comea/lib/services/api.dart` | **수정** | `reactToComment(commentId, reaction)` (auth 헤더). |
| `comea/lib/screens/detail_screen.dart` | **수정** | 각 댓글 타일에 좋아요/싫어요 버튼 + 로컬 선택 상태. |
| `comea/test/services/api_comment_reaction_test.dart` | **생성** | reactToComment MockClient. |

신규 의존성 없음.

## 3. 데이터 모델 변경

```
comment_reactions
  id            SERIAL PK
  user_id       INTEGER NOT NULL REFERENCES users(id)
  comment_id    INTEGER NOT NULL REFERENCES comments(id)
  reaction_type VARCHAR NOT NULL            -- like | dislike
  created_at    TIMESTAMP NOT NULL DEFAULT now()
  UNIQUE (user_id, comment_id)              -- 유저·댓글당 1개
```

`reactions`(글 단위)·`comments`·`posts` 변경 없음. 응답에 댓글 반응 카운트 미포함.

## 4. 외부 인터페이스 (API)

- `POST /api/comments/{comment_id}/reaction` `{reaction}` (로그인 필수). upsert: `(current_user, comment_id)` 존재 → `reaction_type` 갱신, 없음 → 삽입. 200 반환(개수 없음, 간단 ok 바디). 404(없는 댓글)/400(잘못된 reaction)/401(무토큰).
- 기존 `/api/posts`, `/api/posts/{id}/reaction` 불변.

## 5. 핵심 결정 (대안 비교)

- **D1. 별도 `comment_reactions` 테이블** (대안: 기존 reactions에 comment_id 통합). 별도 채택 — 글 단위 반응(한계선)과 책임 분리, elastic-limit 무영향(decided).
- **D2. unique(user_id, comment_id) + upsert** (대안: 스택 적재). upsert 채택 — 진화는 "선호" 신호라 유저·댓글당 1표가 깔끔(스팩 방지). 재탭 = 교체.
- **D3. 어떤 페르소나 선호인지는 `comments.name`으로 매핑** — 댓글이 어느 페르소나가 썼는지 `name`에 있으므로 별도 태그 불필요. 진화 엔진(다음)이 comment_reactions ⋈ comments.name 으로 집계.
- **D4. Flutter 댓글 타일 버튼 + 로컬 상태** — 누른 버튼 강조. 개수 미표시(FR-3).

## 6. 예비 위험 (→ 구현계획서 §2)

- **breaking**: `comment_reactions` 테이블 신설. 운영 DB `create_all` 미반영 가능. (완화: `migrations/004_*.sql` 멱등.)
- **side-effect**: 댓글 타일마다 버튼 + API 호출. (완화: 수집 전용, 한계선/생성 무영향. 실패 시 스낵바·상태 원복.)

## 7. 테스트 전략

- **백엔드 통합**(`test_comment_reaction.py`): auth_client로 댓글 생성 후 like → comment_reactions 1건; 같은 댓글 재호출(dislike) → 여전히 1건이며 type 갱신(AC-2); 무토큰 401; 없는 댓글 404; 잘못된 reaction 400. (댓글은 create_post가 만든 것 사용 또는 직접 insert.)
- **Flutter**: `reactToComment` MockClient 단위(경로/헤더/바디). 댓글 타일 버튼 위젯 테스트는 가벼운 1건(버튼 존재+탭→API 호출) 또는 수동.
- 기존 스위트: 글 단위 반응/한계선/댓글 생성 회귀 없음 전체 green.

---
## 변경이력
<!-- change-history skill auto-appends entries here, oldest first -->
