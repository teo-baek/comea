# Comea 로컬 개발 — 배포 없음, 전부 로컬 기준
# make dev   : DB(도커) + 백엔드(8247) + Flutter 크롬 한 번에
# make db    : PostgreSQL 도커만 기동
# make backend / make front : 각각 단독 실행
# make test  : 백엔드 pytest + Flutter test
# make stop  : 백엔드/DB 정지

.PHONY: dev db backend front test stop

dev:
	@bash scripts/dev.sh

db:
	docker compose up -d db
	@until docker exec comea-postgres pg_isready -U comea -d comea >/dev/null 2>&1; do sleep 1; done
	@echo "✔ PostgreSQL ready (127.0.0.1:5439)"

backend: db
	cd comea_backend && uv run uvicorn main:app --host 127.0.0.1 --port 8247 --reload

front:
	cd comea && flutter run -d chrome

test:
	uv run pytest comea_backend -q
	cd comea && flutter test

stop:
	-lsof -ti tcp:8247 | xargs kill 2>/dev/null || true
	docker compose stop db
	@echo "✔ 정지 완료"
