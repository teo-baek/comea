from elastic_limit import (
    BASE_HARD_CAP,
    compute_base_limit,
    compute_effective_cap,
    compute_final_limit,
    should_lock,
)


def test_base_limit_all_tiers_at_least_ten():
    # 소외 금지: 모든 유형 10개 이상
    assert compute_base_limit(40) == 10   # 잡담
    assert compute_base_limit(59) == 10
    assert compute_base_limit(60) == 15   # 일반
    assert compute_base_limit(89) == 15
    assert compute_base_limit(90) == 20   # 명글
    assert compute_base_limit(100) == 20


def test_effective_cap_fixed_then_scales_with_population():
    assert BASE_HARD_CAP == 25
    assert compute_effective_cap(0) == 25     # 유저 없음 -> 고정 상한
    assert compute_effective_cap(25) == 25
    assert compute_effective_cap(100) == 100  # 유저>25 -> 유저수에 비례


def test_final_limit_neutral_equals_base():
    assert compute_final_limit(10, 0, 0) == 10
    assert compute_final_limit(15, 0, 0) == 15
    assert compute_final_limit(20, 0, 0) == 20


def test_final_limit_grows_with_total_reactions():
    # 10 * (1 + 5*0.1) = 15.0 -> 15
    assert compute_final_limit(10, 5, 0) == 15
    # 20 * (1 + 1*0.1) = 22.0 -> 22
    assert compute_final_limit(20, 1, 0) == 22


def test_final_limit_clamped_to_fixed_cap_when_population_small():
    # 20 * (1 + 3*0.1) = 26.0 -> clamp 25 (population 0)
    assert compute_final_limit(20, 3, 0) == 25


def test_final_limit_can_exceed_25_when_population_large():
    # population 100 -> cap 100, 20 * 1.5 = 30 (clamp 안 됨)
    assert compute_final_limit(20, 5, 100) == 30


def test_final_limit_never_below_base():
    assert compute_final_limit(15, 0, 0) == 15


def test_should_lock_only_at_cap():
    assert should_lock(current_comment_count=24, effective_cap=25) is False
    assert should_lock(current_comment_count=25, effective_cap=25) is True
    assert should_lock(current_comment_count=20, effective_cap=100) is False
