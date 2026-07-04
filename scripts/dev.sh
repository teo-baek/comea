#!/usr/bin/env bash
# Comea 로컬 개발 원커맨드: 도커 DB → 백엔드(8247) → Flutter 크롬
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "── 1/3 PostgreSQL (docker, 5439) ──"
if ! docker info >/dev/null 2>&1; then
  echo "· Docker 데몬이 꺼져 있어 Docker Desktop을 실행합니다…"
  open -ga Docker
  for _ in $(seq 1 60); do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
  if ! docker info >/dev/null 2>&1; then
    echo "✖ Docker 데몬이 2분 내에 준비되지 않았습니다. Docker Desktop 상태를 확인해주세요."
    exit 1
  fi
fi
docker compose up -d db
for _ in $(seq 1 30); do
  docker exec comea-postgres pg_isready -U comea -d comea >/dev/null 2>&1 && break
  sleep 1
done
echo "✔ DB 준비 완료"

echo "── 2/3 백엔드 (uvicorn :8247) ──"
lsof -ti tcp:8247 | xargs kill 2>/dev/null || true
(cd "$ROOT/comea_backend" && uv run uvicorn main:app --host 127.0.0.1 --port 8247 --reload \
  > "$ROOT/.backend-dev.log" 2>&1) &
BACK_PID=$!
cleanup() {
  kill "$BACK_PID" 2>/dev/null || true
  lsof -ti tcp:8247 | xargs kill 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  curl -sf http://127.0.0.1:8247/api/health >/dev/null 2>&1 && break
  sleep 0.5
done
if curl -sf http://127.0.0.1:8247/api/health >/dev/null 2>&1; then
  echo "✔ 백엔드 준비 완료 — 로그: .backend-dev.log"
else
  echo "✖ 백엔드 기동 실패 — .backend-dev.log 마지막 20줄:"
  tail -20 "$ROOT/.backend-dev.log" || true
  exit 1
fi

echo "── 3/3 Flutter (chrome) ──"
cd "$ROOT/comea" && flutter run -d chrome
