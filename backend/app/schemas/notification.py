"""Module 9 response shapes."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    body: str
    interview_id: Optional[int] = None
    # sent | skipped | failed | not_attempted — reported so a candidate is
    # never left assuming an email went out when no mail server is configured.
    email_status: str
    email_error: Optional[str] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class NotificationSummary(BaseModel):
    total: int
    unread: int


class ReminderRun(BaseModel):
    """What a reminder pass actually did — including what it declined to do."""

    unfinished_interviews: int
    reminders_created: int
    # Already reminded about within the de-duplication window. Reported rather
    # than hidden, so a run that produces nothing is distinguishable from a run
    # that found nothing.
    already_reminded: int
    notifications: List[NotificationOut] = []


class EmailPreference(BaseModel):
    """
    The user's automated-email switch, plus whether the deployment can send at
    all. Both are needed: a user who turns email on and receives nothing
    deserves to be told the server has no mail configured, rather than being
    left to assume their own setting failed.
    """

    email_notifications: bool
    delivery_configured: bool = False
