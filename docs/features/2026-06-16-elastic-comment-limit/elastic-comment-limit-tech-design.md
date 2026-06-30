---
slug: elastic-comment-limit
source: elastic-comment-limit-requirements.md
derived: true
---

# 기술설계: 가변적 한계선 + 실시간 반응

> ⚠️ planned.md §4 기술스택 + 현 `comea_backend` 코드 + 사용자 피드백 기준 합성 파생 문서.

## 1. 아키텍처 개요

FastAPI + SQLAlchemy(PostgreSQL 운영 / 테스트 SQLite) 위에 **순수 수식 모듈**(`elastic_limit.py`)과 **페르소나 데이터**(`personas.py`), **인구 상태 훅**(`population.py`)을 분리한다. 반응은 카운터 증가 대신 **개별 레코드(스택)** 로 적재해 동시 클릭 경합을 원천 제거한다. AI 생성 오케스트레이션은 `main.py` 라우트가 담당한다. 속도는 비요구이므로 생성은 단순 동기로 둔다.

## 2. 영향받는 컴포넌트

| 파일 | 작업 | 책임 |
|---|---|---|
| `comea_backend/elastic_limit.py` | **생성** | Base/Effective Cap/Final Limit 수식, 락 판정. 순수 함수 + 상수. |
| `comea_backend/population.py` | **생성** | `current_population` 인메모리 상태 get/set. 일일배치 슬라이스의 주입 훅. |
| `comea_backend/personas.py` | **생성** | 16종 페르소나 풀 + 순환 선택 `get_personas(n, start)`. |
| `comea_backend/comment_style.py` | **생성** | 댓글 분량 후보(`LENGTH_STYLES`) + 랜덤 선택 `pick_length_style(rng)`. |
| `comea_backend/database.py` | **수정** | `PostModel`에 `is_locked` 추가, `ReactionModel`(타임스탬프 스택) 신설, SQLite connect_args. |
| `comea_backend/main.py` | **수정** | `create_post` 수식 리팩터, `POST /api/posts/{id}/reaction` 추가, 하드코딩 키 제거. 반응 카운트 비노출. |
| `comea_backend/tests/` | **생성** | conftest(SQLite override + AI 모킹) + 단위/통합 테스트. |
| `pyproject.toml` | **수정** | dev deps `pytest`, `httpx`. |

## 3. 데이터 모델 변경

- `posts` 테이블: `is_locked BOOLEAN NOT NULL DEFAULT FALSE` **추가**. (좋아요/싫어요 카운트 컬럼은 두지 않음 — FR-3 비노출 + FR-9 스택)
- `reactions` 테이블 **신설**:
  - `id INTEGER PK`
  - `post_id INTEGER FK→posts.id (ondelete CASCADE)`
  - `reaction_type VARCHAR NOT NULL` ("like" | "dislike" — 내부 분석용 저장, 수식은 총량만 사용)
  - `created_at DATETIME NOT NULL DEFAULT now()` (타임스탬프 = 동시 클릭 구분 + 스택 순서)
- ⚠️ `PostModel`에는 `reactions` 관계를 **노출 매핑하지 않는다**(직렬화 시 카운트 유출 방지, FR-3). `ReactionModel`만 단방향 FK 보유.
- `comments` 테이블: 변경 없음.

## 4. 외부 인터페이스 (API)

- `POST /api/posts/{post_id}/reaction`
  - 요청: `{"reaction": "like" | "dislike"}`
  - 동작: 반응 레코드 1건 적재(스택) → (락 아니면) Final 재계산 → 부족분 동기 생성 → Cap 도달 시 잠금(중재자 없음).
  - 응답: 갱신된 post(댓글 포함, **반응 카운트 없음**). 404(없는 글), 400(잘못된 reaction).
- 기존 `POST /api/posts`, `GET /api/posts` 응답에 `is_locked` **추가**(가산적). 반응 카운트는 노출 안 함.

## 5. 핵심 결정 (대안 비교)

- **D1. 반응 = 타임스탬프 스택 레코드** (대안: 카운터 컬럼 증분). 스택 채택 — 동시 클릭 read-modify-write 경합 원천 제거(FR-9), B2B용 시계열 보존. 집계는 COUNT.
- **D2. 증감률 = 총 반응 수(좋아요+싫어요)** (대안: net = 좋아요−싫어요). 총량 채택 — "관심의 총량"이 토론을 키운다는 서비스 핵심(FR-2). 부호 구분은 수식에서 제거.
- **D3. 유저 수 → 상한** `Cap = max(25, current_population)` (대안: base에 곱연산 가중치). 상한 방식 채택 — 유저 적을 땐 고정 25, 폭증 시 유저수 비례 확장(FR-5). 값 출처는 `population.py` 훅(일일배치는 별도).
- **D4. 중재자 제거 + 조용한 종료** (대안: 요약 댓글 후 락). 제거 채택 — 사용자 명시 요구(FR-7). Cap 도달 시 `is_locked`만 세팅.
- **D5. 반응 카운트 비노출** (대안: 응답에 포함). 비노출 채택 — 글쓴이 보호(FR-3). Post에 카운트 컬럼/관계를 직렬화하지 않음.
- **D6. 페르소나 16종 + 순환** (대안: Cap만큼 고유). 순환 채택 — Cap이 유저수만큼 커질 수 있어 고유 정의 불가, 순환으로 충당(FR-12).
- **D7. 댓글 분량 = 랜덤 길이 스타일 주입** (대안: 고정 "2~3줄"). 랜덤 채택 — 긴 글/짧은 글이 섞여야 실제 게시판처럼 보임(FR-13). `comment_style.py`에 후보군+선택 함수를 두어 `generate_ai_comment`에 `length_hint`로 주입. 선택 함수는 `random.Random` 주입으로 테스트 결정성 확보.

## 6. 예비 위험 (→ 구현계획서 §2로 매핑)

- **side-effect:** 반응/생성 시 동기 OpenAI 호출. 속도는 비요구(FR-10)라 지연은 허용이나, 한 요청에서 다량 댓글 생성 시 비용 발생.
- **breaking:** `posts`에 `is_locked` 추가 + `reactions` 테이블 신설. 운영 PostgreSQL은 `create_all`로 ALTER/신설되지 않을 수 있어 마이그레이션 필요. 응답 스키마 `is_locked` 가산.
- **race:** 동시 반응은 스택 INSERT로 해소(FR-9)하나, 동시 생성 경로에서 Cap 초과 생성 가능성(두 요청이 동시에 부족분 계산). 완화: Cap 클램프 + 생성 후 재집계 락.

## 7. 테스트 전략

- **순수 함수**(`elastic_limit`, `personas`, `population`, `comment_style`): 외부 의존 없이 pytest 단위 테스트. `population`은 set/get + Cap 스케일링 검증. `comment_style`은 시드 주입으로 결정적 검증.
- **엔드포인트**: FastAPI `TestClient`(httpx) + SQLite in-memory(`get_db` override). OpenAI 호출(`evaluate_post_quality`, `generate_ai_comment`)은 monkeypatch 더미. 중재자 함수는 없음.
- 응답에 반응 카운트가 없음을 명시적으로 단언(FR-3 회귀 방지).
- `current_population`을 테스트에서 set하여 Cap 확장(AC-4) 검증.

## 변경이력
