from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.databases import Base
from app.core.db.models import TimestampMixin


class AiAnalysisResult(TimestampMixin, Base):
    __tablename__ = "ai_analysis_results"
    # 같은 진료기록·같은 모델의 결과는 1건만 저장 (재추론 방지, 동시 요청 시 중복 방지)
    __table_args__ = (
        UniqueConstraint("record_id", "ai_model", name="uq_ai_results_record_model"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, 
        primary_key=True, 
        autoincrement=True
    )

    record_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("medical_records.id", ondelete="CASCADE")
    )
    
    is_pneumonia: Mapped[bool] = mapped_column(Boolean)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Heatmap은 선택사항: 현재 모델은 생성하지 않으므로 NULL 허용
    heatmap_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_model: Mapped[str] = mapped_column(String(50))