# 공통 입력 검증 (회원가입, 마이페이지 등에서 함께 사용)
import re

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