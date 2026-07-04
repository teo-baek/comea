"""API 요청/응답 스키마 + 조회 시점 조립 헬퍼 (스펙 §8).

- final_limit 은 저장하지 않고 조회 시점에 §4 공식으로 계산한다:
  database.post_stats + elastic_limit + population.get_current_population 조합.
- created_at 은 ISO8601 문자열로 직렬화한다.
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel
from sqlalchemy.orm import Session

# elastic_limit 은 L 에이전트가 재작성 중 — 함수 참조를 호출 시점으로 미루기 위해 모듈 임포트.
import elastic_limit
from database import (
    CommentModel,
    CommentReactionModel,
    PostModel,
    ReactionModel,
    UserModel,
    comment_reaction_map,
    post_stats,
)
from population import get_current_population

# ---------------------------------------------------------------------------
# 요청 모델
# ---------------------------------------------------------------------------


class SignupIn(BaseModel):
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class PostCreateIn(BaseModel):
    content: str


class ReactionIn(BaseModel):
    reaction: str  # "like" | "dislike" | "none"


# ---------------------------------------------------------------------------
# 응답 모델 (스펙 §8)
# ---------------------------------------------------------------------------


class CommentOut(BaseModel):
    id: int
    faction: str
    persona_name: str
    content: str
    turn_index: int
    likes: int
    dislikes: int
    my_reaction: str | None = None  # "like" | "dislike" | None
    created_at: str  # ISO8601


class PostSummaryOut(BaseModel):
    id: int
    content: str
    status: str  # grading | debating | concluded
    score: int | None = None
    base_limit: int | None = None
    final_limit: int  # 조회 시점 계산 (§4)
    likes: int
    dislikes: int
    net_reaction: int
    comment_count: int  # moderator 포함 전체 댓글 수
    verdict: str | None = None  # ally | challenger | tie
    created_at: str  # ISO8601
    author_name: str | None = None  # email 의 @ 앞부분
    is_mine: bool = False
    my_reaction: str | None = None


class PostDetailOut(PostSummaryOut):
    score_breakdown: dict | None = None
    core_claim: str | None = None
    comments: list[CommentOut] = []


# ---------------------------------------------------------------------------
# 조립 헬퍼 — main.py 가 사용
# ---------------------------------------------------------------------------


def _iso(value: dt.datetime | None) -> str:
    """DateTime → ISO8601 문자열 (없으면 빈 문자열)."""
    return value.isoformat() if value is not None else ""


def compute_final_limit_now(db: Session, post: PostModel, stats: dict | None = None) -> int:
    """조회 시점 final_limit (§4). 채점 전(base_limit NULL)은 base 0 으로 간주 → FLOOR 로 클램프."""
    if stats is None:
        stats = post_stats(db, post.id)
    base = post.base_limit if post.base_limit is not None else 0
    bonus = elastic_limit.compute_population_bonus(get_current_population())
    return elastic_limit.compute_final_limit(base, stats["net_reaction"], bonus)


def _author_name(db: Session, post: PostModel) -> str | None:
    """작성자 email 의 @ 앞부분. 익명(author NULL)이면 None."""
    if post.author_user_id is None:
        return None
    email = db.query(UserModel.email).filter(UserModel.id == post.author_user_id).scalar()
    return email.split("@")[0] if email else None


def _my_post_reaction(db: Session, post_id: int, user: UserModel | None) -> str | None:
    if user is None:
        return None
    return (
        db.query(ReactionModel.reaction_type)
        .filter(ReactionModel.post_id == post_id, ReactionModel.user_id == user.id)
        .scalar()
    )


def _my_comment_reactions(db: Session, post_id: int, user: UserModel | None) -> dict[int, str]:
    """현재 유저가 이 글의 댓글들에 남긴 반응: comment_id -> 'like'|'dislike' (1쿼리)."""
    if user is None:
        return {}
    rows = (
        db.query(CommentReactionModel.comment_id, CommentReactionModel.reaction_type)
        .join(CommentModel, CommentModel.id == CommentReactionModel.comment_id)
        .filter(CommentModel.post_id == post_id, CommentReactionModel.user_id == user.id)
        .all()
    )
    return dict(rows)


def build_post_summary(db: Session, post: PostModel, user: UserModel | None) -> PostSummaryOut:
    """PostSummaryOut 조립 — 반응/댓글 집계는 post_stats 1세트로 해결."""
    stats = post_stats(db, post.id)
    return PostSummaryOut(
        id=post.id,
        content=post.content,
        status=post.status,
        score=post.score,
        base_limit=post.base_limit,
        final_limit=compute_final_limit_now(db, post, stats),
        likes=stats["post_likes"],
        dislikes=stats["post_dislikes"],
        net_reaction=stats["net_reaction"],
        comment_count=stats["total_comments"],
        verdict=post.verdict,
        created_at=_iso(post.created_at),
        author_name=_author_name(db, post),
        is_mine=(user is not None and post.author_user_id == user.id),
        my_reaction=_my_post_reaction(db, post.id, user),
    )


def build_comment_out(
    db: Session,
    comment: CommentModel,
    user: UserModel | None,
    reaction_counts: tuple[int, int] | None = None,
    my_reaction: str | None = ...,  # 기본: 단건 조회
) -> CommentOut:
    """CommentOut 조립. 목록 조립 시엔 집계 맵을 주입해 N+1 을 피한다."""
    if reaction_counts is None:
        likes, dislikes = comment_reaction_map(db, comment.post_id).get(comment.id, (0, 0))
    else:
        likes, dislikes = reaction_counts
    if my_reaction is ...:
        my_reaction = None
        if user is not None:
            my_reaction = (
                db.query(CommentReactionModel.reaction_type)
                .filter(
                    CommentReactionModel.comment_id == comment.id,
                    CommentReactionModel.user_id == user.id,
                )
                .scalar()
            )
    return CommentOut(
        id=comment.id,
        faction=comment.faction,
        persona_name=comment.persona_name,
        content=comment.content,
        turn_index=comment.turn_index,
        likes=likes,
        dislikes=dislikes,
        my_reaction=my_reaction,
        created_at=_iso(comment.created_at),
    )


def build_post_detail(db: Session, post: PostModel, user: UserModel | None) -> PostDetailOut:
    """PostDetailOut 조립 — 댓글 반응은 집계 맵 1쿼리 + 내 반응 1쿼리."""
    summary = build_post_summary(db, post, user)
    counts = comment_reaction_map(db, post.id)
    mine = _my_comment_reactions(db, post.id, user)
    comments = (
        db.query(CommentModel)
        .filter(CommentModel.post_id == post.id)
        .order_by(CommentModel.id.asc())
        .all()
    )
    return PostDetailOut(
        **summary.model_dump(),
        score_breakdown=post.score_breakdown,
        core_claim=post.core_claim,
        comments=[
            build_comment_out(
                db,
                c,
                user,
                reaction_counts=counts.get(c.id, (0, 0)),
                my_reaction=mine.get(c.id),
            )
            for c in comments
        ],
    )
