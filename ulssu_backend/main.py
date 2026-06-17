import os
import asyncio
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
from dotenv import load_dotenv

# .env 의 OPENAI_API_KEY / DATABASE_URL 등을 환경변수로 로드 (override=False: 이미 설정된 값은 유지).
# database 모듈이 import 시점에 DATABASE_URL 을 읽으므로 그 전에 호출해야 한다.
load_dotenv()

import database
from database import get_db, PostModel, CommentModel, ReactionModel, UserModel, AiPersonaModel, CommentReactionModel
from auth import hash_password, verify_password, create_token, get_current_user
from persona_deployment import select_deployed_personas
from personas import random_persona
from population_batch import start_scheduler, shutdown_scheduler
from elastic_limit import compute_base_limit, compute_final_limit, compute_effective_cap, should_lock
from personas import get_personas
from population import get_current_population
from comment_style import pick_length_style

# 서버 시작 시 PostgreSQL에 테이블이 없다면 자동으로 생성 (스키마 마이그레이션)
database.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="ulssu AI Square Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OPENAI_API_KEY 는 환경변수에서 읽는다(소스 하드코딩 금지 — 노출된 기존 키는 폐기/회전 필요).
client = OpenAI()


@app.on_event("startup")
def _on_startup():
    # 기동 즉시 인구 집계 + 매일 4시 cron 등록 (테스트는 DISABLE_SCHEDULER 가드로 미기동)
    start_scheduler()


@app.on_event("shutdown")
def _on_shutdown():
    shutdown_scheduler()

class PostRequest(BaseModel):
    content: str


class ReactionRequest(BaseModel):
    reaction: str  # "like" | "dislike"


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str

def evaluate_post_quality(user_post: str) -> int:
    system_instruction = """
    너는 커뮤니티의 모든 글을 검사하는 엄격하고 정밀한 채점관 AI야.
    유저가 올린 글의 '고민의 깊이', '감정의 밀도', '논쟁 가능성'을 종합적으로 판단해서 0점부터 100점 사이의 정수 점수만 출력해줘.
    
    [채점 가이드라인]
    - 90점 이상: 극단적인 감정 표현(예: 한강, 죽고싶다 등), 심각한 경제적/정서적 타격(투자 실패, 이별), 타인과 치열하게 토론할 만한 사회적/철학적 주제.
    - 60~89점: 진지한 커리어 고민, 연애 상담, 가벼운 재테크 질문 등 조언이 필요한 글.
    - 30~59점: 오늘 있었던 일 공유, 단순 유머, 영양가 없는 일상 잡담.
    - 30점 미만: "배고프다", "날씨 좋네", "돈까스 땡긴다" 같이 맥락이 전혀 없는 한 줄짜리 낙서.
    
    ※ 경고: 설명이나 다른 말은 절대 하지 말고, 오직 '숫자(정수)'만 반환할 것. 예: 95
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"이 글의 점수를 매겨줘: '{user_post}'"}
        ],
        temperature=0.0
    )
    try:
        return int(response.choices[0].message.content.strip())
    except ValueError:
        return 50

def generate_ai_comment(persona_prompt: str, user_post: str, previous_comments: str, length_hint: str) -> str:
    system_instruction = (
        "너는 'AI 광장'이라는 커뮤니티의 시민이야. 아래 페르소나에 맞춰 댓글을 달아줘.\n"
        f"[너의 페르소나]\n{persona_prompt}\n"
        f"[분량] {length_hint}"
    )
    user_content = f"유저의 게시글: '{user_post}'\n\n[현재 댓글 상황]\n{previous_comments}\n\n의견을 달아줘."
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ],
        temperature=0.8
    )
    return response.choices[0].message.content


def _count_comments(db: Session, post_id: int) -> int:
    return db.query(CommentModel).filter(CommentModel.post_id == post_id).count()


def _count_reactions(db: Session, post_id: int) -> int:
    return db.query(ReactionModel).filter(ReactionModel.post_id == post_id).count()


def _build_chat_history(db: Session, post_id: int) -> str:
    rows = (
        db.query(CommentModel)
        .filter(CommentModel.post_id == post_id)
        .order_by(CommentModel.id.asc())
        .all()
    )
    return "".join(f"{r.name}: {r.comment}\n" for r in rows)


def _generate_more_comments(db: Session, db_post: PostModel, count: int) -> None:
    """현재 댓글 수를 start 오프셋으로 페르소나를 순환 선택해 count개를 생성. 분량은 랜덤(FR-13)."""
    start = _count_comments(db, db_post.id)
    chat_history = _build_chat_history(db, db_post.id)
    for name, prompt in get_personas(count, start=start):
        comment_text = generate_ai_comment(prompt, db_post.content, chat_history, pick_length_style())
        db.add(CommentModel(post_id=db_post.id, name=name, comment=comment_text))
        chat_history += f"{name}: {comment_text}\n"

# 📌 0. 인증 — 가입(자동 로그인) / 로그인
@app.post("/api/auth/signup", status_code=201)
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    exists = db.query(UserModel).filter(UserModel.email == request.email).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    user = UserModel(email=request.email, password_hash=hash_password(request.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    # 내부 AI 페르소나 1개 생성 (풀에서 랜덤). best-effort — 실패해도 가입은 유지(NFR).
    try:
        name, prompt = random_persona()
        db.add(AiPersonaModel(user_id=user.id, display_name=name, persona_prompt=prompt))
        db.commit()
    except Exception:
        db.rollback()

    return {"token": create_token(user.id)}


@app.post("/api/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == request.email).first()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return {"token": create_token(user.id)}


# 📌 1. 과거에 저장된 모든 고민 글 + AI 댓글 리스트를 역순(최신순)으로 반환하는 API
@app.get("/api/posts")
def get_all_posts(db: Session = Depends(get_db)):
    posts = db.query(PostModel).order_by(PostModel.id.desc()).all()
    return posts

# 📌 2. 고민 등록 시 채점 및 AI 배틀을 진행하고 그 결과를 PostgreSQL에 영구 저장하는 API
@app.post("/api/posts")
async def create_post(
    request: PostRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),  # 로그인 필수 (FR-4)
):
    user_post = request.content

    score = evaluate_post_quality(user_post)
    base_limit = compute_base_limit(score)
    # 반응 0 시점이므로 Final == Base. 초기 생성도 동일 수식 사용(FR-11). 잡담도 최소 10개(FR-1).
    final_limit = compute_final_limit(base_limit, 0, get_current_population())

    # 1. 원문 글 저장하여 고유 ID 확보 (작성자 연결 — 북극성 §4)
    db_post = PostModel(content=user_post, score=score, author_user_id=current_user.id)
    db.add(db_post)
    db.commit()
    db.refresh(db_post)

    # 2. Final Limit 슬롯 = 타 유저 페르소나 출동(최대 2) + 공용 풀. 총 수 불변. 분량 랜덤(FR-13).
    deployed = select_deployed_personas(db, exclude_user_id=current_user.id, k=2)
    pool = get_personas(max(final_limit - len(deployed), 0))
    commenters = (deployed + pool)[:final_limit]
    chat_history = ""
    for name, prompt in commenters:
        comment_text = generate_ai_comment(prompt, user_post, chat_history, pick_length_style())
        db.add(CommentModel(post_id=db_post.id, name=name, comment=comment_text))
        chat_history += f"{name}: {comment_text}\n"

    db.commit()       # 트랜잭션 최종 확정
    db.refresh(db_post)  # 자식 레코드(comments) 상태 동기화
    _ = db_post.comments  # 직렬화 전 lazy 관계 강제 로드(응답에 comments 포함되도록)

    return db_post


# 📌 3. 반응 등록 → 스택 적재 → Final 재계산 → 부족분 생성 → Cap 도달 시 조용히 종료
@app.post("/api/posts/{post_id}/reaction")
def react_to_post(
    post_id: int,
    request: ReactionRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),  # 로그인 필수 (FR-4)
):
    db_post = db.query(PostModel).filter(PostModel.id == post_id).first()
    if db_post is None:
        raise HTTPException(status_code=404, detail="post not found")
    if request.reaction not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="reaction must be 'like' or 'dislike'")

    # 카운터 증분이 아니라 개별 레코드(스택)로 적재 → 동시 클릭 경합 제거(FR-9). 반응자 연결(북극성 §4).
    db.add(ReactionModel(post_id=post_id, reaction_type=request.reaction, user_id=current_user.id))
    db.commit()
    db.refresh(db_post)

    # 잠긴 스레드는 반응만 기록하고 생성/종료 없음 (FR-8)
    if not db_post.is_locked:
        base = compute_base_limit(db_post.score)
        population = get_current_population()
        total_reactions = _count_reactions(db, post_id)
        final = compute_final_limit(base, total_reactions, population)
        current = _count_comments(db, post_id)
        if current < final:
            _generate_more_comments(db, db_post, final - current)
            db.commit()
        if should_lock(_count_comments(db, post_id), compute_effective_cap(population)):
            db_post.is_locked = True  # Cap 도달 → 중재자 없이 조용히 종료(FR-7)
            db.commit()

    db.refresh(db_post)
    _ = db_post.comments  # 직렬화 전 lazy 관계 강제 로드
    return db_post


# 📌 4. 댓글 단위 반응(진화 신호 수집) — 유저·댓글당 1개 upsert. 한계선/생성에 영향 없음.
@app.post("/api/comments/{comment_id}/reaction")
def react_to_comment(
    comment_id: int,
    request: ReactionRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),  # 로그인 필수
):
    comment = db.query(CommentModel).filter(CommentModel.id == comment_id).first()
    if comment is None:
        raise HTTPException(status_code=404, detail="comment not found")
    if request.reaction not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="reaction must be 'like' or 'dislike'")

    existing = (
        db.query(CommentReactionModel)
        .filter(
            CommentReactionModel.user_id == current_user.id,
            CommentReactionModel.comment_id == comment_id,
        )
        .first()
    )
    if existing is not None:
        existing.reaction_type = request.reaction  # 재반응 → 교체(upsert)
    else:
        db.add(CommentReactionModel(
            user_id=current_user.id,
            comment_id=comment_id,
            reaction_type=request.reaction,
        ))
    db.commit()
    return {"ok": True}  # 개수 비노출 (FR-3)