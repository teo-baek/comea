import main


def test_create_post_chitchat_still_gets_ten_comments(client, monkeypatch):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 40)  # 잡담 base 10
    resp = client.post("/api/posts", json={"content": "돈까스 땡긴다"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 40
    assert body["is_locked"] is False
    assert len(body["comments"]) == 10  # 소외 금지: 잡담도 10개


def test_create_post_normal_gets_fifteen(client, monkeypatch):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 70)  # 일반 base 15
    body = client.post("/api/posts", json={"content": "이직 고민"}).json()
    assert len(body["comments"]) == 15


def test_create_post_hot_gets_twenty(client, monkeypatch):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 95)  # 명글 base 20
    body = client.post("/api/posts", json={"content": "영끌 주식 마이너스 20%"}).json()
    assert len(body["comments"]) == 20


def test_create_post_response_hides_reaction_counts(client, monkeypatch):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 70)
    body = client.post("/api/posts", json={"content": "테스트"}).json()
    assert "like_count" not in body
    assert "dislike_count" not in body
    assert "reactions" not in body  # 반응 카운트/목록 비노출 (FR-3)


def test_create_post_comments_use_length_styles(client, monkeypatch):
    import comment_style
    captured = []

    def fake_comment(persona_prompt, user_post, previous, length_hint):
        captured.append(length_hint)
        return "AI 댓글"

    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 40)  # 10개
    monkeypatch.setattr(main, "generate_ai_comment", fake_comment)
    client.post("/api/posts", json={"content": "테스트"})
    assert len(captured) == 10
    assert all(h in comment_style.LENGTH_STYLES for h in captured)  # 분량 변주 주입(FR-13)
