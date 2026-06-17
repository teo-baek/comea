-- 004_add_comment_reactions.sql
-- comment-reactions 슬라이스 스키마를 기존 운영 PostgreSQL 에 반영한다. 멱등.
-- 적용:  psql "$DATABASE_URL" -f migrations/004_add_comment_reactions.sql

CREATE TABLE IF NOT EXISTS comment_reactions (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    comment_id    INTEGER NOT NULL REFERENCES comments(id),
    reaction_type VARCHAR NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_comment UNIQUE (user_id, comment_id)
);

-- 롤백 (down):
--   DROP TABLE IF EXISTS comment_reactions;
