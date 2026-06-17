# 목표 아키텍처 (북극성): 유저 · AI 페르소나

> **목적:** 유저/인증 → 유저별 AI 페르소나 → 동적 진화(planned.md Phase 3)까지의 **최종 형태**를 한 장에 못박는다. 이후 모든 슬라이스(최소 → 중간 → 풀)의 tech-design은 이 문서에 맞춰지는지 `verifying-spec`에서 점검한다. 방향은 여기서 고정, 구현은 단계적.
>
> **이 문서는 buildable plan이 아니라 reference(north-star)다.** 코드 변경 없음.

## 0. 비전 (planned.md §3.1 / Phase 3)

ulssu는 **사람은 글만 쓰고, 댓글은 AI 시민이 다는 커뮤니티 게시판**이다. 궁극적으로 **유저 1명당 1개의 고유 AI 에이전트**가 매칭되고, 그 에이전트는 유저의 행동(좋아요/싫어요, 작성 글)을 반영해 성향·말투가 **매일 진화**한다. 인증은 **이메일+비밀번호**로 시작한다.

## 1. 최종 데이터 모델 (end-state)

```
users
  id            PK
  email         UNIQUE NOT NULL
  password_hash NOT NULL            -- 평문 저장 금지(해시)
  created_at    NOT NULL DEFAULT now()

posts                               -- 기존 + author_user_id 추가
  id, content, score, is_locked
  author_user_id  FK→users.id NULL  -- 기존 익명 글 호환 위해 NULL 허용

comments                            -- AI가 작성 (기존)
  id, post_id, name, comment
  persona_id    FK→ai_personas.id NULL  -- (풀) 어떤 유저의 에이전트가 썼는지(없으면 공용 풀)

reactions                           -- 기존(스택) + user_id 추가
  id, post_id, reaction_type, created_at
  user_id       FK→users.id NULL    -- (행동 추적의 핵심) 누가 눌렀는지. 익명 호환 위해 NULL 허용

ai_personas                         -- 유저별 1:1 에이전트
  id            PK
  user_id       FK→users.id UNIQUE  -- 1 유저 : 1 페르소나
  display_name  NOT NULL
  trait_params  JSON                -- {t_f_score, aggression, ...} 진화 대상
  system_prompt TEXT                -- 동적 조립 결과
  updated_at    NOT NULL            -- 마지막 진화 시각
```

- **인구 가중치(`current_population`)**: 일일 배치가 `COUNT(users)`를 세어 `population.set_current_population()`에 주입(기존 훅 재사용). 별도 테이블 불필요.

## 2. 모듈 경계 (seams)

| 모듈 | 책임 | 도입 슬라이스 |
|---|---|---|
| `auth` (서버) | 회원가입/로그인, password 해시, 세션/토큰(JWT 등) | 최소 |
| 식별 연결 | posts.author_user_id / reactions.user_id 기록 | 최소 |
| `persona` (서버) | 가입 시 ai_personas 1건 생성, 저장/조회 | 중간 |
| 댓글 생성 연동 | 댓글이 공용 풀 대신 유저 페르소나 사용(선택) | 중간~풀 |
| 진화 엔진 (배치) | 행동 로그(reactions/posts) → trait_params·system_prompt 재계산(일 단위) | 풀 |
| 인구 배치 | COUNT(users) → current_population (스케줄러) | 풀(또는 최소 직후 소형) |
| Flutter `auth` UI | 가입/로그인 화면, 토큰 보관, 인증 헤더 | 최소 |

## 3. 슬라이스 맵 (전부 additive — 재작성 없음)

- **최소 (identity-only):** `users` 테이블 + auth(가입/로그인) + `posts.author_user_id`·`reactions.user_id` 기록 + Flutter 로그인 UI. → 유저수 카운트 가능(③ 잠금 해제), 행동 데이터가 1일차부터 축적.
- **중간 (+고정 페르소나):** `ai_personas` 테이블 + 가입 시 1건 생성(고정 성향). 댓글 생성에 선택적 연동.
- **풀 (동적 진화, Phase 3):** 진화 엔진(배치)이 누적 행동을 읽어 `trait_params`/`system_prompt`를 일 단위 갱신. planned.md 팁대로 **초기엔 단순 합산(+1/−1)** 으로 시작, 후에 임베딩.

## 4. 전방 호환 규칙 (드리프트 방지 — 슬라이스가 지켜야 할 것)

1. **이음새는 최소부터 심는다:** `author_user_id`(posts), `user_id`(reactions)는 **최소 슬라이스에서 추가**한다(아직 진화에 안 써도). 나중 retrofit 금지.
2. **NULL 허용으로 기존 익명 데이터 호환:** 기존 글/반응은 작성자 NULL로 남고, 신규부터 채운다. (마이그레이션은 `migrations/`에 SQL 추가.)
3. **비밀번호는 해시 저장**, 토큰 기반 인증. 평문/세션쿠키 비밀 노출 금지.
4. **진화 엔진은 additive**: 기존 식별/게시 코드를 고치지 않고 새 모듈/배치로 얹는다.
5. **댓글 생성은 점진**: 공용 16-페르소나 풀(현재) → 유저 페르소나 사용은 중간~풀에서 *추가 경로*로. 기존 공용 경로는 유지.
6. 각 슬라이스 tech-design은 이 문서의 데이터 모델·경계와 어긋나지 않는지 `verifying-spec`에서 확인한다.

## 5. 범위 메모

- 이 문서는 방향만 고정한다. 각 슬라이스의 구체 FR/AC/구현은 해당 슬라이스의 requirements/tech-design/plan에서 정한다.
- 인증 고도화(이메일 인증메일, 비번 재설정, 소셜 로그인)는 최소 이후 별도 슬라이스 후보.

---
## 변경이력
<!-- 이 문서가 갱신되면 여기에 기록 -->
