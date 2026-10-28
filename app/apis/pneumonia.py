
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.databases import async_get_db
from app.core.security import require_staff
from app.models.medical_record import MedicalRecord
from app.models.xray_image import XrayImage
from app.models.user import User
from worker.predict import predict_pneumonia

router = APIRouter(
    prefix="/predictions",
    tags=["Pneumonia Prediction"],
)

# 프로젝트 루트의 media 폴더
MEDIA_DIR = Path(__file__).resolve().parents[2] / "media"


def predict_image(image: Image.Image) -> dict:
    """이미지 예측 결과를 반환한다."""
    return predict_pneumonia(image.convert("RGB"))


@router.post("/pneumonia")
async def predict_pneumonia_api(
    file: UploadFile = File(...),
):
    """업로드한 X-ray 이미지로 폐렴을 예측한다."""
    try:
        image_bytes = await file.read()
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(
            status_code=400,
            detail="유효한 이미지 파일을 업로드해 주세요.",
        )

    return predict_image(image)


@router.post("/medical-records/{record_id}")
async def predict_medical_record(
    record_id: int,
    _user: User = Depends(require_staff),
    db: AsyncSession = Depends(async_get_db),
):
    """진료기록에 연결된 가장 최근 X-ray 이미지로 폐렴을 예측한다."""

    # 진료기록 존재 여부 확인
    record = await db.get(MedicalRecord, record_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="진료기록을 찾을 수 없습니다.",
        )

    # 해당 진료기록의 가장 최근 X-ray 조회
    stmt = (
        select(XrayImage)
        .where(XrayImage.record_id == record_id)
        .order_by(XrayImage.id.desc())
        .limit(1)
    )
    xray = (await db.execute(stmt)).scalar_one_or_none()

    if xray is None:
        raise HTTPException(
            status_code=404,
            detail="진료기록에 연결된 X-ray 이미지가 없습니다.",
        )

    # DB 경로를 실제 파일 경로로 변환
    image_url = xray.image_url

    # 이 API는 서버에 저장된 이미지 파일만 처리한다.
    if image_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="외부 URL 이미지는 아직 지원하지 않습니다.",
        )

    relative_path = image_url.removeprefix("/media/").lstrip("/")
    image_path = (MEDIA_DIR / relative_path).resolve()

    # media 폴더 바깥의 파일 접근 방지
    if not image_path.is_relative_to(MEDIA_DIR.resolve()):
        raise HTTPException(status_code=400, detail="잘못된 이미지 경로입니다.")

    if not image_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="X-ray 이미지 파일을 찾을 수 없습니다.",
        )

    try:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            result = predict_image(image)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(
            status_code=400,
            detail="저장된 X-ray 파일을 읽을 수 없습니다.",
        )

    return {
        "record_id": record_id,
        "xray_image_id": xray.id,
        **result,
    }
