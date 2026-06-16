from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import PostModel, ReactionModel


def _sqlite_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_post_has_is_locked_default_false():
    db = _sqlite_session()
    try:
        post = PostModel(content="테스트 글", score=95)
        db.add(post)
        db.commit()
        db.refresh(post)
        assert post.is_locked is False
    finally:
        db.close()


def test_reaction_row_stacks_with_timestamp():
    db = _sqlite_session()
    try:
        post = PostModel(content="테스트 글", score=70)
        db.add(post)
        db.commit()
        db.refresh(post)
        db.add(ReactionModel(post_id=post.id, reaction_type="like"))
        db.add(ReactionModel(post_id=post.id, reaction_type="dislike"))
        db.commit()
        rows = db.query(ReactionModel).filter(ReactionModel.post_id == post.id).all()
        assert len(rows) == 2  # 스택 적재
        assert all(r.created_at is not None for r in rows)  # 타임스탬프 부여
    finally:
        db.close()
