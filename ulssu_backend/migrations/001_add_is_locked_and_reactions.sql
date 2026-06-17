-- 001_add_is_locked_and_reactions.sql
-- elastic-comment-limit 슬라이스 스키마를 기존 운영 PostgreSQL 에 반영한다.
-- 멱등(idempotent): 여러 번 실행해도 안전. dev/신규 DB 는 create_all 이 처리하므로 불필요.
-- 적용:  psql "$DATABASE_URL" -f migrations/001_add_is_locked_and_reactions.sql

-- posts.is_locked: 댓글이 상한(Cap)에 도달해 잠긴 스레드 표시. 기본 false.
ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_locked BOOLEAN NOT NULL DEFAULT FALSE;

-- reactions: 좋아요/싫어요를 카운터가 아니라 타임스탬프 스택 레코드로 적재(동시 클릭 경합 제거).
CREATE TABLE IF NOT EXISTS reactions (
    id            SERIAL PRIMARY KEY,
    post_id       INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    reaction_type VARCHAR NOT NULL,            -- "like" | "dislike" (B2B 분석용 저장, 수식은 총량만 사용)
    created_at    TIMESTAMP NOT NULL DEFAULT now()
);

-- post_id 로 자주 COUNT/조회하므로 인덱스.
CREATE INDEX IF NOT EXISTS ix_reactions_post_id ON reactions (post_id);

-- ───────────────────────────────────────────────────────────────────────────
-- 롤백 (down) — 필요 시 수동 실행:
--   DROP TABLE IF EXISTS reactions;
--   ALTER TABLE posts DROP COLUMN IF EXISTS is_locked;
-- ───────────────────────────────────────────────────────────────────────────
