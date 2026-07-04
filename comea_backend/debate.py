"""진영 토론 백그라운드 파이프라인 — 상태 머신 (스펙 §7, PRD 3.1/3.3).

글 등록 API 는 즉시 반환하고(스펙 §0), 이 파이프라인이 BackgroundTasks 로 실행된다.

    grading ──채점──▶ debating ──턴 루프(딜레이 연출)──▶ concluded(중재자 판정)
                          ▲                                   │
                          └──── 재점화(check_reignite) ◀───────┘

- DB 세션은 턴마다 `database.SessionLocal()` 로 짧게 열고 닫는다 (장수 세션 금지).
- 딜레이는 매 턴 env(COMEA_COMMENT_DELAY_MIN/MAX)에서 다시 읽는다 (테스트 0 허용).
- 동시성 가드: 모듈 전역 `_active` — 같은 글의 파이프라인 중복 실행 방지.
  선점은 예약 시점이 아니라 **실행 시점**(이벤트 루프 위, 첫 await 이전)에 수행한다.
  단일 루프에서 검사+추가 사이에 양보점이 없어 코루틴 간 원자적이고, 실행되지 못한
  예약(응답 전송 실패 등)이 가드를 영구 오염시키는 일도 없다.
- 최상위 예외 시에도 상태가 grading/debating 에 영원히 남지 않게 concluded 로 강제 마감.
  (취소는 예외 — 재기동 시 main 의 복구 스캔이 잔류 글의 파이프라인을 재개한다.)
"""

import asyncio
import logging
import os
import random

import database
from database import (
    AiPersonaModel,
    CommentModel,
    PostModel,
    comment_reaction_map,
    post_stats,
)
import elastic_limit
import population
from ai_client import get_ai_client
from comment_style import pick_length_style
from factions import ALLY, CHALLENGER, MODERATOR, faction_for_turn, pick_persona
from grader import grade_post
from personas import MODERATOR_PERSONA, Persona

logger = logging.getLogger("comea.debate")

# 글 상태 문자열 (스펙 §3)
STATUS_GRADING = "grading"
STATUS_DEBATING = "debating"
STATUS_CONCLUDED = "concluded"

# 프롬프트에 넣는 최근 댓글 수 / 페르소나 중복 회피 윈도우
HISTORY_WINDOW = 10
# 연속 턴 실패 허용 횟수 — 도달 시 토론을 접고 종결로 (무한 루프 방지)
MAX_CONSECUTIVE_FAILURES = 3

# 동시성 가드 — 현재 파이프라인이 실행(또는 예약)된 post_id 집합 (스펙 §7)
_active: set[int] = set()

# verdict → 중재자 선언 문구
_VERDICT_LABELS = {ALLY: "호위대 우세", CHALLENGER: "도전자 우세", "tie": "팽팽"}

# 진영별 시스템 프롬프트 지시 (스펙 §7)
_FACTION_DIRECTIVES = {
    ALLY: (
        "너는 글쓴이의 호위대(아군)다. 글쓴이의 핵심 주장에 공감하고 논리를 보강하라. "
        "이전 댓글에 도전자(반대 진영)의 논점이 있으면 그것을 재반박하라."
    ),
    CHALLENGER: (
        "너는 도전자(반대 진영)다. 정중하지만 명확하게 글쓴이의 주장을 반박하고 대안을 제시하라. "
        "이전 댓글에 호위대(아군 진영)의 논점이 있으면 그 허점을 지적하라."
    ),
}

# 히스토리 표기용 진영 라벨
_FACTION_LABELS = {ALLY: "호위대", CHALLENGER: "도전자", MODERATOR: "중재자"}


# ---------------------------------------------------------------------------
# 공개 진입점 (M 이 이 이름으로 import — 스펙 §7 시그니처)
# ---------------------------------------------------------------------------

def ensure_pipeline_scheduled(post_id: int, background_tasks) -> bool:
    """BackgroundTasks 에 파이프라인 실행을 예약한다. 항상 True(예약 성공) 반환.

    중복 방지는 예약 시점이 아니라 **실행 시점**(run_debate_pipeline 첫 부분, 첫 await
    이전)에 이벤트 루프 위에서 원자적으로 수행한다. 이 구조로:
    - threadpool 의 동기 핸들러 2개(create_post / reaction 2종)가 동시에 예약해도
      파이프라인은 1개만 실행된다 (나머지는 실행 시점 no-op).
    - 예약만 되고 실행되지 못한 태스크(핸들러 후속 예외, 응답 전송 실패, 서버 종료)가
      `_active` 를 영구 오염시켜 글을 grading/debating 에 고착시키는 일이 없다.
    """
    background_tasks.add_task(run_debate_pipeline, post_id)
    return True


async def run_debate_pipeline(post_id: int) -> None:
    """파이프라인 실행 진입점 (예약 태스크 / 기동 복구 스캔 / 테스트 공용).

    첫 await 이전에 `_active` 검사+선점을 수행한다 — 단일 이벤트 루프에서 코루틴 간
    원자적이므로 같은 글의 파이프라인이 동시에 2개 돌 수 없다. 이미 실행 중이면 no-op.
    """
    if post_id in _active:
        return
    _active.add(post_id)
    try:
        await _pipeline(post_id)
    finally:
        _active.discard(post_id)


def check_reignite(post_id: int, background_tasks) -> bool:
    """reaction 처리 후 재점화(성장) 검사 (스펙 §7). 파이프라인 예약 여부 반환.

    status==concluded 이고 non-moderator 댓글 수 < 새 final_limit 이고
    조기종결 조건이 아니면 → status=debating 으로 되돌리고 파이프라인 재예약.
    기존 moderator 댓글은 판정 역사로 남긴다. 새 종결 때 새 중재자 댓글이 추가된다.

    부가 복구: grading/debating 인데 실행 중인 파이프라인이 없는 '고아' 글(예약 태스크가
    응답 전송 실패 등으로 유실된 경우)은 재예약으로 자가 복구한다. 실행 중 파이프라인과
    레이스가 나도 실행 시점 no-op 가드가 있어 중복 실행은 발생하지 않는다.
    """
    db = database.SessionLocal()
    try:
        post = db.get(PostModel, post_id)
        if post is None:
            return False
        if post.status in (STATUS_GRADING, STATUS_DEBATING):
            if post_id not in _active:
                # 진행형 상태인데 파이프라인이 없다 — 고아 글 자가 복구 (위 docstring)
                return ensure_pipeline_scheduled(post_id, background_tasks)
            return False  # 파이프라인이 이미 돌고 있음 — 다음 턴에서 최신 반응을 반영
        if post.status != STATUS_CONCLUDED or post.base_limit is None:
            return False
        stats = post_stats(db, post_id)
        final_limit = _current_final_limit(post.base_limit, stats["net_reaction"])
        if stats["non_moderator_count"] >= final_limit:
            return False
        if elastic_limit.should_conclude_early(stats["net_reaction"], stats["non_moderator_count"]):
            return False
        post.status = STATUS_DEBATING
        db.commit()
    finally:
        db.close()
    # ensure_pipeline_scheduled 는 항상 예약에 성공하므로(중복은 실행 시점 no-op),
    # debating 으로 되돌린 글이 파이프라인 없이 방치되지 않는다.
    return ensure_pipeline_scheduled(post_id, background_tasks)


def compute_verdict(ally_likes: int, chal_likes: int) -> str:
    """좋아요 분포만으로 판정 (스펙 §7-3). 0표 또는 15% 이내 격차 → tie."""
    total = ally_likes + chal_likes
    if total == 0 or abs(ally_likes - chal_likes) <= max(1, round(0.15 * total)):
        return "tie"
    return ALLY if ally_likes > chal_likes else CHALLENGER


# ---------------------------------------------------------------------------
# 내부 구현
# ---------------------------------------------------------------------------

async def _pipeline(post_id: int) -> None:
    """채점 → 토론 루프 → 중재자 종결. 최상위 예외 시 concluded 강제 마감 (스펙 §7-4)."""
    try:
        if not await _grade_stage(post_id):
            return
        if await _debate_loop(post_id):
            await _conclude(post_id)
    except asyncio.CancelledError:
        # graceful shutdown 등으로 태스크가 취소된 경우 — 강제 마감하지 않고 전파한다.
        # 글은 grading/debating 으로 남지만 재기동 시 main 의 복구 스캔이 재개한다.
        logger.info("토론 파이프라인 취소 (post_id=%s) — 재기동 복구 스캔이 재개", post_id)
        raise
    except Exception:
        logger.exception("토론 파이프라인 실패 (post_id=%s) — concluded 로 강제 마감", post_id)
        _force_conclude(post_id)


async def _grade_stage(post_id: int) -> bool:
    """status=grading 이면 채점 후 debating 전환. 계속 진행해도 되면 True.

    이미 score 가 있으면 채점을 스킵한다 (재점화 경로 — 스펙 §7-1).
    """
    db = database.SessionLocal()
    try:
        post = db.get(PostModel, post_id)
        if post is None:
            logger.warning("존재하지 않는 글의 파이프라인 예약 (post_id=%s)", post_id)
            return False
        if post.status == STATUS_CONCLUDED:
            return False  # 뒤늦게 실행된 stale 예약 — no-op
        if post.score is None:
            result = await grade_post(post.content)
            post.score = result.score
            post.score_breakdown = result.breakdown
            post.core_claim = result.core_claim
        if post.base_limit is None:
            post.base_limit = elastic_limit.compute_base_limit(post.score)
        if post.status == STATUS_GRADING:
            post.status = STATUS_DEBATING
        db.commit()
        return True
    finally:
        db.close()


async def _debate_loop(post_id: int) -> bool:
    """턴 루프 — 매 턴 DB 를 재조회해 최신 반응을 반영한다 (스펙 §7-2).

    반환값: True = 정상 종결 사유 도달(리밋/조기종결/연속 실패) → 중재자 등판.
            False = 글이 사라졌거나 외부에서 상태가 바뀜 → 중재자 생략.
    """
    consecutive_failures = 0
    while True:
        db = database.SessionLocal()
        try:
            post = db.get(PostModel, post_id)
            if post is None or post.status != STATUS_DEBATING:
                return False
            stats = post_stats(db, post_id)
            final_limit = _current_final_limit(post.base_limit, stats["net_reaction"])
            if stats["non_moderator_count"] >= final_limit:
                return True  # 리밋 도달 → 종결로
            if elastic_limit.should_conclude_early(stats["net_reaction"], stats["non_moderator_count"]):
                return True  # 싫어요 누적 조기 종결 → 중재자 등판

            turn_index = stats["non_moderator_count"]
            challenger_so_far = (
                db.query(CommentModel)
                .filter(CommentModel.post_id == post_id, CommentModel.faction == CHALLENGER)
                .count()
            )
            faction = faction_for_turn(
                turn_index,
                seed=post_id,
                challenger_so_far=challenger_so_far,
                planned_total=final_limit,
            )
            # 페르소나/분량 선택용 결정적 rng (post, turn 별 재현 가능)
            rng = random.Random((post_id, turn_index, 104729).__hash__())
            recent = _recent_comments(db, post_id)
            persona = _resolve_persona(db, post, turn_index, faction, rng, recent)
            system = _build_comment_system(persona, faction, post.core_claim, rng)
            user = _build_comment_user(post.content, recent)

            try:
                content = await _complete_with_retry(system, user, _comment_model())
            except Exception:
                consecutive_failures += 1
                logger.warning(
                    "댓글 생성 실패 — 턴 스킵 (post=%s turn=%s, 연속 %s회)",
                    post_id, turn_index, consecutive_failures,
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    return True  # 연속 3회 실패 → 종결로 (스펙 §7-2)
                continue

            consecutive_failures = 0
            db.add(CommentModel(
                post_id=post_id,
                faction=faction,
                persona_key=persona.key,
                persona_name=persona.name,
                content=content,
                turn_index=turn_index,
            ))
            db.commit()
        finally:
            db.close()

        # 읽는 속도에 맞춘 "스르륵" 연출 — 매 턴 env 재조회 (스펙 §1)
        lo, hi = _read_delay_range()
        delay = random.uniform(lo, hi)
        if delay > 0:
            await asyncio.sleep(delay)


async def _conclude(post_id: int) -> None:
    """중재자 등판: 좋아요 분포 판정 + 요약 댓글 1개 + verdict 저장 + concluded (스펙 §7-3)."""
    db = database.SessionLocal()
    try:
        post = db.get(PostModel, post_id)
        if post is None or post.status == STATUS_CONCLUDED:
            return  # 외부에서 이미 종결됨 — 중복 중재 방지
        ally_likes, chal_likes = _faction_like_sums(db, post_id)
        verdict = compute_verdict(ally_likes, chal_likes)
        content = await _moderator_comment(db, post, ally_likes, chal_likes, verdict)
        stats = post_stats(db, post_id)
        db.add(CommentModel(
            post_id=post_id,
            faction=MODERATOR,
            persona_key=MODERATOR_PERSONA.key,
            persona_name=MODERATOR_PERSONA.name,
            content=content,
            turn_index=stats["total_comments"],
        ))
        post.verdict = verdict
        post.status = STATUS_CONCLUDED
        db.commit()
    finally:
        db.close()


def _force_conclude(post_id: int) -> None:
    """예기치 못한 오류 시 상태만이라도 concluded 로 마감 (verdict 미설정 허용)."""
    try:
        db = database.SessionLocal()
        try:
            post = db.get(PostModel, post_id)
            if post is not None and post.status != STATUS_CONCLUDED:
                post.status = STATUS_CONCLUDED
                db.commit()
        finally:
            db.close()
    except Exception:
        logger.exception("강제 마감마저 실패 (post_id=%s)", post_id)


# --- 계산/조회 헬퍼 ---------------------------------------------------------

def _current_final_limit(base_limit: int, net_reaction: int) -> int:
    """§4 공식으로 현재 final_limit 계산 (저장하지 않고 매번 계산)."""
    bonus = elastic_limit.compute_population_bonus(population.get_current_population())
    return elastic_limit.compute_final_limit(base_limit, net_reaction, bonus)


def _read_delay_range() -> tuple[float, float]:
    """딜레이 범위는 매 턴 env 에서 읽는다 (테스트가 0으로 바꿔도 즉시 반영)."""
    lo = float(os.getenv("COMEA_COMMENT_DELAY_MIN", "5"))
    hi = float(os.getenv("COMEA_COMMENT_DELAY_MAX", "10"))
    return lo, hi


def _comment_model() -> str:
    return os.getenv("COMEA_COMMENT_MODEL", "gpt-4o-mini")


def _judge_model() -> str:
    return os.getenv("COMEA_JUDGE_MODEL", "gpt-4o-mini")


def _recent_comments(db, post_id: int) -> list[CommentModel]:
    """최근 댓글 최대 HISTORY_WINDOW 개 — 오래된 것부터 정렬해 반환."""
    rows = (
        db.query(CommentModel)
        .filter(CommentModel.post_id == post_id)
        .order_by(CommentModel.id.desc())
        .limit(HISTORY_WINDOW)
        .all()
    )
    return list(reversed(rows))


def _resolve_persona(db, post, turn_index: int, faction: str, rng: random.Random, recent) -> Persona:
    """턴에 배치할 페르소나 결정.

    turn 0 호위대장: 글쓴이의 ai_personas 레코드가 있으면 그 페르소나를
    persona_key='user:{user_id}' 로 사용한다 (스펙 §7-2). 없으면 풀에서 선택.
    """
    if turn_index == 0 and faction == ALLY and post.author_user_id is not None:
        record = (
            db.query(AiPersonaModel)
            .filter(AiPersonaModel.user_id == post.author_user_id)
            .first()
        )
        if record is not None:
            return Persona(
                key=f"user:{post.author_user_id}",
                name=record.display_name,
                character_prompt=record.persona_prompt,
            )
    used_keys = {c.persona_key for c in recent if c.persona_key}
    return pick_persona(faction, rng, used_keys)


def _faction_like_sums(db, post_id: int) -> tuple[int, int]:
    """진영별 댓글 좋아요 합계 (판정 재료): (ally_likes, chal_likes)."""
    reaction_map = comment_reaction_map(db, post_id)
    rows = (
        db.query(CommentModel.id, CommentModel.faction)
        .filter(CommentModel.post_id == post_id)
        .all()
    )
    ally_likes = chal_likes = 0
    for comment_id, faction in rows:
        likes, _dislikes = reaction_map.get(comment_id, (0, 0))
        if faction == ALLY:
            ally_likes += likes
        elif faction == CHALLENGER:
            chal_likes += likes
    return ally_likes, chal_likes


# --- 프롬프트/AI 호출 -------------------------------------------------------

def _build_comment_system(persona: Persona, faction: str, core_claim: str | None, rng: random.Random) -> str:
    """system = 캐릭터 + 진영 지시 + 길이 스타일 (스펙 §7-2)."""
    parts = [
        "너는 Comea 커뮤니티의 AI 시민이다. 아래 캐릭터에 맞춰 한국어 댓글 1개만 출력하라.",
        f"[캐릭터] {persona.name}: {persona.character_prompt}",
        f"[진영 지시] {_FACTION_DIRECTIVES[faction]}",
    ]
    if core_claim:
        parts.append(f"[글쓴이의 핵심 주장] {core_claim}")
    parts.append(f"[분량] {pick_length_style(rng)}")
    return "\n".join(parts)


def _build_comment_user(post_content: str, recent_comments) -> str:
    """user = 원글 전문 + 최근 댓글 최대 10개 ([진영/이름] 내용 형식) 히스토리."""
    lines = [f"원글 전문:\n{post_content}"]
    if recent_comments:
        lines.append("\n최근 댓글:")
        for c in recent_comments:
            label = _FACTION_LABELS.get(c.faction, c.faction)
            lines.append(f"[{label}/{c.persona_name}] {c.content}")
    return "\n".join(lines)


async def _complete_with_retry(system: str, user: str, model: str) -> str:
    """AI 호출 — 실패 시 1회 재시도 (개별 턴 실패 정책, 스펙 §7-2)."""
    client = get_ai_client()
    try:
        return await client.complete(system=system, user=user, model=model)
    except Exception:
        logger.warning("AI 호출 실패 — 1회 재시도", exc_info=True)
        return await client.complete(system=system, user=user, model=model)


async def _moderator_comment(db, post, ally_likes: int, chal_likes: int, verdict: str) -> str:
    """중재자 요약 댓글 생성. AI 실패(재시도 포함) 시에도 판정은 지키도록 폴백 문장 사용."""
    label = _VERDICT_LABELS[verdict]
    system = (
        f"[캐릭터] {MODERATOR_PERSONA.name}: {MODERATOR_PERSONA.character_prompt}\n"
        "너는 판정을 바꿀 수 없다 — 좋아요 분포가 곧 판정이다. "
        "양 진영의 핵심 논점을 2~3문장으로 요약한 뒤, 판정 문구를 그대로 선언하라."
    )
    user = (
        _build_comment_user(post.content, _recent_comments(db, post.id))
        + f"\n\n좋아요 분포 — 호위대 {ally_likes} : 도전자 {chal_likes}."
        + f"\n판정: '{label}'. 이 판정 문구를 포함한 중재 댓글을 작성하라."
    )
    fallback = (
        f"토론을 마칩니다. 좋아요 분포(호위대 {ally_likes} : 도전자 {chal_likes})에 따라 "
        f"판정은 '{label}'입니다."
    )
    try:
        return await _complete_with_retry(system, user, _judge_model())
    except Exception:
        logger.warning("중재자 댓글 생성 실패 — 폴백 문장 사용 (post=%s)", post.id)
        return fallback
