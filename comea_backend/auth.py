"""인증 로직: 비밀번호 해시(bcrypt) + JWT(PyJWT) + get_current_user 의존성."""
import os
import datetime as dt

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db, UserModel

JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7  # 7일


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> int:
    """토큰 검증 → user_id 반환. 실패는 전부 jwt.PyJWTError 계열로 정규화한다.

    서명이 유효해도 sub 클레임이 없거나 숫자가 아니면 KeyError/ValueError/TypeError 가
    새어 나가 호출부(get_current_user*)의 except jwt.PyJWTError 를 비껴 500 이 되므로,
    여기서 InvalidTokenError 로 변환해 401(필수)/None(선택) 계약을 지킨다.
    """
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    try:
        return int(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise jwt.InvalidTokenError("sub claim missing or not an integer") from exc


def get_current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> UserModel:
    """Authorization: Bearer <jwt> 검증 → UserModel 반환. 실패 시 401."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[len("Bearer "):]
    try:
        user_id = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid token")
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    return user


def get_current_user_optional(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
) -> UserModel | None:
    """선택 인증: 토큰이 없거나 잘못됐으면 401 대신 None 반환 (비로그인 조회 허용, 스펙 §8)."""
    if not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer "):]
    try:
        user_id = decode_token(token)
    except jwt.PyJWTError:
        return None
    return db.query(UserModel).filter(UserModel.id == user_id).first()
