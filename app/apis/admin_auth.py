# 담당자 C: 관리자, 인증/인가 및 성능 파트
# REQ-USER-004 회원 목록 조회 (검색, 필터, 관리자용)
# REQ-USER-005 회원 권한 변경 (대기자/스태프/어드민)
# NFR-USER-001 인증/인가 (JWT 발급, Access/Refresh 토큰, HttpOnly 쿠키)
# NFR-USER-003 API 성능 (최대 3초 이내 응답)

import logging
import time
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db.databases import async_get_db
from app.models.enums import Department, Gender, Role
from app.models.user import User


# ============================================================
# NFR-USER-001: JWT 발급 / 검증
# ============================================================

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"

bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _create_token(user_id: int, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "user_id": user_id,  # 식별 정보는 user_id만 저장
        "type": token_type,  # access / refresh 구분 (Refresh Token으로 API 호출 방지)
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: int) -> str:
    # 30분
    return _create_token(
        user_id, ACCESS_TOKEN_TYPE, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(user_id: int) -> str:
    # 7일
    return _create_token(
        user_id, REFRESH_TOKEN_TYPE, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str, expected_type: str) -> int:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != expected_type:
            raise unauthorized()
        return int(payload["user_id"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        # 만료(ExpiredSignatureError)도 InvalidTokenError의 하위 클래스 → 401 → 재발급/재로그인 유도
        raise unauthorized()


# ============================================================
# NFR-USER-001: Refresh Token HttpOnly 쿠키
# ============================================================

def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,  # JavaScript에서 읽을 수 없음
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    # 설정할 때와 같은 이름·경로·속성으로 지워야 브라우저에서 삭제됨
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )


# ============================================================
# NFR-USER-001: 현재 사용자 확인 (인증) / 권한 검사 (인가)
# ============================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(async_get_db),
) -> User:
    if credentials is None:
        raise unauthorized()

    user_id = decode_token(credentials.credentials, ACCESS_TOKEN_TYPE)

    # PK 조회 1회. 탈퇴한 회원의 기존 토큰도 여기서 차단 (공통 정책: 401)
    user = await db.get(User, user_id)
    if user is None:
        raise unauthorized()
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )
    return user


def require_roles(*allowed: Role):
    """허용된 권한만 통과시키는 의존성 팩토리."""

    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="접근 권한이 없습니다.",
            )
        return current_user

    return checker


# role은 JWT에 넣지 않고 매 요청마다 DB에서 읽으므로 권한 변경이 바로 적용된다.
require_admin = require_roles(Role.ADMIN)               # 시스템 관리 (회원 관리 등)
require_staff = require_roles(Role.STAFF, Role.ADMIN)   # 흉부 X-ray 읽기/쓰기/수정 (PENDING 차단)


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

router = APIRouter(prefix="/api/v1/users", tags=["회원 관리"])


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