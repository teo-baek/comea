def test_signup_returns_token(client):
    resp = client.post("/api/auth/signup", json={"email": "u1@x.com", "password": "pw123456"})
    assert resp.status_code == 201
    assert "token" in resp.json()


def test_duplicate_email_rejected(client):
    client.post("/api/auth/signup", json={"email": "dup@x.com", "password": "pw123456"})
    resp = client.post("/api/auth/signup", json={"email": "dup@x.com", "password": "pw123456"})
    assert resp.status_code == 409


def test_login_success_and_failure(client):
    client.post("/api/auth/signup", json={"email": "u2@x.com", "password": "pw123456"})
    ok = client.post("/api/auth/login", json={"email": "u2@x.com", "password": "pw123456"})
    assert ok.status_code == 200 and "token" in ok.json()
    bad = client.post("/api/auth/login", json={"email": "u2@x.com", "password": "WRONG"})
    assert bad.status_code == 401


def test_protected_write_requires_token(client):
    # 토큰 없이 글 작성/반응 → 401 (FR-4)
    assert client.post("/api/posts", json={"content": "x"}).status_code == 401
    assert client.post("/api/posts/1/reaction", json={"reaction": "like"}).status_code == 401


def test_authed_post_sets_author(auth_client):
    # 새 스펙(§8): 응답 모델은 author_user_id 대신 is_mine / author_name 을 노출한다
    body = auth_client.post("/api/posts", json={"content": "내 글"}).json()
    assert body["is_mine"] is True                # 작성자 연결됨
    assert body["author_name"] == "tester"        # email @ 앞부분
