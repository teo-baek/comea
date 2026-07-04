"""일일 인구 배치: COUNT(users) → current_population 캐시 갱신 (스펙 §8, PRD 3.5).

- 기동 시 1회 즉시 갱신 + 매일 04:00 cron (APScheduler 인프로세스).
- 테스트는 DISABLE_SCHEDULER=1 로 미기동.
"""
import os

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

import database
import population
from database import UserModel

_scheduler = None


def compute_population(db: Session) -> int:
    """전체 가입 유저수 카운트 (MAU 단순화 — 스펙 §8)."""
    return db.query(UserModel).count()


def run_population_update() -> None:
    """유저수를 집계해 current_population 에 주입. 실패해도 서버 기동을 막지 않는다."""
    try:
        db = database.SessionLocal()
        try:
            population.set_current_population(compute_population(db))
        finally:
            db.close()
    except Exception:
        pass


def start_scheduler() -> None:
    """기동 즉시 1회 집계 + 매일 04:00 cron 등록. DISABLE_SCHEDULER=1 이면 미기동."""
    if os.getenv("DISABLE_SCHEDULER"):
        return
    global _scheduler
    run_population_update()  # 기동 즉시 1회 (population_bonus 0 방치 방지)
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(run_population_update, "cron", hour=4)
    _scheduler.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
