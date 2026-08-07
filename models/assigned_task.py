from datetime import datetime

from extensions import db

from models.enums import (
    TaskPriority,
    TaskStatus
)


class AssignedTask(db.Model):

    __tablename__ = "assigned_tasks"

    # ======================================================
    # PRIMARY KEY
    # ======================================================

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # ======================================================
    # OWNER
    # ======================================================

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    employee_number = db.Column(
        db.String(30),
        nullable=False,
        index=True
    )

    manager_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        nullable=False,
        index=True
    )

    # ======================================================
    # LINK TO WEEKLY PLAN
    # ======================================================

    weekly_plan_id = db.Column(
        db.Integer,
        db.ForeignKey("weekly_plans.id")
    )

    activity_id = db.Column(
        db.Integer,
        db.ForeignKey("activities.id")
    )

    # ======================================================
    # TASK DETAILS
    # ======================================================

    title = db.Column(
        db.String(255),
        nullable=False
    )

    description = db.Column(
        db.Text
    )

    priority = db.Column(
        db.Enum(TaskPriority),
        default=TaskPriority.NORMAL,
        nullable=False
    )

    status = db.Column(
        db.Enum(TaskStatus),
        default=TaskStatus.PENDING,
        nullable=False
    )

    # ======================================================
    # ASSIGNMENT
    # ======================================================

    assigned_date = db.Column(
        db.Date,
        nullable=False
    )

    assigned_time = db.Column(
        db.Time,
        nullable=False
    )

    due_date = db.Column(
        db.Date,
        nullable=False
    )

    due_time = db.Column(
        db.Time
    )

    # ======================================================
    # EMPLOYEE SECTION
    # ======================================================

    acknowledged = db.Column(
        db.Boolean,
        default=False
    )

    acknowledged_at = db.Column(
        db.DateTime
    )

    started_at = db.Column(
        db.DateTime
    )

    completion_notes = db.Column(
        db.Text
    )

    evidence_file = db.Column(
        db.String(255)
    )

    completed_at = db.Column(
        db.DateTime
    )

    completion_percentage = db.Column(
        db.Integer,
        default=0
    )

    # ======================================================
    # MANAGER REVIEW
    # ======================================================

    verified = db.Column(
        db.Boolean,
        default=False
    )

    verified_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    verified_at = db.Column(
        db.DateTime
    )

    manager_feedback = db.Column(
        db.Text
    )

    verification_notes = db.Column(
        db.Text
    )

    returned = db.Column(
        db.Boolean,
        default=False
    )

    return_reason = db.Column(
        db.Text
    )

    # ======================================================
    # PERFORMANCE
    # ======================================================

    quality_rating = db.Column(
        db.Integer
    )

    timeliness_rating = db.Column(
        db.Integer
    )

    overall_rating = db.Column(
        db.Float
    )

    # ======================================================
    # AUDIT
    # ======================================================

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # ======================================================
    # RELATIONSHIPS
    # ======================================================

    employee = db.relationship(
        "User",
        foreign_keys=[employee_id],
        back_populates="assigned_tasks"
    )

    manager = db.relationship(
        "User",
        foreign_keys=[manager_id],
        back_populates="tasks_assigned"
    )

    verifier = db.relationship(
        "User",
        foreign_keys=[verified_by]
    )

    department = db.relationship(
        "Department"
    )

    weekly_plan = db.relationship(
        "WeeklyPlan"
    )

    activity = db.relationship(
        "Activity"
    )

    # ======================================================
    # HELPERS
    # ======================================================

    @property
    def is_completed(self):

        return self.status == TaskStatus.COMPLETED

    @property
    def is_verified(self):

        return self.status == TaskStatus.VERIFIED

    @property
    def is_overdue(self):

        return (
            self.status != TaskStatus.VERIFIED
            and
            datetime.utcnow().date() > self.due_date
        )

    @property
    def days_remaining(self):

        return (
            self.due_date -
            datetime.utcnow().date()
        ).days

    # ======================================================
    # EMPLOYEE ACTIONS
    # ======================================================

    def acknowledge(self):

        self.acknowledged = True

        self.acknowledged_at = datetime.utcnow()

    def start(self):

        self.status = TaskStatus.IN_PROGRESS

        self.started_at = datetime.utcnow()

    def complete(
        self,
        notes=None,
        evidence=None
    ):

        self.status = TaskStatus.COMPLETED

        self.completed_at = datetime.utcnow()

        self.completion_percentage = 100

        self.completion_notes = notes

        self.evidence_file = evidence

    # ======================================================
    # MANAGER ACTIONS
    # ======================================================

    def verify(

        self,

        manager,

        quality_rating,

        timeliness_rating,

        feedback=None,

        notes=None

    ):

        self.status = TaskStatus.VERIFIED

        self.verified = True

        self.verified_by = manager.id

        self.verified_at = datetime.utcnow()

        self.manager_feedback = feedback

        self.verification_notes = notes

        self.quality_rating = quality_rating

        self.timeliness_rating = timeliness_rating

        self.overall_rating = round(

            (

                quality_rating +

                timeliness_rating

            ) / 2,

            2

        )

    def return_to_employee(

        self,

        reason

    ):

        self.status = TaskStatus.IN_PROGRESS

        self.returned = True

        self.return_reason = reason

    def __repr__(self):

        return (

            f"<AssignedTask "

            f"{self.employee_number} "

            f"{self.title}>"

        )