"""내 AI 출동: 작성자 제외 유저 페르소나를 댓글 생성에 일부 참여시킨다.

각 출동 페르소나의 persona_prompt + 진화 hint(trait_params.hint)로 댓글을 생성한다.
"""
import random

from database import AiPersonaModel


def select_deployed_personas(db, exclude_user_id: int, k: int = 2, rng=None):
    """작성자(exclude_user_id) 제외 유저 페르소나 중 랜덤 k명 → [(display_name, prompt+hint)]."""
    personas = (
        db.query(AiPersonaModel)
        .filter(AiPersonaModel.user_id != exclude_user_id)
        .all()
    )
    if not personas:
        return []
    chooser = rng if rng is not None else random
    chosen = chooser.sample(personas, min(k, len(personas)))
    result = []
    for p in chosen:
        hint = ""
        if isinstance(p.trait_params, dict):
            hint = p.trait_params.get("hint") or ""
        prompt = p.persona_prompt + (f"\n[성향 힌트] {hint}" if hint else "")
        result.append((p.display_name, prompt))
    return result
