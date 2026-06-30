import database
import main
from database import AiPersonaModel, UserModel


def test_signup_creates_internal_persona(client):
    resp = client.post("/api/auth/signup", json={"email": "pp@x.com", "password": "pw123456"})
    assert resp.status_code == 201

    # 내부 페르소나가 1건 생성됐는지 DB로 직접 확인 (사용자에겐 노출 안 됨).
    # conftest 가 get_db 를 오버라이드했으므로 같은 엔진 세션을 얻어 조회.
    db = next(main.app.dependency_overrides[database.get_db]())
    try:
        user = db.query(UserModel).filter(UserModel.email == "pp@x.com").first()
        personas = db.query(AiPersonaModel).filter(AiPersonaModel.user_id == user.id).all()
        assert len(personas) == 1  # 1:1
        assert personas[0].display_name  # 이름 채워짐
    finally:
        db.close()
