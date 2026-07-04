# debate.py 파이프라인 테스트 (스펙 §7, §9)
#
# - fake AI + 딜레이 0 + 스크래치 SQLite(StaticPool 인메모리)로 run_debate_pipeline 을 직접 실행.
# - grader/ai_client 가 아직 없어도(병렬 작업 중) 돌 수 있게 sys.modules 스텁을 주입하고,
#   실제 호출부는 monkeypatch(debate.grade_post / debate.get_ai_client)로 대체한다.
# - elastic_limit 은 스펙 §4 공식을 monkeypatch 로 주입해 L 에이전트 진행 상황과 무관하게
#   토론 엔진 ↔ 리밋 공식의 계약을 검증한다 (통합 단계에서 실 모듈과 일치).

import asyncio
import hashlib
import importlib
import math
import sys
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.background import BackgroundTasks

import database
from database import (
    AiPersonaModel,
    CommentModel,
    CommentReactionModel,
    PostModel,
    ReactionModel,
    UserModel,
)
import population


# --- 병렬 작업 중 미완성 모듈 스텁 (실 구현이 있으면 그대로 사용) -----------------

def _ensure_importable(name: str, **attrs) -> None:
    try:
        importlib.import_module(name)
        return
    except ImportError:
        mod = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[name] = mod


async def _stub_async(*_args, **_kwargs):
    raise RuntimeError("스텁 — 테스트에서 monkeypatch 로 대체해야 함")


_ensure_importable("grader", grade_post=_stub_async)
_ensure_importable("ai_client", get_ai_client=lambda: None)

import debate  # noqa: E402  (스텁 주입 이후 import)
import elastic_limit  # noqa: E402


# --- 테스트 더블 ---------------------------------------------------------------

class FakeAI:
    """결정적 fake AI — 동일 입력 = 동일 출력. fail_times 만큼 앞 호출을 실패시킨다."""

    def __init__(self, fail_times: int = 0):
        self.calls: list[tuple[str, str, str]] = []
        self._fail_remaining = fail_times

    async def complete(self, *, system: str, user: str, model: str,
                       temperature: float = 0.8, max_tokens: int | None = 400) -> str:
        self.calls.append((system, user, model))
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise RuntimeError("fake AI 실패")
        digest = hashlib.md5((system + "|" + user).encode()).hexdigest()[:8]
        return f"가짜 댓글 {digest}"


def _make_grade(score: int, core_claim: str = "핵심 주장 한 문장"):
    async def _fake_grade(_content: str):
        return types.SimpleNamespace(
            score=score,
            breakdown={"emotion": 2, "controversy": 2, "clarity": 2, "novelty": 2},
            core_claim=core_claim,
        )
    return _fake_grade


# --- 스펙 §4 공식 (로컬 주입용 — elastic_limit 완성본과 동일해야 한다) ------------

def _spec_base_limit(score: int) -> int:
    if score >= 90:
        return 25
    if score >= 70:
        return 15
    if score >= 40:
        return 8
    return 3


def _spec_population_bonus(mau: int) -> int:
    return max(0, math.floor(math.log10(max(mau, 1))) - 2)


def _spec_final_limit(base_limit: int, net_reaction: int, population_bonus: int, k: int = 3) -> int:
    return max(2, min(500, base_limit + (net_reaction // k) + population_bonus))


def _spec_should_conclude_early(net_reaction: int, comment_count: int) -> bool:
    return net_reaction <= -2 and comment_count >= 2


# --- 픽스처 ---------------------------------------------------------------------

@pytest.fixture(autouse=True)
def debate_env(monkeypatch):
    """스크래치 SQLite + fake AI + 딜레이 0 + §4 공식 주입 + _active 격리."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 세션 간 같은 인메모리 DB 공유
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    database.Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", testing_session)

    monkeypatch.setenv("COMEA_COMMENT_DELAY_MIN", "0")
    monkeypatch.setenv("COMEA_COMMENT_DELAY_MAX", "0")

    monkeypatch.setattr(elastic_limit, "compute_base_limit", _spec_base_limit, raising=False)
    monkeypatch.setattr(elastic_limit, "compute_population_bonus", _spec_population_bonus, raising=False)
    monkeypatch.setattr(elastic_limit, "compute_final_limit", _spec_final_limit, raising=False)
    monkeypatch.setattr(elastic_limit, "should_conclude_early", _spec_should_conclude_early, raising=False)

    population.set_current_population(0)
    debate._active.clear()

    fake_ai = FakeAI()
    monkeypatch.setattr(debate, "get_ai_client", lambda: fake_ai)
    monkeypatch.setattr(debate, "grade_post", _make_grade(30))  # base_limit=3 (작고 결정적)

    yield types.SimpleNamespace(Session=testing_session, fake_ai=fake_ai)

    debate._active.clear()
    engine.dispose()


# --- 데이터 헬퍼 ----------------------------------------------------------------

def _make_user(db, email: str = "writer@x.com", with_persona: bool = True) -> UserModel:
    user = UserModel(email=email, password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    if with_persona:
        db.add(AiPersonaModel(
            user_id=user.id, display_name="호위대장 페르소나", persona_prompt="글쓴이 전속 AI.",
        ))
        db.commit()
    return user


def _make_post(db, user_id: int | None = None, **kwargs) -> PostModel:
    post = PostModel(content="시뮬레이션 정책 도입은 옳은가?", author_user_id=user_id, **kwargs)
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def _comments(db, post_id: int) -> list[CommentModel]:
    return (
        db.query(CommentModel)
        .filter(CommentModel.post_id == post_id)
        .order_by(CommentModel.id)
        .all()
    )


class _RecordingBG:
    """add_task 호출만 기록하는 BackgroundTasks 대역."""

    def __init__(self):
        self.count = 0

    def add_task(self, _fn, *args, **kwargs):
        self.count += 1


# --- 전체 흐름: 채점 → 토론 → 중재자 종결 ---------------------------------------

def test_full_pipeline_grades_debates_and_concludes(debate_env):
    db = debate_env.Session()
    user = _make_user(db)
    post = _make_post(db, user_id=user.id)  # status 기본값 = grading
    post_id, user_id = post.id, user.id
    db.close()

    asyncio.run(debate.run_debate_pipeline(post_id))

    db = debate_env.Session()
    post = db.get(PostModel, post_id)
    # 채점 결과 저장 (스펙 §7-1)
    assert post.score == 30
    assert post.score_breakdown == {"emotion": 2, "controversy": 2, "clarity": 2, "novelty": 2}
    assert post.core_claim == "핵심 주장 한 문장"
    assert post.base_limit == 3
    # 종결 + 판정 저장 (반응 0표 → tie)
    assert post.status == "concluded"
    assert post.verdict == "tie"

    comments = _comments(db, post_id)
    debaters = [c for c in comments if c.faction != "moderator"]
    moderators = [c for c in comments if c.faction == "moderator"]
    # 댓글 수 == final_limit (base 3 + 반응 0)
    assert len(debaters) == 3
    assert [c.turn_index for c in debaters] == [0, 1, 2]
    # 진영 혼재 — turn0 ally + 최소 1 도전자 보장
    assert {c.faction for c in debaters} == {"ally", "challenger"}
    # turn 0 = 글쓴이의 ai_personas 레코드 기반 호위대장 (persona_key='user:{id}')
    assert debaters[0].faction == "ally"
    assert debaters[0].persona_key == f"user:{user_id}"
    assert debaters[0].persona_name == "호위대장 페르소나"
    # 중재자 댓글 1개
    assert len(moderators) == 1
    assert moderators[0].persona_name
    assert moderators[0].content
    # 파이프라인 종료 후 _active 해제
    assert post_id not in debate._active
    db.close()


def test_turn0_uses_pool_when_author_has_no_persona(debate_env):
    db = debate_env.Session()
    user = _make_user(db, email="nopersona@x.com", with_persona=False)
    post = _make_post(db, user_id=user.id)
    post_id = post.id
    db.close()

    asyncio.run(debate.run_debate_pipeline(post_id))

    db = debate_env.Session()
    debaters = [c for c in _comments(db, post_id) if c.faction != "moderator"]
    assert debaters[0].faction == "ally"
    assert not debaters[0].persona_key.startswith("user:")  # 풀 페르소나 사용
    db.close()


# --- 좋아요로 리밋 성장 + 다수 판정 ----------------------------------------------

def test_likes_extend_limit_and_majority_verdict(debate_env):
    db = debate_env.Session()
    author = _make_user(db)
    voters = [_make_user(db, email=f"voter{i}@x.com", with_persona=False) for i in range(5)]
    post = _make_post(db, user_id=author.id, status="debating", score=30, base_limit=3, core_claim="주장")
    seeded = []
    for turn, faction in enumerate(["ally", "ally", "challenger"]):
        comment = CommentModel(
            post_id=post.id, faction=faction, persona_key=f"k{turn}",
            persona_name=f"페르소나{turn}", content="기존 댓글", turn_index=turn,
        )
        db.add(comment)
        seeded.append(comment)
    db.commit()
    # ally 첫 댓글에 5 like, challenger 댓글에 1 like → comment_net=6 → final = 3 + 6//3 = 5
    for voter in voters:
        db.add(CommentReactionModel(user_id=voter.id, comment_id=seeded[0].id, reaction_type="like"))
    db.add(CommentReactionModel(user_id=voters[0].id, comment_id=seeded[2].id, reaction_type="like"))
    db.commit()
    post_id = post.id
    db.close()

    asyncio.run(debate.run_debate_pipeline(post_id))

    db = debate_env.Session()
    post = db.get(PostModel, post_id)
    debaters = [c for c in _comments(db, post_id) if c.faction != "moderator"]
    assert len(debaters) == 5  # 좋아요 6개로 리밋 3 → 5 성장 (§4 공식 반영)
    assert post.status == "concluded"
    assert post.verdict == "ally"  # 5:1 — 15% 허용폭 밖 → 호위대 우세
    db.close()


# --- 조기 종결 (net ≤ −2) --------------------------------------------------------

def test_early_conclusion_on_negative_net(debate_env):
    db = debate_env.Session()
    author = _make_user(db)
    haters = [_make_user(db, email=f"hater{i}@x.com", with_persona=False) for i in range(2)]
    post = _make_post(db, user_id=author.id, status="debating", score=50, base_limit=8, core_claim="주장")
    for turn, faction in enumerate(["ally", "challenger"]):
        db.add(CommentModel(
            post_id=post.id, faction=faction, persona_key=f"k{turn}",
            persona_name=f"페르소나{turn}", content="기존 댓글", turn_index=turn,
        ))
    for hater in haters:
        db.add(ReactionModel(post_id=post.id, user_id=hater.id, reaction_type="dislike"))
    db.commit()
    post_id = post.id
    db.close()

    asyncio.run(debate.run_debate_pipeline(post_id))

    db = debate_env.Session()
    post = db.get(PostModel, post_id)
    comments = _comments(db, post_id)
    debaters = [c for c in comments if c.faction != "moderator"]
    moderators = [c for c in comments if c.faction == "moderator"]
    assert post.status == "concluded"
    assert len(debaters) == 2   # net=-2, count=2 → 추가 생성 없이 조기 종결
    assert len(moderators) == 1  # 조기 종결에도 중재자는 등판
    db.close()


# --- 재점화 (concluded → debating → 새 중재자) -----------------------------------

def test_reignite_after_conclusion(debate_env):
    db = debate_env.Session()
    author = _make_user(db)
    post = _make_post(db, user_id=author.id)
    post_id = post.id
    db.close()

    asyncio.run(debate.run_debate_pipeline(post_id))  # 1차 종결 (댓글 3 + 중재자 1)

    # 글에 좋아요 9개 → net=9 → final = 3 + 9//3 = 6 > 3 → 재점화 대상
    db = debate_env.Session()
    for i in range(9):
        fan = _make_user(db, email=f"fan{i}@x.com", with_persona=False)
        db.add(ReactionModel(post_id=post_id, user_id=fan.id, reaction_type="like"))
    db.commit()
    db.close()

    bg = BackgroundTasks()
    assert debate.check_reignite(post_id, bg) is True

    db = debate_env.Session()
    assert db.get(PostModel, post_id).status == "debating"  # 상태 되돌림
    db.close()

    asyncio.run(bg())  # 예약된 파이프라인 실행 (Starlette 가 응답 후 실행하는 것과 동일)

    db = debate_env.Session()
    post = db.get(PostModel, post_id)
    comments = _comments(db, post_id)
    debaters = [c for c in comments if c.faction != "moderator"]
    moderators = [c for c in comments if c.faction == "moderator"]
    assert post.status == "concluded"
    assert len(debaters) == 6      # 새 final_limit 까지 추가 생성
    assert len(moderators) == 2    # 기존 판정 역사 유지 + 새 중재자 댓글
    db.close()


def test_check_reignite_false_when_limit_already_met(debate_env):
    db = debate_env.Session()
    author = _make_user(db)
    post = _make_post(db, user_id=author.id)
    post_id = post.id
    db.close()

    asyncio.run(debate.run_debate_pipeline(post_id))  # net=0 → final=3 == 댓글 3

    bg = _RecordingBG()
    assert debate.check_reignite(post_id, bg) is False
    assert bg.count == 0

    db = debate_env.Session()
    assert db.get(PostModel, post_id).status == "concluded"  # 상태 유지
    db.close()


def test_check_reignite_false_when_pipeline_active(debate_env):
    """debating + 실행 중 파이프라인 존재(_active) → 재예약하지 않는다."""
    db = debate_env.Session()
    author = _make_user(db)
    post = _make_post(db, user_id=author.id, status="debating", score=30, base_limit=3)
    post_id = post.id
    db.close()

    debate._active.add(post_id)  # 실행 중인 파이프라인이 선점한 상황
    try:
        bg = _RecordingBG()
        assert debate.check_reignite(post_id, bg) is False
        assert bg.count == 0
    finally:
        debate._active.discard(post_id)


def test_check_reignite_rescues_orphaned_debating_post(debate_env):
    """debating 인데 파이프라인이 없는 고아 글(유실된 예약) → 재예약으로 자가 복구."""
    db = debate_env.Session()
    author = _make_user(db)
    post = _make_post(db, user_id=author.id, status="debating", score=30, base_limit=3, core_claim="주장")
    post_id = post.id
    db.close()

    bg = BackgroundTasks()
    assert debate.check_reignite(post_id, bg) is True

    asyncio.run(bg())  # 예약된 파이프라인 실행

    db = debate_env.Session()
    post = db.get(PostModel, post_id)
    debaters = [c for c in _comments(db, post_id) if c.faction != "moderator"]
    assert post.status == "concluded"  # 고아 상태에서 정상 종결까지 복구
    assert len(debaters) == 3
    db.close()


# --- 동시성 가드 (_active — 실행 시점 선점) ---------------------------------------

def test_ensure_pipeline_scheduled_does_not_claim_at_schedule_time(debate_env):
    """예약은 _active 를 선점하지 않는다 — 실행되지 못한 예약이 가드를 오염시키지 않음.

    중복 방지는 실행 시점(run_debate_pipeline)의 no-op 가드가 담당하므로
    예약 자체는 항상 성공(True)한다.
    """
    bg = _RecordingBG()
    assert debate.ensure_pipeline_scheduled(12345, bg) is True
    assert debate.ensure_pipeline_scheduled(12345, bg) is True
    assert bg.count == 2
    assert 12345 not in debate._active  # 예약만으로는 선점 없음


def test_unexecuted_reservation_does_not_block_future_runs(debate_env):
    """예약 태스크가 실행되지 못해도(응답 전송 실패 등) 이후 실행이 막히지 않는다."""
    db = debate_env.Session()
    author = _make_user(db)
    post = _make_post(db, user_id=author.id)
    post_id = post.id
    db.close()

    lost = _RecordingBG()  # add_task 만 기록하고 실행하지 않음 — 유실된 예약 상황
    assert debate.ensure_pipeline_scheduled(post_id, lost) is True
    assert post_id not in debate._active  # _active 잔류 없음

    asyncio.run(debate.run_debate_pipeline(post_id))  # 이후 실행(복구 스캔 등)이 정상 진행

    db = debate_env.Session()
    assert db.get(PostModel, post_id).status == "concluded"
    db.close()


def test_concurrent_pipelines_run_only_once(debate_env):
    """같은 글의 파이프라인 코루틴 2개가 동시에 시작해도 실행 시점 가드로 1개만 돈다."""
    db = debate_env.Session()
    author = _make_user(db)
    post = _make_post(db, user_id=author.id)
    post_id = post.id
    db.close()

    async def _race():
        await asyncio.gather(
            debate.run_debate_pipeline(post_id),
            debate.run_debate_pipeline(post_id),
        )

    asyncio.run(_race())

    db = debate_env.Session()
    post = db.get(PostModel, post_id)
    comments = _comments(db, post_id)
    debaters = [c for c in comments if c.faction != "moderator"]
    moderators = [c for c in comments if c.faction == "moderator"]
    assert post.status == "concluded"
    assert [c.turn_index for c in debaters] == [0, 1, 2]  # 중복 실행이면 turn_index 중복 발생
    assert len(moderators) == 1                            # 중복 실행이면 중재자 2개 발생
    db.close()


def test_run_pipeline_noop_when_already_active(debate_env):
    db = debate_env.Session()
    author = _make_user(db)
    post = _make_post(db, user_id=author.id)
    post_id = post.id
    db.close()

    debate._active.add(post_id)  # 다른 실행이 선점한 상황
    asyncio.run(debate.run_debate_pipeline(post_id))

    db = debate_env.Session()
    post = db.get(PostModel, post_id)
    assert post.status == "grading"  # 아무것도 안 함 (no-op)
    assert len(_comments(db, post_id)) == 0
    assert post_id in debate._active  # 선점자의 소유 — 건드리지 않음
    db.close()


# --- 실패 처리 -------------------------------------------------------------------

def test_turn_failure_recovers_with_retry(debate_env, monkeypatch):
    flaky = FakeAI(fail_times=1)  # 첫 시도만 실패 → 같은 턴 재시도로 복구
    monkeypatch.setattr(debate, "get_ai_client", lambda: flaky)

    db = debate_env.Session()
    author = _make_user(db)
    post = _make_post(db, user_id=author.id)
    post_id = post.id
    db.close()

    asyncio.run(debate.run_debate_pipeline(post_id))

    db = debate_env.Session()
    post = db.get(PostModel, post_id)
    debaters = [c for c in _comments(db, post_id) if c.faction != "moderator"]
    assert post.status == "concluded"
    assert len(debaters) == 3  # 실패에도 리밋까지 채움
    db.close()


def test_exception_forces_concluded(debate_env, monkeypatch):
    async def _boom(_content: str):
        raise RuntimeError("채점기 장애")

    monkeypatch.setattr(debate, "grade_post", _boom)

    db = debate_env.Session()
    author = _make_user(db)
    post = _make_post(db, user_id=author.id)
    post_id = post.id
    db.close()

    asyncio.run(debate.run_debate_pipeline(post_id))  # 예외가 새어 나오면 안 됨

    db = debate_env.Session()
    post = db.get(PostModel, post_id)
    assert post.status == "concluded"  # grading 에 영원히 남지 않음 (스펙 §7-4)
    assert post.verdict is None        # verdict 미설정 허용
    assert post_id not in debate._active  # finally 로 가드 해제
    db.close()


# --- verdict 경계 (0표 / 15% 이내 / 우세) -----------------------------------------

@pytest.mark.parametrize(
    ("ally_likes", "chal_likes", "expected"),
    [
        (0, 0, "tie"),          # 0표 → tie
        (1, 0, "tie"),          # total 1 → 허용폭 max(1, 0)=1, 격차 1 → tie
        (2, 0, "ally"),         # 격차 2 > 1 → 호위대 우세
        (0, 2, "challenger"),   # 반대 방향
        (11, 9, "tie"),         # total 20 → 허용폭 3, 격차 2 → tie
        (11, 8, "tie"),         # total 19 → 허용폭 round(2.85)=3, 격차 3 → tie (경계)
        (12, 8, "ally"),        # total 20 → 허용폭 3, 격차 4 → 우세
        (8, 12, "challenger"),
    ],
)
def test_compute_verdict_boundaries(ally_likes, chal_likes, expected):
    assert debate.compute_verdict(ally_likes, chal_likes) == expected
