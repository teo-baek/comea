from personas import PERSONA_POOL, get_personas


def test_pool_has_at_least_16_unique_personas():
    assert len(PERSONA_POOL) >= 16
    names = [name for name, _ in PERSONA_POOL]
    assert len(set(names)) == len(names)  # 이름 중복 없음


def test_each_persona_is_name_prompt_pair():
    for name, prompt in PERSONA_POOL:
        assert isinstance(name, str) and name
        assert isinstance(prompt, str) and prompt


def test_get_personas_returns_requested_count():
    assert get_personas(3) == PERSONA_POOL[:3]
    assert len(get_personas(5)) == 5


def test_get_personas_cycles_when_exceeding_pool():
    n = len(PERSONA_POOL) + 2
    result = get_personas(n)
    assert len(result) == n
    assert result[len(PERSONA_POOL)] == PERSONA_POOL[0]  # 순환 복귀


def test_get_personas_start_offset():
    assert get_personas(2, start=1) == PERSONA_POOL[1:3]


def test_get_personas_zero_or_negative():
    assert get_personas(0) == []
    assert get_personas(-3) == []
