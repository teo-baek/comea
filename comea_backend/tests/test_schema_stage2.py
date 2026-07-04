# 스테이지 2 스키마 검증 (스펙 §3, §3.1)
# 스크래치 SQLite 파일에 create_all 후 inspector 로 컬럼/제약 존재를 검증하고,
# post_stats / comment_reaction_map 집계 헬퍼 동작을 확인한다.
# conftest 의 client 픽스처(main import)에 의존하지 않는 자급자족 테스트.
import os

# database import 전에 강제 (모듈 로드 시 엔진 생성 — PG 접속 시도 방지)
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database import (
    AiPersonaModel,
    Base,
    CommentModel,
    CommentReactionModel,
    PostModel,
    ReactionModel,
    UserModel,
    comment_reaction_map,
    post_stats,
)


@pytest.fixture
def engine(tmp_path):
    # 인메모리가 아닌 스크래치 파일 DB — 실제 DDL 산출물을 inspector 로 검증
    eng = create_engine(
        f"sqlite:///{tmp_path / 'schema_stage2.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# 1) 컬럼/제약 존재 검증 (inspector)
# ---------------------------------------------------------------------------

def _column_names(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_all_tables_created(engine):
    tables = set(inspect(engine).get_table_names())
    assert {"users", "ai_personas", "posts", "comments", "reactions", "comment_reactions"} <= tables


def test_posts_columns(engine):
    cols = _column_names(engine, "posts")
    assert {
        "id", "content", "author_user_id", "status", "score",
        "score_breakdown", "core_claim", "base_limit", "verdict", "created_at",
    } <= cols
    # 구 스키마의 잠금 플래그는 제거됨
    assert "is_locked" not in cols


def test_comments_columns(engine):
    cols = _column_names(engine, "comments")
    assert {
        "id", "post_id", "faction", "persona_key", "persona_name",
        "content", "turn_index", "created_at",
    } <= cols
    # 구 컬럼명(name/comment)은 하드 컷 교체됨 (하위호환 불필요)
    assert "name" not in cols
    assert "comment" not in cols


def test_reactions_columns_and_unique(engine):
    cols = _column_names(engine, "reactions")
    assert {"id", "post_id", "user_id", "reaction_type", "created_at"} <= cols
    # 인당 1표: UNIQUE(user_id, post_id)
    uniques = [set(u["column_names"]) for u in inspect(engine).get_unique_constraints("reactions")]
    assert {"user_id", "post_id"} in uniques


def test_comment_reactions_unique_kept(engine):
    # 기존 UNIQUE(user_id, comment_id) 유지
    uniques = [set(u["column_names"]) for u in inspect(engine).get_unique_constraints("comment_reactions")]
    assert {"user_id", "comment_id"} in uniques


def test_post_status_default_is_grading(db):
    post = PostModel(content="테스트 글")
    db.add(post)
    db.commit()
    db.refresh(post)
    assert post.status == "grading"
    assert post.score is None  # 채점 전 NULL 허용


def test_reactions_unique_enforced(db):
    user = UserModel(email="a@x.com", password_hash="h")
    post = PostModel(content="글")
    db.add_all([user, post])
    db.commit()

    db.add(ReactionModel(post_id=post.id, user_id=user.id, reaction_type="like"))
    db.commit()
    # 같은 (user, post) 두 번째 반응은 유니크 제약 위반
    db.add(ReactionModel(post_id=post.id, user_id=user.id, reaction_type="dislike"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# 2) 집계 헬퍼 동작 검증 (post_stats / comment_reaction_map)
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded(db):
    """시나리오 데이터.

    post1: 글 반응 like 2 / dislike 1
           댓글 c1(ally)=like 2, c2(challenger)=dislike 1, c3(moderator)=like 1, c4(ally)=반응 없음
           → comment_net = 2 - 1 + 1 = 2 (moderator 포함)
           → net_reaction = (2-1) + 2 = 3
           → total_comments = 4, non_moderator_count = 3
    post2: 격리 확인용 (like 1, 댓글 1 + 그 댓글 like 1)
    """
    u1 = UserModel(email="u1@x.com", password_hash="h")
    u2 = UserModel(email="u2@x.com", password_hash="h")
    u3 = UserModel(email="u3@x.com", password_hash="h")
    post1 = PostModel(content="글1")
    post2 = PostModel(content="글2")
    db.add_all([u1, u2, u3, post1, post2])
    db.commit()

    c1 = CommentModel(post_id=post1.id, faction="ally", persona_name="아군1", content="c1", turn_index=0)
    c2 = CommentModel(post_id=post1.id, faction="challenger", persona_name="도전1", content="c2", turn_index=1)
    c3 = CommentModel(post_id=post1.id, faction="moderator", persona_name="중재자", content="c3", turn_index=2)
    c4 = CommentModel(post_id=post1.id, faction="ally", persona_name="아군2", content="c4", turn_index=3)
    c5 = CommentModel(post_id=post2.id, faction="ally", persona_name="아군3", content="c5", turn_index=0)
    db.add_all([c1, c2, c3, c4, c5])
    db.commit()

    db.add_all([
        # post1 글 반응: like 2, dislike 1
        ReactionModel(post_id=post1.id, user_id=u1.id, reaction_type="like"),
        ReactionModel(post_id=post1.id, user_id=u2.id, reaction_type="like"),
        ReactionModel(post_id=post1.id, user_id=u3.id, reaction_type="dislike"),
        # post2 글 반응: like 1
        ReactionModel(post_id=post2.id, user_id=u1.id, reaction_type="like"),
        # post1 댓글 반응
        CommentReactionModel(comment_id=c1.id, user_id=u1.id, reaction_type="like"),
        CommentReactionModel(comment_id=c1.id, user_id=u2.id, reaction_type="like"),
        CommentReactionModel(comment_id=c2.id, user_id=u1.id, reaction_type="dislike"),
        CommentReactionModel(comment_id=c3.id, user_id=u3.id, reaction_type="like"),
        # post2 댓글 반응 (post1 집계에 섞이면 안 됨)
        CommentReactionModel(comment_id=c5.id, user_id=u2.id, reaction_type="like"),
    ])
    db.commit()
    return {"post1": post1, "post2": post2, "c1": c1, "c2": c2, "c3": c3, "c4": c4, "c5": c5}


def test_post_stats_scenario(db, seeded):
    stats = post_stats(db, seeded["post1"].id)
    assert stats == {
        "post_likes": 2,
        "post_dislikes": 1,
        "comment_net": 2,            # (+2) + (−1) + (+1, moderator 포함) + 0
        "non_moderator_count": 3,    # 리밋 비교용 — moderator 제외
        "total_comments": 4,
        "net_reaction": 3,           # (2−1) + 2
    }


def test_post_stats_isolated_per_post(db, seeded):
    # post2 집계에 post1 데이터가 섞이지 않는다
    stats = post_stats(db, seeded["post2"].id)
    assert stats == {
        "post_likes": 1,
        "post_dislikes": 0,
        "comment_net": 1,
        "non_moderator_count": 1,
        "total_comments": 1,
        "net_reaction": 2,
    }


def test_post_stats_empty_post(db):
    post = PostModel(content="반응 없는 글")
    db.add(post)
    db.commit()
    stats = post_stats(db, post.id)
    assert stats == {
        "post_likes": 0,
        "post_dislikes": 0,
        "comment_net": 0,
        "non_moderator_count": 0,
        "total_comments": 0,
        "net_reaction": 0,
    }


def test_comment_reaction_map_scenario(db, seeded):
    mapping = comment_reaction_map(db, seeded["post1"].id)
    assert mapping == {
        seeded["c1"].id: (2, 0),
        seeded["c2"].id: (0, 1),
        seeded["c3"].id: (1, 0),
        seeded["c4"].id: (0, 0),  # 반응 없는 댓글도 (0,0) 으로 포함
    }
    # 다른 글의 댓글은 포함되지 않는다
    assert seeded["c5"].id not in mapping


def test_comment_reaction_map_empty(db):
    post = PostModel(content="댓글 없는 글")
    db.add(post)
    db.commit()
    assert comment_reaction_map(db, post.id) == {}
