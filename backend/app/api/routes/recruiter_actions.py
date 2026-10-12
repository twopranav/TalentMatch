"""Recruiter-only actions on an application: private notes and the optional
manual score. Mounted under the same /api/applications prefix as
routes/applications.py (see app/main.py); kept in its own module so that file
doesn't keep growing.

Permissions are the same as the rest of the recruiter workflow: the job's
owning recruiter, or an admin/superuser. Candidates get 403, and none of this
data is ever returned by a candidate-facing endpoint.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes.applications import _assert_can_view_job_applications
from app.core.audit import record_audit, snapshot
from app.core.deps import require_recruiter_or_admin
from app.db.session import get_db
from app.models.application import Application
from app.models.application_note import ApplicationNote
from app.models.user import User
from app.schemas.application_note import (
    ApplicationNoteCreate,
    ApplicationNoteRead,
    ManualScoreRead,
    ManualScoreUpdate,
)

router = APIRouter()


def _get_application_for_recruiter(application_id: uuid.UUID, db: Session, current_user: User) -> Application:
    """404 if it doesn't exist, 403 if this recruiter doesn't own its job.
    Same order of checks as the status / shortlist-stage endpoints."""
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    _assert_can_view_job_applications(application.job, current_user)
    return application


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

@router.get("/{application_id}/notes", response_model=list[ApplicationNoteRead])
def list_application_notes(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Every note on this application, newest first."""
    application = _get_application_for_recruiter(application_id, db, current_user)
    return (
        db.query(ApplicationNote)
        .filter(ApplicationNote.application_id == application.id)
        # id as the tie-break so two notes saved in the same instant keep a
        # stable order between requests.
        .order_by(ApplicationNote.created_at.desc(), ApplicationNote.id.desc())
        .all()
    )


@router.post("/{application_id}/notes", response_model=ApplicationNoteRead, status_code=status.HTTP_201_CREATED)
def add_application_note(
    application_id: uuid.UUID,
    payload: ApplicationNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    application = _get_application_for_recruiter(application_id, db, current_user)
    note = ApplicationNote(
        application_id=application.id,
        author_id=current_user.id,
        author_email=current_user.email,
        body=payload.body,
    )
    db.add(note)
    db.flush()  # assigns note.id / created_at before we snapshot it for the audit row
    record_audit(
        db, actor=current_user, action="create", resource_type="application_note",
        resource_id=note.id,
        # job_id is not a column on the note; it is added so the audit
        # endpoint can tell which job a note belongs to (a recruiter may only
        # see audit rows for their own jobs) even after the application is gone.
        after={**snapshot(note, "application_note"), "job_id": str(application.job_id)},
    )
    db.commit()
    db.refresh(note)
    return note


# ---------------------------------------------------------------------------
# Manual score
# ---------------------------------------------------------------------------

@router.patch("/{application_id}/manual-score", response_model=ManualScoreRead)
def update_manual_score(
    application_id: uuid.UUID,
    payload: ManualScoreUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Set (0-100) or clear (null) the recruiter's own score for this
    applicant. Only touches manual_score: the AI match_score is written by the
    scoring worker alone, so it is never changed here and a re-score never
    changes this."""
    application = _get_application_for_recruiter(application_id, db, current_user)
    if payload.manual_score == application.manual_score:
        return application  # nothing changed, so no audit row either
    before = snapshot(application, "application")
    application.manual_score = payload.manual_score
    record_audit(
        db, actor=current_user, action="update", resource_type="application",
        resource_id=application.id, before=before, after=snapshot(application, "application"),
    )
    db.commit()
    db.refresh(application)
    return application
