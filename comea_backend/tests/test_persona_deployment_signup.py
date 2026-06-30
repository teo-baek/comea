import database
import main
from database import AiPersonaModel, UserModel


def test_create_post_deploys_other_user_persona(auth_client, monkeypatch):
    # 다른 유저 B + 페르소나(hint) 시드 (auth_client 의 유저 A 와 별개)
    db = next(main.app.dependency_overrides[database.get_db]())
    try:
        b = UserModel(email="b@x.com", password_hash="h")
        db.add(b)
        db.commit()
        db.refresh(b)
        db.add(AiPersonaModel(
            user_id=b.id, display_name="냉철 김박사",
            persona_prompt="PROMPT_B", trait_params={"hint": "HINT_B"},
        ))
        db.commit()
    finally:
        db.close()

    captured = []

    def fake_comment(persona_prompt, user_post, previous, length_hint):
        captured.append(persona_prompt)
        return "댓글"

    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 40)  # base 10
    monkeypatch.setattr(main, "generate_ai_comment", fake_comment)

    body = auth_client.post("/api/posts", json={"content": "x"}).json()

    # 총 댓글 수 불변(Final == base 10)
    assert len(body["comments"]) == 10
    # B 페르소나(타 유저)가 출동해 prompt+hint 로 생성됨 (AC-1/2)
    assert any("PROMPT_B" in p and "HINT_B" in p for p in captured)
