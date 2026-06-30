from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import PostModel, ReactionModel, UserModel


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_user_and_authorship_columns():
    db = _session()
    try:
        user = UserModel(email="a@b.com", password_hash="x")
        db.add(user)
        db.commit()
        db.refresh(user)

        post = PostModel(content="글", score=70, author_user_id=user.id)
        db.add(post)
        db.commit()
        db.refresh(post)
        assert post.author_user_id == user.id

        r = ReactionModel(post_id=post.id, reaction_type="like", user_id=user.id)
        db.add(r)
        db.commit()
        assert r.user_id == user.id

        # 익명 호환: author/user NULL 허용
        anon = PostModel(content="익명", score=40)
        db.add(anon)
        db.commit()
        db.refresh(anon)
        assert anon.author_user_id is None
    finally:
        db.close()
