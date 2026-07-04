# 테스트 픽스처는 루트 conftest(comea_backend/conftest.py)가 전담한다.
# (env 강제 + 스크래치 SQLite 파일 + client/auth_client/db_tables 픽스처)
# 이 파일에서 DATABASE_URL 등을 다시 설정하면 루트 설정을 덮어써 파이프라인 테스트가 깨지므로 비워 둔다.
