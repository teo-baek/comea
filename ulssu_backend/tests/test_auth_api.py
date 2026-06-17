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
