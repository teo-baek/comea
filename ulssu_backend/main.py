import os
import asyncio
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI

import database
from database import get_db, PostModel, CommentModel, ReactionModel
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

class PostRequest(BaseModel):
    content: str

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

# 📌 1. 과거에 저장된 모든 고민 글 + AI 댓글 리스트를 역순(최신순)으로 반환하는 API
@app.get("/api/posts")
def get_all_posts(db: Session = Depends(get_db)):
    posts = db.query(PostModel).order_by(PostModel.id.desc()).all()
    return posts

# 📌 2. 고민 등록 시 채점 및 AI 배틀을 진행하고 그 결과를 PostgreSQL에 영구 저장하는 API
@app.post("/api/posts")
async def create_post(request: PostRequest, db: Session = Depends(get_db)):
    user_post = request.content

    score = evaluate_post_quality(user_post)
    base_limit = compute_base_limit(score)
    # 반응 0 시점이므로 Final == Base. 초기 생성도 동일 수식 사용(FR-11). 잡담도 최소 10개(FR-1).
    final_limit = compute_final_limit(base_limit, 0, get_current_population())

    # 1. 원문 글 저장하여 고유 ID 확보
    db_post = PostModel(content=user_post, score=score)
    db.add(db_post)
    db.commit()
    db.refresh(db_post)

    # 2. Final Limit 만큼 페르소나를 순환 선택해 생성. 분량은 매번 랜덤 변주(FR-13).
    chat_history = ""
    for name, prompt in get_personas(final_limit):
        comment_text = generate_ai_comment(prompt, user_post, chat_history, pick_length_style())
        db.add(CommentModel(post_id=db_post.id, name=name, comment=comment_text))
        chat_history += f"{name}: {comment_text}\n"

    db.commit()       # 트랜잭션 최종 확정
    db.refresh(db_post)  # 자식 레코드(comments) 상태 동기화
    _ = db_post.comments  # 직렬화 전 lazy 관계 강제 로드(응답에 comments 포함되도록)

    return db_post