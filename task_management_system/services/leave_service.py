from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func

from extensions import db
from models.user import User
from models.enums import (
    LeaveStatus,
    UserRole,
    NotificationType,
    NotificationPriority,
)
from models.leave_type import LeaveType
from models.leave_request import LeaveRequest, LeaveAttachment
from utils.appdate import app_today
from utils.enum_map import leave_status_from_fe
from utils.rbac import Permission, has_permission, permissions_for
from services.notification_service import NotificationService


# A request in one of these states still occupies the employee's calendar, so
# it is what the overlap check tests against. A REJECTED or CANCELLED request
# blocks nothing — the employee is free to apply for those dates again.
BLOCKING_STATUSES = (LeaveStatus.PENDING, LeaveStatus.APPROVED)


class LeaveValidationError(Exception):
    """A business-rule refusal with a field-level breakdown, raised by the
    service and turned into the app's standard 422 envelope by the route.
    Separate from a plain ValueError so a genuine bug never gets reported to
    the user as a validation message."""

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.message = message
        self.errors = errors or {}


def _parse_date(value, field):
    if not value:
        raise LeaveValidationError("A start and end date are required.", {field: "required"})

    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        raise LeaveValidationError(
            "Invalid date — expected YYYY-MM-DD.", {field: "invalid"}
        ) from None


class LeaveService:
    """Leave applications, their review, and everything derived from them.

    Built entirely on the machinery the application already has: scoping
    follows the same scoped_query() idiom as tasks and queries, decisions are
    announced through NotificationService, and every
    transition is recorded by AuditService from the route. What this service
    owns that nothing else could express is the leave calendar itself — the
    overlap rule, the notice/backdating policy, and "who is away on a given
    date", which the task-assignment warning reads."""

    # ==================================================================
    # SCOPE
    # ==================================================================

    @staticmethod
    def scoped_query(current_user):
        """The single authority on which leave rows a user may see.

        Anyone without LEAVE_VIEW_ALL sees their own requests and nothing
        else — the filter is applied here, on the server, from the
        authenticated identity. No route accepts an employee_id that widens
        this; the filters below can only narrow what this returns."""

        query = LeaveRequest.query

        if not has_permission(current_user, Permission.LEAVE_VIEW_ALL):
            return query.filter(LeaveRequest.employee_id == current_user.id)

        return query

    @staticmethod
    def apply_filters(query, args):
        employee_id = args.get("employee_id")
        department_id = args.get("department_id")
        leave_type_id = args.get("leave_type_id")
        status = args.get("status")
        date_from = args.get("date_from") or args.get("start")
        date_to = args.get("date_to") or args.get("end")
        search = args.get("search")

        if employee_id:
            query = query.filter(LeaveRequest.employee_id == employee_id)

        if leave_type_id:
            query = query.filter(LeaveRequest.leave_type_id == leave_type_id)

        if status and str(status).lower() != "all":
            parsed = leave_status_from_fe(status)
            if parsed is not None:
                query = query.filter(LeaveRequest.status == parsed)

        if department_id or search:
            query = query.join(User, LeaveRequest.employee_id == User.id)

        if department_id:
            query = query.filter(User.department_id == department_id)

        if search:
            like = f"%{search}%"
            query = query.filter(
                db.or_(
                    User.first_name.ilike(like),
                    User.last_name.ilike(like),
                    User.employee_number.ilike(like),
                    LeaveRequest.reason.ilike(like),
                )
            )

        # Overlap semantics, not containment: a range filter returns every
        # request that touches the window, so a leave spanning the boundary
        # is never invisible in a date-filtered view.
        for raw, column_filter in (
            (date_from, lambda d: LeaveRequest.end_date >= d),
            (date_to, lambda d: LeaveRequest.start_date <= d),
        ):
            if raw:
                try:
                    query = query.filter(column_filter(datetime.fromisoformat(str(raw)).date()))
                except (TypeError, ValueError):
                    pass

        return query.order_by(
            LeaveRequest.created_at.desc(),
            LeaveRequest.id.desc(),
        )

    # ==================================================================
    # AUTHORIZATION HELPERS
    # ==================================================================

    @staticmethod
    def can_review(actor, leave_request):
        """Whether `actor` may approve or reject this specific request.
        Returns None when allowed, otherwise (message, http_status) — the
        status travels with the reason so the route never has to infer 403
        vs 409 from the wording of a message.

        The self-review guard is the important one and is checked here rather
        than in the route: holding LEAVE_REVIEW makes a Manager, HR or Super
        Admin a reviewer of *other people's* leave, never of their own. Their
        own applications are decided by somebody else, exactly like a staff
        member's."""

        if not has_permission(actor, Permission.LEAVE_REVIEW):
            return "You do not have permission to review leave requests.", 403

        if leave_request.employee_id == actor.id:
            return "You cannot review your own leave request.", 403

        if leave_request.status != LeaveStatus.PENDING:
            return (
                f"This request has already been {leave_request.status.value.lower()}.",
                409,
            )

        return None

    @staticmethod
    def can_cancel(actor, leave_request):
        """The employee may withdraw their own request; a reviewer may cancel
        anyone's. Approved leave can still be cancelled — plans change — but
        a request that is already rejected or cancelled is closed."""

        is_owner = leave_request.employee_id == actor.id
        is_reviewer = has_permission(actor, Permission.LEAVE_REVIEW)

        if not (is_owner or is_reviewer):
            return "You do not have permission to cancel this leave request.", 403

        if leave_request.status in (LeaveStatus.REJECTED, LeaveStatus.CANCELLED):
            return f"This request is already {leave_request.status.value.lower()}.", 409

        return None

    @staticmethod
    def can_view_attachment(actor, leave_request):
        """Document access rides on the same rule as record access: you can
        open a leave document if and only if you are allowed to see the leave
        request it belongs to."""

        if leave_request.employee_id == actor.id:
            return True

        return has_permission(actor, Permission.LEAVE_VIEW_ALL)

    @staticmethod
    def reviewers(exclude_user_id=None):
        """Every active account that may decide a leave request, derived from
        the capability table rather than a hardcoded role list — granting
        LEAVE_REVIEW to a new role automatically starts notifying it."""

        roles = [
            role
            for role in UserRole
            if Permission.LEAVE_REVIEW in permissions_for(role)
        ]

        query = User.query.filter(
            User.role.in_(roles),
            User.deleted_at.is_(None),
        )

        if exclude_user_id is not None:
            query = query.filter(User.id != exclude_user_id)

        return [user for user in query.all() if user.is_active]

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def compute_days(start, end, is_half_day=False):
        """Inclusive calendar days between two dates — 15 Sept to 19 Sept is
        5 days, matching how the paper form is filled in. Half days are only
        meaningful on a single-date request.

        Calendar days, not working days, because this system holds no public
        holiday calendar and no configured working week; inventing one would
        produce a number the HR team could not reconcile against their own
        records."""

        if is_half_day:
            return Decimal("0.5")

        return Decimal((end - start).days + 1)

    @staticmethod
    def validate(data, employee, leave_type, exclude_request_id=None):
        """Every rule that decides whether an application is admissible.

        Runs server-side on create and on edit. The frontend mirrors some of
        this for a better form experience, but nothing here depends on the
        client having done so."""

        errors = {}

        start = _parse_date(data.get("start_date"), "start_date")
        end = _parse_date(data.get("end_date"), "end_date")

        is_half_day = bool(data.get("is_half_day"))

        if end < start:
            errors["end_date"] = "End date cannot be before the start date."

        if is_half_day and start != end:
            errors["is_half_day"] = "A half day must start and end on the same date."

        reason = (data.get("reason") or "").strip()

        if not reason:
            errors["reason"] = "A reason for the leave is required."
        elif len(reason) < 3:
            errors["reason"] = "Please give a meaningful reason."

        today = app_today()

        # Past-dated applications follow the leave type's own policy rather
        # than a blanket rule: sick and emergency leave is reported after the
        # fact by definition, planned leave is not.
        if start < today and not leave_type.allows_backdating:
            errors["start_date"] = (
                f"{leave_type.name} must be applied for in advance — "
                "it cannot start in the past."
            )

        # "Submit at least N days before commencement", per the company form.
        # Skipped for a backdated-capable type, where notice is meaningless.
        elif leave_type.min_notice_days and start >= today:
            earliest = today + timedelta(days=leave_type.min_notice_days)
            if start < earliest:
                errors["start_date"] = (
                    f"{leave_type.name} needs at least {leave_type.min_notice_days} "
                    f"days' notice — the earliest start date is {earliest.isoformat()}."
                )

        if errors:
            raise LeaveValidationError("Please correct the highlighted fields.", errors)

        # Overlap is checked last so the message is never buried under a
        # simpler field error the applicant should fix first.
        clash = LeaveService.find_overlap(
            employee.id, start, end, exclude_request_id=exclude_request_id
        )

        if clash:
            raise LeaveValidationError(
                (
                    f"You already have {clash.status.value.lower()} "
                    f"{clash.leave_type.name} from {clash.start_date.isoformat()} to "
                    f"{clash.end_date.isoformat()}. Cancel it first, or choose dates "
                    "that do not overlap."
                ),
                {"start_date": "overlap", "end_date": "overlap"},
            )

        return {
            "start_date": start,
            "end_date": end,
            "is_half_day": is_half_day,
            "days": LeaveService.compute_days(start, end, is_half_day),
            "reason": reason,
        }

    @staticmethod
    def find_overlap(employee_id, start, end, exclude_request_id=None):
        """The first still-live request of this employee's that intersects
        [start, end], or None.

        Two ranges overlap when each starts on or before the other ends —
        expressed in SQL so the check runs against the database, not against
        a list the client could have influenced."""

        query = LeaveRequest.query.filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_(BLOCKING_STATUSES),
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )

        if exclude_request_id:
            query = query.filter(LeaveRequest.id != exclude_request_id)

        return query.order_by(LeaveRequest.start_date.asc()).first()

    # ==================================================================
    # WRITES
    # ==================================================================

    @staticmethod
    def create(data, employee, leave_type):
        validated = LeaveService.validate(data, employee, leave_type)

        handover_to_id = data.get("handover_to_id")

        if handover_to_id:
            cover = User.query.filter(
                User.id == handover_to_id, User.deleted_at.is_(None)
            ).first()

            if not cover:
                raise LeaveValidationError(
                    "The person selected for handover was not found.",
                    {"handover_to_id": "invalid"},
                )

            if cover.id == employee.id:
                raise LeaveValidationError(
                    "You cannot hand your work over to yourself.",
                    {"handover_to_id": "invalid"},
                )

        request = LeaveRequest(
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            start_date=validated["start_date"],
            end_date=validated["end_date"],
            days=validated["days"],
            is_half_day=validated["is_half_day"],
            reason=validated["reason"],
            status=LeaveStatus.PENDING,
            submitted_at=datetime.utcnow(),
            # Defaults pulled from the applicant's own profile so the "contact
            # during leave" section is pre-filled with something correct
            # rather than left blank.
            contact_phone=(data.get("contact_phone") or employee.phone or None),
            contact_address=(data.get("contact_address") or None),
            handover_to_id=handover_to_id or None,
            handover_contact=(data.get("handover_contact") or None),
        )

        db.session.add(request)
        db.session.commit()

        return request

    @staticmethod
    def update(request, data, leave_type=None):
        """Amend a request that has not been decided yet. Deliberately does
        not touch status, reviewer or any timestamp — an edit is an edit, and
        the only path to a decided state is decide()."""

        target_type = leave_type or request.leave_type

        validated = LeaveService.validate(
            data, request.employee, target_type, exclude_request_id=request.id
        )

        request.leave_type_id = target_type.id
        request.start_date = validated["start_date"]
        request.end_date = validated["end_date"]
        request.days = validated["days"]
        request.is_half_day = validated["is_half_day"]
        request.reason = validated["reason"]

        for field in ("contact_phone", "contact_address", "handover_contact"):
            if field in data:
                setattr(request, field, data.get(field) or None)

        if "handover_to_id" in data:
            request.handover_to_id = data.get("handover_to_id") or None

        db.session.commit()

        return request

    @staticmethod
    def decide(request, reviewer, approved, comment=None):
        request.decide(reviewer, approved=approved, comment=comment)

        db.session.commit()

        return request

    @staticmethod
    def cancel(request, actor, reason=None):
        request.cancel(actor, reason=reason)

        db.session.commit()

        return request

    # ==================================================================
    # ATTACHMENTS
    # ==================================================================

    @staticmethod
    def add_attachment(request, uploaded_file, actor):
        """Store one supporting document against a request.

        Validated on what was actually received — the byte length of the file
        read into memory, and the browser-declared content type checked
        against a whitelist — rather than on a client-supplied size field."""

        file_name = (uploaded_file.filename or "").strip()

        if not file_name:
            raise LeaveValidationError("No file was selected.", {"file": "required"})

        content = uploaded_file.read()

        if not content:
            raise LeaveValidationError("The selected file is empty.", {"file": "empty"})

        if len(content) > LeaveAttachment.MAX_BYTES:
            raise LeaveValidationError(
                f"Documents must be {LeaveAttachment.MAX_BYTES // (1024 * 1024)} MB or smaller.",
                {"file": "too_large"},
            )

        content_type = (uploaded_file.mimetype or "").lower()

        if content_type not in LeaveAttachment.ALLOWED_CONTENT_TYPES:
            raise LeaveValidationError(
                "Supporting documents must be a PDF, Word document or image.",
                {"file": "unsupported_type"},
            )

        attachment = LeaveAttachment(
            leave_request_id=request.id,
            file_name=file_name[:255],
            content_type=content_type,
            file_size=len(content),
            content=content,
            uploaded_by=actor.id,
        )

        db.session.add(attachment)
        db.session.commit()

        return attachment

    # ==================================================================
    # DERIVED VIEWS
    # ==================================================================

    @staticmethod
    def summary(query):
        """Headline counters for a Leave Management dashboard, computed from
        the caller's already-scoped query so a staff member's summary counts
        only their own requests and a reviewer's counts the organization."""

        today = app_today()

        rows = query.with_entities(
            LeaveRequest.status, func.count(LeaveRequest.id)
        ).group_by(LeaveRequest.status).all()

        by_status = {status: count for status, count in rows}

        def _count(*extra_filters):
            return query.filter(*extra_filters).count()

        return {
            "total": sum(by_status.values()),
            "pending": by_status.get(LeaveStatus.PENDING, 0),
            "approved": by_status.get(LeaveStatus.APPROVED, 0),
            "rejected": by_status.get(LeaveStatus.REJECTED, 0),
            "cancelled": by_status.get(LeaveStatus.CANCELLED, 0),
            "on_leave_now": _count(
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date <= today,
                LeaveRequest.end_date >= today,
            ),
            "upcoming": _count(
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date > today,
            ),
        }

    @staticmethod
    def balance_for(employee, leave_type, year=None):
        """The form's "Days Avail." / "Days After" figures, derived rather
        than ledgered.

        `entitlement_days` on the leave type is the allowance; usage is the
        sum of APPROVED days in the calendar year. This is deliberately NOT
        an accrual system — there is no carry-over, no pro-rating and no
        opening balance, because the business has not specified any. A type
        with no entitlement configured reports None and the UI simply omits
        the figure."""

        if leave_type.entitlement_days is None:
            return None

        year = year or app_today().year

        used = db.session.query(
            func.coalesce(func.sum(LeaveRequest.days), 0)
        ).filter(
            LeaveRequest.employee_id == employee.id,
            LeaveRequest.leave_type_id == leave_type.id,
            LeaveRequest.status == LeaveStatus.APPROVED,
            func.extract("year", LeaveRequest.start_date) == year,
        ).scalar()

        used = float(used or 0)
        entitlement = float(leave_type.entitlement_days)

        return {
            "year": year,
            "entitlement_days": entitlement,
            "used_days": used,
            "remaining_days": round(entitlement - used, 1),
        }

    @staticmethod
    def balances_for(employee, year=None):
        """One row per active leave type that actually has an entitlement
        configured. Types with none are skipped entirely rather than reported
        as zero, so the UI shows nothing instead of implying an exhausted
        allowance that was never set."""

        balances = []

        for leave_type in LeaveTypeService.active():
            balance = LeaveService.balance_for(employee, leave_type, year)

            if balance is None:
                continue

            balances.append({
                "leave_type_id": leave_type.id,
                "leave_type": leave_type.name,
                "code": leave_type.code,
                **balance,
            })

        return balances

    @staticmethod
    def approved_leave_between(start, end, employee_ids=None):
        """Every approved leave overlapping a window, optionally narrowed to
        specific employees. This is the one query the task-assignment warning
        and the "currently away" strip both read, so both always agree."""

        query = LeaveRequest.query.filter(
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )

        if employee_ids:
            query = query.filter(LeaveRequest.employee_id.in_(employee_ids))

        return query.order_by(LeaveRequest.start_date.asc()).all()

    @staticmethod
    def conflicts_by_employee(start, end, employee_ids=None):
        """{employee_id: [LeaveRequest, ...]} for one date window — the shape
        the assignment screen needs to badge a whole employee list without a
        query per person."""

        conflicts = {}

        for leave in LeaveService.approved_leave_between(start, end, employee_ids):
            conflicts.setdefault(leave.employee_id, []).append(leave)

        return conflicts

    @staticmethod
    def leave_conflict_for_task(employee_id, assigned_date, due_date=None):
        """The approved leave, if any, covering the window a task would be
        worked in. Returns the record so the caller can name the dates in its
        warning — never blocks, by design: a manager may have a good reason to
        schedule across somebody's leave, and the system's job is to make sure
        they know they are doing it."""

        if not assigned_date:
            return None

        window_end = due_date or assigned_date

        if window_end < assigned_date:
            window_end = assigned_date

        matches = LeaveService.approved_leave_between(
            assigned_date, window_end, [employee_id]
        )

        return matches[0] if matches else None

    # ==================================================================
    # ANNOUNCEMENTS
    #
    # Both channels go through NotificationService.notify, which writes the
    # in-app record and sends the matching email. Leave used to send its own
    # mail here; it no longer does, so leave and every other module now
    # announce identically. There is deliberately no leave-specific
    # notification table or mailer.
    # ==================================================================

    @staticmethod
    def _period_label(request):
        if request.start_date == request.end_date:
            return request.start_date.strftime("%d %B %Y")

        return (
            f"{request.start_date.strftime('%d %B')} – "
            f"{request.end_date.strftime('%d %B %Y')}"
        )

    @staticmethod
    def _announce(recipient, title, message, sender=None, priority=NotificationPriority.NORMAL,
                  action_url=None, email=True):
        NotificationService.notify(
            recipient=recipient,
            sender=sender,
            title=title,
            message=message,
            notification_type=NotificationType.LEAVE_REQUEST,
            priority=priority,
            action_url=action_url,
            email=email,
        )

    @staticmethod
    def notify_submitted(request):
        """Everyone who may decide this request hears about it — except the
        applicant, who cannot review their own."""

        period = LeaveService._period_label(request)
        employee = request.employee

        for reviewer in LeaveService.reviewers(exclude_user_id=employee.id):
            LeaveService._announce(
                recipient=reviewer,
                sender=employee,
                title="Leave request awaiting review",
                message=(
                    f"{employee.full_name} has applied for "
                    f"{request.leave_type.name} ({period}, {request.days} day"
                    f"{'' if float(request.days) == 1 else 's'}). Reason: {request.reason}"
                ),
                priority=NotificationPriority.HIGH,
                action_url="/leave-management",
            )

    @staticmethod
    def notify_decision(request, reviewer):
        period = LeaveService._period_label(request)
        approved = request.status == LeaveStatus.APPROVED

        message = (
            f"Your {request.leave_type.name} request for {period} has been "
            f"{'approved' if approved else 'rejected'} by {reviewer.full_name}."
        )

        if request.review_comment:
            message += f" Reason: {request.review_comment}"

        LeaveService._announce(
            recipient=request.employee,
            sender=reviewer,
            title=f"Leave request {'approved' if approved else 'rejected'}",
            message=message,
            priority=NotificationPriority.HIGH if not approved else NotificationPriority.NORMAL,
            action_url="/my-leave",
        )

        # The nominated cover only needs to know once the leave is real.
        if approved and request.handover_to:
            LeaveService._announce(
                recipient=request.handover_to,
                sender=reviewer,
                title="You are covering approved leave",
                message=(
                    f"{request.employee.full_name} is on approved "
                    f"{request.leave_type.name} for {period}, with you named as handover."
                ),
                action_url="/my-leave",
                email=False,
            )

    @staticmethod
    def notify_cancelled(request, actor):
        period = LeaveService._period_label(request)

        if actor.id == request.employee_id:
            # The employee withdrew it — tell the reviewers so a pending item
            # disappears from their queue with an explanation.
            for reviewer in LeaveService.reviewers(exclude_user_id=actor.id):
                LeaveService._announce(
                    recipient=reviewer,
                    sender=actor,
                    title="Leave request withdrawn",
                    message=(
                        f"{actor.full_name} withdrew their {request.leave_type.name} "
                        f"request for {period}."
                    ),
                    action_url="/leave-management",
                    email=False,
                )
            return

        message = (
            f"Your {request.leave_type.name} for {period} was cancelled by "
            f"{actor.full_name}."
        )

        if request.cancellation_reason:
            message += f" Reason: {request.cancellation_reason}"

        LeaveService._announce(
            recipient=request.employee,
            sender=actor,
            title="Leave cancelled",
            message=message,
            priority=NotificationPriority.HIGH,
            action_url="/my-leave",
        )


class LeaveTypeService:
    """The leave type catalogue. Small enough not to need its own module, but
    kept separate from LeaveService because its authorization is different:
    applying for leave and defining what leave exists are different powers."""

    @staticmethod
    def active():
        return (
            LeaveType.query.filter_by(is_active=True)
            .order_by(LeaveType.sort_order.asc(), LeaveType.name.asc())
            .all()
        )

    @staticmethod
    def all():
        return LeaveType.query.order_by(
            LeaveType.sort_order.asc(), LeaveType.name.asc()
        ).all()

    BOOLEAN_FIELDS = ("requires_attachment", "allows_backdating", "is_paid", "is_active")

    INTEGER_FIELDS = ("min_notice_days", "sort_order")

    @staticmethod
    def _code_from_name(name):
        cleaned = "".join(ch if ch.isalnum() else "_" for ch in name.upper())

        return "_".join(part for part in cleaned.split("_") if part)[:30]

    @staticmethod
    def create(data):
        name = (data.get("name") or "").strip()

        if not name:
            raise LeaveValidationError(
                "A name is required.", {"name": "required"}
            )

        if LeaveType.query.filter(func.lower(LeaveType.name) == name.lower()).first():
            raise LeaveValidationError(
                f"A leave type called '{name}' already exists.", {"name": "duplicate"}
            )

        code = (data.get("code") or LeaveTypeService._code_from_name(name)).strip().upper()

        if LeaveType.query.filter_by(code=code).first():
            raise LeaveValidationError(
                f"The code '{code}' is already in use.", {"code": "duplicate"}
            )

        leave_type = LeaveType(name=name, code=code)

        LeaveTypeService._apply(leave_type, data)

        db.session.add(leave_type)
        db.session.commit()

        return leave_type

    @staticmethod
    def update(leave_type, data):
        if data.get("name"):
            name = data["name"].strip()

            clash = LeaveType.query.filter(
                func.lower(LeaveType.name) == name.lower(), LeaveType.id != leave_type.id
            ).first()

            if clash:
                raise LeaveValidationError(
                    f"A leave type called '{name}' already exists.", {"name": "duplicate"}
                )

            leave_type.name = name

        LeaveTypeService._apply(leave_type, data)

        db.session.commit()

        return leave_type

    @staticmethod
    def _apply(leave_type, data):
        if "description" in data:
            leave_type.description = (data.get("description") or "").strip() or None

        for field in LeaveTypeService.BOOLEAN_FIELDS:
            if field in data:
                setattr(leave_type, field, bool(data.get(field)))

        for field in LeaveTypeService.INTEGER_FIELDS:
            if field in data and data.get(field) is not None:
                try:
                    setattr(leave_type, field, max(0, int(data[field])))
                except (TypeError, ValueError):
                    raise LeaveValidationError(
                        f"'{field}' must be a whole number.", {field: "invalid"}
                    ) from None

        if "entitlement_days" in data:
            raw = data.get("entitlement_days")

            if raw in (None, ""):
                leave_type.entitlement_days = None
            else:
                try:
                    leave_type.entitlement_days = max(0, int(raw))
                except (TypeError, ValueError):
                    raise LeaveValidationError(
                        "Entitlement must be a whole number of days.",
                        {"entitlement_days": "invalid"},
                    ) from None

    # The catalogue every deployment starts with — taken from the company's
    # own EMPLOYEE LEAVE APPLICATION FORM, including the "Off Day" that the
    # Survitec example writes into the form's "Other" box. Seeded once and
    # then owned by HR: nothing in the code refers to any of these by name.
    DEFAULTS = [
        {
            "name": "Annual Leave", "code": "ANNUAL", "sort_order": 1,
            "entitlement_days": 21, "min_notice_days": 3,
            "description": "Planned paid time off from the yearly entitlement.",
        },
        {
            "name": "Sick Leave", "code": "SICK", "sort_order": 2,
            "allows_backdating": True, "requires_attachment": True,
            "description": "Illness or injury. A medical document is required.",
        },
        {
            "name": "Maternity Leave", "code": "MATERNITY", "sort_order": 3,
            "allows_backdating": True, "requires_attachment": True,
            "description": "Statutory maternity leave.",
        },
        {
            "name": "Paternity Leave", "code": "PATERNITY", "sort_order": 4,
            "allows_backdating": True,
            "description": "Statutory paternity leave.",
        },
        {
            "name": "Compassionate Leave", "code": "COMPASSIONATE", "sort_order": 5,
            "allows_backdating": True,
            "description": "Bereavement or a family emergency.",
        },
        {
            "name": "Emergency Leave", "code": "EMERGENCY", "sort_order": 6,
            "allows_backdating": True,
            "description": "Unforeseen circumstances requiring immediate absence.",
        },
        {
            "name": "Off Day", "code": "OFF_DAY", "sort_order": 7,
            "description": "A single day or half day off.",
        },
        {
            "name": "Unpaid Leave", "code": "UNPAID", "sort_order": 8,
            "is_paid": False, "min_notice_days": 3,
            "description": "Approved absence without pay.",
        },
        {
            "name": "Other", "code": "OTHER", "sort_order": 99,
            "description": "Anything not covered above — state the reason in full.",
        },
    ]

    @staticmethod
    def seed_defaults():
        """Idempotent, matched on `code`. Never overwrites a type HR has
        already edited and never reactivates one they retired."""

        created = 0

        for spec in LeaveTypeService.DEFAULTS:
            if LeaveType.query.filter_by(code=spec["code"]).first():
                continue

            db.session.add(LeaveType(**spec))
            created += 1

        if created:
            db.session.commit()

        return created
