# factions.py 단위 테스트 (스펙 §9 필수 커버리지)
# - turn0=ally / 최소 1 도전자 보장 / 1000턴 시뮬 도전자 비율 30~50% / 시드 결정성
# DB·AI 의존 없음 — conftest 픽스처 불필요한 순수 로직 테스트.

import random

from factions import ALLY, CHALLENGER, MODERATOR, faction_for_turn, pick_persona
from personas import MODERATOR_PERSONA, PERSONAS


# --- turn 0 = 호위대장 자리 --------------------------------------------------

def test_turn0_is_always_ally():
    for seed in range(100):
        assert faction_for_turn(0, seed=seed, challenger_so_far=0, planned_total=5) == ALLY


def test_turn0_ally_even_with_tiny_planned_total():
    # planned_total=1 이어도 turn 0 규칙이 최소 보장 규칙보다 우선한다
    assert faction_for_turn(0, seed=1, challenger_so_far=0, planned_total=1) == ALLY


# --- 최소 1 도전자 보장 (에코챔버 방지) ---------------------------------------

def test_min_one_challenger_forced_on_last_turn():
    # 마지막 턴까지 도전자가 0명이면 시드와 무관하게 도전자 강제
    for seed in range(100):
        assert faction_for_turn(4, seed=seed, challenger_so_far=0, planned_total=5) == CHALLENGER


def test_no_force_when_challenger_already_exists():
    # 이미 도전자가 있으면 마지막 턴도 확률 배정 → 여러 시드에서 양 진영 모두 등장
    results = {
        faction_for_turn(4, seed=seed, challenger_so_far=1, planned_total=5)
        for seed in range(300)
    }
    assert results == {ALLY, CHALLENGER}


def test_full_run_simulation_always_has_challenger():
    # 실제 루프처럼 challenger_so_far 를 누적하며 전체 토론을 시뮬 — 어떤 시드든 도전자 ≥ 1
    for seed in range(200):
        planned_total = 5
        challengers = 0
        for turn in range(planned_total):
            faction = faction_for_turn(
                turn, seed=seed, challenger_so_far=challengers, planned_total=planned_total
            )
            if faction == CHALLENGER:
                challengers += 1
        assert challengers >= 1, f"seed={seed} 에서 도전자 0명"


# --- 1000턴 시뮬 도전자 비율 30~50% -------------------------------------------

def test_challenger_ratio_between_30_and_50_percent():
    total = 1000
    challengers = 0
    for turn in range(1, total + 1):
        # planned_total 을 크게 잡아 최소 보장 규칙이 개입하지 않는 순수 확률 구간만 측정
        faction = faction_for_turn(turn, seed=42, challenger_so_far=1, planned_total=10_000)
        if faction == CHALLENGER:
            challengers += 1
    ratio = challengers / total
    assert 0.30 <= ratio <= 0.50, f"도전자 비율 {ratio:.3f} — 30~50% 밖"


# --- 결정적 시드 --------------------------------------------------------------

def test_same_seed_same_sequence():
    seq_a = [faction_for_turn(t, seed=7, challenger_so_far=1, planned_total=1000) for t in range(200)]
    seq_b = [faction_for_turn(t, seed=7, challenger_so_far=1, planned_total=1000) for t in range(200)]
    assert seq_a == seq_b


def test_different_seeds_can_differ():
    seq_a = [faction_for_turn(t, seed=1, challenger_so_far=1, planned_total=1000) for t in range(200)]
    seq_b = [faction_for_turn(t, seed=2, challenger_so_far=1, planned_total=1000) for t in range(200)]
    assert seq_a != seq_b  # 시드가 다르면 배정 시퀀스도 달라진다 (사실상 확실)


# --- pick_persona -------------------------------------------------------------

def test_pick_persona_avoids_used_keys():
    rng = random.Random(1)
    used = {p.key for p in PERSONAS[:-1]}  # 마지막 1명만 남기고 전부 사용됨
    for _ in range(10):
        chosen = pick_persona(ALLY, rng, used)
        assert chosen.key == PERSONAS[-1].key


def test_pick_persona_falls_back_when_all_used():
    rng = random.Random(2)
    used = {p.key for p in PERSONAS}
    chosen = pick_persona(CHALLENGER, rng, used)
    assert chosen in PERSONAS  # 전부 사용됐으면 회피 포기(재사용 허용)


def test_pick_persona_moderator_is_fixed():
    assert pick_persona(MODERATOR, random.Random(3), set()) is MODERATOR_PERSONA


def test_persona_pool_has_16_unique_keys():
    keys = [p.key for p in PERSONAS]
    assert len(keys) == 16
    assert len(set(keys)) == 16
    assert MODERATOR_PERSONA.key not in keys  # 중재자는 시민 풀과 분리
