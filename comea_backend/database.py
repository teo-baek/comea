import os
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Text,
    String,
    ForeignKey,
    DateTime,
    func,
    case,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# GCP 환경변수 주입을 고려한 설계 (Docker 로컬 주소를 기본값으로 셋팅)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://comea:comea@127.0.0.1:5439/comea",
)

# SQLite(테스트)일 때만 단일 커넥션/스레드 옵션을 적용. PostgreSQL(운영)은 기본값.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 중재자 진영 문자열 (factions.py 의 MODERATOR 와 동일 값 — 순환 임포트 방지 위해 리터럴 유지)
_MODERATOR = "moderator"


class PostModel(Base):
    # 스테이지 2 글: 채점(grading) → 토론(debating) → 종결(concluded) 상태 머신 (스펙 §3, §7)
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 익명 호환 NULL
    status = Column(String(16), nullable=False, default="grading", server_default="grading")
    score = Column(Integer, nullable=True)  # 0~100, 채점 전 NULL
    score_breakdown = Column(JSON, nullable=True)  # {"emotion":1~5,"controversy":..,"clarity":..,"novelty":..}
    core_claim = Column(Text, nullable=True)  # 채점관이 추출한 핵심 주장 1문장
    base_limit = Column(Integer, nullable=True)  # 점수 구간별 기본 댓글 리밋 (§4)
    verdict = Column(String(16), nullable=True)  # ally | challenger | tie (마지막 판정)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    comments = relationship("CommentModel", back_populates="post", cascade="all, delete-orphan")
    # 주의: reactions 관계는 의도적으로 노출하지 않음(직렬화 시 카운트 유출 방지). 집계는 post_stats 사용.


class CommentModel(Base):
    # AI 진영 댓글: faction(ally|challenger|moderator) + 페르소나 + 턴 순서 (스펙 §3, §7)
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    faction = Column(String(16), nullable=False)  # ally | challenger | moderator
    persona_key = Column(String, nullable=True)  # 페르소나 풀 key 또는 "user:{user_id}" (호위대장)
    persona_name = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    turn_index = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    post = relationship("PostModel", back_populates="comments")


class ReactionModel(Base):
    # 글 단위 좋아요/싫어요 — 인당 1표(토글/변경). UNIQUE(user_id, post_id) 로 강제 (스펙 §3)
    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reaction_type = Column(String, nullable=False)  # 'like' | 'dislike'
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_user_post"),)


class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class AiPersonaModel(Base):
    # 유저별 1:1 AI 페르소나(내부). 가입 시 풀에서 랜덤 배정. 자기 글에선 호위대장으로 등장 (§7).
    __tablename__ = "ai_personas"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    persona_prompt = Column(Text, nullable=False)
    trait_params = Column(JSON, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class CommentReactionModel(Base):
    # 댓글 단위 좋아요/싫어요(진화 신호 + verdict 판정 재료). 유저·댓글당 1개(토글/변경).
    __tablename__ = "comment_reactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=False)
    reaction_type = Column(String, nullable=False)  # 'like' | 'dislike'
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "comment_id", name="uq_user_comment"),)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 공용 집계 헬퍼 (스펙 §3.1) — D(토론)/M(API) 이 공용 사용. N+1 금지: 집계 쿼리 고정 3회/1회.
# ---------------------------------------------------------------------------

def post_stats(db, post_id: int) -> dict:
    """글 하나의 반응/댓글 집계.

    반환: {"post_likes", "post_dislikes", "comment_net",
           "non_moderator_count", "total_comments", "net_reaction"}
    - comment_net = Σ(각 댓글 like−dislike) — moderator 댓글 반응 포함 (§4)
    - net_reaction = (post_likes − post_dislikes) + comment_net
    - non_moderator_count = 리밋과 비교하는 댓글 수 (moderator 제외)
    """
    # 1) 글 반응 집계 (조건부 합계 1쿼리)
    post_likes, post_dislikes = db.query(
        func.coalesce(func.sum(case((ReactionModel.reaction_type == "like", 1), else_=0)), 0),
        func.coalesce(func.sum(case((ReactionModel.reaction_type == "dislike", 1), else_=0)), 0),
    ).filter(ReactionModel.post_id == post_id).one()

    # 2) 댓글 반응 순합 (댓글 조인 1쿼리 — moderator 포함)
    comment_net = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (CommentReactionModel.reaction_type == "like", 1),
                        (CommentReactionModel.reaction_type == "dislike", -1),
                        else_=0,
                    )
                ),
                0,
            )
        )
        .join(CommentModel, CommentModel.id == CommentReactionModel.comment_id)
        .filter(CommentModel.post_id == post_id)
        .scalar()
    )

    # 3) 댓글 수 (전체 + moderator 제외, 조건부 합계 1쿼리)
    total_comments, non_moderator_count = db.query(
        func.count(CommentModel.id),
        func.coalesce(func.sum(case((CommentModel.faction != _MODERATOR, 1), else_=0)), 0),
    ).filter(CommentModel.post_id == post_id).one()

    post_likes = int(post_likes)
    post_dislikes = int(post_dislikes)
    comment_net = int(comment_net)
    return {
        "post_likes": post_likes,
        "post_dislikes": post_dislikes,
        "comment_net": comment_net,
        "non_moderator_count": int(non_moderator_count),
        "total_comments": int(total_comments),
        "net_reaction": (post_likes - post_dislikes) + comment_net,
    }


def comment_reaction_map(db, post_id: int) -> dict[int, tuple[int, int]]:
    """글의 댓글별 반응 집계: comment_id -> (likes, dislikes).

    반응이 없는 댓글도 (0, 0) 으로 포함 (LEFT JOIN + GROUP BY 1쿼리 — N+1 금지).
    """
    rows = (
        db.query(
            CommentModel.id,
            func.coalesce(
                func.sum(case((CommentReactionModel.reaction_type == "like", 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((CommentReactionModel.reaction_type == "dislike", 1), else_=0)), 0
            ),
        )
        .outerjoin(CommentReactionModel, CommentReactionModel.comment_id == CommentModel.id)
        .filter(CommentModel.post_id == post_id)
        .group_by(CommentModel.id)
        .all()
    )
    return {cid: (int(likes), int(dislikes)) for cid, likes, dislikes in rows}
