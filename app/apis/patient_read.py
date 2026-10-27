# 담당자 B: 환자 조회 파트 (5일차 통합 명세서 5장, 6장)
# REQ-PTNT-002 환자 목록 조회 (이름 검색, 성별·나이 범위 필터, 페이지네이션)
# REQ-PTNT-003 환자 정보 상세 조회
#
# - 라우터에는 /patients만 작성하고, /api/v1은 main.py에서 API_PREFIX로 등록한다.
# - 인증·인가는 공통 app/core/security.py의 require_staff 사용 (STAFF·ADMIN, PENDING은 403)
#   조회는 부서(department)와 관계없이 허용한다.
# - 응답은 공통 PatientResponse(app/schemas/patient.py) 사용

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.databases import async_get_db
from app.core.security import require_staff
from app.models.enums import Gender
from app.models.patient import Patient
from app.models.user import User
from app.schemas.patient import PatientListResponse, PatientResponse

# patients.age 컬럼은 SMALLINT, 사람 나이 기준으로 0~150 범위만 허용
AGE_MIN = 0
AGE_MAX = 150

PATIENT_NOT_FOUND = "환자를 찾을 수 없습니다."

# 프론트(male/female)와 DB Enum(M/F) 모두 받을 수 있게 변환
_GENDER_ALIASES = {
    "male": Gender.M,
    "m": Gender.M,
    "female": Gender.F,
    "f": Gender.F,
}


# ───────────────────────── 요청 스키마 ─────────────────────────

class PatientListQuery(BaseModel):
    """환자 목록 조회 쿼리 파라미터 (FastAPI Query Parameter Model)."""

    # 정의되지 않은 쿼리 파라미터는 User API 회원 목록과 동일하게 무시
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=30, description="이름 부분 검색")
    gender: Gender | None = Field(default=None, description="성별 필터 (M / F, male / female 허용)")
    min_age: int | None = Field(default=None, ge=AGE_MIN, le=AGE_MAX, description="최소 나이 (이상)")
    max_age: int | None = Field(default=None, ge=AGE_MIN, le=AGE_MAX, description="최대 나이 (이하)")
    page: int = Field(default=1, ge=1, description="페이지 번호")
    size: int = Field(default=10, ge=1, le=100, description="페이지당 조회 수")

    @field_validator("gender", mode="before")
    @classmethod
    def map_gender(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:  # 프론트의 '성별 전체' 선택 시 빈 문자열 → 필터 없음
                return None
            return _GENDER_ALIASES.get(value.lower(), value.upper())
        return value

    @model_validator(mode="after")
    def check_age_range(self):
        if self.min_age is not None and self.max_age is not None and self.min_age > self.max_age:
            raise ValueError("최소 나이는 최대 나이보다 클 수 없습니다.")
        return self


# ───────────────────────── 레포지토리 ─────────────────────────

def _build_conditions(query: PatientListQuery) -> list:
    conditions = []
    if query.name:
        # 부분 일치 검색, %·_ 는 일반 문자로 처리(autoescape)
        conditions.append(Patient.name.contains(query.name, autoescape=True))
    if query.gender is not None:
        conditions.append(Patient.gender == query.gender)
    if query.min_age is not None:
        conditions.append(Patient.age >= query.min_age)
    if query.max_age is not None:
        conditions.append(Patient.age <= query.max_age)
    return conditions


async def find_patients(db: AsyncSession, query: PatientListQuery) -> tuple[list[Patient], int]:
    conditions = _build_conditions(query)

    # 페이지네이션: 전체 개수와 현재 페이지 목록만 조회
    total = await db.scalar(select(func.count()).select_from(Patient).where(*conditions))

    result = await db.execute(
        select(Patient)
        .where(*conditions)
        .order_by(Patient.id.desc())  # 최근 등록 환자부터
        .offset((query.page - 1) * query.size)
        .limit(query.size)
    )
    return list(result.scalars().all()), total or 0


async def find_patient_by_id(db: AsyncSession, patient_id: int) -> Patient | None:
    return await db.get(Patient, patient_id)  # PK 조회 1회


# ───────────────────────── 서비스 ─────────────────────────

async def get_patient_list(db: AsyncSession, query: PatientListQuery) -> PatientListResponse:
    patients, total = await find_patients(db, query)
    return PatientListResponse(
        items=[PatientResponse.model_validate(p) for p in patients],
        total=total,
        page=query.page,
        size=query.size,
    )


async def get_patient_detail(db: AsyncSession, patient_id: int) -> Patient:
    patient = await find_patient_by_id(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PATIENT_NOT_FOUND)
    return patient


# ───────────────────────── 라우터 ─────────────────────────

router = APIRouter(prefix="/patients", tags=["환자 관리"])


@router.get(
    "",
    summary="환자 목록 조회 (REQ-PTNT-002)",
    response_model=PatientListResponse,
)
async def get_patient_list_handler(
    query: PatientListQuery = Query(),
    _user: User = Depends(require_staff),
    db: AsyncSession = Depends(async_get_db),
):
    return await get_patient_list(db, query)


@router.get(
    "/{patient_id}",
    summary="환자 정보 상세 조회 (REQ-PTNT-003)",
    response_model=PatientResponse,
)
async def get_patient_detail_handler(
    patient_id: int = Path(ge=1, description="환자 고유 ID"),
    _user: User = Depends(require_staff),
    db: AsyncSession = Depends(async_get_db),
):
    return await get_patient_detail(db, patient_id)
