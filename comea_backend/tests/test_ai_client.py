"""ai_client 테스트 (스펙 §5) — 네트워크 호출 없이 fake/real 모드 스위칭과 결정성 검증."""

import asyncio
import json

import pytest

from ai_client import AIClient, FakeAIClient, get_ai_client, is_fake_mode, reset_ai_client


@pytest.fixture(autouse=True)
def _isolate_singleton():
    """각 테스트 전후로 싱글턴을 초기화해 교차 오염 방지."""
    reset_ai_client()
    yield
    reset_ai_client()


def _run(coro):
    # pytest-asyncio 미의존 — asyncio.run 으로 직접 실행
    return asyncio.run(coro)


# ── 모드 스위칭 ──────────────────────────────────────────────────────────────

def test_fake_mode_when_env_set(monkeypatch):
    monkeypatch.setenv("COMEA_FAKE_AI", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-anything")
    assert is_fake_mode() is True
    assert isinstance(get_ai_client(), FakeAIClient)


def test_fake_mode_when_no_api_key(monkeypatch):
    # 키 부재 → 자동 fake (경고 로그와 함께)
    monkeypatch.delenv("COMEA_FAKE_AI", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert is_fake_mode() is True
    assert isinstance(get_ai_client(), FakeAIClient)


def test_real_mode_when_key_present(monkeypatch):
    monkeypatch.delenv("COMEA_FAKE_AI", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    assert is_fake_mode() is False
    assert isinstance(get_ai_client(), AIClient)


def test_mode_switches_without_reset(monkeypatch):
    # env 는 호출 시점에 읽으므로 reset 없이도 다음 get 에서 모드가 갈아탄다
    monkeypatch.delenv("COMEA_FAKE_AI", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    assert isinstance(get_ai_client(), AIClient)
    monkeypatch.setenv("COMEA_FAKE_AI", "1")
    assert is_fake_mode() is True
    assert isinstance(get_ai_client(), FakeAIClient)


def test_singleton_and_reset(monkeypatch):
    monkeypatch.setenv("COMEA_FAKE_AI", "1")
    first = get_ai_client()
    assert get_ai_client() is first  # 같은 모드면 같은 인스턴스
    reset_ai_client()
    assert get_ai_client() is not first  # reset 후 재생성


# ── FakeAIClient 동작 ───────────────────────────────────────────────────────

def test_fake_returns_valid_grading_json(monkeypatch):
    monkeypatch.setenv("COMEA_FAKE_AI", "1")
    client = get_ai_client()
    raw = _run(client.complete(
        system="너는 채점관이다. 반드시 JSON 으로만 답하라.",
        user="[채점 대상 글]\n이직을 해야 할지 고민입니다.\n\n위 글을 루브릭에 따라 JSON 으로만 채점하라.",
        model="gpt-4o-mini",
    ))
    data = json.loads(raw)
    for axis in ("emotion", "controversy", "clarity", "novelty"):
        assert isinstance(data[axis], int)
        assert 1 <= data[axis] <= 5
    assert isinstance(data["core_claim"], str) and data["core_claim"]


def test_fake_returns_korean_comment_without_json(monkeypatch):
    monkeypatch.setenv("COMEA_FAKE_AI", "1")
    client = get_ai_client()
    out = _run(client.complete(
        system="너는 냉철 김박사다. 팩트 위주로 댓글을 단다.",
        user="유저의 게시글: '요즘 너무 힘들어요.' 의견을 달아줘.",
        model="gpt-4o-mini",
    ))
    assert isinstance(out, str) and out
    # JSON 이 아닌 자연어 한국어 문장이어야 한다
    assert any("가" <= ch <= "힣" for ch in out)
    with pytest.raises(ValueError):
        json.loads(out)


def test_fake_is_deterministic(monkeypatch):
    # 같은 입력 = 같은 출력 (댓글/JSON 둘 다)
    monkeypatch.setenv("COMEA_FAKE_AI", "1")
    client = get_ai_client()
    kwargs = dict(system="너는 공감 요정 웅이다.", user="게시글: '오늘 시험에 떨어졌어요.'", model="m")
    assert _run(client.complete(**kwargs)) == _run(client.complete(**kwargs))

    json_kwargs = dict(system="채점관. JSON only.", user="글: '부모님과 갈등이 심합니다.'", model="m")
    assert _run(client.complete(**json_kwargs)) == _run(client.complete(**json_kwargs))


def test_fake_varies_by_persona(monkeypatch):
    # 페르소나(system)가 다르면 서로 다른 문장 (hash 기반 변주)
    monkeypatch.setenv("COMEA_FAKE_AI", "1")
    client = get_ai_client()
    user = "유저의 게시글: '퇴사하고 세계여행을 갈까 합니다.' 의견을 달아줘."
    outputs = {
        _run(client.complete(system=f"너는 {name}다. 캐릭터에 맞게 댓글을 달아라.", user=user, model="m"))
        for name in ("냉철 김박사", "공감 요정 웅이", "삐딱 키보드워리어", "감성 시인 노을")
    }
    assert len(outputs) >= 2  # 최소한 전부 같지는 않아야 함


def test_fake_faction_tone_hints(monkeypatch):
    # 진영 지시가 들어간 system 이면 해당 진영 톤의 문장 풀에서 나온다
    import ai_client as mod

    monkeypatch.setenv("COMEA_FAKE_AI", "1")
    client = get_ai_client()
    user = "원글: '주 4일제 도입이 필요하다고 생각합니다.'"

    ally_out = _run(client.complete(
        system="[진영] 너는 호위대다. 글쓴이에게 공감하고 논리를 보강하라. 이전 도전자 논점이 있으면 재반박하라.",
        user=user, model="m"))
    assert any(opener in ally_out for opener in mod._ALLY_OPENERS)

    chal_out = _run(client.complete(
        system="[진영] 너는 도전자다. 정중하지만 명확하게 반박하고 대안을 제시하라. 이전 호위대 논점을 지적하라.",
        user=user, model="m"))
    assert any(opener in chal_out for opener in mod._CHALLENGER_OPENERS)

    mod_out = _run(client.complete(
        system="너는 중재자다. 토론을 요약하고 우세 진영을 선언하라.",
        user=user, model="m"))
    assert any(opener in mod_out for opener in mod._MODERATOR_OPENERS)
