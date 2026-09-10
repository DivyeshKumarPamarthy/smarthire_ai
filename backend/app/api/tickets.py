from datetime import datetime, timezone
from typing import List, Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.ticket import Ticket, TicketStatus
from app.models.user import Role, User
from app.schemas.ticket import REASONS, TicketCreate, TicketOut, TicketStatusUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _loaded(db: Session):
    return db.query(Ticket).options(
        selectinload(Ticket.reporter), selectinload(Ticket.against)
    )


@router.get("/reasons", response_model=List[str])
def list_reasons():
    """The allowed report reasons. Enum-like, matches the schema validator."""
    return REASONS


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Report another user. Administrators review the queue."""
    if payload.against_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot report yourself."
        )

    target = db.query(User).filter(User.id == payload.against_id).first()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That user does not exist."
        )

    ticket = Ticket(
        reporter_id=current_user.id,
        against_id=target.id,
        reason=payload.reason,
        details=payload.details,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    _notify_admins_of_ticket(db, current_user, ticket)
    return TicketOut.from_model(ticket)


def _notify_admins_of_ticket(db: Session, reporter, ticket) -> None:
    """
    Module 9: put a new report in front of the people who triage it.

    Best-effort. A notification failing must never cost the reporter their
    ticket — the report itself is already committed above.
    """
    try:
        from app.models.notification import NotificationKind
        from app.models.user import Role
        from app.services import notifications as notify_service

        title, body = notify_service.compose_ticket_raised(reporter.name, ticket.reason)
        notify_service.notify_role(
            db, Role.ADMIN,
            kind=NotificationKind.SESSION_ALERT,
            title=title, body=body,
            send_email=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not notify admins about ticket %s", ticket.id)


@router.get("", response_model=List[TicketOut])
def list_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ticket_status: Optional[TicketStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    Administrators see every ticket. Everyone else sees only the ones they
    raised — a candidate must not be able to read reports made against them.
    """
    query = _loaded(db)

    if current_user.role != Role.ADMIN:
        query = query.filter(Ticket.reporter_id == current_user.id)

    if ticket_status is not None:
        query = query.filter(Ticket.status == ticket_status)

    tickets = query.order_by(Ticket.id.desc()).offset(offset).limit(limit).all()
    return [TicketOut.from_model(t) for t in tickets]


@router.put(
    "/{ticket_id}/status",
    response_model=TicketOut,
    dependencies=[Depends(require_roles(Role.ADMIN))],
)
def update_ticket_status(
    ticket_id: int,
    payload: TicketStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resolve or dismiss a ticket. Administrators only."""
    ticket = _loaded(db).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    ticket.status = payload.status
    ticket.resolved_by_id = current_user.id
    ticket.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)
    return TicketOut.from_model(ticket)
