import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from helpers.anonymity import pseudo_id_for
from helpers.server_message import ServerMessageException, typed_server_message
from models.user import UserModel
from schemas.common import ResponseMetadata, SuccessEnvelope
from schemas.user import UserCreate, UserPaginationMetadata, UserResponse
from services.auth_service import get_current_active_user, require_admin
from services.user_service import (
    create_admin,
    find_user_by_email,
    get_admin_by_id,
    get_users_paginated,
    pseudo_id_exists,
    user_to_dict,
)

router = APIRouter(prefix="/api/admins", tags=["admins"])


def _user_dict(user: UserModel) -> UserResponse:
    return UserResponse.model_validate(user_to_dict(user))


@router.get(
    "", response_model=SuccessEnvelope[list[UserResponse], UserPaginationMetadata]
)
def list_admins(
    page: int = Query(1, gt=0),
    limit: int = Query(10, gt=0, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    result = get_users_paginated(db, page=page, limit=limit, is_admin=True)
    data = [_user_dict(u) for u in result["data"]]
    return typed_server_message(
        "ADMINS_FETCHED",
        data,
        SuccessEnvelope[list[UserResponse], UserPaginationMetadata],
        "admins_list",
        meta=result["meta"].model_dump(),
    )


@router.post(
    "", response_model=SuccessEnvelope[UserResponse, ResponseMetadata], status_code=201
)
def create_new_admin(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    if not current_user.is_admin:
        raise ServerMessageException("UNAUTHORIZED_ACCESS", status=403)
    if find_user_by_email(db, data.email):
        raise ServerMessageException("EMAIL_ALREADY_EXISTS")
    if data.telnumber and pseudo_id_exists(db, pseudo_id_for(data.telnumber)):
        raise ServerMessageException("TELNUMBER_ALREADY_EXISTS")
    admin = create_admin(db, data)
    return typed_server_message(
        "ADMIN_CREATED",
        _user_dict(admin),
        SuccessEnvelope[UserResponse, ResponseMetadata],
        "admins_create",
    )


@router.get(
    "/{user_id}", response_model=SuccessEnvelope[UserResponse, ResponseMetadata]
)
def get_admin(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    admin = get_admin_by_id(db, user_id)
    if not admin:
        raise ServerMessageException("ADMIN_NOT_FOUND")
    return typed_server_message(
        "ADMIN_FETCHED",
        _user_dict(admin),
        SuccessEnvelope[UserResponse, ResponseMetadata],
        "admins_read",
    )
