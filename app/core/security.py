# 공통 인증·인가 모듈 (NFR-USER-001)
# 비밀번호 해시, JWT 발급·검증, Refresh Token 쿠키, 현재 사용자 확인, 권한 검사

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db.databases import async_get_db
from app.models.enums import Department, Role
from app.models.user import User


# ============================================================
# 비밀번호 해시 (Argon2)
# ============================================================

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


# ============================================================
# JWT 발급 / 검증
# ============================================================

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

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
    return _create_token(
        user_id, ACCESS_TOKEN_TYPE, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(user_id: int) -> str:
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
        # 만료(ExpiredSignatureError)도 InvalidTokenError의 하위 클래스 → 401
        raise unauthorized()


# ============================================================
# Refresh Token HttpOnly 쿠키
# ============================================================

REFRESH_COOKIE_NAME = "refresh_token"
# 라우터 prefix가 아니라 브라우저 기준 실제 경로 (main.py의 /api/v1 + /auth)
REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
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
# 현재 사용자 확인 (인증) / 권한 검사 (인가)
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
require_staff = require_roles(Role.STAFF, Role.ADMIN)   # 환자·진료기록 조회/수정/삭제 (PENDING 차단)


async def require_medical_staff(current_user: User = Depends(require_staff)) -> User:
    """환자·진료기록 등록용: STAFF/ADMIN 이면서 의료 부서(MEDICAL)인 회원만 허용."""
    if current_user.department != Department.MEDICAL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="의료진만 등록할 수 있습니다.",
        )
    return current_user