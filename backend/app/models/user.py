from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from .base import created_at_column


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # None for an account made with Google sign-in (T-156).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Google's stable account id ("sub"), set on first Google sign-in.
    google_sub: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    # Practice goal: mock interviews per week.
    weekly_goal: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    # Seeded sales-demo account (T-166): no password, opened only by an admin.
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "has_password": bool(self.password_hash),
            "google": bool(self.google_sub),
            "created_at": self.created_at.isoformat() + "Z",
        }
