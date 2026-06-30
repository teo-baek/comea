"""글 점수 + 반응 총량 + 전체 유저수 기반 가변적 댓글 한계선 순수 로직.

외부 의존(DB/OpenAI) 없는 순수 함수만 둔다. PRD §3.3 수식의 단일 출처.
서비스 핵심(소외 금지): 모든 유형의 Base Limit 은 10 이상.
"""

# --- 설정 상수 ---
BASE_HARD_CAP = 25  # 유저가 적을 때의 고정 상한. 유저수가 이를 넘으면 상한도 확장.
ADJUST_STEP = 0.1   # 반응 1건(좋아요/싫어요 무관)당 증감률


def compute_base_limit(score: int) -> int:
    """채점 점수 → 유형별 기본 한계선. 0개 유형 없음(소외 금지)."""
    if score >= 90:
        return 20
    if score >= 60:
        return 15
    return 10


def compute_effective_cap(current_population: int) -> int:
    """유저 적을 땐 고정 25, 유저수가 25를 넘으면 유저수에 비례해 상한 확장."""
    return max(BASE_HARD_CAP, current_population)


def compute_final_limit(base_limit: int, total_reactions: int, current_population: int) -> int:
    """Final Limit = round( base × (1 + 총반응수 × STEP) ), [base, effective_cap] 클램프.

    round 는 round-half-up(`int(x + 0.5)`)로 고정. 좋아요/싫어요 구분 없이 총량만 사용.
    """
    cap = compute_effective_cap(current_population)
    adjust_rate = total_reactions * ADJUST_STEP
    final = int(base_limit * (1 + adjust_rate) + 0.5)
    if final < base_limit:
        final = base_limit
    if final > cap:
        final = cap
    return final


def should_lock(current_comment_count: int, effective_cap: int) -> bool:
    """현재 댓글 수가 상한(Cap)에 도달하면 잠근다. 중재자 요약 없이 조용히 종료."""
    return current_comment_count >= effective_cap
