# 담당자 D: 진료기록 상세 조회
# REQ-MDR-003 진료기록 상세 조회  GET /api/v1/medical-records/{record_id}
# NFR-MDR-001 API 성능 (최대 3초 이내 응답)
#
# - 라우터에는 /api/v1 prefix를 붙이지 않는다. main.py의 include_router(prefix="/api/v1")에서 공통 적용한다.
# - 인증·인가는 app/core/security.py의 require_staff를 그대로 재사용한다. (STAFF·ADMIN 허용, PENDING은 403, 조회는 부서와 무관)
# - 에러 응답은 공통 형식 {"detail": "..."} (HTTPException)만 사용한다.

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_serializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.databases import async_get_db
from app.core.security import require_staff
from app.models.medical_record import MedicalRecord #담당자 D
from app.models.patient import Patient
from app.models.user import User
from app.models.xray_image import XrayImage

RECORD_NOT_FOUND_MESSAGE = "해당 진료기록을 찾을 수 없습니다."

# DB에 상대 경로로 저장된 이미지(예: xray/a.jpg)를 응답 URL로 바꿀 때 붙이는 prefix.
# main.py에서 media 폴더를 "/media"로 마운트하고 있다.
MEDIA_URL_PREFIX = "/media"


# ============================================================
# 스키마
# ============================================================

class MedicalRecordDetailResponse(BaseModel):
    record_id: int
    patient_id: int
    patient_name: str
    chart_number: str
    symptoms: str
    xray_image_url: str | None
    created_at: datetime
    updated_at: datetime | None

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime | None) -> str | None:
        # DB의 DateTime 컬럼은 시간대 정보가 없다(naive).
        # 저장값을 UTC로 보고 "2026-10-27T02:00:00Z" 형식으로 반환한다.
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================
# DB 접근
# ============================================================

def build_xray_image_url(image_url: str | None) -> str | None:
    """DB의 image_url을 응답용 URL로 변환한다. 이미지가 없으면 None."""
    if not image_url:
        return None
    # 이미 URL(http...) 또는 절대 경로(/media/...)면 그대로 사용
    if image_url.startswith(("http://", "https://", "/")):
        return image_url
    return f"{MEDIA_URL_PREFIX}/{image_url}"


async def get_record_detail(
    db: AsyncSession,
    record_id: int,
) -> MedicalRecordDetailResponse | None:
    # 진료기록 + 환자 이름 + 가장 최근 X-Ray 이미지를 쿼리 1번으로 조회한다.
    latest_image_url = (
        select(XrayImage.image_url)
        .where(XrayImage.record_id == MedicalRecord.id)
        .order_by(XrayImage.id.desc())
        .limit(1)
        .correlate(MedicalRecord)
        .scalar_subquery()
    )

    stmt = (
        select(MedicalRecord, Patient.name, latest_image_url)
        .join(Patient, Patient.id == MedicalRecord.patient_id)
        .where(MedicalRecord.id == record_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None

    record, patient_name, image_url = row
    return MedicalRecordDetailResponse(
        record_id=record.id,
        patient_id=record.patient_id,
        patient_name=patient_name,
        chart_number=record.chart_number,
        symptoms=record.symptoms,
        xray_image_url=build_xray_image_url(image_url),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# ============================================================
# API
# ============================================================

router = APIRouter(tags=["진료기록"])


@router.get(
    "/medical-records/{record_id}",
    summary="진료기록 상세 조회 (REQ-MDR-003)",
    response_model=MedicalRecordDetailResponse,
)
async def get_medical_record_handler(
    record_id: int,
    _user: User = Depends(require_staff),
    db: AsyncSession = Depends(async_get_db),
):
    detail = await get_record_detail(db, record_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=RECORD_NOT_FOUND_MESSAGE,
        )
    return detail
