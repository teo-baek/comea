import random

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from database import AiPersonaModel, UserModel
from personas import PERSONA_POOL, random_persona


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_random_persona_returns_pool_member_deterministic():
    name, prompt = random_persona(random.Random(0))
    assert (name, prompt) in PERSONA_POOL
    assert random_persona(random.Random(3)) == random_persona(random.Random(3))


def test_ai_persona_record_one_to_one():
    db = _session()
    try:
        user = UserModel(email="p@x.com", password_hash="h")
        db.add(user)
        db.commit()
        db.refresh(user)
        name, prompt = random_persona(random.Random(1))
        db.add(AiPersonaModel(user_id=user.id, display_name=name, persona_prompt=prompt))
        db.commit()
        rows = db.query(AiPersonaModel).filter(AiPersonaModel.user_id == user.id).all()
        assert len(rows) == 1
        assert rows[0].display_name == name
        assert rows[0].trait_params is None  # 풀 단계 진화 엔진이 채움
    finally:
        db.close()
