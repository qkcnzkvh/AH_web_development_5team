# app/apis/practice_apis.py
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator

user_list = [
    {
        "id": 1,
        "name": "홍길동",
        "age": 24,
        "email": "gildong24@example.com",
        "password": "Password1234!!",
    },
    {
        "id": 2,
        "name": "장문복",
        "age": 21,
        "email": "moonluck12@example.com",
        "password": "Check1321!",
    },
    {
        "id": 3,
        "name": "임우진",
        "age": 31,
        "email": "limousine33@example.com",
        "password": "lwsPAssword12@",
    },
]

router = APIRouter(prefix="/practice_api", tags=["practice_api"])

# ---------------------------------------------------------------------------
# 검증 규칙
# ---------------------------------------------------------------------------
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MIN_AGE = 14


def _validate_password(value: str) -> str:
    """대문자·소문자·특수문자 각 1개 이상 필수 (길이 8~20은 Field에서 검증)."""
    if not re.search(r"[A-Z]", value):
        raise ValueError("비밀번호에는 대문자가 1개 이상 포함되어야 합니다.")
    if not re.search(r"[a-z]", value):
        raise ValueError("비밀번호에는 소문자가 1개 이상 포함되어야 합니다.")
    if not re.search(r"[^A-Za-z0-9]", value):
        raise ValueError("비밀번호에는 특수문자가 1개 이상 포함되어야 합니다.")
    return value


def _validate_email(value: str) -> str:
    if not EMAIL_PATTERN.fullmatch(value):
        raise ValueError("올바른 이메일 형식이 아닙니다.")
    return value


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------
class UserResponse(BaseModel):
    """응답용 스키마. password는 노출하지 않는다."""

    id: int
    name: str
    age: int
    email: str


class UserCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=10)
    age: int = Field(ge=MIN_AGE)
    email: str = Field(max_length=30)
    password: str = Field(min_length=8, max_length=20)

    _check_email = field_validator("email")(_validate_email)
    _check_password = field_validator("password")(_validate_password)


class UserUpdateRequest(BaseModel):
    """모든 항목이 선택 입력. 입력된 항목만 수정에 반영한다."""

    age: Optional[int] = Field(default=None, ge=MIN_AGE)
    email: Optional[str] = Field(default=None, max_length=30)
    password: Optional[str] = Field(default=None, min_length=8, max_length=20)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: Optional[str]) -> Optional[str]:
        return value if value is None else _validate_email(value)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: Optional[str]) -> Optional[str]:
        return value if value is None else _validate_password(value)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
# 삭제 후에도 id가 재사용되지 않도록 별도 카운터로 관리한다.
_next_id = max((u["id"] for u in user_list), default=0) + 1


def _issue_id() -> int:
    global _next_id
    issued = _next_id
    _next_id += 1
    return issued


def _find_user(user_id: int) -> dict:
    for user in user_list:
        if user["id"] == user_id:
            return user
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="존재하지 않는 회원입니다.")


def _ensure_email_available(email: str, exclude_id: Optional[int] = None) -> None:
    """이메일 중복 검사 (대소문자 구분 없이, 수정 시에는 본인 제외)."""
    for user in user_list:
        if user["id"] != exclude_id and user["email"].lower() == email.lower():
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일입니다."
            )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@router.get("/users", response_model=list[UserResponse])
def get_users():
    """모든 회원의 정보를 목록으로 조회"""
    return user_list


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int):
    """특정 회원의 정보를 조회 (없으면 404)"""
    return _find_user(user_id)


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreateRequest):
    """회원 추가 (id는 자동 증가)"""
    _ensure_email_available(body.email)

    new_user = {"id": _issue_id(), **body.model_dump()}
    user_list.append(new_user)
    return new_user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, body: UserUpdateRequest):
    """회원 정보 수정 (입력된 항목만 반영, 모두 미입력 시 400)"""
    user = _find_user(user_id)

    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="수정할 항목(age, email, password)을 하나 이상 입력해야 합니다.",
        )

    if "email" in changes:
        _ensure_email_available(changes["email"], exclude_id=user_id)

    user.update(changes)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int):
    """회원 삭제 (없으면 404)"""
    user = _find_user(user_id)
    user_list.remove(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
