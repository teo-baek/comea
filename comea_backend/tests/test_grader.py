"""grader 테스트 (스펙 §6) — fake 모드 채점, 서버측 score 계산, 파싱 재시도/폴백."""

import asyncio
import json

import pytest

import grader
from ai_client import reset_ai_client
from grader import AXES, WEIGHTS, GradeResult, grade_post


@pytest.fixture(autouse=True)
def _fake_mode(monkeypatch):
    """모든 테스트를 fake 모드로 강제 (네트워크 호출 0) + 싱글턴 격리."""
    monkeypatch.setenv("COMEA_FAKE_AI", "1")
    reset_ai_client()
    yield
    reset_ai_client()


def _run(coro):
    return asyncio.run(coro)


class StubClient:
    """미리 정한 응답(또는 예외)을 순서대로 돌려주는 채점용 스텁."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def complete(self, **kwargs):
        self.calls += 1
        item = self.responses.pop(0) if self.responses else ""
        if isinstance(item, Exception):
            raise item
        return item


# ── fake 모드 기본 동작 ─────────────────────────────────────────────────────

def test_grade_post_returns_valid_result():
    result = _run(grade_post("치매 초기인 아버지를 요양원에 모셔야 할지 고민입니다."))
    assert isinstance(result, GradeResult)
    assert isinstance(result.score, int)
    assert 0 <= result.score <= 100
    assert set(result.breakdown) == set(AXES)
    for value in result.breakdown.values():
        assert isinstance(value, int)
        assert 1 <= value <= 5
    assert isinstance(result.core_claim, str) and result.core_claim


def test_score_is_server_computed_weighted_sum():
    # score == round(가중합 * 20) — 반환된 breakdown 으로 역검산
    result = _run(grade_post("연봉을 줄여서라도 워라밸을 택하는 게 맞을까요?"))
    expected = round(sum(WEIGHTS[axis] * result.breakdown[axis] for axis in AXES) * 20)
    assert result.score == expected


def test_grade_post_is_deterministic():
    content = "부모님 반대를 무릅쓰고 비혼을 선언했습니다. 제가 이기적인 걸까요?"
    first = _run(grade_post(content))
    second = _run(grade_post(content))
    assert first == second  # fake 모드: 같은 글 = 같은 채점


# ── score 공식 경계 (StubClient 로 breakdown 고정) ─────────────────────────

def test_score_bounds_all_axes_extremes(monkeypatch):
    # 전축 5 → 100, 전축 1 → 20 (가중치 합 1.0 * 축값 * 20)
    top = json.dumps({a: 5 for a in AXES} | {"core_claim": "주장"}, ensure_ascii=False)
    monkeypatch.setattr(grader, "get_ai_client", lambda: StubClient([top]))
    assert _run(grade_post("글")).score == 100

    bottom = json.dumps({a: 1 for a in AXES} | {"core_claim": "주장"}, ensure_ascii=False)
    monkeypatch.setattr(grader, "get_ai_client", lambda: StubClient([bottom]))
    assert _run(grade_post("글")).score == 20


def test_out_of_range_axis_is_clamped(monkeypatch):
    # 모델이 범위를 벗어난 값을 내놓아도 1~5 로 클램프
    raw = '{"emotion":9,"controversy":0,"clarity":3.6,"novelty":-2,"core_claim":"주장"}'
    monkeypatch.setattr(grader, "get_ai_client", lambda: StubClient([raw]))
    result = _run(grade_post("글"))
    assert result.breakdown == {"emotion": 5, "controversy": 1, "clarity": 4, "novelty": 1}


# ── 파싱 관용성 ─────────────────────────────────────────────────────────────

def test_markdown_codefence_json_is_parsed(monkeypatch):
    fenced = '```json\n{"emotion":4,"controversy":4,"clarity":3,"novelty":3,"core_claim":"핵심"}\n```'
    stub = StubClient([fenced])
    monkeypatch.setattr(grader, "get_ai_client", lambda: stub)
    result = _run(grade_post("글"))
    assert stub.calls == 1  # 재시도 없이 1회에 파싱 성공
    assert result.breakdown == {"emotion": 4, "controversy": 4, "clarity": 3, "novelty": 3}
    assert result.core_claim == "핵심"
    assert result.score == round((0.35 * 4 + 0.30 * 4 + 0.20 * 3 + 0.15 * 3) * 20)


def test_json_with_surrounding_prose_is_parsed(monkeypatch):
    noisy = '네, 채점 결과입니다: {"emotion":2,"controversy":3,"clarity":4,"novelty":1,"core_claim":"요지"} 감사합니다.'
    monkeypatch.setattr(grader, "get_ai_client", lambda: StubClient([noisy]))
    result = _run(grade_post("글"))
    assert result.core_claim == "요지"


def test_missing_core_claim_falls_back_to_content_slice(monkeypatch):
    raw = '{"emotion":3,"controversy":3,"clarity":3,"novelty":3}'
    monkeypatch.setattr(grader, "get_ai_client", lambda: StubClient([raw]))
    content = "가" * 120
    result = _run(grade_post(content))
    assert result.core_claim == content[:80]


# ── 재시도 + 폴백 ───────────────────────────────────────────────────────────

def test_parse_failure_retries_once_then_fallback(monkeypatch):
    stub = StubClient(["이건 JSON 이 아님", "여전히 아님"])
    monkeypatch.setattr(grader, "get_ai_client", lambda: stub)
    content = "폴백 확인용 글 " * 10
    result = _run(grade_post(content))
    assert stub.calls == 2  # 최초 1회 + 재시도 1회
    assert result.score == 60
    assert result.breakdown == {axis: 3 for axis in AXES}
    assert result.core_claim == content[:80]


def test_retry_succeeds_after_first_broken_response(monkeypatch):
    good = '{"emotion":5,"controversy":4,"clarity":4,"novelty":2,"core_claim":"재시도 성공"}'
    stub = StubClient(["{깨진 json", good])
    monkeypatch.setattr(grader, "get_ai_client", lambda: stub)
    result = _run(grade_post("글"))
    assert stub.calls == 2
    assert result.core_claim == "재시도 성공"
    assert result.score == round((0.35 * 5 + 0.30 * 4 + 0.20 * 4 + 0.15 * 2) * 20)


def test_exception_from_client_falls_back(monkeypatch):
    # 호출 자체가 터져도 (네트워크 등) 폴백으로 파이프라인은 계속 진행
    stub = StubClient([RuntimeError("boom"), RuntimeError("boom again")])
    monkeypatch.setattr(grader, "get_ai_client", lambda: stub)
    result = _run(grade_post("예외 폴백 글"))
    assert stub.calls == 2
    assert result.score == 60
    assert result.breakdown == {axis: 3 for axis in AXES}
    assert result.core_claim == "예외 폴백 글"


def test_wrong_type_axis_triggers_fallback(monkeypatch):
    # 축 값이 숫자가 아니면 파싱 실패로 간주 (bool 포함)
    bad = '{"emotion":"높음","controversy":3,"clarity":3,"novelty":3,"core_claim":"x"}'
    stub = StubClient([bad, bad])
    monkeypatch.setattr(grader, "get_ai_client", lambda: stub)
    result = _run(grade_post("타입 오류 글"))
    assert result.score == 60
    assert result.breakdown == {axis: 3 for axis in AXES}
