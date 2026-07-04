"""pytest 루트 conftest (스펙 §9).

1) **모듈 import 전에** 테스트 환경변수를 강제한다 — database/main 등은 import 시점에
   DATABASE_URL 을 읽어 엔진을 만들고, main 의 load_dotenv 는 override=False 라 여기 값이 이긴다.
2) 테스트 세션마다 유니크한 스크래치 SQLite **파일**을 쓴다 — BackgroundTasks(debate 파이프라인)가
   별도 세션(database.SessionLocal)에서 같은 DB 를 보게 하기 위함 (인메모리는 커넥션마다 분리됨).
3) comea_backend/ 를 sys.path 에 올려 플랫 임포트(from database import ...)를 지원한다.
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

# --- 1) env 강제: 어떤 백엔드 모듈보다 먼저 실행되어야 한다 ---
os.environ["COMEA_FAKE_AI"] = "1"           # OpenAI 호출 없이 결정적 스텁
os.environ["COMEA_COMMENT_DELAY_MIN"] = "0"  # 딜레이 0 → 파이프라인 결정적 실행
os.environ["COMEA_COMMENT_DELAY_MAX"] = "0"
os.environ["DISABLE_SCHEDULER"] = "1"        # APScheduler 미기동
os.environ["JWT_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"  # 32B 이상 (HMAC 경고 방지)

# --- 2) 세션 유니크 스크래치 SQLite 파일 ---
_SCRATCH_DIR = Path(tempfile.mkdtemp(prefix="comea-test-"))
_SCRATCH_DB = _SCRATCH_DIR / f"comea_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB}"

# --- 3) 플랫 임포트 지원 ---
_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import pytest


@pytest.fixture()
def db_tables():
    """테스트마다 테이블 생성 → 종료 시 전부 드롭 (테스트 간 데이터 격리)."""
    import database

    database.Base.metadata.create_all(bind=database.engine)
    yield
    database.Base.metadata.drop_all(bind=database.engine)


@pytest.fixture()
def client(db_tables):
    """FastAPI TestClient. 응답 후 BackgroundTasks 를 동기 실행하므로
    delay=0 + fake AI 조합으로 debate 파이프라인을 결정적으로 검증할 수 있다."""
    from fastapi.testclient import TestClient

    import main
    import population

    population.set_current_population(0)  # 인메모리 전역 상태 격리
    with TestClient(main.app) as c:
        yield c
    population.set_current_population(0)


@pytest.fixture()
def auth_client(client):
    """가입해서 토큰을 받은 뒤 Authorization 기본 헤더를 단 TestClient."""
    resp = client.post("/api/auth/signup", json={"email": "tester@x.com", "password": "pw123456"})
    assert resp.status_code == 201
    client.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
    return client
