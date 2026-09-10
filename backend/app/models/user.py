import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String
from sqlalchemy.sql import func

from app.db.session import Base


class Role(str, enum.Enum):
    CANDIDATE = "CANDIDATE"
    RECRUITER = "RECRUITER"
    ADMIN = "ADMIN"


class Provider(str, enum.Enum):
    LOCAL = "LOCAL"
    GOOGLE = "GOOGLE"
    GITHUB = "GITHUB"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)

    # Null for Google accounts: they never set a local password.
    password = Column(String(255), nullable=True)

    role = Column(Enum(Role), nullable=False, default=Role.CANDIDATE)
    provider = Column(Enum(Provider), nullable=False, default=Provider.LOCAL)

    # Set by an administrator. A blocked user cannot log in and their existing
    # token stops working, so blocking is real rather than cosmetic.
    is_blocked = Column(Boolean, nullable=False, default=False, server_default="false")

    # Module 9: whether automated email is sent to this user.
    #
    # Defaults to on, because everything sent is transactional — it is about
    # the user's own interviews or their own work queue, not marketing. It is
    # still a real switch: automated mail with no way to stop it is a defect,
    # not a feature. Nothing sends at all until SMTP_HOST is configured.
    email_notifications = Column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
