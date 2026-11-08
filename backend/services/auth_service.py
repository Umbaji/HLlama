from datetime import datetime, timedelta, timezone

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from helpers.email import normalize_email
from helpers.server_message import ServerMessageException
from models.user import UserModel

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_DUMMY_PASSWORD_HASH = pwd_context.hash("not-a-real-hllama-account-password")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(db: Session, email: str, password: str) -> UserModel | None:
    normalized = normalize_email(email)
    users = db.execute(
        select(UserModel)
        .where(func.lower(UserModel.email) == normalized)
        .limit(2)
    ).scalars().all()
    user = users[0] if len(users) == 1 else None
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserModel:
    if not token:
        raise ServerMessageException("UNAUTHORIZED_ACCESS")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise ServerMessageException("TOKEN_INVALID")
    except InvalidTokenError:
        raise ServerMessageException("TOKEN_INVALID")

    result = db.execute(select(UserModel).where(UserModel.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise ServerMessageException("TOKEN_INVALID")
    if user.is_admin and settings.ADMIN_MFA_REQUIRED and payload.get("mfa") is not True:
        raise ServerMessageException("TOKEN_INVALID")
    return user


def get_current_active_user(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    if not current_user.is_active:
        raise ServerMessageException("INACTIVE_USER")
    return current_user


def require_admin(current_user: UserModel = Depends(get_current_active_user)) -> UserModel:
    """Réservé aux admins connectés : 401 sans jeton, 403 pour un compte normal."""
    if not current_user.is_admin:
        raise ServerMessageException("UNAUTHORIZED_ACCESS", status=403)
    return current_user
