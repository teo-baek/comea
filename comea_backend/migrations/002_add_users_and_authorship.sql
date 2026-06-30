-- 002_add_users_and_authorship.sql
-- user-auth 슬라이스 스키마를 기존 운영 PostgreSQL 에 반영한다. 멱등.
-- 적용:  psql "$DATABASE_URL" -f migrations/002_add_users_and_authorship.sql

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE posts     ADD COLUMN IF NOT EXISTS author_user_id INTEGER REFERENCES users(id);
ALTER TABLE reactions ADD COLUMN IF NOT EXISTS user_id        INTEGER REFERENCES users(id);

-- 롤백 (down):
--   ALTER TABLE reactions DROP COLUMN IF EXISTS user_id;
--   ALTER TABLE posts     DROP COLUMN IF EXISTS author_user_id;
--   DROP TABLE IF EXISTS users;
