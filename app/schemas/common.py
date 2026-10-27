# 공통 응답 스키마 도구 (5일차 명세서 2장: 날짜·시간)
# DB에는 시간대 없이 UTC로 저장되므로, 응답할 때 UTC를 붙여 ISO 8601 + "Z" 형식으로 내보낸다.
# 예: 2026-10-27 03:03:00 (DB) → "2026-10-27T03:03:00Z" (응답)
#
# 사용법: created_at: UtcDateTime / updated_at: UtcDateTime | None

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


UtcDateTime = Annotated[datetime, AfterValidator(to_utc)]
