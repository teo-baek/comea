from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import population
import population_batch
from database import UserModel


def _session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_compute_population_counts_users():
    Session = _session_factory()
    db = Session()
    try:
        assert population_batch.compute_population(db) == 0
        db.add(UserModel(email="a@x.com", password_hash="h"))
        db.add(UserModel(email="b@x.com", password_hash="h"))
        db.commit()
        assert population_batch.compute_population(db) == 2
    finally:
        db.close()


def test_run_population_update_sets_value(monkeypatch):
    Session = _session_factory()
    seed = Session()
    seed.add(UserModel(email="c@x.com", password_hash="h"))
    seed.commit()
    seed.close()

    # run_population_update 는 database.SessionLocal 을 사용 → 테스트 팩토리로 치환
    monkeypatch.setattr(database, "SessionLocal", Session)
    population.set_current_population(999)

    population_batch.run_population_update()

    assert population.get_current_population() == 1


def test_run_population_update_swallows_errors(monkeypatch):
    # 세션 생성에서 예외가 나도 전파되지 않아야 함 (AC-5)
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(database, "SessionLocal", boom)
    population_batch.run_population_update()  # 예외 없이 통과
