# 환자 응답 스키마 (5일차 명세서 2.4)
# 환자 등록·수정·목록 항목·상세 조회 응답에 모두 같은 PatientResponse를 사용한다.

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Gender
from app.schemas.common import UtcDateTime


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    age: int
    gender: Gender | None  # DB 스키마상 NULL 허용
    phone_number: str = Field(validation_alias="phone")  # DB 컬럼 phone → API 필드 phone_number
    created_at: UtcDateTime
    updated_at: UtcDateTime | None


class PatientListResponse(BaseModel):
    """목록 조회 공통 구조 (User API 회원 목록과 동일: items, total, page, size)"""

    items: list[PatientResponse]
    total: int
    page: int
    size: int
