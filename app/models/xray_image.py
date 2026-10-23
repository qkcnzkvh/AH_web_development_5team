from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.databases import Base


class XrayImage(Base):
    __tablename__ = "xray_images"

    id: Mapped[int] = mapped_column(
        BigInteger, 
        primary_key=True, 
        autoincrement=True
    )

    record_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("medical_records.id", ondelete="CASCADE")
    )

    uploader_id: Mapped[int | None] = mapped_column(
        BigInteger, 
        ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True
    )
    image_url: Mapped[str] = mapped_column(String(2048))
    shooting_datetime: Mapped[datetime] = mapped_column(DateTime)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=text("current_timestamp(0)")
    )