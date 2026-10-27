# 담당자 C: 진료기록 등록·목록 조회 (5일차 통합 명세서 9장, 10장)
# REQ-MDR-001 진료기록 등록         POST /api/v1/medical-records
# REQ-MDR-002 환자별 진료기록 목록  GET  /api/v1/patients/{patient_id}/medical-records

from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.databases import async_get_db
from app.core.security import require_medical_staff, require_staff
from app.core.storage import save_xray_file
from app.models import MedicalRecord, Patient, User, XrayImage
from app.schemas.common import UtcDateTime

# 라우터 prefix 없이 전체 경로를 직접 적는다. (/patients/{patient_id}/medical-records 때문)
# /api/v1은 main.py에서 include_router(..., prefix=API_PREFIX)로 적용한다.
router = APIRouter(tags=["진료기록"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
SYMPTOMS_PREVIEW_LEN = 100
CHART_NUMBER_MAX_LEN = 50  # medical_records.chart_number String(50)

PATIENT_NOT_FOUND = "환자를 찾을 수 없습니다."
CHART_NUMBER_CONFLICT = "이미 등록된 차트 번호입니다."


# ---------- 스키마 ----------
class MedicalRecordCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    chart_number: str
    symptoms: str
    created_at: UtcDateTime
    updated_at: UtcDateTime | None = None


class MedicalRecordListItem(BaseModel):
    id: int
    patient_id: int
    chart_number: str
    symptoms: str
    created_at: UtcDateTime


class MedicalRecordListResponse(BaseModel):
    items: list[MedicalRecordListItem]
    total: int
    page: int
    size: int


def _preview_symptoms(symptoms: str) -> str:
    """100자를 넘으면 앞 100자 + '…'으로 반환한다."""
    if len(symptoms) <= SYMPTOMS_PREVIEW_LEN:
        return symptoms
    return symptoms[:SYMPTOMS_PREVIEW_LEN] + "…"


# ---------- REQ-MDR-001 진료기록 등록 ----------
@router.post(
    "/medical-records",
    summary="진료기록 등록 (REQ-MDR-001)",
    response_model=MedicalRecordCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_medical_record(
    patient_id: int = Form(..., ge=1),
    chart_number: str = Form(..., max_length=CHART_NUMBER_MAX_LEN),
    symptoms: str = Form(...),
    xray_image: UploadFile = File(...),
    db: AsyncSession = Depends(async_get_db),
    current_user: User = Depends(require_medical_staff),
):
    chart_number = chart_number.strip()
    symptoms = symptoms.strip()
    if not chart_number or not symptoms:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="차트 번호와 증상은 비워둘 수 없습니다.",
        )

    # 환자 존재 확인
    if await db.get(Patient, patient_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PATIENT_NOT_FOUND)

    # 차트 번호 중복 확인 (파일을 저장하기 전에 먼저 거른다)
    duplicated = await db.scalar(
        select(MedicalRecord.id).where(MedicalRecord.chart_number == chart_number)
    )
    if duplicated is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CHART_NUMBER_CONFLICT)

    # 이미지 검증 (확장자, content-type, 크기)
    ext = Path(xray_image.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS or xray_image.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="PNG 또는 JPG 이미지 파일만 업로드할 수 있습니다.",
        )

    # 최대 크기 + 1바이트까지만 읽어 초과 여부를 판단한다.
    content = await xray_image.read(MAX_IMAGE_SIZE + 1)
    if len(content) == 0 or len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="이미지 파일 크기는 10MB 이하여야 합니다.",
        )

    # 파일 저장 (media/xray/{uuid4}.{확장자})
    image_url, save_path = save_xray_file(content, ext)

    # DB 저장, 실패하면 롤백하고 저장한 파일도 삭제
    try:
        record = MedicalRecord(
            patient_id=patient_id,
            chart_number=chart_number,
            symptoms=symptoms,
        )
        db.add(record)
        await db.flush()  # record.id 확보

        db.add(
            XrayImage(
                record_id=record.id,
                image_url=image_url,
                uploader_id=current_user.id,
                # shooting_datetime은 NOT NULL이며 요청에 없으므로 업로드 시각(UTC)으로 저장한다.
                # DB 컬럼이 timezone 없는 DateTime이라 tzinfo를 제거한다.
                shooting_datetime=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        await db.commit()
        await db.refresh(record)
    except IntegrityError:
        # 중복 확인 직후 다른 요청이 같은 차트 번호를 저장한 경우 (DB unique 제약)
        await db.rollback()
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CHART_NUMBER_CONFLICT)
    except Exception:
        await db.rollback()
        save_path.unlink(missing_ok=True)
        raise

    return record


# ---------- REQ-MDR-002 환자별 진료기록 목록 조회 ----------
@router.get(
    "/patients/{patient_id}/medical-records",
    summary="환자별 진료기록 목록 조회 (REQ-MDR-002)",
    response_model=MedicalRecordListResponse,
)
async def list_medical_records(
    patient_id: int = PathParam(..., ge=1),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(async_get_db),
    current_user: User = Depends(require_staff),
):
    if await db.get(Patient, patient_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PATIENT_NOT_FOUND)

    condition = MedicalRecord.patient_id == patient_id

    total = (
        await db.scalar(select(func.count()).select_from(MedicalRecord).where(condition))
    ) or 0

    result = await db.scalars(
        select(MedicalRecord)
        .where(condition)
        .order_by(MedicalRecord.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    records = result.all()

    items = [
        MedicalRecordListItem(
            id=r.id,
            patient_id=r.patient_id,
            chart_number=r.chart_number,
            symptoms=_preview_symptoms(r.symptoms),
            created_at=r.created_at,
        )
        for r in records
    ]

    return MedicalRecordListResponse(items=items, total=total, page=page, size=size)
