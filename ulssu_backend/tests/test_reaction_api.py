import main


def _create(client, monkeypatch, score):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: score)
    return client.post("/api/posts", json={"content": "테스트 고민 글"}).json()


def test_reaction_stacks_and_grows_comments(client, monkeypatch):
    post = _create(client, monkeypatch, 70)  # base 15 -> 댓글 15
    assert len(post["comments"]) == 15
    # 15 * (1 + 1*0.1) = 16.5 -> 17 : 좋아요든 싫어요든 토론이 커짐
    resp = client.post(f"/api/posts/{post['id']}/reaction", json={"reaction": "dislike"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["comments"]) == 17
    assert body["is_locked"] is False
    # 응답에 반응 카운트 비노출(FR-3)
    assert "like_count" not in body and "dislike_count" not in body


def test_invalid_reaction_returns_400(client, monkeypatch):
    post = _create(client, monkeypatch, 70)
    resp = client.post(f"/api/posts/{post['id']}/reaction", json={"reaction": "love"})
    assert resp.status_code == 400


def test_reaction_on_missing_post_returns_404(client):
    resp = client.post("/api/posts/99999/reaction", json={"reaction": "like"})
    assert resp.status_code == 404
