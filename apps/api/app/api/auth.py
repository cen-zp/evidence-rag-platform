from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_session
from app.models import KnowledgeBase, User, UserSession
from app.schemas.auth import AuthenticatedUser, Credentials, SessionResponse
from app.services.auth import (
    create_session,
    get_auth_settings,
    get_current_session,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: Credentials,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_auth_settings),
) -> SessionResponse:
    email = payload.email.lower()
    if session.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    is_first_user = session.scalar(select(func.count(User.id))) == 0
    user = User(email=email, password_hash=hash_password(payload.password))
    token, user_session = create_session(user, settings.auth_session_days)
    session.add_all([user, user_session])
    try:
        session.flush()
        if is_first_user:
            session.execute(
                update(KnowledgeBase)
                .where(KnowledgeBase.owner_id.is_(None))
                .values(owner_id=user.id)
            )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from error

    return SessionResponse(access_token=token, user=AuthenticatedUser.model_validate(user))


@router.post("/login", response_model=SessionResponse)
def login(
    payload: Credentials,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_auth_settings),
) -> SessionResponse:
    user = session.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, user_session = create_session(user, settings.auth_session_days)
    session.add(user_session)
    session.commit()
    return SessionResponse(access_token=token, user=AuthenticatedUser.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    current_session: UserSession = Depends(get_current_session),
    session: Session = Depends(get_session),
) -> None:
    session.delete(current_session)
    session.commit()


@router.get("/me", response_model=AuthenticatedUser)
def get_me(current_user: User = Depends(get_current_user)) -> AuthenticatedUser:
    return AuthenticatedUser.model_validate(current_user)
