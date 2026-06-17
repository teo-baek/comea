"""일일 인구 배치: COUNT(users) → current_population. APScheduler 인프로세스."""
import os

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

import database
import population
from database import UserModel

_scheduler = None


def compute_population(db: Session) -> int:
    """전체 가입 유저수."""
    return db.query(UserModel).count()


def run_population_update() -> None:
    """유저수를 집계해 current_population 에 주입. 실패해도 전파하지 않음(AC-5)."""
    try:
        db = database.SessionLocal()
        try:
            population.set_current_population(compute_population(db))
        finally:
            db.close()
    except Exception:
        pass


def start_scheduler() -> None:
    """기동 즉시 1회 집계 + 매일 4시 cron 등록. 테스트(DISABLE_SCHEDULER)면 미기동(D5)."""
    if os.getenv("DISABLE_SCHEDULER"):
        return
    global _scheduler
    run_population_update()  # 기동 즉시 1회 (0 방지, FR-2)
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(run_population_update, "cron", hour=4)
    _scheduler.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
