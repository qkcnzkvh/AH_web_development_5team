# ForeignKey("patients.id"): 진료 기록을 환자 테이블과 연결
# ondelete="CASCADE": 환자가 삭제되면 관련 진료 기록도 삭제하도록 설정
# unique=True: 차트 번호 중복 방지
# Text: 증상 내용을 길이 제한 없이 저장

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.databases import Base
from app.core.db.models import TimestampMixin

class MedicalRecord(TimestampMixin, Base):
    __tablename__ = "medical_records"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    patient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    chart_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    symptoms: Mapped[str] = mapped_column(Text, nullable=False)
