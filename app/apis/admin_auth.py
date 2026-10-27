# 담당자 C: 관리자, 인증/인가 및 성능 파트
# REQ-USER-004 회원 목록 조회 (검색, 필터, 관리자용)
# REQ-USER-005 회원 권한 변경 (대기자/스태프/어드민)
# NFR-USER-001 인증/인가 (JWT 발급, Access/Refresh 토큰, HttpOnly 쿠키)
# NFR-USER-003 API 성능 (최대 3초 이내 응답)

import logging
import time

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.databases import async_get_db
# 인증·인가는 공통 모듈 사용 (require_staff는 기존 import 경로 호환용으로 함께 노출)
from app.core.security import require_admin, require_staff  # noqa: F401
from app.models.enums import Department, Gender, Role
from app.models.user import User

# ============================================================
# 스키마
# ============================================================

class UserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    name: str | None
    department: Department
    gender: Gender
    phone_number: str | None  # 숫자만 반환
    is_active: bool
    role: Role


class UserListResponse(BaseModel):
    items: list[UserListItem]
    total: int
    page: int
    size: int


class RoleUpdateRequest(BaseModel):
    role: Role  # PENDING / STAFF / ADMIN 외의 값은 자동으로 422


class RoleUpdateResponse(BaseModel):
    id: int
    role: Role
    message: str


# ============================================================
# REQ-USER-004: 회원 목록 조회
# ============================================================

async def list_users(
    db: AsyncSession,
    search: str | None,
    department: Department | None,
    page: int,
    size: int,
) -> tuple[list[User], int]:
    conditions = []

    if search:
        keyword = search.strip()
        if keyword:
            # 이메일 또는 이름 부분 일치 (%, _ 는 이스케이프)
            conditions.append(
                or_(
                    User.email.icontains(keyword, autoescape=True),
                    User.name.icontains(keyword, autoescape=True),
                )
            )

    if department is not None:
        conditions.append(User.department == department)

    # 페이지네이션: 전체 개수와 현재 페이지 목록만 조회
    total = await db.scalar(select(func.count()).select_from(User).where(*conditions))

    result = await db.execute(
        select(User)
        .where(*conditions)
        .order_by(User.id)
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(result.scalars().all()), total or 0


# ============================================================
# REQ-USER-005: 회원 권한 변경
# ============================================================

async def update_user_role(db: AsyncSession, user_id: int, role: Role) -> User:
    user = await db.get(User, user_id)  # PK 조회 1회
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 회원을 찾을 수 없습니다.",
        )

    if user.role != role:  # 같은 권한이면 불필요한 UPDATE 생략
        user.role = role
        await db.commit()
        await db.refresh(user)

    return user


# ============================================================
# 관리자 API
# ============================================================

router = APIRouter(prefix="/users", tags=["회원 관리"])


@router.get(
    "",
    summary="회원 목록 조회 (REQ-USER-004)",
    response_model=UserListResponse,
)
async def list_users_handler(
    search: str | None = Query(default=None, max_length=50, description="이메일 또는 이름 검색"),
    department: Department | None = Query(default=None, description="부서 필터"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(async_get_db),
):
    users, total = await list_users(db, search, department, page, size)
    return UserListResponse(
        items=[UserListItem.model_validate(u) for u in users],
        total=total,
        page=page,
        size=size,
    )


@router.patch(
    "/{user_id}/role",
    summary="회원 권한 변경 (REQ-USER-005)",
    response_model=RoleUpdateResponse,
)
async def update_user_role_handler(
    user_id: int,
    body: RoleUpdateRequest,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(async_get_db),
):
    user = await update_user_role(db, user_id, body.role)
    return RoleUpdateResponse(
        id=user.id,
        role=user.role,
        message="회원 권한이 변경되었습니다.",
    )


# ============================================================
# NFR-USER-003: API 성능 측정
# ============================================================

logger = logging.getLogger("api.performance")
SLOW_API_THRESHOLD_SEC = 3.0


def register_performance_middleware(app: FastAPI) -> None:
    """main.py에서 app 생성 후 한 번 호출한다."""

    @app.middleware("http")
    async def measure_response_time(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        # Swagger나 테스트에서 3초 이내인지 바로 확인할 수 있음
        response.headers["X-Process-Time"] = f"{elapsed:.3f}"
        if elapsed > SLOW_API_THRESHOLD_SEC:
            logger.warning(
                "느린 API (3초 초과): %s %s %.3fs",
                request.method,
                request.url.path,
                elapsed,
            )
        return response