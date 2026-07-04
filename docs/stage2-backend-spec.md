# Comea 스테이지 1+2 백엔드 스펙 (구현 계약서)

> PRD: `planned.md` (v2). 이 문서는 스테이지 1(진영 토론 PoC) + 스테이지 2(가변 댓글 엔진 MVP)를
> 하나의 FastAPI 백엔드로 구현하기 위한 **구현 계약서**다. 모든 구현 에이전트는 이 문서를 단일 진실로 삼는다.
> 기존 코드(comea_backend/)는 재사용 가능하지만, 이 스펙과 충돌하면 스펙이 이긴다.

## 0. 원칙

- **객관성**: 승패 조작 없음. 호위대 ~60% / 도전자 ~40% (최소 1명 보장), 중재자는 좋아요 분포로만 판정.
- **진짜 게시판**: 댓글 고정 상한 없음. `clamp(base + floor(net/k) + bonus, 2, 500)`.
- **즉시 반환**: 글 등록 API는 채점/댓글 생성을 기다리지 않는다. BackgroundTasks + 딜레이 순차 Insert.
- **플랫 임포트 유지**: `comea_backend/` 내 모듈은 `from database import ...` 식 플랫 임포트 (기존 방식).
- 실행: `cd comea_backend && uv run uvicorn main:app --port 8247` (uv가 루트 pyproject를 찾음).

## 1. 실행 환경

- 루트 `.env` (python-dotenv 로 로드, 기존 `main.py` 방식 유지):
  - `OPENAI_API_KEY`, `JWT_SECRET`
  - `DATABASE_URL=postgresql://comea:comea@127.0.0.1:5439/comea` (도커 `comea-postgres`)
  - `COMEA_PORT=8247`
  - `COMEA_COMMENT_MODEL` / `COMEA_JUDGE_MODEL` (기본 `gpt-4o-mini`)
  - `COMEA_COMMENT_DELAY_MIN=5` / `COMEA_COMMENT_DELAY_MAX=10` (초, float 허용. 테스트는 0)
  - `COMEA_FAKE_AI=1` 이면 OpenAI 호출 없이 결정적 스텁 사용 (키 없을 때도 자동 fake + 경고 로그)
  - `DISABLE_SCHEDULER=1` 이면 APScheduler 미기동 (테스트)
- 테스트는 SQLite (기존 conftest 패턴 유지). JSON 컬럼은 `sqlalchemy.JSON` 사용 (PG/SQLite 겸용).
- 새 파이썬 의존성 추가 금지 (fastapi/sqlalchemy/openai/apscheduler/bcrypt/pyjwt/psycopg2/python-dotenv/pytest/httpx 만 사용).

## 2. 파일 소유권 (병렬 작업 충돌 방지 — 자기 소유 파일만 생성/수정)

| 에이전트 | 소유 파일 |
|---|---|
| F(기반) | `database.py`, `migrations/005_stage2_faction.sql`, `tests/test_schema_stage2.py` |
| L(리밋) | `elastic_limit.py`, `tests/test_elastic_limit.py` (기존 stale 리밋 테스트 삭제 권한: `tests/test_lock_and_scale.py` 등 리밋 관련) |
| G(AI/채점) | `ai_client.py`, `grader.py`, `tests/test_ai_client.py`, `tests/test_grader.py` |
| D(토론) | `factions.py`, `debate.py`, `personas.py`, `comment_style.py`, `tests/test_factions.py`, `tests/test_debate.py` |
| M(API) | `main.py`, `schemas.py`, `auth.py`, `population.py`, `population_batch.py`, `tests/test_api_stage2.py`, `conftest.py` |
| I(통합) | 전체 (드리프트 수정, stale 테스트 정리) |

## 3. DB 스키마 (`database.py` 재작성)

기존 SQLAlchemy 2.0 declarative 패턴, `Base.metadata.create_all` 기동 시 실행 유지.

```
users            : id PK | email str unique not null | password_hash str not null | created_at dt now
ai_personas      : id PK | user_id FK unique | display_name str | persona_prompt text | trait_params JSON | updated_at dt   (기존 유지)
posts            : id PK | content text not null | author_user_id FK users nullable
                 | status str(16) not null default 'grading'   # grading | debating | concluded
                 | score int nullable                          # 0~100
                 | score_breakdown JSON nullable               # {"emotion":1~5,"controversy":..,"clarity":..,"novelty":..}
                 | core_claim text nullable                    # 채점관이 추출한 핵심 주장 1문장
                 | base_limit int nullable
                 | verdict str(16) nullable                    # ally | challenger | tie (마지막 판정)
                 | created_at dt now
comments         : id PK | post_id FK not null | faction str(16) not null   # ally | challenger | moderator
                 | persona_key str nullable | persona_name str not null
                 | content text not null | turn_index int not null default 0
                 | created_at dt now
reactions        : id PK | post_id FK not null | user_id FK not null | reaction_type str  # 'like'|'dislike'
                 | created_at dt now | UNIQUE(user_id, post_id)     # 인당 1표 (토글/변경)
comment_reactions: id PK | comment_id FK not null | user_id FK not null | reaction_type str
                 | created_at dt now | UNIQUE(user_id, comment_id)  (기존 유지)
```

- `migrations/005_stage2_faction.sql`: 위 변경분의 멱등 SQL (참고용, 런타임은 create_all).
- 기존 `comments.name`/`comments.comment` 컬럼명은 `persona_name`/`content` 로 교체 (하위호환 불필요 — 프론트도 재작성됨).

### 3.1 공용 집계 헬퍼 (database.py 에 함께 구현 — D/M 이 공용 사용)

```python
def post_stats(db, post_id: int) -> dict
    # {"post_likes": int, "post_dislikes": int, "comment_net": int,
    #  "non_moderator_count": int, "total_comments": int, "net_reaction": int}
    # net_reaction = (post_likes - post_dislikes) + comment_net   (§4 정의와 동일)

def comment_reaction_map(db, post_id: int) -> dict[int, tuple[int, int]]
    # comment_id -> (likes, dislikes)
```

## 4. `elastic_limit.py` (전면 재작성 — PRD 3.3 공식)

```python
K_REACTIONS_PER_COMMENT = 3
FLOOR = 2
SAFETY_CEILING = 500

def compute_base_limit(score: int) -> int
    # 0~39 → 3 | 40~69 → 8 | 70~89 → 15 | 90~100 → 25

def compute_population_bonus(mau: int) -> int
    # max(0, floor(log10(max(mau, 1))) - 2)   # 100명=0, 1천=1, 1만=2

def compute_final_limit(base_limit: int, net_reaction: int, population_bonus: int, k: int = 3) -> int
    # clamp(base_limit + (net_reaction // k) + population_bonus, FLOOR, SAFETY_CEILING)
    # 주의: 파이썬 // 는 음수 내림 — 그대로 사용 (net=-1,k=3 → -1)

def should_conclude_early(net_reaction: int, comment_count: int) -> bool
    # net_reaction <= -2 and comment_count >= FLOOR
```

`net_reaction` 정의: **(글 like−dislike) + Σ(각 댓글 like−dislike, moderator 댓글 포함)**.
리밋과 비교하는 댓글 수는 **moderator 제외** 카운트.

## 5. `ai_client.py`

```python
class AIClient:      # AsyncOpenAI 래퍼
    async def complete(self, *, system: str, user: str, model: str,
                       temperature: float = 0.8, max_tokens: int | None = 400) -> str

class FakeAIClient:  # 결정적 스텁 (네트워크 0)
    # 요청 텍스트에 'JSON' 포함 → 유효한 채점 JSON 문자열 반환
    #   예: {"emotion":4,"controversy":4,"clarity":3,"novelty":3,"core_claim":"..."}
    # 그 외 → 페르소나/진영 힌트를 섞은 짧은 한국어 댓글 (hash(system+user) 기반 변주, 항상 동일 입력=동일 출력)

def get_ai_client() -> AIClient | FakeAIClient   # 싱글턴. COMEA_FAKE_AI=1 또는 키 없음 → Fake
def reset_ai_client() -> None                    # 테스트용
def is_fake_mode() -> bool
```

## 6. `grader.py` (PRD 3.2 — 채점관)

```python
@dataclass
class GradeResult:
    score: int              # 0~100 (서버 계산)
    breakdown: dict         # {"emotion":1~5,"controversy":..,"clarity":..,"novelty":..}
    core_claim: str         # 글쓴이의 핵심 주장 1문장 (진영 프롬프트에 사용)

async def grade_post(content: str) -> GradeResult
```

- temperature **0**, 모델 `COMEA_JUDGE_MODEL`. 프롬프트에 **few-shot 예시 3개 고정** (저품질/중품질/고품질 글 + 정답 JSON).
- 루브릭: 정서적 깊이 0.35 / 논쟁 유발성 0.30 / 주제 명확성 0.20 / 신규성 0.15.
- 모델은 각 축 1~5 + core_claim 만 JSON으로 출력. **score 는 서버가 계산**: `round(가중합 * 20)`.
- JSON 파싱 실패 → 1회 재시도 → 그래도 실패 시 폴백 `GradeResult(60, 전축3, content[:80])`.

## 7. `factions.py` + `debate.py` (PRD 3.1 — 진영 토론)

### factions.py

- 상수: `ALLY="ally"`, `CHALLENGER="challenger"`, `MODERATOR="moderator"`.
- 기존 `personas.py` 16종을 `Persona(key, name, character_prompt)` 리스트로 재정리 (성향 중립 캐릭터 — 진영은 배치 시 부여). 중재자 전용 페르소나 1종 별도.
- `faction_for_turn(turn_index: int, seed: int, challenger_so_far: int, planned_total: int) -> str`
  - turn 0 → ALLY (호위대장 자리)
  - `challenger_so_far == 0 and turn_index >= planned_total - 1` → CHALLENGER (최소 1명 보장)
  - 그 외 → `random.Random((seed, turn_index).__hash__()).random() < 0.4` 이면 CHALLENGER 아니면 ALLY
- `pick_persona(faction: str, rng: random.Random, used_keys: set[str]) -> Persona` — 최근 사용 페르소나 중복 회피.

### debate.py — 백그라운드 파이프라인 (상태 머신)

```python
async def run_debate_pipeline(post_id: int) -> None      # BackgroundTasks 로 실행
def ensure_pipeline_scheduled(post_id: int, background_tasks) -> bool  # 중복 방지 후 add_task
def check_reignite(post_id: int, background_tasks) -> bool
    # reaction 처리 후 M 이 호출: status==concluded 이고 non-moderator 수 < 새 final_limit
    # 이고 조기종결 조건이 아니면 status=debating 으로 되돌리고 ensure_pipeline_scheduled. 예약 여부 반환.
```

- **동시성 가드**: 모듈 전역 `_active: set[int]`. 이미 active면 no-op. 파이프라인 종료 시(finally) 제거.
- 흐름:
  1. status=`grading` 이면: `grade_post` → score/breakdown/core_claim/base_limit 저장 → status=`debating`. (이미 score 있으면 스킵 — 재점화 경로)
  2. 루프 (매 턴 DB 재조회로 최신 반응 반영):
     - `final_limit` 계산 (§4). non-moderator 댓글 수 ≥ final_limit → 종결로.
     - `should_conclude_early` → 종결로.
     - `faction_for_turn(...)` (planned_total=final_limit, seed=post_id) 로 진영 결정.
     - 페르소나: **turn 0 은 글쓴이의 `ai_personas` 레코드가 있으면 그것** (호위대장, persona_key=`user:{user_id}`), 없으면 풀에서 선택.
     - 댓글 생성: system = 캐릭터 + 진영 지시 + 길이 스타일(`comment_style.pick_length_style`).
       - ALLY: 글쓴이(core_claim)에 공감하고 논리를 보강하라. 이전 도전자 논점이 있으면 재반박하라.
       - CHALLENGER: 정중하지만 명확하게 반박하고 대안을 제시하라. 이전 호위대 논점을 지적하라.
       - user = 원글 전문 + 최근 댓글 최대 10개 (`[진영/이름] 내용` 형식) 히스토리.
     - Insert(faction, persona, content, turn_index) → commit → `asyncio.sleep(uniform(DELAY_MIN, DELAY_MAX))`.
     - 개별 턴 실패: 1회 재시도 후 해당 턴 스킵(로그). 연속 3회 실패 시 종결로.
  3. 종결: **중재자 등판** —
     - `ally_likes` = ally 댓글 like 합, `chal_likes` = challenger 댓글 like 합.
     - `total = ally_likes + chal_likes`; `verdict = "tie"` if `total == 0 or abs(ally-chal) <= max(1, round(0.15*total))` else 다수 쪽 (`ally`/`challenger`).
     - 중재자 댓글 1개 생성 (AI: 토론 요약 + "호위대 우세/도전자 우세/팽팽" 선언. fake 모드는 스텁 문장).
     - `post.verdict` 저장, status=`concluded`.
  4. 최상위 try/except: 예기치 못한 오류 시에도 status가 `grading`/`debating` 에 영원히 남지 않게 `concluded` 로 마감 (verdict 미설정 허용) + 로그.
- **재점화(성장)**: reaction API 처리 후 — status=`concluded` 이고 non-moderator 댓글 수 < 새 final_limit 이고 조기종결 조건 아님 → status=`debating` 으로 되돌리고 `ensure_pipeline_scheduled`. 기존 moderator 댓글은 남긴다 (판정 역사). 새 종결 때 새 중재자 댓글 추가.

## 8. API (`main.py` + `schemas.py`) — 포트 8247

- `CORSMiddleware(allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])` — Flutter 웹 필수.
- 인증: 기존 JWT Bearer. `get_current_user`(필수) + `get_current_user_optional`(선택) 둘 다 제공.

### 응답 모델

```
CommentOut     : id, faction, persona_name, content, turn_index, likes, dislikes,
                 my_reaction ("like"|"dislike"|null), created_at(ISO8601)
PostSummaryOut : id, content, status, score, base_limit, final_limit, likes, dislikes,
                 net_reaction, comment_count(모더레이터 포함 전체), verdict, created_at,
                 author_name(email @ 앞부분), is_mine(bool), my_reaction
PostDetailOut  : PostSummaryOut 필드 전부 + score_breakdown, core_claim, comments:[CommentOut]
```

`final_limit` 은 조회 시점에 §4 공식으로 계산해 응답에 포함 (저장 안 함).

### 엔드포인트

| 메서드/경로 | 인증 | 동작 |
|---|---|---|
| GET `/api/health` | — | `{"ok":true,"db":true,"ai_mode":"real"\|"fake"}` (db는 SELECT 1 확인) |
| POST `/api/auth/signup` `{email,password}` | — | 201 `{token}` + 랜덤 페르소나 배정 (기존 유지) |
| POST `/api/auth/login` `{email,password}` | — | `{token}` / 401 |
| GET `/api/posts` | 선택 | `{"posts":[PostSummaryOut]}` id desc |
| POST `/api/posts` `{content}` | 필수 | **즉시** 201 PostDetailOut(status=grading, comments=[]) + 파이프라인 예약 |
| GET `/api/posts/{id}` | 선택 | PostDetailOut (Flutter 가 2초 폴링) / 404 |
| POST `/api/posts/{id}/reaction` `{reaction:"like"\|"dislike"\|"none"}` | 필수 | 토글/변경/삭제 → PostDetailOut. 재점화 조건 검사(§7) |
| POST `/api/comments/{id}/reaction` `{reaction:"like"\|"dislike"\|"none"}` | 필수 | 토글/변경/삭제 → CommentOut. 소속 글 재점화 조건 검사 |

- 토글 규칙: 같은 reaction 재전송 또는 `"none"` → 삭제, 다른 값 → 교체.
- `population_batch.py`: `compute_population` 은 `users` 수 카운트로 단순화, 기동 시 1회 즉시 갱신 + 매일 04:00 갱신 (기존 APScheduler 패턴, `DISABLE_SCHEDULER` 가드 유지).
- `if __name__ == "__main__": uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("COMEA_PORT", "8247")))`

## 9. 테스트 정책

- `conftest.py`: SQLite + `COMEA_FAKE_AI=1` + `COMEA_COMMENT_DELAY_MIN/MAX=0` + `DISABLE_SCHEDULER=1` 강제 (env 세팅은 import 전).
- Starlette `TestClient` 는 응답 후 BackgroundTasks 를 동기 실행하므로 delay=0 이면 파이프라인 흐름을 결정적으로 테스트 가능.
- 기존 테스트 중 새 스펙과 충돌하는 것(구 리밋 공식, is_locked, 동기 댓글 생성 가정)은 **삭제/재작성** — 통합 에이전트가 최종 정리.
- 필수 커버리지:
  - 공식 경계표: score 39/40/69/70/89/90, net 음수 내림, clamp 2/500, population_bonus 1/100/1000/10000
  - `faction_for_turn`: turn0=ally, 최소 1 도전자 보장, 1000턴 시뮬에서 도전자 비율 30~50%
  - grader: fake JSON 파싱, 파싱 실패 폴백
  - API 플로우: 글 작성 → (BG 실행 후) 댓글 존재 + 진영 혼재 + status=concluded + 중재자 댓글 존재 → 좋아요 누적 → final_limit 증가 → 재점화
  - verdict 경계 (0표=tie, 15% 이내=tie, 우세 판정)
  - 파이프라인 중복 예약 방지, 예외 시 concluded 마감

## 10. 완료 기준 (DoD)

1. `uv run pytest` 전체 통과 (루트에서).
2. `COMEA_FAKE_AI=1` 로 서버 기동(8247) → curl 스모크: signup → 글 작성 → 폴링으로 댓글 증가 관찰 → 투표 → detail 에 verdict/moderator 확인.
3. 도커 PG(5439) 에 create_all 로 스키마 생성 확인.
4. 실 OpenAI 모드에서 글 1개로 채점+댓글 생성 동작 (통합 단계에서 1회만, 짧은 글).
