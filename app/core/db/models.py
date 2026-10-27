import uuid as uuid_pkg
from datetime import datetime

from sqlalchemy import Boolean, DateTime, func, text
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7


class UUIDMixin:
    uuid: Mapped[uuid_pkg.UUID] = mapped_column(
        CHAR(36), primary_key=True, default=uuid7
    )


class TimestampMixin:
    # 파이썬 default 없이 DB의 current_timestamp만 사용 (요청 시점의 시각이 저장됨)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("current_timestamp(0)")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        server_default=text("current_timestamp(0)"),
        onupdate=func.now(),
    )   


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
