"""Comea 스테이지 1+2 API 레이어 (스펙 §8) — 포트 8247.

- 글 작성은 **즉시 201** 반환. 채점/진영 토론은 debate 파이프라인(BackgroundTasks)이 수행.
- OpenAI 직접 호출 없음 — 채점은 grader, 댓글 생성은 debate 모듈 소관.
- 반응 처리 후 debate.check_reignite 로 종결 글 재점화 여부를 검사한다.
- 기동 시 grading/debating 잔류 글을 스캔해 파이프라인을 재개한다 (재시작 복구).
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

# 루트 .env 로드 (override=False: 이미 설정된 환경변수 — 테스트 conftest 값 등 — 은 유지).
# database 모듈이 import 시점에 DATABASE_URL 을 읽으므로 반드시 그 전에 호출한다.
_ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
if _ROOT_ENV.exists():
    load_dotenv(_ROOT_ENV)
else:
    load_dotenv()  # 폴백: cwd 기준 탐색 (기존 방식)

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

import ai_client
import database
import debate
from auth import (
    create_token,
    get_current_user,
    get_current_user_optional,
    hash_password,
    verify_password,
)
from database import (
    AiPersonaModel,
    CommentModel,
    CommentReactionModel,
    PostModel,
    ReactionModel,
    UserModel,
    get_db,
)
from population_batch import shutdown_scheduler, start_scheduler
from schemas import (
    CommentOut,
    LoginIn,
    PostCreateIn,
    PostDetailOut,
    PostSummaryOut,
    ReactionIn,
    SignupIn,
    build_comment_out,
    build_post_detail,
    build_post_summary,
)

# 서버 시작 시 테이블이 없으면 자동 생성 (런타임 마이그레이션은 create_all — 스펙 §3)
database.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Comea Backend")

# Flutter 웹(다른 origin)에서의 호출 허용 — 스펙 §8
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_VALID_REACTIONS = ("like", "dislike", "none")

# 복구 스캔이 띄운 파이프라인 태스크 참조 보관 (GC 로 태스크가 사라지는 것 방지)
_recovery_tasks: set[asyncio.Task] = set()


def _resume_stuck_pipelines() -> None:
    """재시작 복구 스캔: grading/debating 잔류 글의 파이프라인을 재개한다.

    파이프라인은 요청 단위 BackgroundTasks(인메모리)로만 돌기 때문에, 프로세스가
    죽거나 graceful shutdown 으로 태스크가 취소되면 글이 grading/debating 에 남는다.
    기동 시 이런 글을 조회해 run_debate_pipeline 을 다시 띄운다 (없으면 무한 폴링).
    반드시 실행 중인 이벤트 루프 안(async startup)에서 호출해야 한다.
    """
    db = database.SessionLocal()
    try:
        stuck_ids = [
            row[0]
            for row in db.query(PostModel.id)
            .filter(PostModel.status.in_([debate.STATUS_GRADING, debate.STATUS_DEBATING]))
            .order_by(PostModel.id)
            .all()
        ]
    finally:
        db.close()
    for post_id in stuck_ids:
        task = asyncio.create_task(debate.run_debate_pipeline(post_id))
        _recovery_tasks.add(task)
        task.add_done_callback(_recovery_tasks.discard)


@app.on_event("startup")
async def _on_startup():
    # 기동 즉시 인구 집계 1회 + 매일 04:00 cron (DISABLE_SCHEDULER=1 이면 미기동)
    start_scheduler()
    # 이전 프로세스에서 중단된 토론 파이프라인 재개 (스펙 §7-4 취지의 복구 경로)
    _resume_stuck_pipelines()


@app.on_event("shutdown")
def _on_shutdown():
    shutdown_scheduler()


# ---------------------------------------------------------------------------
# 헬스체크
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    """DB(SELECT 1) + AI 모드 상태 반환."""
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"ok": True, "db": db_ok, "ai_mode": "fake" if ai_client.is_fake_mode() else "real"}


# ---------------------------------------------------------------------------
# 인증 — 가입(자동 로그인) / 로그인
# ---------------------------------------------------------------------------


def _pick_signup_persona() -> tuple[str, str] | None:
    """가입 시 배정할 (이름, 프롬프트) 1개.

    페르소나 풀 모듈은 D 에이전트가 재정리 중이라 구조 변화에 견고하게 대응한다:
    구 personas.random_persona → factions 의 Persona 풀 순으로 시도, 모두 실패 시 None.
    """
    try:
        from personas import random_persona

        name, prompt = random_persona()
        return name, prompt
    except Exception:
        pass
    try:
        import random as _random

        import factions

        pool = list(getattr(factions, "PERSONAS", []) or [])
        if pool:
            p = _random.choice(pool)
            return p.name, p.character_prompt
    except Exception:
        pass
    return None


@app.post("/api/auth/signup", status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    exists = db.query(UserModel).filter(UserModel.email == body.email).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    user = UserModel(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    # 내부 AI 페르소나 1개 랜덤 배정 (자기 글의 호위대장 후보). best-effort — 실패해도 가입 유지.
    picked = _pick_signup_persona()
    if picked is not None:
        try:
            name, prompt = picked
            db.add(AiPersonaModel(user_id=user.id, display_name=name, persona_prompt=prompt))
            db.commit()
        except Exception:
            db.rollback()

    return {"token": create_token(user.id)}


@app.post("/api/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return {"token": create_token(user.id)}


# ---------------------------------------------------------------------------
# 글 — 목록 / 작성(즉시 201) / 상세(폴링 대상)
# ---------------------------------------------------------------------------


@app.get("/api/posts")
def list_posts(
    db: Session = Depends(get_db),
    current_user: UserModel | None = Depends(get_current_user_optional),
):
    """글 목록 (id desc). 비로그인 허용 — is_mine/my_reaction 은 None/False."""
    posts = db.query(PostModel).order_by(PostModel.id.desc()).all()
    return {"posts": [build_post_summary(db, p, current_user) for p in posts]}


@app.post("/api/posts", status_code=201, response_model=PostDetailOut)
def create_post(
    body: PostCreateIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """글 저장 후 **즉시** 201 반환(status=grading, comments=[]). 채점/토론은 백그라운드."""
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="content must not be empty")

    post = PostModel(content=content, author_user_id=current_user.id, status="grading")
    db.add(post)
    db.commit()
    db.refresh(post)

    # 채점 → 진영 토론 → 중재 파이프라인 예약 (중복 실행은 debate 가 실행 시점에 방지)
    debate.ensure_pipeline_scheduled(post.id, background_tasks)

    return build_post_detail(db, post, current_user)


@app.get("/api/posts/{post_id}", response_model=PostDetailOut)
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel | None = Depends(get_current_user_optional),
):
    """글 상세 (Flutter 가 2초 폴링). 비로그인 허용."""
    post = db.query(PostModel).filter(PostModel.id == post_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail="post not found")
    return build_post_detail(db, post, current_user)


# ---------------------------------------------------------------------------
# 반응 — 글/댓글 좋아요·싫어요 (토글/변경/삭제) + 재점화 검사
# ---------------------------------------------------------------------------


def _validate_reaction(value: str) -> None:
    if value not in _VALID_REACTIONS:
        raise HTTPException(status_code=400, detail="reaction must be 'like', 'dislike' or 'none'")


@app.post("/api/posts/{post_id}/reaction", response_model=PostDetailOut)
def react_to_post(
    post_id: int,
    body: ReactionIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """글 반응 토글: 같은 값 재전송 또는 'none' → 삭제, 다른 값 → 교체 (인당 1표)."""
    post = db.query(PostModel).filter(PostModel.id == post_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail="post not found")
    _validate_reaction(body.reaction)

    existing = (
        db.query(ReactionModel)
        .filter(ReactionModel.post_id == post_id, ReactionModel.user_id == current_user.id)
        .first()
    )
    if body.reaction == "none" or (existing is not None and existing.reaction_type == body.reaction):
        if existing is not None:
            db.delete(existing)  # 토글 해제 / 명시 삭제
    elif existing is not None:
        existing.reaction_type = body.reaction  # like <-> dislike 교체
    else:
        db.add(ReactionModel(post_id=post_id, user_id=current_user.id, reaction_type=body.reaction))
    db.commit()

    # 종결 글이 새 final_limit 보다 작아졌으면 재점화 (§7). status 변경은 별도 세션에서 일어나므로 만료 후 재조회.
    debate.check_reignite(post_id, background_tasks)
    db.expire_all()

    return build_post_detail(db, post, current_user)


@app.post("/api/comments/{comment_id}/reaction", response_model=CommentOut)
def react_to_comment(
    comment_id: int,
    body: ReactionIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """댓글 반응 토글 (verdict 판정 재료 + net_reaction 기여). 소속 글 재점화 검사 포함."""
    comment = db.query(CommentModel).filter(CommentModel.id == comment_id).first()
    if comment is None:
        raise HTTPException(status_code=404, detail="comment not found")
    _validate_reaction(body.reaction)

    existing = (
        db.query(CommentReactionModel)
        .filter(
            CommentReactionModel.comment_id == comment_id,
            CommentReactionModel.user_id == current_user.id,
        )
        .first()
    )
    if body.reaction == "none" or (existing is not None and existing.reaction_type == body.reaction):
        if existing is not None:
            db.delete(existing)
    elif existing is not None:
        existing.reaction_type = body.reaction
    else:
        db.add(
            CommentReactionModel(
                comment_id=comment_id, user_id=current_user.id, reaction_type=body.reaction
            )
        )
    db.commit()

    # 댓글 반응도 net_reaction 에 포함되므로 소속 글의 재점화 조건을 검사한다.
    debate.check_reignite(comment.post_id, background_tasks)

    return build_comment_out(db, comment, current_user)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("COMEA_PORT", "8247")))
