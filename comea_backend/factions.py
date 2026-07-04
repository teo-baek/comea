"""진영(Faction) 상수 + 턴별 진영 결정 + 페르소나 선택 (스펙 §7, PRD 3.1).

원칙(객관성): 승패 조작 없음. 호위대 ~60% / 도전자 ~40%, 최소 1 도전자 보장.
진영 배정은 (seed, turn_index) 기반의 결정적 난수로 재현 가능하다.
"""

import random

from personas import MODERATOR_PERSONA, PERSONAS, Persona

# 진영 문자열 상수 — comments.faction / posts.verdict 에 그대로 저장
ALLY = "ally"
CHALLENGER = "challenger"
MODERATOR = "moderator"

# 도전자 배정 확률 (~40%). 나머지는 호위대.
CHALLENGER_RATIO = 0.4


def faction_for_turn(turn_index: int, seed: int, challenger_so_far: int, planned_total: int) -> str:
    """턴 번호에 따라 진영을 결정한다 (결정적 시드 — 스펙 §7).

    - turn 0 → ALLY (호위대장 자리)
    - 마지막 턴까지 도전자가 없으면 → CHALLENGER 강제 (에코챔버 방지: 최소 1명 보장)
    - 그 외 → (seed, turn_index) 시드 난수로 40% 도전자
    """
    if turn_index == 0:
        return ALLY
    if challenger_so_far == 0 and turn_index >= planned_total - 1:
        return CHALLENGER
    rng = random.Random((seed, turn_index).__hash__())
    return CHALLENGER if rng.random() < CHALLENGER_RATIO else ALLY


def pick_persona(faction: str, rng: random.Random, used_keys: set[str]) -> Persona:
    """진영에 배치할 페르소나 선택. 최근 사용(used_keys) 페르소나는 회피한다.

    - MODERATOR → 중재자 전용 페르소나 고정
    - 풀 전체가 최근 사용됐으면 회피를 포기하고 전체 풀에서 선택 (재사용 허용)
    """
    if faction == MODERATOR:
        return MODERATOR_PERSONA
    candidates = [p for p in PERSONAS if p.key not in used_keys]
    if not candidates:
        candidates = list(PERSONAS)
    return rng.choice(candidates)
