import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from helpers.anonymity import pseudo_id_for
from helpers.server_message import ServerMessageException, typed_server_message
from models.user import UserModel
from schemas.common import ResponseMetadata, SuccessEnvelope
from schemas.user import (
    UserCreate,
    UserPaginationMetadata,
    UserResponse,
    UserUpdate,
    UserUpdateResponse,
)
from services.auth_service import get_current_active_user, require_admin
from services.user_service import (
    create_user,
    find_user_by_email,
    find_user_by_pseudo_id,
    get_user_by_id,
    get_user_by_id_for_actor,
    get_users_paginated,
    pseudo_id_exists,
    update_user_by_id_for_actor,
    user_to_dict,
)

router = APIRouter(prefix="/api/users", tags=["users"])


def _user_dict(user: UserModel) -> UserResponse:
    return UserResponse.model_validate(user_to_dict(user))


@router.get(
    "", response_model=SuccessEnvelope[list[UserResponse], UserPaginationMetadata]
)
def list_users(
    page: int = Query(1, gt=0),
    limit: int = Query(10, gt=0, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    result = get_users_paginated(db, page=page, limit=limit, is_admin=False)
    data = [_user_dict(u) for u in result["data"]]
    return typed_server_message(
        "USERS_FETCHED",
        data,
        SuccessEnvelope[list[UserResponse], UserPaginationMetadata],
        "users_list",
        meta=result["meta"].model_dump(),
    )


@router.post(
    "", response_model=SuccessEnvelope[UserResponse, ResponseMetadata], status_code=201
)
def create_new_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    if find_user_by_email(db, data.email):
        raise ServerMessageException("EMAIL_ALREADY_EXISTS")
    if data.telnumber and pseudo_id_exists(db, pseudo_id_for(data.telnumber)):
        raise ServerMessageException("TELNUMBER_ALREADY_EXISTS")
    user = create_user(db, data)
    return typed_server_message(
        "USER_CREATED",
        _user_dict(user),
        SuccessEnvelope[UserResponse, ResponseMetadata],
        "users_create",
    )


@router.get(
    "/me/", response_model=SuccessEnvelope[UserResponse, ResponseMetadata]
)
def read_current_user(current_user=Depends(get_current_active_user)):
    return typed_server_message(
        "CURRENT_USER_FETCHED",
        _user_dict(current_user),
        SuccessEnvelope[UserResponse, ResponseMetadata],
        "users_read_current",
    )


@router.get(
    "/{user_id}", response_model=SuccessEnvelope[UserResponse, ResponseMetadata]
)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise ServerMessageException("USER_NOT_FOUND")
    return typed_server_message(
        "USER_FETCHED",
        _user_dict(user),
        SuccessEnvelope[UserResponse, ResponseMetadata],
        "users_read",
    )


@router.put(
    "/{user_id}",
    response_model=SuccessEnvelope[UserUpdateResponse, ResponseMetadata],
)
def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    user = get_user_by_id_for_actor(
        db, user_id, current_user.id, current_user.is_admin
    )
    if not user:
        raise ServerMessageException("USER_NOT_FOUND")
    if data.email:
        existing = find_user_by_email(db, data.email)
        if existing and existing.id != user.id:
            raise ServerMessageException("EMAIL_ALREADY_EXISTS")
    if data.telnumber:
        existing = find_user_by_pseudo_id(db, pseudo_id_for(data.telnumber))
        if existing and existing.id != user.id:
            raise ServerMessageException("TELNUMBER_ALREADY_EXISTS")
    try:
        result = update_user_by_id_for_actor(
            db,
            user_id,
            current_user.id,
            current_user.is_admin,
            data,
        )
    except ValueError as e:
        msg = str(e)
        if msg == "NO_UPDATE_DATA":
            raise ServerMessageException("NO_UPDATE_DATA")
        raise ServerMessageException("USER_NOT_FOUND")
    return typed_server_message(
        "USER_UPDATED",
        result,
        SuccessEnvelope[UserUpdateResponse, ResponseMetadata],
        "users_update",
    )
