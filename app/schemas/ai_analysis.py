# AI 분석 결과 응답 스키마 (6일차 명세서 2.3)
# 예측 수행(POST .../predict)과 결과 목록(GET .../analyses) 항목에 같은 모델을 사용한다.

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.common import UtcDateTime


class AiAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    record_id: int
    is_pneumonia: bool
    confidence: float  # 0~100(%) 단위, 소수 둘째 자리. 프론트가 `${confidence}%`로 그대로 표시
    heatmap_url: str | None  # 현재 모델은 Heatmap을 만들지 않아 null
    ai_model: str
    created_at: UtcDateTime  # UTC ISO 8601 (Z 포함)

    @field_validator("confidence", mode="before")
    @classmethod
    def decimal_to_float(cls, value):
        # DB의 Numeric(5,2)는 Decimal로 읽힌다. JSON에서 문자열이 되지 않도록 숫자로 변환한다.
        return float(value)
