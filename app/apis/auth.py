import asyncio
import re
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db.databases import async_get_db
from app.core.security import hash_password, verify_password  # Argon2 (공통 모듈)
from app.models.enums import Department, Gender, Role
from app.models.user import User


# ============================================================
# 공통 입력 검증
# ============================================================

PASSWORD_ERROR_MESSAGE = (
    "비밀번호는 8~20자이며 대문자, 소문자, 특수문자를 각각 1개 이상 포함해야 합니다."
)
PHONE_ERROR_MESSAGE = "전화번호는 01012345678 형식(숫자 10~11자리)이어야 합니다."

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 20

_PHONE_PATTERN = re.compile(r"01[016789][0-9]{7,8}")


def normalize_phone(value: str) -> str:
    digits = re.sub(r"[^0-9]", "", value)

    if not _PHONE_PATTERN.fullmatch(digits):
        raise ValueError(PHONE_ERROR_MESSAGE)

    return digits


def validate_password(value: str) -> str:
    if (
        not PASSWORD_MIN_LENGTH <= len(value) <= PASSWORD_MAX_LENGTH
        or not re.search(r"[A-Z]", value)
        or not re.search(r"[a-z]", value)
        or not re.search(r"[^A-Za-z0-9]", value)
    ):
        raise ValueError(PASSWORD_ERROR_MESSAGE)

    return value


# ============================================================
# JWT 및 현재 로그인 사용자 조회
# ============================================================

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _create_token(
    user_id: int,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)

    payload = {
        "user_id": user_id,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_access_token(user_id: int) -> str:
    return _create_token(
        user_id,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        user_id,
        REFRESH_TOKEN_TYPE,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: str) -> int:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        if payload.get("type") != expected_type:
            raise _unauthorized()

        return int(payload["user_id"])

    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise _unauthorized()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(async_get_db),
) -> User:
    if credentials is None:
        raise _unauthorized()

    user_id = decode_token(credentials.credentials, ACCESS_TOKEN_TYPE)
    user = await get_by_id(db, user_id)

    # 탈퇴한 회원의 기존 토큰 차단 (공통 정책: 401로 통일)
    if user is None:
        raise _unauthorized()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )

    return user


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
        raise _unauthorized()

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
    prefix="/api/v1/auth",
    tags=["auth"],
)

_ACCESS_EXPIRES_IN = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


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

    _set_refresh_cookie(response, refresh_token)

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
        raise _unauthorized()

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
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    return response