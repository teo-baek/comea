from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import persona_evolution
from database import (
    AiPersonaModel,
    CommentModel,
    CommentReactionModel,
    PostModel,
    UserModel,
)


def _factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _seed_user_reactions(db):
    u = UserModel(email="e@x.com", password_hash="h")
    db.add(u)
    db.commit()
    db.refresh(u)
    post = PostModel(content="x", score=40)
    db.add(post)
    db.commit()
    db.refresh(post)
    c1 = CommentModel(post_id=post.id, name="냉철 김박사", comment="a")
    c2 = CommentModel(post_id=post.id, name="공감 요정 웅이", comment="b")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)
    db.add(CommentReactionModel(user_id=u.id, comment_id=c1.id, reaction_type="like"))
    db.add(CommentReactionModel(user_id=u.id, comment_id=c2.id, reaction_type="dislike"))
    db.commit()
    return u


def test_compute_preferences_sums_plus_minus():
    db = _factory()()
    try:
        u = _seed_user_reactions(db)
        prefs = persona_evolution.compute_persona_preferences(db, u.id)
        assert prefs == {"냉철 김박사": 1, "공감 요정 웅이": -1}
    finally:
        db.close()


def test_build_prompt_hint():
    assert "냉철 김박사" in persona_evolution.build_prompt_hint({"냉철 김박사": 2, "공감 요정 웅이": -1})
    assert persona_evolution.build_prompt_hint({}) == ""
    assert persona_evolution.build_prompt_hint({"x": -1}) == ""  # 양수 없으면 빈 힌트


def test_run_persona_evolution_updates_trait_params(monkeypatch):
    Session = _factory()
    seed = Session()
    u = _seed_user_reactions(seed)
    seed.add(AiPersonaModel(user_id=u.id, display_name="x", persona_prompt="p"))
    seed.commit()
    seed.close()

    monkeypatch.setattr(database, "SessionLocal", Session)
    persona_evolution.run_persona_evolution()

    check = Session()
    try:
        p = check.query(AiPersonaModel).filter(AiPersonaModel.user_id == u.id).first()
        assert p.trait_params["prefs"]["냉철 김박사"] == 1
        assert "냉철 김박사" in p.trait_params["hint"]
    finally:
        check.close()
