import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from helpers.anonymity import (
    decrypt_number,
    decrypt_personal_text,
    encrypt_number,
    encrypt_personal_text,
    mask_number,
    pseudo_id_for,
)
from helpers.email import normalize_email
from models.user import UserModel
from schemas.user import UserCreate, UserUpdate, PaginationMeta
from services.auth_service import hash_password


def create_user(db: Session, data: UserCreate) -> UserModel:
    user = UserModel(
        fullname=data.fullname,
        pseudo_id=pseudo_id_for(data.telnumber),
        telnumber=encrypt_number(data.telnumber),
        location=data.location,
        age=data.age,
        email=data.email,
        password_hash=hash_password(data.password),
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_admin(db: Session, data: UserCreate) -> UserModel:
    user = UserModel(
        fullname=data.fullname,
        pseudo_id=pseudo_id_for(data.telnumber) if data.telnumber else uuid.uuid4().hex,
        telnumber=encrypt_number(data.telnumber),
        location=data.location,
        age=data.age,
        email=data.email,
        password_hash=hash_password(data.password),
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, user_id: uuid.UUID) -> UserModel | None:
    result = db.execute(select(UserModel).where(UserModel.id == user_id))
    return result.scalar_one_or_none()


def get_user_by_id_for_actor(
    db: Session,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
    is_admin: bool,
) -> UserModel | None:
    statement = select(UserModel).where(UserModel.id == user_id)
    if not is_admin:
        statement = statement.where(UserModel.id == actor_id)
    return db.execute(statement).scalar_one_or_none()


def get_admin_by_id(db: Session, user_id: uuid.UUID) -> UserModel | None:
    result = db.execute(
        select(UserModel).where(UserModel.id == user_id, UserModel.is_admin == True)
    )
    return result.scalar_one_or_none()


def find_user_by_email(db: Session, email: str) -> UserModel | None:
    result = db.execute(
        select(UserModel)
        .where(func.lower(UserModel.email) == normalize_email(email))
        .order_by(UserModel.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


def find_user_by_pseudo_id(db: Session, pseudo_id: str) -> UserModel | None:
    result = db.execute(select(UserModel).where(UserModel.pseudo_id == pseudo_id))
    return result.scalar_one_or_none()


def pseudo_id_exists(db: Session, pseudo_id: str) -> bool:
    return find_user_by_pseudo_id(db, pseudo_id) is not None


class UserDeletedError(ValueError):
    """The pseudo_id belongs to a soft-deleted user: the bot must not write for her."""


def get_or_create_bot_user(db: Session, pseudo_id: str, telnumber: str | None = None) -> UserModel:
    user = find_user_by_pseudo_id(db, pseudo_id)
    if user:
        if user.deleted_at is not None:
            raise UserDeletedError("USER_DELETED")
        if telnumber and not user.telnumber:
            user.telnumber = encrypt_number(telnumber)
            db.commit()
            db.refresh(user)
        return user
    email = f"bot_{pseudo_id[:20]}@hllama.local"
    user = UserModel(
        pseudo_id=pseudo_id,
        telnumber=encrypt_number(telnumber),
        email=email,
        password_hash=hash_password(uuid.uuid4().hex),
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_bot_profile(user: UserModel | None, pseudo_id: str) -> dict[str, str | None]:
    return {
        "pseudo_id": pseudo_id,
        "preferred_name": (
            decrypt_personal_text(user.preferred_name_encrypted) if user else None
        ),
    }


def update_bot_preferred_name(
    db: Session,
    user: UserModel,
    preferred_name: str,
) -> dict[str, str | None]:
    user.preferred_name_encrypted = encrypt_personal_text(preferred_name)
    db.commit()
    db.refresh(user)
    return get_bot_profile(user, user.pseudo_id)


def update_user_by_id_for_actor(
    db: Session,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
    is_admin: bool,
    data: UserUpdate,
) -> dict:
    statement = select(UserModel).where(UserModel.id == user_id)
    if not is_admin:
        statement = statement.where(UserModel.id == actor_id)
    result = db.execute(statement)
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("USER_NOT_FOUND")

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise ValueError("NO_UPDATE_DATA")

    for field, value in update_data.items():
        if field == "telnumber" and value:
            user.telnumber = encrypt_number(value)
        else:
            setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return {"id": str(user.id), "updated_fields": list(update_data.keys())}


def user_to_dict(user: UserModel) -> dict:
    """Serializes a user for admin-facing responses without exposing PII.

    Regular users are returned strictly pseudonymous: pseudo_id + masked
    number, with fullname/email/location/age omitted. Staff accounts
    (is_admin) keep their name/email so the backoffice stays usable, but
    their phone number is masked as well.
    """
    return {
        "id": str(user.id),
        "pseudo_id": user.pseudo_id,
        "telnumber_masked": mask_number(decrypt_number(user.telnumber)),
        "fullname": user.fullname if user.is_admin else None,
        "location": user.location if user.is_admin else None,
        "age": user.age if user.is_admin else None,
        "email": user.email if user.is_admin else None,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "deleted_at": user.deleted_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def get_users_paginated(
    db: Session,
    page: int = 1,
    limit: int = 10,
    is_admin: bool = False,
) -> dict:
    query = select(UserModel).where(UserModel.is_admin == is_admin)

    count_result = db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total_count = count_result.scalar()
    total_pages = math.ceil(total_count / limit) if total_count else 0

    offset = (page - 1) * limit
    query = query.order_by(UserModel.id).offset(offset).limit(limit)
    result = db.execute(query)
    users = result.scalars().all()

    return {
        "data": users,
        "meta": PaginationMeta(
            current_page=page,
            total_pages=total_pages,
            total_count=total_count,
            page_size=limit,
            has_more=page < total_pages,
        ),
    }
