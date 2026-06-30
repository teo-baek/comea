-- 003_add_ai_personas.sql
-- user-ai-persona-fixed 슬라이스 스키마를 기존 운영 PostgreSQL 에 반영한다. 멱등.
-- 적용:  psql "$DATABASE_URL" -f migrations/003_add_ai_personas.sql

CREATE TABLE IF NOT EXISTS ai_personas (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER UNIQUE NOT NULL REFERENCES users(id),
    display_name   VARCHAR NOT NULL,
    persona_prompt TEXT NOT NULL,
    trait_params   JSONB,
    updated_at     TIMESTAMP NOT NULL DEFAULT now()
);

-- 롤백 (down):
--   DROP TABLE IF EXISTS ai_personas;
