import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from schemas.common import ResponseMetadata


class UserCreate(BaseModel):
    fullname: str | None = None
    telnumber: str
    location: str | None = None
    age: int | None = None
    password: str
    email: EmailStr


class UserUpdate(BaseModel):
    fullname: str | None = None
    telnumber: str | None = None
    location: str | None = None
    age: int | None = None
    email: EmailStr | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    pseudo_id: str
    telnumber_masked: str | None = None
    fullname: str | None = None
    location: str | None = None
    age: int | None = None
    email: str | None = None
    is_admin: bool = False
    is_active: bool = True
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PaginationMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    current_page: int
    total_pages: int
    total_count: int
    page_size: int
    has_more: bool


class UserListResponse(BaseModel):
    data: list[UserResponse]
    meta: PaginationMeta


class UserPaginationMetadata(ResponseMetadata):
    model_config = ConfigDict(extra="forbid", strict=True)

    current_page: int
    total_pages: int
    total_count: int
    page_size: int
    has_more: bool


class UserUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    updated_fields: list[str]
