# 마이페이지(담당자 B) API 통합 파일
# 대상 유저는 URL이 아니라 토큰(get_current_user)으로 결정하므로 본인 정보만 다룰 수 있다.
# PENDING(대기자)도 마이페이지는 이용할 수 있으므로 권한(role) 검사는 하지 않는다.
# REQ-USER-006 조회, REQ-USER-007 정보 수정, REQ-USER-008 비밀번호 변경, REQ-USER-009 회원 탈퇴

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db.databases import async_get_db
from app.core.security import get_current_user, hash_password, verify_password
from app.core.validators import normalize_phone, validate_password
from app.models.enums import Department, Gender, Role
from app.models.user import User

PHONE_NUMBER_CONFLICT = "이미 사용 중인 휴대폰 번호입니다."

# 로그아웃과 같은 이름·경로·속성으로 지워야 브라우저에서 쿠키가 삭제됨
REFRESH_TOKEN_COOKIE = "refresh_token"
REFRESH_TOKEN_COOKIE_PATH = "/api/v1/auth"


# ───────────────────────── 스키마 ─────────────────────────

class MyPageResponse(BaseModel):
    """마이페이지 조회 응답. 비밀번호(해시 포함)는 절대 노출하지 않는다."""

    # User ORM 객체를 그대로 응답 모델로 변환할 수 있게 함
    model_config = ConfigDict(from_attributes=True)

    name: str | None
    email: str | None
    department: Department
    gender: Gender
    phone_number: str | None  # 숫자만 저장·반환 (01012345678)
    role: Role


class MyPageUpdateRequest(BaseModel):
    """회원 정보 부분 수정(Partial). 부서와 휴대폰 번호만 수정할 수 있다."""

    # 허용되지 않은 추가 필드는 무시
    model_config = ConfigDict(extra="ignore")

    department: Department | None = None
    phone_number: str | None = None

    @field_validator("phone_number")
    @classmethod
    def check_phone_number(cls, value: str | None) -> str | None:
        # 하이픈 유무와 관계없이 받아서 DB에는 숫자만 저장 (01012345678)
        return value if value is None else normalize_phone(value)


class PasswordChangeRequest(BaseModel):
    """비밀번호 변경. 새 비밀번호는 회원가입과 같은 규칙으로 검증한다."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=20)

    @field_validator("new_password")
    @classmethod
    def check_new_password(cls, value: str) -> str:
        return validate_password(value)


# ───────────────────────── 레포지토리 ─────────────────────────

async def get_user_by_phone_number(db: AsyncSession, phone_number: str) -> User | None:
    stmt = select(User).where(User.phone_number == phone_number)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def save_user(db: AsyncSession, user: User) -> User:
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user: User) -> None:
    # Hard Delete: 업로드한 xray_images는 FK(ondelete="SET NULL")에 따라 uploader_id만 NULL이 됨
    await db.delete(user)
    await db.commit()


# ───────────────────────── 서비스 ─────────────────────────

async def update_my_info(db: AsyncSession, user: User, body: MyPageUpdateRequest) -> User:
    # 보낸 필드만 수정 (값이 없거나 null인 필드는 기존 값 유지)
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수정할 항목이 없습니다.",
        )

    new_phone_number = fields.get("phone_number")
    if new_phone_number and new_phone_number != user.phone_number:
        owner = await get_user_by_phone_number(db, new_phone_number)
        if owner is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PHONE_NUMBER_CONFLICT)

    for key, value in fields.items():
        setattr(user, key, value)

    try:
        return await save_user(db, user)
    except IntegrityError:
        # 중복 검사 직후 다른 요청이 같은 번호를 저장한 경우 (DB unique 제약)
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PHONE_NUMBER_CONFLICT)


async def change_password(db: AsyncSession, user: User, body: PasswordChangeRequest) -> None:
    # Argon2는 CPU를 쓰는 동기 함수이므로 스레드로 넘겨 이벤트 루프가 막히지 않게 함
    password_ok = bool(user.hashed_password) and await asyncio.to_thread(
        verify_password,
        body.current_password,
        user.hashed_password,
    )
    if not password_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="기존 비밀번호가 일치하지 않습니다.",
        )
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="새 비밀번호는 기존 비밀번호와 달라야 합니다.",
        )

    user.hashed_password = await asyncio.to_thread(hash_password, body.new_password)
    await save_user(db, user)


async def withdraw(db: AsyncSession, user: User) -> None:
    await delete_user(db, user)


# ───────────────────────── 라우터 ─────────────────────────

router = APIRouter(prefix="/users", tags=["마이페이지"])


@router.get(
    "/me",
    summary="마이페이지 조회 (REQ-USER-006)",
    response_model=MyPageResponse,
)
async def get_my_page_handler(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.patch(
    "/me",
    summary="회원 정보 수정 (REQ-USER-007)",
    response_model=MyPageResponse,
)
async def update_my_info_handler(
    body: MyPageUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db),
):
    return await update_my_info(db, current_user, body)


@router.patch(
    "/me/password",
    summary="비밀번호 변경 (REQ-USER-008)",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def change_password_handler(
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db),
):
    await change_password(db, current_user, body)


@router.delete(
    "/me",
    summary="회원 탈퇴 (REQ-USER-009)",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def withdraw_handler(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db),
):
    await withdraw(db, current_user)
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE,
        path=REFRESH_TOKEN_COOKIE_PATH,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )