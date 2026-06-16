import random

from comment_style import LENGTH_STYLES, pick_length_style


def test_has_at_least_three_varied_styles():
    assert len(LENGTH_STYLES) >= 3
    assert len(set(LENGTH_STYLES)) == len(LENGTH_STYLES)  # 중복 없음


def test_pick_returns_a_pool_member():
    assert pick_length_style(random.Random(0)) in LENGTH_STYLES


def test_pick_is_deterministic_with_same_seed():
    assert pick_length_style(random.Random(7)) == pick_length_style(random.Random(7))


def test_pick_varies_across_seeds():
    picks = {pick_length_style(random.Random(s)) for s in range(50)}
    assert len(picks) >= 2  # 시드별로 분량이 갈린다(다양성)
