from datetime import datetime

from extensions import db


class LeaveType(db.Model):
    """The kinds of leave this organization actually grants, and the policy
    knobs that go with each one.

    Deliberately a table rather than an enum: the company's own paper form
    ends its checkbox list with "Other: ____" (the Survitec example has
    "Off Day" written in), so the set is open by definition. HR and the Super
    Admin maintain it through the API; nothing in the frontend hardcodes a
    leave type, and no business rule below is compiled into Python.

    Every policy field defaults to the permissive value, so a type created
    with nothing but a name behaves as "no restrictions" — the system stays
    usable for a company that has not written its leave policy down yet."""

    __tablename__ = "leave_types"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # Display name as it appears on the form ("Annual Leave").
    name = db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )

    # Stable machine key ("ANNUAL"). Reports and any future integration match
    # on this, so renaming a type for display never breaks them.
    code = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
        index=True
    )

    description = db.Column(
        db.Text
    )

    # --- Policy (all configurable; none of it is hardcoded elsewhere) ------

    # Sick leave needs the medical document the form asks for. Enforced in
    # LeaveService.validate() rather than at the column level, because the
    # attachment is uploaded after the request row exists.
    requires_attachment = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    # Whether a request may start in the past. False for planned leave;
    # true for sick/emergency, which by nature is reported after the fact.
    allows_backdating = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    # "Please submit this form at least 3 working days before the
    # commencement of leave" — from the company's own form footer. Counted in
    # calendar days. 0 disables the rule entirely.
    min_notice_days = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    # The form's "Days Avail." column. NULL means this type is not tracked
    # against an entitlement at all, which is the default — see
    # LeaveService.balance_for(), which derives usage from approved requests
    # rather than maintaining an accrual ledger.
    entitlement_days = db.Column(
        db.Integer
    )

    is_paid = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    # Retired types stay in the table so historical requests still resolve
    # their leave type; they just stop being offered on the application form.
    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    sort_order = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    requests = db.relationship(
        "LeaveRequest",
        back_populates="leave_type",
        lazy="dynamic"
    )

    def __repr__(self):
        return f"<LeaveType {self.code}>"
