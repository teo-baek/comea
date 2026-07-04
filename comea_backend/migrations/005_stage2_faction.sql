-- 005_stage2_faction.sql
-- 스테이지 2(진영 토론) 스키마 변경분을 기존 운영 PostgreSQL 에 반영한다. 멱등.
-- 참고용 문서 — 런타임 스키마 생성은 create_all 이 담당한다 (스펙 §3).
-- 적용:  psql "$DATABASE_URL" -f migrations/005_stage2_faction.sql

-- ---------------------------------------------------------------------------
-- 1) posts: 상태 머신(grading|debating|concluded) + 채점 결과 + 판정 컬럼
-- ---------------------------------------------------------------------------
ALTER TABLE posts ADD COLUMN IF NOT EXISTS status          VARCHAR(16) NOT NULL DEFAULT 'grading';
ALTER TABLE posts ADD COLUMN IF NOT EXISTS score_breakdown JSON;                  -- {"emotion":1~5,"controversy":..,"clarity":..,"novelty":..}
ALTER TABLE posts ADD COLUMN IF NOT EXISTS core_claim      TEXT;                  -- 채점관이 추출한 핵심 주장 1문장
ALTER TABLE posts ADD COLUMN IF NOT EXISTS base_limit      INTEGER;               -- 점수 구간별 기본 댓글 리밋
ALTER TABLE posts ADD COLUMN IF NOT EXISTS verdict         VARCHAR(16);           -- ally | challenger | tie
ALTER TABLE posts ADD COLUMN IF NOT EXISTS created_at      TIMESTAMP NOT NULL DEFAULT now();

-- 채점 전 NULL 허용 (구 스키마는 NOT NULL)
ALTER TABLE posts ALTER COLUMN score DROP NOT NULL;

-- 구 리밋 잠금 플래그 제거 (스테이지 2 는 status 상태 머신으로 대체)
ALTER TABLE posts DROP COLUMN IF EXISTS is_locked;

-- ---------------------------------------------------------------------------
-- 2) comments: 진영/페르소나/턴 컬럼 + 컬럼명 교체 (name→persona_name, comment→content)
--    하위호환 불필요(프론트 재작성) — 하드 컷 리네임 (스펙 §3)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'comments' AND column_name = 'name') THEN
        ALTER TABLE comments RENAME COLUMN name TO persona_name;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'comments' AND column_name = 'comment') THEN
        ALTER TABLE comments RENAME COLUMN comment TO content;
    END IF;
END $$;

-- 기존 행 채움을 위해 DEFAULT 'ally' 로 추가 후 DEFAULT 제거 (모델에는 default 없음)
ALTER TABLE comments ADD COLUMN IF NOT EXISTS faction VARCHAR(16) NOT NULL DEFAULT 'ally';
ALTER TABLE comments ALTER COLUMN faction DROP DEFAULT;

ALTER TABLE comments ADD COLUMN IF NOT EXISTS persona_key VARCHAR;                -- 풀 key 또는 'user:{user_id}'
ALTER TABLE comments ADD COLUMN IF NOT EXISTS turn_index  INTEGER NOT NULL DEFAULT 0;
ALTER TABLE comments ADD COLUMN IF NOT EXISTS created_at  TIMESTAMP NOT NULL DEFAULT now();

-- 고아 댓글 정리 후 post_id NOT NULL 강제 (구 스키마는 NULL 허용)
DELETE FROM comments WHERE post_id IS NULL;
ALTER TABLE comments ALTER COLUMN post_id SET NOT NULL;

-- ---------------------------------------------------------------------------
-- 3) reactions: 인당 1표 (토글/변경) — UNIQUE(user_id, post_id)
-- ---------------------------------------------------------------------------
-- 익명 반응(구 스키마 NULL 허용) 제거 후 NOT NULL 강제
DELETE FROM reactions WHERE user_id IS NULL;
ALTER TABLE reactions ALTER COLUMN user_id SET NOT NULL;

-- 유니크 제약 위반 방지: (user_id, post_id) 중복 행은 최신(id 최대)만 남긴다
DELETE FROM reactions r
USING reactions r2
WHERE r.user_id = r2.user_id
  AND r.post_id = r2.post_id
  AND r.id < r2.id;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_user_post') THEN
        ALTER TABLE reactions ADD CONSTRAINT uq_user_post UNIQUE (user_id, post_id);
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 롤백 (down):
--   ALTER TABLE reactions DROP CONSTRAINT IF EXISTS uq_user_post;
--   ALTER TABLE reactions ALTER COLUMN user_id DROP NOT NULL;
--   ALTER TABLE comments RENAME COLUMN persona_name TO name;
--   ALTER TABLE comments RENAME COLUMN content TO comment;
--   ALTER TABLE comments DROP COLUMN IF EXISTS faction,
--                        DROP COLUMN IF EXISTS persona_key,
--                        DROP COLUMN IF EXISTS turn_index,
--                        DROP COLUMN IF EXISTS created_at;
--   ALTER TABLE posts DROP COLUMN IF EXISTS status,
--                     DROP COLUMN IF EXISTS score_breakdown,
--                     DROP COLUMN IF EXISTS core_claim,
--                     DROP COLUMN IF EXISTS base_limit,
--                     DROP COLUMN IF EXISTS verdict,
--                     DROP COLUMN IF EXISTS created_at;
--   ALTER TABLE posts ADD COLUMN is_locked BOOLEAN NOT NULL DEFAULT false;
