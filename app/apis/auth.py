import asyncio

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db.databases import async_get_db
from app.core.security import (
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_TYPE,
    clear_refresh_cookie,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    set_refresh_cookie,
    unauthorized,
    verify_password,
)
from app.core.validators import normalize_phone, validate_password
from app.models.enums import Department, Gender, Role
from app.models.user import User


# ============================================================
# 요청 및 응답 스키마
# ============================================================

_DEPARTMENT_ALIASES = {
    "developer": Department.DEV,
    "dev": Department.DEV,
    "medical team": Department.MEDICAL,
    "medical": Department.MEDICAL,
    "researcher": Department.RESEARCH,
    "research": Department.RESEARCH,
}

_GENDER_ALIASES = {
    "male": Gender.M,
    "m": Gender.M,
    "female": Gender.F,
    "f": Gender.F,
}


class SignupRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str
    name: str = Field(min_length=2, max_length=20)
    department: Department
    gender: Gender
    phone_number: str

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_password(value)

    @field_validator("phone_number")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("department", mode="before")
    @classmethod
    def map_department(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            return _DEPARTMENT_ALIASES.get(normalized, value.strip().upper())
        return value

    @field_validator("gender", mode="before")
    @classmethod
    def map_gender(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            return _GENDER_ALIASES.get(normalized, value.strip().upper())
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str  # 기존 회원 로그인을 위해 규칙 검증은 걸지 않음

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    name: str | None
    department: Department
    gender: Gender
    phone_number: str | None
    role: Role


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(TokenResponse):
    user: UserPublic


# ============================================================
# DB 접근 함수
# ============================================================

async def get_by_id(
    db: AsyncSession,
    user_id: int,
) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_by_email(
    db: AsyncSession,
    email: str,
) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email)
    )
    return result.scalar_one_or_none()


async def get_by_phone_number(
    db: AsyncSession,
    phone_number: str,
) -> User | None:
    result = await db.execute(
        select(User).where(User.phone_number == phone_number)
    )
    return result.scalar_one_or_none()


async def add_user(
    db: AsyncSession,
    user: User,
) -> User:
    db.add(user)
    await db.flush()
    return user


# ============================================================
# 비즈니스 로직
# ============================================================

LOGIN_FAILED_MESSAGE = "아이디 또는 비밀번호를 확인해주세요."

# 존재하지 않는 이메일로 로그인해도 응답 시간이 비슷하도록 사용하는 더미 해시
_DUMMY_HASH = hash_password("dummy-Password-1!")


async def signup(
    db: AsyncSession,
    body: SignupRequest,
) -> User:
    if await get_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 가입된 이메일입니다.",
        )

    if await get_by_phone_number(db, body.phone_number):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 전화번호입니다.",
        )

    hashed_password = await asyncio.to_thread(
        hash_password,
        body.password,
    )

    user = User(
        email=body.email,
        hashed_password=hashed_password,
        name=body.name,
        phone_number=body.phone_number,
        gender=body.gender,
        department=body.department,
        role=Role.PENDING,
    )

    try:
        await add_user(db, user)
        await db.commit()
        await db.refresh(user)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 가입된 이메일 또는 전화번호입니다.",
        )

    return user


async def login(
    db: AsyncSession,
    email: str,
    password: str,
) -> tuple[str, str, User]:
    user = await get_by_email(db, email)

    hashed = user.hashed_password if user else _DUMMY_HASH

    password_ok = await asyncio.to_thread(
        verify_password,
        password,
        hashed,
    )

    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=LOGIN_FAILED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )

    return (
        create_access_token(user.id),
        create_refresh_token(user.id),
        user,
    )


async def refresh_access_token(
    db: AsyncSession,
    refresh_token: str,
) -> str:
    user_id = decode_token(refresh_token, REFRESH_TOKEN_TYPE)
    user = await get_by_id(db, user_id)

    if user is None:
        raise unauthorized()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )

    return create_access_token(user.id)


# ============================================================
# 인증 API
# ============================================================

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

_ACCESS_EXPIRES_IN = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


@router.post(
    "/signup",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
async def signup_api(
    body: SignupRequest,
    db: AsyncSession = Depends(async_get_db),
):
    return await signup(db, body)


@router.post("/login", response_model=LoginResponse)
async def login_api(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(async_get_db),
):
    access_token, refresh_token, user = await login(
        db,
        body.email,
        body.password,
    )

    set_refresh_cookie(response, refresh_token)

    return LoginResponse(
        access_token=access_token,
        expires_in=_ACCESS_EXPIRES_IN,
        user=UserPublic.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_api(
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(async_get_db),
):
    if not refresh_token:
        raise unauthorized()

    access_token = await refresh_access_token(db, refresh_token)

    return TokenResponse(
        access_token=access_token,
        expires_in=_ACCESS_EXPIRES_IN,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout_api():
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response)
    return response