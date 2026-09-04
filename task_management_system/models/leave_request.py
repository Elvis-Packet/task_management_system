from datetime import datetime

from sqlalchemy.orm import deferred

from extensions import db

from models.enums import LeaveStatus


class LeaveRequest(db.Model):
    """One employee's application for time off, and the single reviewed
    decision made on it.

    Modelled on the company's own EMPLOYEE LEAVE APPLICATION FORM, section by
    section: employee information comes from the User relationship (never
    duplicated onto this row), section 2 is the leave detail below, section 3
    the reason, section 4 the contact/handover block, section 5 the
    authorization — reviewed_by / reviewer_role / reviewed_at /
    review_comment.

    A request never silently becomes approved. `status` only leaves PENDING
    through decide() or cancel(), both of which stamp who acted and when, and
    both of which are invoked from LeaveService so the audit entry and
    notification are written in the same place as the transition."""

    __tablename__ = "leave_requests"

    __table_args__ = (
        # The two hot paths: "this employee's leave history" and the overlap
        # check, which scans one employee's live requests by date range.
        db.Index("idx_leave_request_employee_status", "employee_id", "status"),
        db.Index("idx_leave_request_dates", "start_date", "end_date"),
        db.Index("idx_leave_request_status_start", "status", "start_date"),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    leave_type_id = db.Column(
        db.Integer,
        db.ForeignKey("leave_types.id"),
        nullable=False,
        index=True
    )

    # --- Section 2: leave details -----------------------------------------

    start_date = db.Column(
        db.Date,
        nullable=False
    )

    end_date = db.Column(
        db.Date,
        nullable=False
    )

    # Numeric rather than Integer so the form's "Half Day? ☐ Yes ☐ No" can be
    # recorded honestly as 0.5 instead of being rounded to a whole day.
    # Always computed server-side by LeaveService — never trusted from the
    # client, or the days figure would stop matching the dates beside it.
    days = db.Column(
        db.Numeric(5, 1),
        nullable=False
    )

    is_half_day = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    # --- Section 3: reason -------------------------------------------------

    reason = db.Column(
        db.Text,
        nullable=False
    )

    # --- Section 4: contact during leave -----------------------------------

    contact_phone = db.Column(
        db.String(30)
    )

    contact_address = db.Column(
        db.String(255)
    )

    # Who is covering the work. A real User where possible, so a manager can
    # see the cover arrangement against an actual account rather than a name
    # typed into a box; free-text contact number kept alongside because the
    # paper form allows a cover person who has no system account.
    handover_to_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    handover_contact = db.Column(
        db.String(30)
    )

    # --- Lifecycle ---------------------------------------------------------

    status = db.Column(
        db.Enum(LeaveStatus),
        default=LeaveStatus.PENDING,
        nullable=False,
        index=True
    )

    submitted_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # --- Section 5: authorization -----------------------------------------

    reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    # The role the reviewer held at the moment of the decision. The paper form
    # has separate "Line Manager Approval" and "HR Approval" signature blocks;
    # storing the role here keeps that distinction readable years later, even
    # if the reviewer's own role changes afterwards.
    reviewer_role = db.Column(
        db.String(30)
    )

    reviewed_at = db.Column(
        db.DateTime
    )

    # The form's "Comments" box. Optional on approval, mandatory on rejection
    # — enforced in the route, because "rejected, no reason given" is not an
    # acceptable employment record.
    review_comment = db.Column(
        db.Text
    )

    # --- Withdrawal --------------------------------------------------------

    cancelled_at = db.Column(
        db.DateTime
    )

    cancelled_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    cancellation_reason = db.Column(
        db.Text
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # --- Relationships -----------------------------------------------------

    employee = db.relationship(
        "User",
        foreign_keys=[employee_id],
        backref=db.backref("leave_requests", lazy="dynamic")
    )

    leave_type = db.relationship(
        "LeaveType",
        back_populates="requests"
    )

    reviewer = db.relationship(
        "User",
        foreign_keys=[reviewed_by]
    )

    canceller = db.relationship(
        "User",
        foreign_keys=[cancelled_by]
    )

    handover_to = db.relationship(
        "User",
        foreign_keys=[handover_to_id]
    )

    # --- Derived state -----------------------------------------------------

    @property
    def is_pending(self):
        return self.status == LeaveStatus.PENDING

    @property
    def is_approved(self):
        return self.status == LeaveStatus.APPROVED

    @property
    def is_decided(self):
        return self.status != LeaveStatus.PENDING

    @property
    def is_active_today(self):
        """Approved and today falls inside the leave period — "currently on
        leave" on the Manager/HR dashboard."""

        if not self.is_approved:
            return False

        from utils.appdate import app_today

        return self.start_date <= app_today() <= self.end_date

    @property
    def is_upcoming(self):
        if not self.is_approved:
            return False

        from utils.appdate import app_today

        return self.start_date > app_today()

    def covers(self, day):
        return self.start_date <= day <= self.end_date

    # --- Transitions -------------------------------------------------------

    def decide(self, reviewer, approved, comment=None):
        """PENDING -> APPROVED | REJECTED, exactly once. The reviewer, their
        role, the timestamp and the comment are all written together — there
        is no code path that sets `status` to a decided value without them."""

        self.status = LeaveStatus.APPROVED if approved else LeaveStatus.REJECTED

        self.reviewed_by = reviewer.id

        self.reviewer_role = reviewer.role.value

        self.reviewed_at = datetime.utcnow()

        self.review_comment = (comment or "").strip() or None

    def cancel(self, actor, reason=None):
        """Withdrawal. Distinct from rejection: cancelling is the employee (or
        an authorized reviewer) taking the request off the table, and it keeps
        its own actor/timestamp so the record never confuses "I changed my
        mind" with "this was refused"."""

        self.status = LeaveStatus.CANCELLED

        self.cancelled_by = actor.id

        self.cancelled_at = datetime.utcnow()

        self.cancellation_reason = (reason or "").strip() or None

    def __repr__(self):
        return (
            f"<LeaveRequest #{self.id} employee={self.employee_id} "
            f"{self.start_date}..{self.end_date} {self.status.value}>"
        )


class LeaveAttachment(db.Model):
    """A supporting document on a leave request — the medical certificate a
    sick-leave application needs, and anything else HR asks for.

    The bytes live in Postgres rather than on disk because this application
    has no object-storage integration and its hosting filesystem is ephemeral;
    a file written to disk would be gone on the next deploy. Kept in its own
    table (not a column on leave_requests) so listing or filtering leave never
    loads a single byte of document content — the relationship is lazy and
    only the download route ever touches `content`.

    If object storage is introduced later, only `content` is replaced by a
    key/URL column: every other field, the access-control rule and the route
    stay exactly as they are."""

    __tablename__ = "leave_attachments"

    # 5 MB. Large enough for a scanned certificate, small enough that a row
    # never becomes a denial-of-service vector against the database.
    MAX_BYTES = 5 * 1024 * 1024

    ALLOWED_CONTENT_TYPES = {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    leave_request_id = db.Column(
        db.Integer,
        db.ForeignKey("leave_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    file_name = db.Column(
        db.String(255),
        nullable=False
    )

    content_type = db.Column(
        db.String(120),
        nullable=False
    )

    file_size = db.Column(
        db.Integer,
        nullable=False
    )

    # Deferred: never loaded by a SELECT unless the download route explicitly
    # asks for it, so listing a request's attachments costs metadata only.
    content = deferred(
        db.Column(
            db.LargeBinary,
            nullable=False
        )
    )

    uploaded_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    leave_request = db.relationship(
        "LeaveRequest",
        backref=db.backref(
            "attachments",
            order_by="LeaveAttachment.created_at.asc()",
            cascade="all, delete-orphan",
            lazy="select",
        ),
    )

    uploader = db.relationship(
        "User",
        foreign_keys=[uploaded_by]
    )

    def __repr__(self):
        return f"<LeaveAttachment #{self.id} {self.file_name}>"
