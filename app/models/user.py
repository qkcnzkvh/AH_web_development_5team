from sqlalchemy import BigInteger, Boolean, Enum, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.databases import Base
from app.core.db.models import TimestampMixin
from app.models.enums import Department, Gender, Role


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(20))
    phone_number: Mapped[str | None] = mapped_column(String(20), unique=True)
    gender: Mapped[Gender] = mapped_column(Enum(Gender))
    department: Mapped[Department] = mapped_column(Enum(Department))
    role: Mapped[Role] = mapped_column(Enum(Role))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))