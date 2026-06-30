def test_get_posts_empty(client):
    resp = client.get("/api/posts")
    assert resp.status_code == 200
    assert resp.json() == []
