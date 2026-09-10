"""
Module 9 — in-app notifications.

A notification is a record that something happened which the user should know
about. It is stored whether or not an email went out, and the email result is
stored alongside it: the in-app feed is the source of truth, and email is one
optional delivery channel for the same fact. That ordering matters — if email
were primary, an unconfigured mail server would mean the user is never told
anything at all.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from app.db.session import Base


class NotificationKind(str, enum.Enum):
    """
    Why the user is being told. Kept as an enum rather than a free string so
    the UI can group and filter, and so a typo cannot invent a new category.
    """

    INTERVIEW_REMINDER = "INTERVIEW_REMINDER"   # an interview left unfinished
    SESSION_ALERT = "SESSION_ALERT"             # something during/about a session
    REPORT_READY = "REPORT_READY"               # scoring finished, report available
    PERFORMANCE_SUMMARY = "PERFORMANCE_SUMMARY" # periodic roll-up of progress


class EmailStatus(str, enum.Enum):
    """
    What became of the email for this notification.

    NOT_ATTEMPTED and SKIPPED are different: the first means this kind of
    notification does not send mail, the second means it would have but no mail
    server is configured. Merging them would make a broken deployment look like
    a deliberate design decision.
    """

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    SKIPPED = "SKIPPED"
    SENT = "SENT"
    FAILED = "FAILED"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind = Column(Enum(NotificationKind), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)

    # The interview this is about, when there is one. SET NULL rather than
    # CASCADE: deleting an interview should not silently erase the record that
    # the candidate was once told about it.
    interview_id = Column(
        Integer,
        ForeignKey("interviews.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    email_status = Column(
        Enum(EmailStatus), nullable=False, default=EmailStatus.NOT_ATTEMPTED
    )
    email_error = Column(Text, nullable=True)

    # Null means unread. A timestamp rather than a boolean so "when did they
    # see this" is answerable later without a second column.
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # No `relationship("User")` here on purpose. Nothing reads it — every
    # query filters on user_id directly — and a string-named relationship makes
    # this model unimportable unless the User model happens to have been
    # registered first, turning a harmless import into a mapper error at query
    # time.

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self) -> None:
        if self.read_at is None:
            self.read_at = datetime.now(timezone.utc)
