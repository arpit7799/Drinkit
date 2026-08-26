from sqlalchemy import DateTime, String, Uuid

from app.models.auth import AuthSession, Device, User


def test_identity_models_have_explicit_tables_and_security_columns():
    assert User.__table__.name == "users"
    assert Device.__table__.name == "devices"
    assert AuthSession.__table__.name == "auth_sessions"
    assert isinstance(User.__table__.c.email.type, String)
    assert isinstance(User.__table__.c.password_hash.type, String)
    assert isinstance(Device.__table__.c.user_id.type, Uuid)
    assert isinstance(AuthSession.__table__.c.token_family_id.type, Uuid)
    assert isinstance(AuthSession.__table__.c.expires_at.type, DateTime)
    assert AuthSession.__table__.c.refresh_token_hash.unique is True


def test_identity_models_require_database_level_lifecycle_invariants():
    assert User.__table__.c.email.nullable is False
    assert User.__table__.c.password_hash.nullable is False
    assert Device.__table__.c.user_id.nullable is False
    assert AuthSession.__table__.c.user_id.nullable is False
    assert AuthSession.__table__.c.revoked_at.nullable is True
    assert any(
        constraint.name == "ck_users_email_not_blank" for constraint in User.__table__.constraints
    )


def test_user_email_uniqueness_is_case_insensitive_in_the_database():
    assert any(
        index.name == "uq_users_email_ci" and index.unique for index in User.__table__.indexes
    )
