import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models import User, UserSession

_bearer_scheme = HTTPBearer(auto_error=False)
_scrypt_n = 2**14
_scrypt_r = 8
_scrypt_p = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_scrypt_n,
        r=_scrypt_r,
        p=_scrypt_p,
        dklen=32,
    )
    return "scrypt${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived_key).decode("ascii"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, encoded_salt, encoded_key = password_hash.split("$", maxsplit=2)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
        expected_key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
        actual_key = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_scrypt_n,
            r=_scrypt_r,
            p=_scrypt_p,
            dklen=len(expected_key),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual_key, expected_key)


def create_session(user: User, session_days: int) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(32)
    record = UserSession(
        user=user,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(days=session_days),
    )
    return token, record


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_session),
) -> UserSession:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    user_session = session.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user))
        .where(UserSession.token_hash == hash_token(credentials.credentials))
    )
    if user_session is None or _is_expired(user_session.expires_at):
        raise _unauthorized()
    return user_session


def get_current_user(
    user_session: UserSession = Depends(get_current_session),
) -> User:
    return user_session.user


def get_auth_settings(settings: Settings = Depends(get_settings)) -> Settings:
    return settings


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required",
        headers={"WWW-Authenticate": "Bearer"},
    )
