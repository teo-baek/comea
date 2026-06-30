import database
import main
from database import CommentReactionModel


def _create_post_with_comments(auth_client, monkeypatch):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: 40)  # 잡담 base 10
    return auth_client.post("/api/posts", json={"content": "테스트"}).json()


def _comment_reaction_rows(comment_id):
    db = next(main.app.dependency_overrides[database.get_db]())
    try:
        return db.query(CommentReactionModel).filter(CommentReactionModel.comment_id == comment_id).all()
    finally:
        db.close()


def test_comment_reaction_upsert(auth_client, monkeypatch):
    post = _create_post_with_comments(auth_client, monkeypatch)
    comment_id = post["comments"][0]["id"]

    r1 = auth_client.post(f"/api/comments/{comment_id}/reaction", json={"reaction": "like"})
    assert r1.status_code == 200
    rows = _comment_reaction_rows(comment_id)
    assert len(rows) == 1 and rows[0].reaction_type == "like"

    # 같은 유저·댓글 재호출 → 갱신(여전히 1건, dislike)
    auth_client.post(f"/api/comments/{comment_id}/reaction", json={"reaction": "dislike"})
    rows = _comment_reaction_rows(comment_id)
    assert len(rows) == 1 and rows[0].reaction_type == "dislike"


def test_comment_reaction_requires_token(client, monkeypatch):
    # 무토큰 401
    assert client.post("/api/comments/1/reaction", json={"reaction": "like"}).status_code == 401


def test_comment_reaction_missing_comment_404(auth_client):
    assert auth_client.post("/api/comments/99999/reaction", json={"reaction": "like"}).status_code == 404


def test_comment_reaction_invalid_400(auth_client, monkeypatch):
    post = _create_post_with_comments(auth_client, monkeypatch)
    cid = post["comments"][0]["id"]
    assert auth_client.post(f"/api/comments/{cid}/reaction", json={"reaction": "love"}).status_code == 400
