def test_get_posts_empty(client):
    # 스펙 §8: 목록 응답은 {"posts": [...]} 래핑 형태
    resp = client.get("/api/posts")
    assert resp.status_code == 200
    assert resp.json() == {"posts": []}
