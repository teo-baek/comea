import os
from sqlalchemy import create_engine, Column, Integer, Text, String, ForeignKey, Boolean, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# GCP 환경변수 주입을 고려한 설계 (Docker 로컬 주소를 기본값으로 셋팅)
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:password@localhost:5432/ulssu_db"
)

# SQLite(테스트)일 때만 단일 커넥션/스레드 옵션을 적용. PostgreSQL(운영)은 기본값.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class PostModel(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    score = Column(Integer, nullable=False)
    is_locked = Column(Boolean, nullable=False, default=False, server_default="false")
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 익명 호환 NULL (북극성 §4)
    comments = relationship("CommentModel", back_populates="post", cascade="all, delete-orphan")
    # 주의: reactions 관계는 의도적으로 노출하지 않음(직렬화 시 카운트 유출 방지, FR-3).

class CommentModel(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"))
    name = Column(String, nullable=False)
    comment = Column(Text, nullable=False)
    post = relationship("PostModel", back_populates="comments")


class ReactionModel(Base):
    # 좋아요/싫어요를 카운터가 아니라 개별 레코드(스택)로 적재 → 동시 클릭 경합 제거(FR-9).
    # 총 반응 수는 COUNT 집계. reaction_type 은 B2B 분석용 저장(수식은 총량만 사용).
    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    reaction_type = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 누가 눌렀나, 익명 호환 NULL (북극성 §4)


class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()