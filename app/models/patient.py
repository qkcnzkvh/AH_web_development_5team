# BigInteger: ERD에 맞춰 ID를 큰 정수로 설정
# SmallInteger: 나이 저장
# String(30), String(11): 이름과 전화번호의 최대 길이 지정
# TimestampMixin: created_at, updated_at 컬럼 재사용

from sqlalchemy import BigInteger, SmallInteger, String, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.databases import Base
from app.core.db.models import TimestampMixin
from app.models.enums import Gender


class Patient(TimestampMixin, Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    age: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    gender: Mapped[Gender | None] = mapped_column(Enum(Gender), nullable=True)
    phone: Mapped[str] = mapped_column(String(11), nullable=False)