import random

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import persona_deployment
from database import AiPersonaModel, UserModel


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _user_with_persona(db, email, name, hint):
    u = UserModel(email=email, password_hash="h")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(AiPersonaModel(
        user_id=u.id, display_name=name, persona_prompt=f"PROMPT_{name}",
        trait_params={"hint": hint} if hint else None,
    ))
    db.commit()
    return u


def test_excludes_author_and_injects_hint():
    db = _session()
    try:
        a = _user_with_persona(db, "a@x.com", "A페르소나", "")
        _user_with_persona(db, "b@x.com", "B페르소나", "HINT_B")
        result = persona_deployment.select_deployed_personas(db, exclude_user_id=a.id, k=2, rng=random.Random(0))
        names = [n for n, _ in result]
        assert "A페르소나" not in names           # 작성자 제외
        assert "B페르소나" in names                # 타 유저 포함
        prompt_b = dict(result)["B페르소나"]
        assert "PROMPT_B페르소나" in prompt_b and "HINT_B" in prompt_b  # prompt + hint
    finally:
        db.close()


def test_respects_k_limit():
    db = _session()
    try:
        author = _user_with_persona(db, "au@x.com", "작성자", "")
        for i in range(5):
            _user_with_persona(db, f"u{i}@x.com", f"P{i}", "")
        result = persona_deployment.select_deployed_personas(db, exclude_user_id=author.id, k=2, rng=random.Random(1))
        assert len(result) == 2
    finally:
        db.close()


def test_empty_when_no_other_personas():
    db = _session()
    try:
        a = _user_with_persona(db, "solo@x.com", "혼자", "")
        assert persona_deployment.select_deployed_personas(db, exclude_user_id=a.id, k=2) == []
    finally:
        db.close()
