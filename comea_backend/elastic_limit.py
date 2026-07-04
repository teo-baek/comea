"""가변 댓글 한계선 순수 로직 (PRD 3.3 / 스펙 §4 — 단일 출처).

외부 의존(DB/OpenAI) 없는 순수 함수만 둔다.
공식: final_limit = clamp(base + floor(net/k) + bonus, FLOOR, SAFETY_CEILING)

net_reaction 정의: (글 like−dislike) + Σ(각 댓글 like−dislike, moderator 댓글 포함).
리밋과 비교하는 댓글 수는 moderator 제외 카운트 (호출 측 책임).
"""

# --- 설정 상수 ---
K_REACTIONS_PER_COMMENT = 3  # 순반응 k건당 댓글 1개 추가
FLOOR = 2                    # 하한 — 어떤 글도 최소 2개 댓글은 보장 (소외 금지)
SAFETY_CEILING = 500         # 상한 — 폭주 방지용 안전 천장


def compute_base_limit(score: int) -> int:
    """채점 점수(0~100) → 기본 한계선.

    0~39 → 3 | 40~69 → 8 | 70~89 → 15 | 90~100 → 25
    """
    if score >= 90:
        return 25
    if score >= 70:
        return 15
    if score >= 40:
        return 8
    return 3


def compute_population_bonus(mau: int) -> int:
    """전체 유저 규모 → 보너스: max(0, floor(log10(max(mau, 1))) - 2).

    100명=0, 1천=1, 1만=2. float log10 오차를 피하기 위해
    양의 정수에서 floor(log10(n)) == len(str(n)) - 1 항등식을 사용한다.
    """
    n = max(mau, 1)
    return max(0, (len(str(n)) - 1) - 2)


def compute_final_limit(base_limit: int, net_reaction: int, population_bonus: int, k: int = 3) -> int:
    """최종 한계선 = clamp(base + (net // k) + bonus, FLOOR, SAFETY_CEILING).

    주의: 파이썬 // 는 음수도 내림 — 그대로 사용 (net=-1, k=3 → -1).
    """
    raw = base_limit + (net_reaction // k) + population_bonus
    return max(FLOOR, min(SAFETY_CEILING, raw))


def should_conclude_early(net_reaction: int, comment_count: int) -> bool:
    """조기 종결: 순반응이 -2 이하이고 댓글이 FLOOR 개 이상 달렸으면 토론을 접는다."""
    return net_reaction <= -2 and comment_count >= FLOOR
