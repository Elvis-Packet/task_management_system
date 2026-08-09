from datetime import datetime

from extensions import db

from models.enums import (
    TaskPriority,
    TaskStatus
)


class AssignedTask(db.Model):

    __tablename__ = "assigned_tasks"

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

    manager_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    related_activity_id = db.Column(
        db.Integer,
        db.ForeignKey("activities.id")
    )

    # The weekly plan this task was created under (day-by-day planner).
    # Nullable — manager-assigned tasks, and tasks created before this
    # existed, have no plan. SET NULL on delete: removing a plan should
    # never destroy a task's own history/verification record.
    plan_id = db.Column(
        db.Integer,
        db.ForeignKey("weekly_plans.id", ondelete="SET NULL"),
        index=True
    )

    title = db.Column(
        db.String(255),
        nullable=False
    )

    description = db.Column(
        db.Text
    )

    # What the employee expects this task to achieve — an optional part of
    # the weekly-plan entry, distinct from the description of the work itself.
    expected_outcome = db.Column(
        db.Text
    )

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

    priority = db.Column(
        db.Enum(TaskPriority),
        default=TaskPriority.NORMAL
    )

    status = db.Column(
        db.Enum(TaskStatus),
        default=TaskStatus.PENDING
    )

    progress = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    verification_notes = db.Column(
        db.Text
    )

    verified_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    verified_at = db.Column(
        db.DateTime
    )

    completed_at = db.Column(
        db.DateTime
    )

    submitted_at = db.Column(
        db.DateTime
    )

    approved_at = db.Column(
        db.DateTime
    )

    overdue_notified = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    email_sent = db.Column(
        db.Boolean,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

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

    related_activity = db.relationship(
        "Activity"
    )

    plan = db.relationship(
        "WeeklyPlan"
    )

    progress_updates = db.relationship(
        "TaskProgressUpdate",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskProgressUpdate.created_at.asc()"
    )

    @property
    def is_overdue(self):

        non_overdue_eligible = {
            TaskStatus.COMPLETED,
            TaskStatus.VERIFIED,
            TaskStatus.REJECTED,
            TaskStatus.CANCELLED,
        }

        return (
            self.status not in non_overdue_eligible
            and
            datetime.utcnow().date() > self.due_date
        )

    def approve(self, manager):
        """SUBMITTED -> PENDING. The staff-created task is now authorized to work on."""

        self.status = TaskStatus.PENDING

        self.approved_at = datetime.utcnow()

    def reject_submission(self, manager, notes=None):
        """SUBMITTED -> REJECTED. Manager declines a staff-initiated task outright."""

        self.status = TaskStatus.REJECTED

        self.verified_by = manager.id

        self.verified_at = datetime.utcnow()

        self.verification_notes = notes

    def complete(self):

        self.status = TaskStatus.COMPLETED

        self.progress = 100

        self.completed_at = datetime.utcnow()

    def verify(
        self,
        manager,
        approved=True,
        notes=None
    ):
        """COMPLETED -> VERIFIED, or COMPLETED -> IN_PROGRESS if the manager
        returns it. A returned verification is never a dead end: it goes
        back to an active working state so the staff member can revise and
        resubmit, unlike reject_submission() (SUBMITTED -> REJECTED), which
        is a proposal being declined outright. Every decision is also
        AuditLog'd by the caller — verified_at/verified_by only ever hold
        the *latest* decision, but the full verify/return history survives
        in the timeline via those audit entries."""

        if approved:
            self.status = TaskStatus.VERIFIED
        else:
            self.status = TaskStatus.IN_PROGRESS

        self.verified_by = manager.id

        self.verified_at = datetime.utcnow()

        self.verification_notes = notes

    def __repr__(self):

        return f"<AssignedTask {self.title}>"

    acknowledged = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    acknowledged_at = db.Column(
        db.DateTime
    )