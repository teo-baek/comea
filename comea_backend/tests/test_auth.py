import jwt
import pytest

from auth import create_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"            # 평문 아님
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False


def test_token_roundtrip():
    token = create_token(42)
    assert decode_token(token) == 42


def test_decode_forged_token_raises():
    bad = jwt.encode({"sub": "1"}, "WRONG-SECRET", algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        decode_token(bad)
