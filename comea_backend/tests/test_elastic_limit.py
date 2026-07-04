"""elastic_limit 순수 함수 경계표 테스트 (스펙 §4 / §9 — DB 불필요)."""

from elastic_limit import (
    FLOOR,
    K_REACTIONS_PER_COMMENT,
    SAFETY_CEILING,
    compute_base_limit,
    compute_final_limit,
    compute_population_bonus,
    should_conclude_early,
)


# --- 상수 계약 ---

def test_constants_match_spec():
    assert K_REACTIONS_PER_COMMENT == 3
    assert FLOOR == 2
    assert SAFETY_CEILING == 500


# --- compute_base_limit: score 경계 39/40/69/70/89/90 ---

def test_base_limit_score_boundaries():
    assert compute_base_limit(0) == 3
    assert compute_base_limit(39) == 3    # 저품질 상단 경계
    assert compute_base_limit(40) == 8    # 중품질 하단 경계
    assert compute_base_limit(69) == 8
    assert compute_base_limit(70) == 15   # 일반 하단 경계
    assert compute_base_limit(89) == 15
    assert compute_base_limit(90) == 25   # 명글 하단 경계
    assert compute_base_limit(100) == 25


# --- compute_population_bonus: mau 1/99/100/999/1000/9999/10000 ---

def test_population_bonus_boundaries():
    assert compute_population_bonus(1) == 0
    assert compute_population_bonus(99) == 0
    assert compute_population_bonus(100) == 0     # 100명 = 0
    assert compute_population_bonus(999) == 0
    assert compute_population_bonus(1000) == 1    # 1천 = 1
    assert compute_population_bonus(9999) == 1
    assert compute_population_bonus(10000) == 2   # 1만 = 2


def test_population_bonus_guards_nonpositive_mau():
    # max(mau, 1) 가드: 0 이하 입력도 안전하게 0
    assert compute_population_bonus(0) == 0
    assert compute_population_bonus(-5) == 0


# --- compute_final_limit: 기본 합산 ---

def test_final_limit_plain_sum():
    # 8 + (6 // 3) + 1 = 11
    assert compute_final_limit(8, 6, 1) == 11
    # 순반응 0, 보너스 0 → base 그대로
    assert compute_final_limit(15, 0, 0) == 15
    # 양수 내림: 5 // 3 = 1
    assert compute_final_limit(8, 5, 0) == 9


def test_final_limit_negative_net_floors_down():
    # 파이썬 // 음수 내림: -1 // 3 = -1 (0 이 아님)
    assert compute_final_limit(8, -1, 0) == 7
    # -3 // 3 = -1, -4 // 3 = -2
    assert compute_final_limit(8, -3, 0) == 7
    assert compute_final_limit(8, -4, 0) == 6


def test_final_limit_clamp_floor_2():
    # 3 + (-30 // 3) + 0 = -7 → 하한 2
    assert compute_final_limit(3, -30, 0) == 2
    # 정확히 하한에 걸리는 값: 3 + (-3 // 3) + 0 = 2
    assert compute_final_limit(3, -3, 0) == 2
    # 하한 바로 위: 3 + 0 + 0 = 3
    assert compute_final_limit(3, 0, 0) == 3


def test_final_limit_clamp_ceiling_500():
    # 25 + (3000 // 3) + 0 = 1025 → 상한 500
    assert compute_final_limit(25, 3000, 0) == 500
    # 정확히 상한: 25 + (1425 // 3) + 0 = 500
    assert compute_final_limit(25, 1425, 0) == 500
    # 상한 바로 아래: 25 + (1422 // 3) + 0 = 499
    assert compute_final_limit(25, 1422, 0) == 499


def test_final_limit_custom_k():
    # k 파라미터 존중: net=10, k=5 → +2
    assert compute_final_limit(8, 10, 0, k=5) == 10


# --- should_conclude_early: 경계 ---

def test_should_conclude_early_boundaries():
    # 순반응 -2 이하 AND 댓글 FLOOR(2)개 이상 → 조기 종결
    assert should_conclude_early(-2, 2) is True
    assert should_conclude_early(-3, 5) is True
    # 순반응 경계 밖 (-1 은 아직 아님)
    assert should_conclude_early(-1, 2) is False
    assert should_conclude_early(0, 10) is False
    # 댓글 수 경계 밖 (FLOOR 미만이면 반응이 나빠도 유지)
    assert should_conclude_early(-2, 1) is False
    assert should_conclude_early(-100, 0) is False
