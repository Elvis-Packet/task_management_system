from datetime import datetime

from flask import Blueprint, request, Response

from models.user import User
from models.leave_type import LeaveType
from models.leave_request import LeaveRequest, LeaveAttachment
from models.enums import (
    LeaveStatus,
    AuditAction,
    CommentTargetType,
)
from services.leave_service import (
    LeaveService,
    LeaveTypeService,
    LeaveValidationError,
)
from services.audit_service import AuditService
from utils.response import ok, err
from utils.rbac import (
    Permission,
    require_auth,
    require_permission,
    get_current_user,
    has_permission,
)
from utils.serializers import (
    serialize_leave_request,
    serialize_leave_type,
    serialize_leave_attachment,
    serialize_leave_conflict,
    serialize_user,
)
from utils.pagination import paginate
from utils.appdate import app_today

leave_bp = Blueprint("leave", __name__)


def _visible_request(leave_id, current_user):
    """A leave request is reachable only through the caller's own scoped
    query, so an arbitrary id can never be walked into a readable record.
    Everything below resolves the request this way — there is no code path
    that loads a LeaveRequest by primary key alone."""

    return LeaveService.scoped_query(current_user).filter(
        LeaveRequest.id == leave_id
    ).first()


def _payload():
    return request.get_json(silent=True) or {}


def _validation_error(exc):
    return err(exc.message, 422, errors=exc.errors)


def _resolve_leave_type(leave_type_id):
    if not leave_type_id:
        return None, err(
            "Select a leave type.", 422, errors={"leave_type_id": "required"}
        )

    leave_type = LeaveType.query.filter_by(id=leave_type_id).first()

    if not leave_type:
        return None, err(
            "Leave type not found.", 422, errors={"leave_type_id": "invalid"}
        )

    if not leave_type.is_active:
        return None, err(
            f"'{leave_type.name}' is no longer available. Choose another leave type.",
            422,
            errors={"leave_type_id": "inactive"},
        )

    return leave_type, None


# ==========================================================
# LEAVE TYPES
# ==========================================================

@leave_bp.get("/types")
@require_auth
def list_leave_types():
    """The application form's dropdown. Everybody who can apply for leave can
    read this; only the inactive ones are hidden, and only from applicants —
    an administrator managing the catalogue asks for all of them."""

    current_user = get_current_user()

    include_inactive = (
        str(request.args.get("include_inactive")).lower() in ("1", "true", "yes")
        and has_permission(current_user, Permission.LEAVE_TYPE_MANAGE)
    )

    types = LeaveTypeService.all() if include_inactive else LeaveTypeService.active()

    return ok({"items": [serialize_leave_type(t) for t in types], "total": len(types)})


@leave_bp.post("/types")
@require_permission(Permission.LEAVE_TYPE_MANAGE)
def create_leave_type():
    current_user = get_current_user()

    try:
        leave_type = LeaveTypeService.create(_payload())
    except LeaveValidationError as exc:
        return _validation_error(exc)

    AuditService.log_action(
        current_user, AuditAction.LEAVE_TYPE_MANAGED,
        f"Created leave type '{leave_type.name}'.",
    )

    return ok(
        {"leave_type": serialize_leave_type(leave_type)},
        message="Leave type created.",
        status=201,
    )


@leave_bp.patch("/types/<int:type_id>")
@require_permission(Permission.LEAVE_TYPE_MANAGE)
def update_leave_type(type_id):
    current_user = get_current_user()

    leave_type = LeaveType.query.filter_by(id=type_id).first()

    if not leave_type:
        return err("Leave type not found.", 404)

    try:
        leave_type = LeaveTypeService.update(leave_type, _payload())
    except LeaveValidationError as exc:
        return _validation_error(exc)

    AuditService.log_action(
        current_user, AuditAction.LEAVE_TYPE_MANAGED,
        f"Updated leave type '{leave_type.name}'.",
    )

    return ok({"leave_type": serialize_leave_type(leave_type)}, message="Leave type updated.")


# ==========================================================
# LEAVE REQUESTS
# ==========================================================

@leave_bp.get("")
@require_auth
def list_leave_requests():
    """One endpoint, three answers, decided entirely by the authenticated
    identity: a staff member gets their own requests, a reviewer gets the
    organization's. Query parameters can only narrow that set — passing
    ?employee_id= as a staff member filters within your own rows, it does not
    reach anybody else's."""

    current_user = get_current_user()

    query = LeaveService.scoped_query(current_user)
    query = LeaveService.apply_filters(query, request.args)

    return ok(paginate(query, serialize_leave_request))


@leave_bp.get("/summary")
@require_auth
def leave_summary():
    """Headline counters over the same scoped set the list returns, so the
    numbers on a dashboard can never describe records the viewer is not
    allowed to see."""

    current_user = get_current_user()

    scoped = LeaveService.scoped_query(current_user)

    return ok({
        "summary": LeaveService.summary(scoped),
        "balances": LeaveService.balances_for(current_user),
        "can_review": has_permission(current_user, Permission.LEAVE_REVIEW),
        "can_view_all": has_permission(current_user, Permission.LEAVE_VIEW_ALL),
        "can_manage_types": has_permission(current_user, Permission.LEAVE_TYPE_MANAGE),
    })


@leave_bp.get("/on-leave")
@require_permission(Permission.LEAVE_VIEW_ALL)
def on_leave_today():
    """Who is away right now, and who is away next. Feeds the Manager/HR
    "currently on leave" strip and answers the everyday question a task
    assigner actually has."""

    today = app_today()

    current = LeaveService.approved_leave_between(today, today)

    upcoming = LeaveRequest.query.filter(
        LeaveRequest.status == LeaveStatus.APPROVED,
        LeaveRequest.start_date > today,
    ).order_by(LeaveRequest.start_date.asc()).limit(20).all()

    return ok({
        "on_leave": [serialize_leave_request(leave) for leave in current],
        "upcoming": [serialize_leave_request(leave) for leave in upcoming],
        "as_of": today.isoformat(),
    })


@leave_bp.get("/availability")
@require_auth
def availability():
    """Does anybody have approved leave in this window?

    Read by the task-assignment screen before it assigns work. Returns leave
    only for the employees asked about, and only the approved ones — never a
    pending application, which is nobody's business until it is decided.

    Authorization note: this deliberately exposes a narrow slice (name, leave
    type, dates) to anyone who may assign work, because scheduling around
    somebody's absence requires knowing about it. Callers without
    LEAVE_VIEW_ALL only ever get their own record back."""

    current_user = get_current_user()

    try:
        start = datetime.fromisoformat(request.args.get("start", "")).date()
        end = datetime.fromisoformat(request.args.get("end") or request.args.get("start", "")).date()
    except (TypeError, ValueError):
        return err("Provide a valid start (and optional end) date.", 422,
                   errors={"start": "required"})

    if end < start:
        start, end = end, start

    raw_ids = request.args.get("employee_ids") or request.args.get("employee_id") or ""

    employee_ids = [int(part) for part in str(raw_ids).split(",") if part.strip().isdigit()]

    if not has_permission(current_user, Permission.LEAVE_VIEW_ALL):
        employee_ids = [current_user.id]

    conflicts = LeaveService.conflicts_by_employee(start, end, employee_ids or None)

    return ok({
        "start": start.isoformat(),
        "end": end.isoformat(),
        "conflicts": {
            str(employee_id): [serialize_leave_conflict(leave) for leave in leaves]
            for employee_id, leaves in conflicts.items()
        },
    })


@leave_bp.get("/employees/<int:employee_id>/history")
@require_permission(Permission.LEAVE_VIEW_ALL)
def employee_leave_history(employee_id):
    """One employee's complete leave record — what HR and the Manager need
    before deciding the request in front of them."""

    employee = User.query.filter(
        User.id == employee_id, User.deleted_at.is_(None)
    ).first()

    if not employee:
        return err("Employee not found.", 404)

    history = LeaveRequest.query.filter_by(employee_id=employee.id).order_by(
        LeaveRequest.start_date.desc()
    ).all()

    approved_days = sum(
        float(leave.days) for leave in history if leave.status == LeaveStatus.APPROVED
    )

    return ok({
        "employee": serialize_user(employee),
        "items": [serialize_leave_request(leave) for leave in history],
        "total": len(history),
        "approved_days": round(approved_days, 1),
        "balances": LeaveService.balances_for(employee),
    })


@leave_bp.get("/<int:leave_id>")
@require_auth
def get_leave_request(leave_id):
    current_user = get_current_user()

    leave_request = _visible_request(leave_id, current_user)

    if not leave_request:
        return err("Leave request not found.", 404)

    return ok({
        "leave_request": serialize_leave_request(
            leave_request, include_timeline=True, include_balance=True
        ),
        "can_review": LeaveService.can_review(current_user, leave_request) is None,
        "can_cancel": LeaveService.can_cancel(current_user, leave_request) is None,
    })


@leave_bp.post("")
@require_permission(Permission.LEAVE_APPLY)
def create_leave_request():
    """Apply for leave.

    The applicant is always the authenticated user — there is no employee_id
    in this payload and no way to file an application in somebody else's
    name. Every request starts PENDING; nothing here can produce an approved
    record."""

    current_user = get_current_user()
    data = _payload()

    leave_type, error = _resolve_leave_type(data.get("leave_type_id"))

    if error:
        return error

    try:
        leave_request = LeaveService.create(data, current_user, leave_type)
    except LeaveValidationError as exc:
        return _validation_error(exc)

    LeaveService.notify_submitted(leave_request)

    AuditService.log_action(
        current_user, AuditAction.LEAVE_REQUEST_CREATED,
        (
            f"Applied for {leave_type.name} from "
            f"{leave_request.start_date.isoformat()} to {leave_request.end_date.isoformat()} "
            f"({leave_request.days} day(s))."
        ),
        target_type=CommentTargetType.LEAVE_REQUEST, target_id=leave_request.id,
    )

    return ok(
        {"leave_request": serialize_leave_request(leave_request)},
        message="Leave request submitted for review.",
        status=201,
    )


@leave_bp.patch("/<int:leave_id>")
@require_auth
def update_leave_request(leave_id):
    """Amend an application that has not been decided yet.

    Only the applicant may edit their own request, and only while it is still
    PENDING — a reviewer cannot rewrite the dates or reason of somebody's
    application, because then the record would no longer be what the employee
    actually asked for."""

    current_user = get_current_user()

    leave_request = _visible_request(leave_id, current_user)

    if not leave_request:
        return err("Leave request not found.", 404)

    if leave_request.employee_id != current_user.id:
        return err("You can only edit your own leave request.", 403)

    if leave_request.status != LeaveStatus.PENDING:
        return err(
            f"This request has already been {leave_request.status.value.lower()} "
            "and can no longer be edited.",
            409,
        )

    data = _payload()

    leave_type = leave_request.leave_type

    if data.get("leave_type_id") and data["leave_type_id"] != leave_request.leave_type_id:
        leave_type, error = _resolve_leave_type(data["leave_type_id"])

        if error:
            return error

    try:
        leave_request = LeaveService.update(leave_request, data, leave_type=leave_type)
    except LeaveValidationError as exc:
        return _validation_error(exc)

    AuditService.log_action(
        current_user, AuditAction.LEAVE_REQUEST_CREATED,
        "Updated their pending leave request.",
        target_type=CommentTargetType.LEAVE_REQUEST, target_id=leave_request.id,
    )

    return ok(
        {"leave_request": serialize_leave_request(leave_request, include_timeline=True)},
        message="Leave request updated.",
    )


@leave_bp.post("/<int:leave_id>/approve")
@require_permission(Permission.LEAVE_REVIEW)
def approve_leave_request(leave_id):
    """HR, the Operational Manager or the Super Admin approves.

    The @require_permission guard is the outer gate; LeaveService.can_review()
    is the inner one, and it is the guard that matters — it refuses a
    self-review and a second decision on an already-decided request. A staff
    member calling this endpoint with a known id never reaches either: they
    are stopped by the permission check, and would be stopped again by the
    scoped lookup."""

    current_user = get_current_user()

    leave_request = _visible_request(leave_id, current_user)

    if not leave_request:
        return err("Leave request not found.", 404)

    refusal = LeaveService.can_review(current_user, leave_request)

    if refusal:
        return err(*refusal)

    data = _payload()
    comment = (data.get("comment") or data.get("review_comment") or "").strip()

    leave_request = LeaveService.decide(
        leave_request, current_user, approved=True, comment=comment
    )

    LeaveService.notify_decision(leave_request, current_user)

    AuditService.log_action(
        current_user, AuditAction.LEAVE_REQUEST_APPROVED,
        (
            f"Approved {leave_request.leave_type.name} for "
            f"{leave_request.employee.full_name} "
            f"({leave_request.start_date.isoformat()} to {leave_request.end_date.isoformat()})."
            + (f" Comment: {comment}" if comment else "")
        ),
        target_type=CommentTargetType.LEAVE_REQUEST, target_id=leave_request.id,
    )

    return ok(
        {"leave_request": serialize_leave_request(leave_request, include_timeline=True)},
        message="Leave request approved.",
    )


@leave_bp.post("/<int:leave_id>/reject")
@require_permission(Permission.LEAVE_REVIEW)
def reject_leave_request(leave_id):
    """Refuse a request. A reason is mandatory — an employment record that
    says "rejected" with nothing beside it is not one the employee can act
    on, and it is exactly what the paper form's Comments box exists for."""

    current_user = get_current_user()

    leave_request = _visible_request(leave_id, current_user)

    if not leave_request:
        return err("Leave request not found.", 404)

    refusal = LeaveService.can_review(current_user, leave_request)

    if refusal:
        return err(*refusal)

    data = _payload()
    comment = (data.get("comment") or data.get("reason") or data.get("review_comment") or "").strip()

    if len(comment) < 5:
        return err(
            "Give a reason for the rejection — the employee sees this.",
            422,
            errors={"comment": "required"},
        )

    leave_request = LeaveService.decide(
        leave_request, current_user, approved=False, comment=comment
    )

    LeaveService.notify_decision(leave_request, current_user)

    AuditService.log_action(
        current_user, AuditAction.LEAVE_REQUEST_REJECTED,
        (
            f"Rejected {leave_request.leave_type.name} for "
            f"{leave_request.employee.full_name} "
            f"({leave_request.start_date.isoformat()} to {leave_request.end_date.isoformat()}). "
            f"Reason: {comment}"
        ),
        target_type=CommentTargetType.LEAVE_REQUEST, target_id=leave_request.id,
    )

    return ok(
        {"leave_request": serialize_leave_request(leave_request, include_timeline=True)},
        message="Leave request rejected.",
    )


@leave_bp.post("/<int:leave_id>/cancel")
@require_auth
def cancel_leave_request(leave_id):
    """Withdraw a request. The employee may cancel their own at any point
    before or after approval; a reviewer may cancel anybody's, which is how
    approved leave gets recalled when circumstances change."""

    current_user = get_current_user()

    leave_request = _visible_request(leave_id, current_user)

    if not leave_request:
        return err("Leave request not found.", 404)

    refusal = LeaveService.can_cancel(current_user, leave_request)

    if refusal:
        return err(*refusal)

    reason = (_payload().get("reason") or "").strip()

    is_owner = leave_request.employee_id == current_user.id

    # Somebody cancelling another person's leave has to say why; withdrawing
    # your own application needs no justification.
    if not is_owner and len(reason) < 5:
        return err(
            "Give a reason for cancelling this employee's leave.",
            422,
            errors={"reason": "required"},
        )

    leave_request = LeaveService.cancel(leave_request, current_user, reason=reason)

    LeaveService.notify_cancelled(leave_request, current_user)

    AuditService.log_action(
        current_user, AuditAction.LEAVE_REQUEST_CANCELLED,
        (
            f"Cancelled {leave_request.leave_type.name} for "
            f"{leave_request.employee.full_name} "
            f"({leave_request.start_date.isoformat()} to {leave_request.end_date.isoformat()})."
            + (f" Reason: {reason}" if reason else "")
        ),
        target_type=CommentTargetType.LEAVE_REQUEST, target_id=leave_request.id,
    )

    return ok(
        {"leave_request": serialize_leave_request(leave_request, include_timeline=True)},
        message="Leave request cancelled.",
    )


# ==========================================================
# SUPPORTING DOCUMENTS
# ==========================================================

@leave_bp.post("/<int:leave_id>/attachments")
@require_auth
def upload_attachment(leave_id):
    """Attach a supporting document — the medical certificate sick leave
    needs, or anything else HR asks for.

    Only the applicant attaches to their own request, and only while it is
    still pending: a document added after a decision would change the
    evidence the decision was made on."""

    current_user = get_current_user()

    leave_request = _visible_request(leave_id, current_user)

    if not leave_request:
        return err("Leave request not found.", 404)

    if leave_request.employee_id != current_user.id:
        return err("You can only attach documents to your own leave request.", 403)

    if leave_request.status != LeaveStatus.PENDING:
        return err(
            "Documents can only be attached while the request is still pending.", 409
        )

    if len(leave_request.attachments) >= 5:
        return err("A leave request can hold at most 5 documents.", 422,
                   errors={"file": "too_many"})

    uploaded = request.files.get("file") or request.files.get("attachment")

    if uploaded is None:
        return err("No file was uploaded.", 422, errors={"file": "required"})

    try:
        attachment = LeaveService.add_attachment(leave_request, uploaded, current_user)
    except LeaveValidationError as exc:
        return _validation_error(exc)

    return ok(
        {
            "attachment": serialize_leave_attachment(attachment),
            "leave_request": serialize_leave_request(leave_request),
        },
        message="Document attached.",
        status=201,
    )


@leave_bp.get("/<int:leave_id>/attachments/<int:attachment_id>")
@require_auth
def download_attachment(leave_id, attachment_id):
    """Serve a leave document.

    Authorization is re-derived here on every hit rather than trusted from
    whatever page produced the link: the request must be one the caller can
    see at all, and the attachment must belong to that request. A staff member
    who guesses another employee's attachment id gets a 404 from the scoped
    lookup, not a document.

    Sent as an attachment with a fixed disposition so a stored HTML or SVG
    payload can never execute in the application's own origin."""

    current_user = get_current_user()

    leave_request = _visible_request(leave_id, current_user)

    if not leave_request:
        return err("Leave request not found.", 404)

    if not LeaveService.can_view_attachment(current_user, leave_request):
        return err("You do not have permission to view this document.", 403)

    attachment = LeaveAttachment.query.filter_by(
        id=attachment_id, leave_request_id=leave_request.id
    ).first()

    if not attachment:
        return err("Document not found.", 404)

    safe_name = attachment.file_name.replace('"', "").replace("\r", "").replace("\n", "")

    return Response(
        attachment.content,
        mimetype=attachment.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Content-Length": str(attachment.file_size),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@leave_bp.delete("/<int:leave_id>/attachments/<int:attachment_id>")
@require_auth
def delete_attachment(leave_id, attachment_id):
    """Remove a document you attached, while the request is still pending."""

    from extensions import db

    current_user = get_current_user()

    leave_request = _visible_request(leave_id, current_user)

    if not leave_request:
        return err("Leave request not found.", 404)

    if leave_request.employee_id != current_user.id:
        return err("You can only remove documents from your own leave request.", 403)

    if leave_request.status != LeaveStatus.PENDING:
        return err(
            "Documents can only be removed while the request is still pending.", 409
        )

    attachment = LeaveAttachment.query.filter_by(
        id=attachment_id, leave_request_id=leave_request.id
    ).first()

    if not attachment:
        return err("Document not found.", 404)

    db.session.delete(attachment)
    db.session.commit()

    return ok(
        {"leave_request": serialize_leave_request(leave_request)},
        message="Document removed.",
    )
