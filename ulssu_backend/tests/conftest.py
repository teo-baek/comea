import os

# main/database import 전에 반드시 먼저 세팅 (모듈 로드 시 엔진 생성 + create_all 실행됨)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["OPENAI_API_KEY"] = "test-dummy-key"
os.environ["JWT_SECRET"] = "test-secret"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import main
import population


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    database.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[database.get_db] = override_get_db

    # 인메모리 전역 상태 격리: 각 테스트 시작 시 0으로 리셋
    population.set_current_population(0)

    # OpenAI 호출 함수 결정적 더미로 치환 (실제 네트워크 호출 차단).
    # generate_ai_comment 는 length_hint 까지 4개 인자를 받는다(Task 7에서 시그니처 확정).
    monkeypatch.setattr(main, "evaluate_post_quality", lambda user_post: 95, raising=False)
    monkeypatch.setattr(
        main,
        "generate_ai_comment",
        lambda persona_prompt, user_post, previous, length_hint: "AI 댓글",
        raising=False,
    )

    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
    population.set_current_population(0)


@pytest.fixture
def auth_client(client):
    """가입해서 토큰을 받은 뒤 Authorization 헤더를 단 TestClient."""
    resp = client.post("/api/auth/signup", json={"email": "tester@x.com", "password": "pw123456"})
    token = resp.json()["token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
