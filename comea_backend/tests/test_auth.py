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


@pytest.mark.parametrize(
    "payload",
    [
        {},                    # sub 클레임 없음 (KeyError 경로)
        {"sub": "not-a-num"},  # 숫자가 아닌 sub (ValueError 경로)
        {"sub": None},         # None sub (TypeError 경로)
    ],
)
def test_decode_token_with_bad_sub_raises_pyjwt_error(payload):
    """서명은 유효하지만 sub 가 깨진 토큰 — 500 이 아니라 PyJWTError 로 정규화돼야 한다."""
    import auth

    token = jwt.encode(payload, auth.JWT_SECRET, algorithm=auth.JWT_ALGORITHM)
    with pytest.raises(jwt.PyJWTError):
        decode_token(token)
