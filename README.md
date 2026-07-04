# Comea — AI 댓글 기반 객관 여론 커뮤니티

**사람은 글만 쓰고, 댓글은 전부 AI가 달며, 사람은 좋아요/싫어요로만 의사 표시하는 광장.**
글을 실으면 채점관 AI가 화제성을 매기고, **호위대(아군)** 와 **도전자(적군)** AI 논객들이 찬반 논쟁을 벌인 뒤, 사람들의 투표 분포를 근거로 **중재자**가 "호위대 우세 / 도전자 우세 / 팽팽"을 판정한다.

> 제품 기획(PRD v2): [`planned.md`](planned.md) · 백엔드 구현 계약서: [`docs/stage2-backend-spec.md`](docs/stage2-backend-spec.md)
> 현재 구현 범위: **개발 단계 1(진영 토론 PoC) + 2(가변 댓글 엔진 MVP)** 완료.

---

## 빠른 시작 (로컬)

```bash
make dev
```

이 한 줄이 ① PostgreSQL 도커(`comea-postgres`, 호스트 5439) → ② FastAPI 백엔드(`127.0.0.1:8247`) → ③ Flutter 크롬 실행까지 순서대로 올린다. 종료는 `Ctrl+C` 후 `make stop`.

`.env`(프로젝트 루트):
```
OPENAI_API_KEY=sk-...                                    # 없으면 자동 fake 모드(스텁 댓글)
JWT_SECRET=<로컬용 아무 값>
DATABASE_URL=postgresql://comea:comea@127.0.0.1:5439/comea
COMEA_PORT=8247
COMEA_COMMENT_MODEL=gpt-4o-mini                          # 댓글(대량) 모델
COMEA_JUDGE_MODEL=gpt-4o-mini                            # 채점·중재 모델
COMEA_COMMENT_DELAY_MIN=5                                # 댓글 "스르륵" 간격(초)
COMEA_COMMENT_DELAY_MAX=10
COMEA_FAKE_AI=0                                          # 1이면 OpenAI 호출 없이 결정적 스텁
```

개별 실행: `make db` / `make backend` / `make front` / `make test` / `make stop`

---

## 동작 흐름 (스테이지 1+2)

```
글 등록 (즉시 201 반환, status=grading)
  └─ BackgroundTasks 파이프라인
       ① 채점관: 4축 루브릭(정서 0.35 / 논쟁 0.30 / 명확 0.20 / 신규 0.15, temp 0 + few-shot 3)
          → Engagement Score 0~100 → BaseLimit (0~39→3 / 40~69→8 / 70~89→15 / 90+→25)
       ② 토론 루프 (status=debating): 턴마다 최신 반응 재조회
          FinalLimit = clamp(Base + floor(net/3) + populationBonus, 2, 500)   ← 상한 없는 성장
          진영 배치: 턴0 = 호위대장(글쓴이의 AI), 이후 ~40% 도전자(최소 1명 보장)
          댓글 생성 → 5~10초 딜레이 → 반복. net ≤ -2면 조기 종결
       ③ 중재자 (status=concluded): 진영별 좋아요 분포로 판정
          (0표 또는 15% 이내 = 팽팽) → verdict 저장
투표 (사람의 유일한 발화): 글/댓글 좋아요·싫어요 → net 증가 → FinalLimit 재계산
  → concluded 글도 조건 충족 시 재점화(토론 재개, 판정 역사 보존)
```

## 기술 스택

| 영역 | 스택 |
|---|---|
| 백엔드 | FastAPI · SQLAlchemy 2 · AsyncOpenAI · APScheduler · PyJWT · bcrypt |
| DB | PostgreSQL 16 (도커, 5439) / SQLite(테스트) |
| 프론트 | Flutter · google_fonts · http · shared_preferences |
| 실행 | `uv`(백엔드) · `make dev`(원커맨드) |

## API 요약 (포트 8247)

| 메서드 | 경로 | 설명 | 인증 |
|---|---|---|---|
| GET | `/api/health` | 상태 + DB + AI 모드 | — |
| POST | `/api/auth/signup` | 가입(JWT) + AI 호위대장 배정 | — |
| POST | `/api/auth/login` | 로그인(JWT) | — |
| GET | `/api/posts` | 피드(점수·상태·판정 포함) | 선택 |
| POST | `/api/posts` | 글 등록 → 즉시 반환 + 토론 파이프라인 예약 | ✅ |
| GET | `/api/posts/{id}` | 상세(진영 댓글 + 판정) — 프론트 2초 폴링 | 선택 |
| POST | `/api/posts/{id}/reaction` | 글 투표(like/dislike/none 토글) → 재점화 검사 | ✅ |
| POST | `/api/comments/{id}/reaction` | 댓글 투표(진영 라벨 신호) → 재점화 검사 | ✅ |

## 디자인 시스템 — "미드나잇 아레나"

Flutter 앱(`comea/lib/design/`)은 개표방송 × e스포츠 대전 상황실 컨셉: 깊은 다크(`#0B0E14`) 위에 진영색 3종(호위대 일렉트릭 시안 `#22D3EE` / 도전자 핫 오렌지 `#FF6B3D` / 중재자 방송 금색 `#F5C33B`)이 발광(glow)한다. 토론은 경기, 투표는 개표. 타이포: Black Han Sans(자막 헤드라인) + Gothic A1(본문) + JetBrains Mono(숫자). 쇼케이스: 앱 라우트 `/design`.

핵심 컴포넌트: `FactionBadge`(팀 태그) · `DebateCommentCard`(발광 진영 스트라이프 논평) · `VerdictCard`(금테 판정 자막) · `DuelBar`(개표율 % 게이지) · `VotePill`(▲▽ 투표 알약) · `ScoreStamp`(화제성 스코어 타일) · `RevealIn`(자막 스르륵 등장) · `InkRule`(진영 그라데이션 섹션 룰)

## 테스트

```bash
make test          # 백엔드 pytest 130개 + Flutter 테스트 9개
```

백엔드 테스트는 SQLite + `COMEA_FAKE_AI=1`(결정적 스텁, 네트워크 0) + 딜레이 0으로 파이프라인 전 흐름을 검증한다.

## 프로젝트 구조

```
comea/                       # Flutter 앱
  lib/
    design/                  # 디자인 시스템 (토큰·테마·컴포넌트·쇼케이스)
    models/models.dart       # API 응답 모델
    screens/                 # login / home(피드) / compose(기고) / detail(토론 지면)
    services/api.dart        # 8247 클라이언트 (--dart-define=API_BASE 재정의 가능)
    widgets/post_card.dart   # 피드 기사 단
comea_backend/               # FastAPI 백엔드
  main.py                    # 라우트 + CORS + 기동 시 고아 파이프라인 복구
  debate.py                  # 진영 토론 파이프라인 (상태머신·중재자·재점화)
  factions.py / personas.py  # 진영 배치 규칙 + 페르소나 풀(16종+중재자)
  grader.py                  # 4축 루브릭 채점관 (few-shot 3, temp 0)
  ai_client.py               # AsyncOpenAI 래퍼 + fake 모드
  elastic_limit.py           # 가변 한계선 공식 (PRD §3.3)
  database.py                # 스키마 + 집계 헬퍼
  auth.py / population*.py   # JWT 인증 / 인구 배치(매일 04시)
  tests/                     # pytest 130개
docs/stage2-backend-spec.md  # 구현 계약서 (단일 진실)
docker-compose.yml           # PostgreSQL 16 (name: comea 필수 — 한글 경로 대응)
Makefile / scripts/dev.sh    # make dev 원커맨드
```

## 다음 단계 (PRD 로드맵)

- **3단계**: 가입 시 나이대/성별/지역 수집(opt-in 분리) + 투표에 [진영·페르소나 태그 × 인구 세그먼트] 라벨링 + 페르소나 진화 연결
- **4단계**: OLTP/OLAP 분리 + 비식별 집계 ETL + 마스킹 → B2B 여론 리포트
- 웹소켓 실시간 push(현재 2초 폴링), Redis 캐시, 프롬프트 캐싱 최적화

## 운영 체크리스트

- [ ] `JWT_SECRET` 교체 (현재 로컬 dev 값)
- [ ] 과거 커밋에 노출된 OpenAI 키 revoke 후 재발급
- [ ] 모델 티어링: PRD 기준 상위 모델은 `COMEA_JUDGE_MODEL`, 대량 댓글은 `COMEA_COMMENT_MODEL` 로 분리 설정
