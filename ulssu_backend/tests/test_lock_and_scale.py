import main
import population


def _create(client, monkeypatch, score):
    monkeypatch.setattr(main, "evaluate_post_quality", lambda p: score)
    return client.post("/api/posts", json={"content": "테스트 고민 글"}).json()


def test_reaches_cap_and_locks_without_moderator(client, monkeypatch):
    # population 0 -> cap 25. 명글 base 20.
    post = _create(client, monkeypatch, 95)
    pid = post["id"]
    assert len(post["comments"]) == 20

    body = None
    for _ in range(5):
        body = client.post(f"/api/posts/{pid}/reaction", json={"reaction": "like"}).json()
        if body["is_locked"]:
            break
    assert body["is_locked"] is True
    assert len(body["comments"]) == 25  # Cap 25 도달
    # 중재자 댓글 없음(FR-7)
    assert all(c["name"] != "중재자 AI" for c in body["comments"])


def test_locked_thread_is_idempotent(client, monkeypatch):
    post = _create(client, monkeypatch, 95)
    pid = post["id"]
    body = None
    for _ in range(5):
        body = client.post(f"/api/posts/{pid}/reaction", json={"reaction": "like"}).json()
        if body["is_locked"]:
            break
    locked_count = len(body["comments"])
    # 잠긴 뒤 추가 반응: 댓글 수 불변 (FR-8)
    body2 = client.post(f"/api/posts/{pid}/reaction", json={"reaction": "dislike"}).json()
    assert body2["is_locked"] is True
    assert len(body2["comments"]) == locked_count


def test_large_population_allows_more_than_25_comments(client, monkeypatch):
    population.set_current_population(100)  # cap 100 (AC-4)
    post = _create(client, monkeypatch, 95)  # base 20
    pid = post["id"]
    body = None
    for _ in range(4):
        body = client.post(f"/api/posts/{pid}/reaction", json={"reaction": "like"}).json()
    # 20 * (1 + 4*0.1) = 28 -> 28, cap 100이라 25 초과 허용
    assert len(body["comments"]) == 28
    assert body["is_locked"] is False
