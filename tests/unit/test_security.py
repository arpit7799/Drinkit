from uuid import uuid4

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing_uses_a_one_way_hash():
    password = "correct horse battery staple"

    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash) is True
    assert verify_password("incorrect password", password_hash) is False


def test_access_tokens_round_trip_with_subject_and_session_claims():
    user_id = uuid4()
    session_id = uuid4()

    token = create_access_token(user_id=user_id, session_id=session_id)

    claims = decode_access_token(token)

    assert claims.subject == user_id
    assert claims.session_id == session_id
    assert claims.token_type == "access"
