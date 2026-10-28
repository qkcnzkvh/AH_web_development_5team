# AI 폐렴 예측 API (6일차 명세서 4장)
# REQ-PRED-001 AI 폐렴 예측 수행  POST /api/v1/medical-records/{record_id}/predict
# NFR-PRED-002 API 성능 (3초 이내 응답)
#
# - 라우터에는 /api/v1 prefix를 붙이지 않는다. main.py의 include_router(prefix="/api/v1")에서 공통 적용한다.
# - 인증·인가는 require_staff (STAFF·ADMIN, 부서 무관. PENDING은 403)
# - 에러 응답은 공통 형식 {"detail": "..."} (HTTPException)만 사용한다.
# - 결과 목록 조회(GET .../analyses, 명세서 5장)는 이 파일 아래쪽에 추가한다.

import asyncio
import logging
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from PIL import Image
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db.databases import async_get_db
from app.core.security import require_staff
from app.core.storage import MEDIA_DIR
from app.models.ai_analysis_result import AiAnalysisResult
from app.models.medical_record import MedicalRecord
from app.models.user import User
from app.models.xray_image import XrayImage
from app.schemas.ai_analysis import AiAnalysisResponse
from worker.predict import predict_pneumonia

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/medical-records", tags=["AI Prediction"])

RECORD_NOT_FOUND_MESSAGE = "진료기록을 찾을 수 없습니다."
XRAY_NOT_FOUND_MESSAGE = "진료기록의 X-Ray 이미지를 찾을 수 없습니다."
PREDICT_FAILED_MESSAGE = "AI 예측 중 오류가 발생했습니다."
MODEL_UNAVAILABLE_MESSAGE = "AI 모델을 사용할 수 없습니다."


def _image_url_to_path(image_url: str) -> FilePath:
    """DB의 image_url(/media/xray/{파일명})을 서버의 media 폴더 안 파일 경로로 바꾼다."""
    relative = image_url.removeprefix("/media/").lstrip("/")
    path = (MEDIA_DIR / relative).resolve()
    # media 폴더 바깥 접근 방지
    if not path.is_relative_to(MEDIA_DIR.resolve()):
        raise ValueError(f"media 폴더 밖의 경로입니다: {image_url}")
    return path


def _run_inference(image_path: FilePath) -> dict:
    """이미지를 읽어 추론한다. CPU를 쓰는 동기 작업이므로 asyncio.to_thread로 호출한다."""
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    return predict_pneumonia(image)


async def _get_saved_result(
    db: AsyncSession, record_id: int, ai_model: str
) -> AiAnalysisResult | None:
    stmt = select(AiAnalysisResult).where(
        AiAnalysisResult.record_id == record_id,
        AiAnalysisResult.ai_model == ai_model,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


@router.post(
    "/{record_id}/predict",
    response_model=AiAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "이미 저장된 결과를 그대로 반환 (추론 미수행)"},
        201: {"description": "새로 추론하여 저장한 결과"},
    },
)
async def predict_medical_record(
    request: Request,
    response: Response,
    record_id: int = Path(ge=1, description="진료기록 고유 ID"),
    _user: User = Depends(require_staff),
    db: AsyncSession = Depends(async_get_db),
):
    """진료기록의 가장 최근 X-Ray로 폐렴을 예측하고 결과를 저장한다."""
    ai_model = settings.AI_MODEL_NAME

    # 2. 진료기록 확인
    if await db.get(MedicalRecord, record_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, RECORD_NOT_FOUND_MESSAGE)

    # 3. 같은 진료기록·같은 모델의 저장된 결과가 있으면 추론 없이 반환 (200)
    saved = await _get_saved_result(db, record_id, ai_model)
    if saved is not None:
        response.status_code = status.HTTP_200_OK
        return saved

    # 모델이 로드되지 않았으면 추론할 수 없다 (저장된 결과는 위에서 이미 반환 가능)
    if not getattr(request.app.state, "model_loaded", False):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, MODEL_UNAVAILABLE_MESSAGE
        )

    # 4. 가장 최근 X-Ray (xray_images.id 내림차순 첫 번째)
    xray = (
        await db.execute(
            select(XrayImage)
            .where(XrayImage.record_id == record_id)
            .order_by(XrayImage.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if xray is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, XRAY_NOT_FOUND_MESSAGE)

    # 5~6. 이미지 파일을 읽어 추론 (이벤트 루프를 막지 않도록 스레드에서 실행)
    try:
        image_path = _image_url_to_path(xray.image_url)
        if not image_path.is_file():
            raise FileNotFoundError(str(image_path))
        prediction = await asyncio.to_thread(_run_inference, image_path)
    except Exception:
        logger.exception("AI 예측 실패 (record_id=%s)", record_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, PREDICT_FAILED_MESSAGE
        )

    # 7. 반환값을 API 필드로 변환 (명세서 4.5)
    #    is_pneumonia = (class_id == 1), confidence = softmax 확률(0~1) × 100 → 소수 둘째 자리
    confidence = (Decimal(str(prediction["confidence"])) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    result = AiAnalysisResult(
        record_id=record_id,
        is_pneumonia=prediction["class_id"] == 1,
        confidence=confidence,
        heatmap_url=None,  # 현재 모델은 Heatmap을 생성하지 않는다
        ai_model=ai_model,
    )

    # 8. 저장 후 201 반환
    db.add(result)
    try:
        await db.commit()
    except IntegrityError:
        # 9. 동시 요청: UNIQUE(record_id, ai_model) 위반 → 먼저 저장된 결과를 200으로 반환
        await db.rollback()
        saved = await _get_saved_result(db, record_id, ai_model)
        if saved is None:
            # UNIQUE 위반이 아닌 다른 제약 위반(예: 그 사이 진료기록 삭제)
            logger.exception("AI 결과 저장 실패 (record_id=%s)", record_id)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, PREDICT_FAILED_MESSAGE
            )
        response.status_code = status.HTTP_200_OK
        return saved

    await db.refresh(result)  # DB가 채운 id, created_at 로드
    return result
