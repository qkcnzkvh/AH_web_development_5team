# 담당자 A: 환자 등록·수정·삭제 파트 (5일차 통합 명세서 4장, 7장, 8장)
# REQ-PTNT-001 환자 정보 등록
# REQ-PTNT-004 환자 정보 수정
# REQ-PTNT-005 환자 정보 삭제
#
# - 라우터에는 /patients만 작성하고, /api/v1은 main.py에서 API_PREFIX로 등록한다.
# - 인증·인가는 공통 app/core/security.py 사용
#   등록: require_medical_staff (STAFF·ADMIN + department = MEDICAL)
#   수정·삭제: require_staff (STAFF·ADMIN, PENDING은 403)
# - 응답은 공통 PatientResponse(app/schemas/patient.py) 사용

import logging
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.databases import async_get_db
from app.core.security import require_medical_staff, require_staff
from app.core.validators import normalize_phone
from app.models.enums import Gender
from app.models.medical_record import MedicalRecord
from app.models.patient import Patient
from app.models.user import User
from app.models.xray_image import XrayImage
from app.schemas.patient import PatientResponse

logger = logging.getLogger(__name__)

# patients.age 컬럼은 SMALLINT, 사람 나이 기준으로 0~150 범위만 허용
AGE_MIN = 0
AGE_MAX = 150

PATIENT_NOT_FOUND = "환자를 찾을 수 없습니다."
NOTHING_TO_UPDATE = "수정할 항목이 없습니다."

# 프로젝트 루트 (main.py의 BASE_DIR과 같은 위치). /media/... URL을 실제 파일 경로로 바꿀 때 사용
BASE_DIR = FilePath(__file__).resolve().parent.parent.parent
MEDIA_DIR = BASE_DIR / "media"

# 프론트(male/female)와 DB Enum(M/F) 모두 받을 수 있게 변환
_GENDER_ALIASES = {
    "male": Gender.M,
    "m": Gender.M,
    "female": Gender.F,
    "f": Gender.F,
}


# ───────────────────────── 요청 스키마 ─────────────────────────

class PatientCreateRequest(BaseModel):
    """환자 등록 (이름·나이·성별·연락처 모두 필수)"""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=30)
    age: int = Field(ge=AGE_MIN, le=AGE_MAX)
    gender: Gender  # DB는 NULL 허용이지만 등록 시에는 필수
    phone_number: str

    @field_validator("gender", mode="before")
    @classmethod
    def map_gender(cls, value):
        if isinstance(value, str):
            return _GENDER_ALIASES.get(value.strip().lower(), value.strip().upper())
        return value

    @field_validator("phone_number")
    @classmethod
    def check_phone_number(cls, value: str) -> str:
        # 하이픈 유무와 관계없이 받아서 숫자만 저장 (010-1234-5678 → 01012345678)
        return normalize_phone(value)


class PatientUpdateRequest(BaseModel):
    """환자 정보 부분 수정(Partial). 이름과 연락처만 수정할 수 있다."""

    # 나이·성별 등 허용되지 않은 필드는 무시
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    name: str | None = Field(default=None, min_length=1, max_length=30)
    phone_number: str | None = None

    @field_validator("phone_number")
    @classmethod
    def check_phone_number(cls, value: str | None) -> str | None:
        return value if value is None else normalize_phone(value)


# ───────────────────────── 레포지토리 ─────────────────────────

async def find_patient_by_id(db: AsyncSession, patient_id: int) -> Patient | None:
    return await db.get(Patient, patient_id)  # PK 조회 1회


async def find_xray_image_urls(db: AsyncSession, patient_id: int) -> list[str]:
    # 환자의 진료기록에 연결된 X-Ray 이미지 경로를 한 번의 쿼리로 조회
    result = await db.execute(
        select(XrayImage.image_url)
        .join(MedicalRecord, XrayImage.record_id == MedicalRecord.id)
        .where(MedicalRecord.patient_id == patient_id)
    )
    return list(result.scalars().all())


async def save_patient(db: AsyncSession, patient: Patient) -> Patient:
    db.add(patient)
    await db.commit()
    await db.refresh(patient)  # DB 기본값(created_at, updated_at)을 다시 읽어옴
    return patient


async def delete_patient_row(db: AsyncSession, patient: Patient) -> None:
    # Hard Delete: FK ON DELETE CASCADE로 medical_records → xray_images, ai_analysis_results도 함께 삭제
    await db.delete(patient)
    await db.commit()


# ───────────────────────── 서비스 ─────────────────────────

def _media_url_to_path(image_url: str) -> FilePath | None:
    """/media/xray/{파일명} → {프로젝트}/media/xray/{파일명}. media 폴더 밖을 가리키면 None."""
    path = (BASE_DIR / image_url.lstrip("/")).resolve()
    if not path.is_relative_to(MEDIA_DIR.resolve()):
        return None
    return path


def _delete_image_files(image_urls: list[str]) -> None:
    # TODO: 담당자 C의 공통 이미지 삭제 함수가 머지되면 그 함수로 교체
    for image_url in image_urls:
        path = _media_url_to_path(image_url)
        if path is None:
            logger.warning("media 폴더 밖의 이미지 경로라 삭제하지 않음: %s", image_url)
            continue
        try:
            path.unlink(missing_ok=True)  # 파일이 이미 없으면 무시
        except OSError:
            # DB 삭제는 이미 끝났으므로 응답은 성공으로 두고 로그만 남김
            logger.warning("X-Ray 이미지 파일 삭제 실패: %s", path, exc_info=True)


async def get_patient_or_404(db: AsyncSession, patient_id: int) -> Patient:
    patient = await find_patient_by_id(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PATIENT_NOT_FOUND)
    return patient


async def create_patient(db: AsyncSession, body: PatientCreateRequest) -> Patient:
    patient = Patient(
        name=body.name,
        age=body.age,
        gender=body.gender,
        phone=body.phone_number,  # API 필드 phone_number → DB 컬럼 phone
    )
    return await save_patient(db, patient)


async def update_patient(db: AsyncSession, patient_id: int, body: PatientUpdateRequest) -> Patient:
    # 보낸 필드만 수정 (값이 없거나 null인 필드는 기존 값 유지)
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=NOTHING_TO_UPDATE)

    patient = await get_patient_or_404(db, patient_id)

    if "name" in fields:
        patient.name = fields["name"]
    if "phone_number" in fields:
        patient.phone = fields["phone_number"]

    return await save_patient(db, patient)


async def delete_patient(db: AsyncSession, patient_id: int) -> None:
    patient = await get_patient_or_404(db, patient_id)

    # CASCADE로 DB 행이 사라지기 전에 이미지 경로를 먼저 모아 둔다
    image_urls = await find_xray_image_urls(db, patient_id)
    await delete_patient_row(db, patient)

    # DB CASCADE는 실제 파일을 지우지 않으므로 커밋 후 직접 삭제
    _delete_image_files(image_urls)


# ───────────────────────── 라우터 ─────────────────────────

router = APIRouter(prefix="/patients", tags=["환자 관리"])


@router.post(
    "",
    summary="환자 정보 등록 (REQ-PTNT-001)",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_patient_handler(
    body: PatientCreateRequest,
    _user: User = Depends(require_medical_staff),
    db: AsyncSession = Depends(async_get_db),
):
    return await create_patient(db, body)


@router.patch(
    "/{patient_id}",
    summary="환자 정보 수정 (REQ-PTNT-004)",
    response_model=PatientResponse,
)
async def update_patient_handler(
    body: PatientUpdateRequest,
    patient_id: int = Path(ge=1, description="환자 고유 ID"),
    _user: User = Depends(require_staff),
    db: AsyncSession = Depends(async_get_db),
):
    return await update_patient(db, patient_id, body)


@router.delete(
    "/{patient_id}",
    summary="환자 정보 삭제 (REQ-PTNT-005)",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_patient_handler(
    patient_id: int = Path(ge=1, description="환자 고유 ID"),
    _user: User = Depends(require_staff),
    db: AsyncSession = Depends(async_get_db),
):
    await delete_patient(db, patient_id)
