from typing import Literal
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import Text, and_, cast, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager, joinedload
from app.core.audit import record_audit, snapshot
from app.core.config import settings
from app.core.deps import get_current_user, rate_limit_user, require_recruiter_or_admin
from app.db.session import get_db
from app.models.application import Application, ApplicationStatus, ShortlistStage
from app.models.resume import Resume, ResumeExtractionStatus
from app.models.job import Job, JobStatus
from app.models.user import User, UserRole
from app.schemas.application import (
    MAX_BULK_APPLY,
    BulkApplyRequest,
    BulkApplyResult,
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
    ShortlistStageUpdate,
    ApplicationWithJob,
    ApplicationWithApplicant,
)

from app.core.dispatch import acquire_once, dispatch_extraction
from app.core.matching_tasks import dispatch_score_for_job, score_application_task
from app.core.skills_extraction_tasks import run_skills_extraction_task
from app.api.routes.resumes import _discard_blob, _make_resume_row, stage_uploads

router = APIRouter()


def _require_ready_resume(candidate_id: uuid.UUID, db: Session) -> Resume:
    """Gate for application creation: 'no resume, no application.' Runs
    before the Application row is ever created — an application without
    a fully-processed resume behind it isn't something a recruiter can
    evaluate, so it shouldn't exist as a row at all, not even a
    provisional one waiting to be filled in later.

    Three separate checks rather than one combined condition, on purpose:
    each maps to exactly one candidate-facing message, in the order a
    candidate would actually hit them (no resume -> unreadable resume ->
    not-finished-yet resume).
    """
    resume = (
        db.query(Resume)
        .filter(Resume.owner_id == candidate_id, Resume.is_archived.is_(False))
        .first()
    )
    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload a resume to your profile before applying to a job.",
        )
    if resume.skills_extraction_status == ResumeExtractionStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="We couldn't read your resume — please try uploading it again.",
        )
    if resume.skills_extraction_status != ResumeExtractionStatus.DONE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your resume is still being processed — try applying again in a moment.",
        )
    return resume


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def apply_to_job(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.get(Job, payload.job_id)
    if job is None or job.status != JobStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    existing = (
        db.query(Application)
        .filter(Application.user_id == current_user.id, Application.job_id == job.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already applied to this job")

    resume = _require_ready_resume(current_user.id, db)

    application = Application(user_id=current_user.id, job_id=job.id, resume_id=resume.id)
    db.add(application)
    db.flush()  # assigns application.id before we snapshot it for the audit row
    record_audit(
        db, actor=current_user, action="create", resource_type="application",
        resource_id=application.id, after=snapshot(application, "application"),
    )
    db.commit()
    db.refresh(application)

    # After commit: the worker reads the row in its own session. If the JD's
    # skills are not extracted yet the task parks the row as 'pending' and
    # the JD extraction task re-triggers it.
    dispatch_extraction(score_application_task, application.id)
    return application

@router.get("/me", response_model=list[ApplicationWithJob])
def list_my_applications(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    apps = (
        db.query(Application)
        .options(joinedload(Application.job).joinedload(Job.created_by))
        .filter(Application.user_id == current_user.id)
        .order_by(Application.applied_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        ApplicationWithJob(
            id=a.id, user_id=a.user_id, job_id=a.job_id, resume_id=a.resume_id, status=a.status,
            applied_at=a.applied_at, updated_at=a.updated_at,
            job_title=a.job.title, job_status=a.job.status.value,
            location=a.job.location, company=a.job.created_by.company,
        )
        for a in apps
    ]

def _assert_can_view_job_applications(job: Job, current_user: User):
    is_privileged = current_user.role in (UserRole.ADMIN, UserRole.SUPERUSER)
    if not is_privileged and job.created_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to view these applications")

def _like_escape(text: str) -> str:
    """Escape LIKE wildcards so a search for '100%' or 'a_b' is literal."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _clean_skill_list(values: list[str] | None) -> list[str]:
    return [v.strip() for v in (values or []) if v and v.strip()]


def _applicant_filters(
    *,
    q: str | None,
    statuses: list[ApplicationStatus] | None,
    shortlist_stages: list[ShortlistStage] | None,
    min_score: float | None,
    max_score: float | None,
    skills_matched: list[str],
    skills_proven: list[str],
    skills_missing: list[str],
    skill_mode: str,
    resume_skill: str | None,
    min_years: float | None,
    max_years: float | None,
) -> list:
    """Every optional applicant filter as a SQL condition. Used for both the
    page query and the total-count query, so the two can never disagree."""
    filters: list = []

    if q and q.strip():
        pattern = f"%{_like_escape(q.strip())}%"
        filters.append(or_(
            User.full_name.ilike(pattern, escape="\\"),
            User.email.ilike(pattern, escape="\\"),
            Resume.candidate_name.ilike(pattern, escape="\\"),
            Resume.candidate_email.ilike(pattern, escape="\\"),
            Resume.original_filename.ilike(pattern, escape="\\"),
        ))

    if statuses:
        filters.append(Application.status.in_(statuses))

    # Only meaningful for shortlisted applications (the stage is NULL for
    # everything else, so this naturally excludes them).
    if shortlist_stages:
        filters.append(Application.shortlist_stage.in_(shortlist_stages))

    # Unscored applicants (NULL score) drop out as soon as a score bound is set.
    if min_score is not None:
        filters.append(Application.match_score >= min_score)
    if max_score is not None:
        filters.append(Application.match_score <= max_score)

    # Experience comes from the resume itself; unknown experience drops out
    # once a bound is set, same reasoning as the score.
    if min_years is not None:
        filters.append(Resume.experience_months >= round(min_years * 12))
    if max_years is not None:
        filters.append(Resume.experience_months <= round(max_years * 12))

    # Free-text skill search over everything extracted from the resume
    # (including skills the JD never asked for).
    if resume_skill and resume_skill.strip():
        pattern = f"%{_like_escape(resume_skill.strip())}%"
        filters.append(cast(Resume.skills_result, Text).ilike(pattern, escape="\\"))

    # Per-JD-skill conditions read from the stored match explanation
    # (match_details.matched / .missing), so they always agree with what the
    # score explanation shows. JSONB containment (@>) does the lookup.
    skill_conds = []
    for skill in skills_matched:
        skill_conds.append(Application.match_details.contains({"matched": [{"jd_skill": skill}]}))
    for skill in skills_proven:
        skill_conds.append(Application.match_details.contains({"matched": [{"jd_skill": skill, "status": "proven"}]}))
    for skill in skills_missing:
        skill_conds.append(Application.match_details.contains({"missing": [skill]}))
    if skill_conds:
        filters.append(and_(*skill_conds) if skill_mode == "all" else or_(*skill_conds))

    return filters


@router.get("/job/{job_id}", response_model=list[ApplicationWithApplicant])
def list_job_applications(
    job_id: uuid.UUID,
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: Literal["score", "applied_at"] = "score",
    q: str | None = Query(default=None, max_length=100, description="Name, email or resume file name contains this"),
    statuses: list[ApplicationStatus] | None = Query(default=None, alias="status"),
    shortlist_stages: list[ShortlistStage] | None = Query(default=None, alias="shortlist_stage", description="Shortlist sub-state (shortlisted applicants only)"),
    min_score: float | None = Query(default=None, ge=0, le=100),
    max_score: float | None = Query(default=None, ge=0, le=100),
    skills_matched: list[str] | None = Query(default=None, description="JD skills the resume must match (proven or mentioned)"),
    skills_proven: list[str] | None = Query(default=None, description="JD skills the resume must prove in a project or job"),
    skills_missing: list[str] | None = Query(default=None, description="JD skills the resume must be missing"),
    skill_mode: Literal["all", "any"] = "all",
    resume_skill: str | None = Query(default=None, max_length=100, description="Any skill on the resume contains this"),
    min_years: float | None = Query(default=None, ge=0),
    max_years: float | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Applicants for a job. Default order is best match score first, with
    unscored applicants last. Ties on score go to whoever applied first,
    then to applicant name A-Z, then to application id (so paging with
    offset never repeats or skips a row). sort=applied_at gives newest
    first.

    All filters are optional and combine with AND. The size of the whole
    filtered set (not just this page) comes back in the X-Total-Count
    header, so the client can draw page numbers.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _assert_can_view_job_applications(job, current_user)

    filters = _applicant_filters(
        q=q, statuses=statuses, shortlist_stages=shortlist_stages, min_score=min_score, max_score=max_score,
        skills_matched=_clean_skill_list(skills_matched),
        skills_proven=_clean_skill_list(skills_proven),
        skills_missing=_clean_skill_list(skills_missing),
        skill_mode=skill_mode, resume_skill=resume_skill,
        min_years=min_years, max_years=max_years,
    )

    # Outer joins: recruiter-submitted applications have no User row at all.
    display_name = func.lower(func.coalesce(
        User.full_name, User.email, Resume.candidate_name, Resume.original_filename,
    ))
    order = (
        [
            Application.match_score.desc().nulls_last(),
            Application.applied_at.asc(),
            display_name.asc(),
            Application.id.asc(),
        ]
        if sort == "score"
        else [Application.applied_at.desc(), Application.id.asc()]
    )

    total = (
        db.query(func.count(Application.id))
        .outerjoin(User, User.id == Application.user_id)
        .outerjoin(Resume, Resume.id == Application.resume_id)
        .filter(Application.job_id == job_id, *filters)
        .scalar()
    )
    response.headers["X-Total-Count"] = str(total)

    apps = (
        db.query(Application)
        .outerjoin(User, User.id == Application.user_id)
        .outerjoin(Resume, Resume.id == Application.resume_id)
        .options(
            contains_eager(Application.user),
            contains_eager(Application.resume),
            joinedload(Application.submitted_by),
        )
        .filter(Application.job_id == job_id, *filters)
        .order_by(*order)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_applicant(a) for a in apps]


def _to_applicant(a: Application) -> ApplicationWithApplicant:
    if a.user is not None:
        name, email = a.user.full_name, a.user.email
    else:
        # No account: identify the row by whatever the resume tells us,
        # falling back to the file name so it is never blank.
        name = (a.resume.candidate_name if a.resume else None) or (a.resume.original_filename if a.resume else None)
        email = a.resume.candidate_email if a.resume else None
    return ApplicationWithApplicant(
        id=a.id, user_id=a.user_id, job_id=a.job_id, resume_id=a.resume_id, status=a.status,
        shortlist_stage=a.shortlist_stage, interview_at=a.interview_at,
        applied_at=a.applied_at, updated_at=a.updated_at,
        applicant_email=email, applicant_name=name,
        submitted_by_email=a.submitted_by.email if a.submitted_by else None,
        resume_filename=a.resume.original_filename if a.resume else None,
        match_score=a.match_score, manual_score=a.manual_score, match_status=a.match_status,
        match_details=a.match_details, match_error=a.match_error,
    )

# ---------------------------------------------------------------------------
# Recruiter bulk apply: apply many resumes to one job, no candidate accounts
# ---------------------------------------------------------------------------

def _get_job_for_bulk_apply(job_id: uuid.UUID, db: Session, current_user: User) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    # Same rule as viewing the applicants: admin/superuser, or the job's owner.
    _assert_can_view_job_applications(job, current_user)
    if job.status != JobStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Publish the job before applying resumes to it.")
    return job


def _add_unowned_application(db: Session, job: Job, resume: Resume, actor: User) -> Application:
    application = Application(user_id=None, submitted_by_id=actor.id, job_id=job.id, resume_id=resume.id)
    db.add(application)
    db.flush()  # assigns application.id (and trips the unique index on a duplicate)
    record_audit(
        db, actor=actor, action="create", resource_type="application",
        resource_id=application.id, after=snapshot(application, "application"),
    )
    return application


def _check_resume_usable(resume: Resume | None, db: Session, job: Job, actor: User) -> str | None:
    """Returns a candidate-readable reason this resume can't be applied, or
    None if it can. A resume the caller isn't allowed to use reads as
    'not found', same as everywhere else in resumes.py."""
    is_admin = actor.role in (UserRole.ADMIN, UserRole.SUPERUSER)
    if resume is None or (not is_admin and resume.uploaded_by_id != actor.id):
        return "Resume not found."
    if resume.owner_id is not None:
        return "This resume belongs to a candidate account; they need to apply themselves."
    if resume.is_archived:
        return "This resume is archived."
    if resume.skills_extraction_status == ResumeExtractionStatus.FAILED:
        return "This resume couldn't be read. Re-run extraction or upload it again."
    already = (
        db.query(Application.id)
        .filter(Application.job_id == job.id, Application.resume_id == resume.id)
        .first()
    )
    if already:
        return "Already applied to this job."
    return None


@router.post(
    "/job/{job_id}/bulk",
    response_model=list[BulkApplyResult],
    dependencies=[Depends(rate_limit_user("bulk_apply", 10, 60))],
)
def bulk_apply_resumes(
    job_id: uuid.UUID,
    payload: BulkApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Apply resumes already in the library (bulk-uploaded, no account) to a
    job, one application each. Partial success: every resume gets its own
    result, and one bad row doesn't stop the rest.

    Resumes still being extracted are accepted: the scoring task parks the
    row as 'pending' and is re-triggered when extraction finishes (see
    matching_tasks.py). Only a FAILED extraction is turned away.
    """
    job = _get_job_for_bulk_apply(job_id, db, current_user)

    resume_ids = list(dict.fromkeys(payload.resume_ids))  # de-dupe, keep order
    resumes = {r.id: r for r in db.query(Resume).filter(Resume.id.in_(resume_ids)).all()}

    results: list[BulkApplyResult] = []
    created: list[uuid.UUID] = []
    for resume_id in resume_ids:
        resume = resumes.get(resume_id)
        filename = resume.original_filename if resume else str(resume_id)
        error = _check_resume_usable(resume, db, job, current_user)
        if error is None:
            try:
                with db.begin_nested():
                    application = _add_unowned_application(db, job, resume, current_user)
                created.append(application.id)
                results.append(BulkApplyResult(
                    original_filename=filename, success=True,
                    resume_id=resume_id, application_id=application.id,
                ))
                continue
            except IntegrityError:
                # Lost a race with another request applying the same resume.
                error = "Already applied to this job."
        results.append(BulkApplyResult(
            original_filename=filename, success=False,
            resume_id=resume_id if resume else None, error=error,
        ))

    db.commit()
    for application_id in created:
        dispatch_extraction(score_application_task, application_id)
    return results


@router.post(
    "/job/{job_id}/bulk-upload",
    response_model=list[BulkApplyResult],
    dependencies=[Depends(rate_limit_user("upload", 30, 60))],
)
async def bulk_upload_and_apply(
    job_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Upload resume files and apply every one to this job in a single step.
    Each file is stored exactly as POST /resumes/bulk would store it (so it
    also lands in the library, unowned, uploaded_by the caller), then gets
    its application. One bad file doesn't stop the rest.

    Extraction is queued per resume. The new applications sit at match
    'pending' until it finishes; the resume-extraction task then queues
    their scoring, so nothing needs dispatching here.
    """
    job = _get_job_for_bulk_apply(job_id, db, current_user)
    if len(files) > MAX_BULK_APPLY:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload at most {MAX_BULK_APPLY} files at a time.",
        )

    # Phase 1: read, validate and store every blob (in parallel, off the
    # event loop; see resumes.stage_uploads). Phase 2: a resume row plus its
    # application per stored file, each in its own savepoint.
    staged = await stage_uploads(files)

    results: list[BulkApplyResult] = []
    stored: list[uuid.UUID] = []
    stored_blobs: list[str] = []
    for item in staged:
        filename = item.file.filename
        if item.error is not None:
            results.append(BulkApplyResult(original_filename=filename, success=False, error=item.error))
            continue
        try:
            with db.begin_nested():
                resume = _make_resume_row(
                    item.blob_path, filename, item.file.content_type, item.size, None, current_user, db,
                )
                application = _add_unowned_application(db, job, resume, current_user)
            stored.append(resume.id)
            stored_blobs.append(item.blob_path)
            results.append(BulkApplyResult(
                original_filename=filename, success=True,
                resume_id=resume.id, application_id=application.id,
            ))
        except Exception:
            # The savepoint rolled the rows back, but the blob (written
            # before the rows) is still there; don't leave it orphaned.
            _discard_blob(item.blob_path)
            results.append(BulkApplyResult(
                original_filename=filename, success=False, error="Could not apply this file.",
            ))

    try:
        db.commit()
    except Exception:
        for blob_path in stored_blobs:
            _discard_blob(blob_path)
        raise
    for resume_id in stored:
        dispatch_extraction(run_skills_extraction_task, resume_id)
    return results


@router.post(
    "/job/{job_id}/rescore",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_user("rescore", 5, 60))],
)
def rescore_job_applications(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Re-queue scoring for every applicant to this job (e.g. after changing
    the embedding model or weights). Scores update as the worker gets to them."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _assert_can_view_job_applications(job, current_user)
    # Dedupe: a repeat inside the lock window would only re-queue the same
    # work behind itself, so acknowledge it and queue nothing.
    if not acquire_once(f"rescore:job:{job_id}", settings.RESCORE_LOCK_SECONDS):
        return {"queued": 0, "already_in_progress": True}
    queued = dispatch_score_for_job(db, job_id)
    return {"queued": queued}


@router.patch("/{application_id}/status", response_model=ApplicationRead)
def update_application_status(
    application_id: uuid.UUID,
    payload: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    _assert_can_view_job_applications(application.job, current_user)
    before = snapshot(application, "application")
    if payload.status != application.status:
        # The shortlist sub-state only exists while shortlisted: entering the
        # shortlist starts at the default stage, leaving it clears the stage
        # and any interview time.
        application.shortlist_stage = (
            ShortlistStage.SHORTLISTED if payload.status == ApplicationStatus.SHORTLISTED else None
        )
        application.interview_at = None
    application.status = payload.status
    record_audit(
        db, actor=current_user, action="update", resource_type="application",
        resource_id=application.id, before=before, after=snapshot(application, "application"),
    )
    db.commit()
    db.refresh(application)
    return application

@router.patch("/{application_id}/shortlist-stage", response_model=ApplicationRead)
def update_shortlist_stage(
    application_id: uuid.UUID,
    payload: ShortlistStageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Move a shortlisted applicant between shortlist stages. For
    interview_scheduled, interview_at (timezone-aware) is required."""
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    _assert_can_view_job_applications(application.job, current_user)
    if application.status != ApplicationStatus.SHORTLISTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only shortlisted applicants have a shortlist stage.",
        )
    before = snapshot(application, "application")
    application.shortlist_stage = payload.stage
    application.interview_at = payload.interview_at
    record_audit(
        db, actor=current_user, action="update", resource_type="application",
        resource_id=application.id, before=before, after=snapshot(application, "application"),
    )
    db.commit()
    db.refresh(application)
    return application


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_application(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    if application.user_id is None:
        # Recruiter-submitted: there is no candidate to withdraw it, so the
        # people who manage the job can.
        can_remove = current_user.role in (UserRole.ADMIN, UserRole.SUPERUSER) or (
            current_user.role == UserRole.RECRUITER and application.job.created_by_id == current_user.id
        )
    else:
        can_remove = application.user_id == current_user.id
    if not can_remove:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    record_audit(
        db, actor=current_user, action="delete", resource_type="application",
        resource_id=application.id, before=snapshot(application, "application"),
    )
    db.delete(application)
    db.commit()