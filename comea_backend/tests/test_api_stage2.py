"""스테이지 2 API 플로우 테스트 (스펙 §8, §9).

TestClient 는 응답 생성 **후** BackgroundTasks 를 동기 실행하므로:
- POST /api/posts 의 응답 JSON 은 파이프라인 실행 전 상태(grading, comments=[])
- 같은 client.post(...) 호출이 반환된 시점에는 파이프라인이 이미 완주한 상태
- 따라서 이후 GET 상세로 concluded/댓글/중재자/verdict 를 결정적으로 검증할 수 있다
(conftest 가 COMEA_FAKE_AI=1, 딜레이 0, 스케줄러 비활성, 파일 SQLite 를 강제)
"""
import datetime as dt

PASSWORD = "pw123456"


def _signup(client, email: str) -> str:
    resp = client.post("/api/auth/signup", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 201
    return resp.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_post(client, content: str = "이직을 해야 할지 3년째 고민 중입니다. 연봉은 오르지만 성장이 멈춘 느낌이에요.") -> dict:
    resp = client.post("/api/posts", json={"content": content})
    assert resp.status_code == 201
    return resp.json()


def _factions(detail: dict) -> list[str]:
    return [c["faction"] for c in detail["comments"]]


def _non_moderator_count(detail: dict) -> int:
    return sum(1 for c in detail["comments"] if c["faction"] != "moderator")


def _moderator_count(detail: dict) -> int:
    return sum(1 for c in detail["comments"] if c["faction"] == "moderator")


# ---------------------------------------------------------------------------
# 헬스체크 / 인증
# ---------------------------------------------------------------------------


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["db"] is True
    assert body["ai_mode"] == "fake"  # conftest 가 COMEA_FAKE_AI=1 강제


def test_signup_login_flow(client):
    # 가입 → 201 + 토큰
    token = _signup(client, "a@x.com")
    assert token

    # 중복 이메일 → 409
    dup = client.post("/api/auth/signup", json={"email": "a@x.com", "password": PASSWORD})
    assert dup.status_code == 409

    # 로그인 성공 → 토큰
    ok = client.post("/api/auth/login", json={"email": "a@x.com", "password": PASSWORD})
    assert ok.status_code == 200
    assert ok.json()["token"]

    # 비밀번호 오류 / 미가입 이메일 → 401
    assert client.post("/api/auth/login", json={"email": "a@x.com", "password": "wrong!"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "no@x.com", "password": PASSWORD}).status_code == 401


def test_signup_assigns_random_persona(client):
    """가입 시 내부 AI 페르소나 1개 배정 (자기 글 호위대장 후보 — 스펙 §8)."""
    import database
    from database import AiPersonaModel, UserModel

    _signup(client, "persona@x.com")
    db = database.SessionLocal()
    try:
        user = db.query(UserModel).filter(UserModel.email == "persona@x.com").first()
        persona = db.query(AiPersonaModel).filter(AiPersonaModel.user_id == user.id).first()
        assert persona is not None
        assert persona.display_name
        assert persona.persona_prompt
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 글 작성 — 즉시 201 + 백그라운드 파이프라인
# ---------------------------------------------------------------------------


def test_create_post_returns_immediately_as_grading(auth_client):
    created = _create_post(auth_client)
    # 즉시 반환 시점: 채점 전 상태 + 댓글 없음 (파이프라인은 응답 후 실행)
    assert created["status"] == "grading"
    assert created["comments"] == []
    assert created["score"] is None
    assert created["base_limit"] is None
    assert created["verdict"] is None
    assert created["is_mine"] is True
    assert created["author_name"] == "tester"  # email @ 앞부분
    # created_at 은 ISO8601 문자열
    dt.datetime.fromisoformat(created["created_at"])


def test_pipeline_concludes_with_factions_and_moderator(auth_client):
    created = _create_post(auth_client)

    # TestClient 특성상 위 요청이 반환된 시점엔 파이프라인이 완주됨 → 상세 재조회
    detail = auth_client.get(f"/api/posts/{created['id']}").json()

    assert detail["status"] == "concluded"
    assert detail["score"] is not None and 0 <= detail["score"] <= 100
    assert detail["base_limit"] is not None
    assert detail["score_breakdown"] is not None
    assert detail["core_claim"]

    comments = detail["comments"]
    assert len(comments) > 0
    factions = _factions(detail)
    assert set(factions) <= {"ally", "challenger", "moderator"}
    assert factions[0] == "ally"            # turn 0 = 호위대장 자리
    assert factions.count("challenger") >= 1  # 도전자 최소 1명 보장
    assert _moderator_count(detail) == 1      # 종결 시 중재자 1명 등판

    # 반응이 0 이므로 final_limit == base_limit, 비중재 댓글은 리밋만큼 채워짐
    assert detail["final_limit"] == detail["base_limit"]
    assert _non_moderator_count(detail) == detail["final_limit"]
    # comment_count 는 moderator 포함 전체
    assert detail["comment_count"] == len(comments)

    # 댓글 좋아요 0 → 판정은 팽팽(tie)
    assert detail["verdict"] == "tie"

    # 댓글 필드 검증
    for c in comments:
        assert c["persona_name"]
        assert c["content"]
        assert c["likes"] == 0 and c["dislikes"] == 0
        assert c["my_reaction"] is None
        dt.datetime.fromisoformat(c["created_at"])


def test_create_post_rejects_empty_content(auth_client):
    resp = auth_client.post("/api/posts", json={"content": "   "})
    assert resp.status_code == 400


def test_posts_list_desc_order(auth_client):
    first = _create_post(auth_client, "첫 번째 글입니다. 재택근무가 생산성에 도움이 될까요?")
    second = _create_post(auth_client, "두 번째 글입니다. 대학원 진학이 의미가 있을까요?")
    body = auth_client.get("/api/posts").json()
    ids = [p["id"] for p in body["posts"]]
    assert ids.index(second["id"]) < ids.index(first["id"])  # id desc
    assert all("comments" not in p for p in body["posts"])   # 목록은 Summary (댓글 미포함)


# ---------------------------------------------------------------------------
# 글 반응 — 토글 / 변경 / 삭제 + my_reaction
# ---------------------------------------------------------------------------


def test_post_reaction_toggle_change_delete(auth_client):
    post_id = _create_post(auth_client)["id"]

    # like 등록
    r1 = auth_client.post(f"/api/posts/{post_id}/reaction", json={"reaction": "like"}).json()
    assert (r1["likes"], r1["dislikes"], r1["my_reaction"]) == (1, 0, "like")
    assert r1["net_reaction"] == 1

    # 같은 like 재전송 → 토글 삭제
    r2 = auth_client.post(f"/api/posts/{post_id}/reaction", json={"reaction": "like"}).json()
    assert (r2["likes"], r2["dislikes"], r2["my_reaction"]) == (0, 0, None)

    # like → dislike 교체
    auth_client.post(f"/api/posts/{post_id}/reaction", json={"reaction": "like"})
    r3 = auth_client.post(f"/api/posts/{post_id}/reaction", json={"reaction": "dislike"}).json()
    assert (r3["likes"], r3["dislikes"], r3["my_reaction"]) == (0, 1, "dislike")

    # "none" → 명시 삭제
    r4 = auth_client.post(f"/api/posts/{post_id}/reaction", json={"reaction": "none"}).json()
    assert (r4["likes"], r4["dislikes"], r4["my_reaction"]) == (0, 0, None)

    # 허용 외 값 → 400
    bad = auth_client.post(f"/api/posts/{post_id}/reaction", json={"reaction": "love"})
    assert bad.status_code == 400


def test_comment_reaction_toggle_and_my_reaction(auth_client):
    post_id = _create_post(auth_client)["id"]
    detail = auth_client.get(f"/api/posts/{post_id}").json()
    comment_id = detail["comments"][0]["id"]

    # like 등록 → CommentOut 반환
    c1 = auth_client.post(f"/api/comments/{comment_id}/reaction", json={"reaction": "like"}).json()
    assert (c1["likes"], c1["dislikes"], c1["my_reaction"]) == (1, 0, "like")

    # 상세 재조회에도 my_reaction 반영
    detail2 = auth_client.get(f"/api/posts/{post_id}").json()
    target = next(c for c in detail2["comments"] if c["id"] == comment_id)
    assert target["my_reaction"] == "like"
    assert target["likes"] == 1

    # 같은 like 재전송 → 토글 삭제
    c2 = auth_client.post(f"/api/comments/{comment_id}/reaction", json={"reaction": "like"}).json()
    assert (c2["likes"], c2["my_reaction"]) == (0, None)

    # dislike 등록 후 "none" → 삭제
    auth_client.post(f"/api/comments/{comment_id}/reaction", json={"reaction": "dislike"})
    c3 = auth_client.post(f"/api/comments/{comment_id}/reaction", json={"reaction": "none"}).json()
    assert (c3["likes"], c3["dislikes"], c3["my_reaction"]) == (0, 0, None)

    # 허용 외 값 → 400
    assert auth_client.post(f"/api/comments/{comment_id}/reaction", json={"reaction": "x"}).status_code == 400


# ---------------------------------------------------------------------------
# 좋아요 누적 → final_limit 증가 → 재점화
# ---------------------------------------------------------------------------


def test_likes_grow_final_limit_and_reignite(auth_client):
    post_id = _create_post(auth_client)["id"]
    before = auth_client.get(f"/api/posts/{post_id}").json()
    assert before["status"] == "concluded"
    base = before["base_limit"]
    assert _non_moderator_count(before) == base
    assert _moderator_count(before) == 1

    # 서로 다른 유저 3명이 like → net +3 → final_limit = base + (3 // k=3) = base + 1
    for i in range(3):
        token = _signup(auth_client, f"voter{i}@x.com")
        resp = auth_client.post(
            f"/api/posts/{post_id}/reaction", json={"reaction": "like"}, headers=_auth(token)
        )
        assert resp.status_code == 200

    # 3번째 like 요청의 BackgroundTasks 로 재점화 파이프라인이 완주된 뒤 상태
    after = auth_client.get(f"/api/posts/{post_id}").json()
    assert after["final_limit"] == base + 1          # 조회 시점 재계산
    assert after["status"] == "concluded"            # 재점화 후 다시 종결
    assert _non_moderator_count(after) == base + 1   # 댓글 1개 추가 생성
    assert _moderator_count(after) == 2              # 기존 판정 유지 + 새 중재자 댓글
    assert after["likes"] == 3
    assert after["net_reaction"] == 3


# ---------------------------------------------------------------------------
# 비로그인 조회 허용 / 401 / 404
# ---------------------------------------------------------------------------


def test_unauthenticated_reads_allowed(auth_client):
    post_id = _create_post(auth_client)["id"]
    auth_client.post(f"/api/posts/{post_id}/reaction", json={"reaction": "like"})

    anon = {"Authorization": ""}  # 기본 헤더 무력화 (비로그인)
    listing = auth_client.get("/api/posts", headers=anon)
    assert listing.status_code == 200
    summary = next(p for p in listing.json()["posts"] if p["id"] == post_id)
    assert summary["is_mine"] is False
    assert summary["my_reaction"] is None
    assert summary["likes"] == 1  # 집계 자체는 공개

    detail = auth_client.get(f"/api/posts/{post_id}", headers=anon)
    assert detail.status_code == 200
    assert detail.json()["my_reaction"] is None

    # 잘못된 토큰도 401 이 아니라 비로그인으로 처리 (get_current_user_optional)
    broken = auth_client.get(f"/api/posts/{post_id}", headers={"Authorization": "Bearer broken"})
    assert broken.status_code == 200
    assert broken.json()["is_mine"] is False


def test_signed_token_with_bad_sub_is_not_500(auth_client):
    """서명은 유효하지만 sub 가 없거나 숫자가 아닌 토큰 — 선택 인증은 비로그인, 필수 인증은 401.

    (decode_token 이 KeyError/ValueError 를 흘려 500 이 나던 결함의 회귀 방지)
    """
    import jwt as pyjwt

    import auth

    for payload in ({}, {"sub": "not-a-number"}):
        weird = pyjwt.encode(payload, auth.JWT_SECRET, algorithm=auth.JWT_ALGORITHM)
        headers = {"Authorization": f"Bearer {weird}"}

        listing = auth_client.get("/api/posts", headers=headers)  # 선택 인증
        assert listing.status_code == 200
        assert all(p["is_mine"] is False for p in listing.json()["posts"])

        write = auth_client.post("/api/posts", json={"content": "글"}, headers=headers)  # 필수 인증
        assert write.status_code == 401


def test_write_endpoints_require_auth(auth_client):
    post_id = _create_post(auth_client)["id"]
    detail = auth_client.get(f"/api/posts/{post_id}").json()
    comment_id = detail["comments"][0]["id"]

    anon = {"Authorization": ""}
    assert auth_client.post("/api/posts", json={"content": "글"}, headers=anon).status_code == 401
    assert (
        auth_client.post(f"/api/posts/{post_id}/reaction", json={"reaction": "like"}, headers=anon).status_code
        == 401
    )
    assert (
        auth_client.post(
            f"/api/comments/{comment_id}/reaction", json={"reaction": "like"}, headers=anon
        ).status_code
        == 401
    )

    # 위조 토큰 → 401 (필수 인증 엔드포인트)
    bad = {"Authorization": "Bearer bogus"}
    assert auth_client.post("/api/posts", json={"content": "글"}, headers=bad).status_code == 401


def test_not_found_cases(auth_client):
    assert auth_client.get("/api/posts/999999").status_code == 404
    assert (
        auth_client.post("/api/posts/999999/reaction", json={"reaction": "like"}).status_code == 404
    )
    assert (
        auth_client.post("/api/comments/999999/reaction", json={"reaction": "like"}).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# 재시작 복구 — grading/debating 잔류 글의 파이프라인 재개 (main startup 스캔)
# ---------------------------------------------------------------------------


def test_startup_resumes_stuck_pipelines(db_tables):
    """프로세스가 죽어 grading/debating 에 잔류한 글은 재기동 시 파이프라인이 재개된다.

    파이프라인은 요청 단위 BackgroundTasks(인메모리)라 서버 재시작 시 사라진다 —
    startup 복구 스캔이 없으면 잔류 글은 영원히 진행되지 않는다(무한 폴링) 결함의 회귀 방지.
    """
    import time

    from fastapi.testclient import TestClient

    import database
    import main
    import population
    from database import PostModel

    population.set_current_population(0)

    # 이전 프로세스가 중간에 죽은 상황 재현: 서버(TestClient) 기동 전에 잔류 글을 심는다
    db = database.SessionLocal()
    try:
        grading = PostModel(content="채점 중에 서버가 죽은 글입니다.", status="grading")
        debating = PostModel(
            content="토론 중에 서버가 죽은 글입니다.",
            status="debating", score=30, base_limit=3, core_claim="핵심 주장",
        )
        db.add_all([grading, debating])
        db.commit()
        grading_id, debating_id = grading.id, debating.id
    finally:
        db.close()

    with TestClient(main.app) as client:  # startup 훅 → 복구 스캔 → 파이프라인 재개
        deadline = time.time() + 10  # fake AI + 딜레이 0 이라 실제로는 수십 ms 내 종결
        g = d = None
        while time.time() < deadline:
            g = client.get(f"/api/posts/{grading_id}").json()
            d = client.get(f"/api/posts/{debating_id}").json()
            if g["status"] == "concluded" and d["status"] == "concluded":
                break
            time.sleep(0.05)

        assert g["status"] == "concluded"
        assert g["score"] is not None            # grading 잔류 글은 채점부터 재개
        assert _moderator_count(g) == 1
        assert d["status"] == "concluded"
        assert _non_moderator_count(d) == d["final_limit"]  # debating 잔류 글은 턴 루프부터 재개
        assert _moderator_count(d) == 1

    population.set_current_population(0)
