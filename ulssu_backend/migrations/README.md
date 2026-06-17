# DB 마이그레이션 (수동 SQL)

`database.py`의 `Base.metadata.create_all()`은 **없는 테이블만 생성**하고, 이미 존재하는 테이블에 **컬럼을 추가(ALTER)하지 못한다.** 따라서:

- **dev / 신규 DB**: 별도 작업 불필요 — 앱 기동 시 `create_all`이 전체 스키마를 만든다.
- **데이터가 있는 기존 운영 PostgreSQL**: 새 컬럼/테이블이 누락되어 INSERT가 깨지므로, 아래 스크립트를 **한 번 적용**해야 한다.

## 적용 방법

```bash
# DATABASE_URL 은 운영 DB 접속 문자열 (예: postgresql://user:pw@host:5432/ulssu_db)
psql "$DATABASE_URL" -f migrations/001_add_is_locked_and_reactions.sql
```

- 모든 스크립트는 **멱등**(`IF NOT EXISTS` 등) — 재실행해도 안전하다.
- 번호 순서(`001_`, `002_`, …)대로 적용한다.

## 마이그레이션 목록

| 파일 | 내용 | 관련 슬라이스 |
|---|---|---|
| `001_add_is_locked_and_reactions.sql` | `posts.is_locked` 컬럼 추가 + `reactions` 테이블 생성 | elastic-comment-limit |

## 롤백

각 스크립트 하단 주석의 down SQL을 역순으로 수동 실행한다.

## 향후

배포 파이프라인/CI가 생기면 버전 관리되는 마이그레이션 도구(Alembic 등)로 이관하는 것을 권장한다. 현재는 배포가 없어 수동 SQL로 충분하다.
