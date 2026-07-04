"""페르소나 진화 엔진: comment_reactions ⋈ comments.persona_name 합산 → ai_personas.trait_params 갱신.

단순 합산(+1 like / −1 dislike). 저장만(댓글 생성 사용은 다음 슬라이스).
스테이지 2 스키마(스펙 §3)의 comments.persona_name/content 컬럼을 사용한다.
"""
import database
from database import AiPersonaModel, CommentModel, CommentReactionModel


def compute_persona_preferences(db, user_id: int) -> dict:
    """유저의 댓글 반응을 페르소나(comments.persona_name)별 +1/−1 합산한 선호 맵."""
    rows = (
        db.query(CommentModel.persona_name, CommentReactionModel.reaction_type)
        .join(CommentReactionModel, CommentReactionModel.comment_id == CommentModel.id)
        .filter(CommentReactionModel.user_id == user_id)
        .all()
    )
    prefs: dict = {}
    for name, rtype in rows:
        prefs[name] = prefs.get(name, 0) + (1 if rtype == "like" else -1)
    return prefs


def build_prompt_hint(prefs: dict) -> str:
    """최고 양수 선호 페르소나로 프롬프트 힌트 문장. 양수 없으면 빈 문자열."""
    if not prefs:
        return ""
    top_name, top_score = max(prefs.items(), key=lambda kv: kv[1])
    if top_score <= 0:
        return ""
    return f"당신의 주인은 현재 '{top_name}' 같은 답변을 선호합니다."


def run_persona_evolution() -> None:
    """모든 페르소나를 유저 행동으로 진화(trait_params 갱신). 유저 단위 예외 격리(AC-5)."""
    try:
        db = database.SessionLocal()
    except Exception:
        return
    try:
        for persona in db.query(AiPersonaModel).all():
            try:
                prefs = compute_persona_preferences(db, persona.user_id)
                persona.trait_params = {"prefs": prefs, "hint": build_prompt_hint(prefs)}
                db.commit()
            except Exception:
                db.rollback()
    finally:
        db.close()
