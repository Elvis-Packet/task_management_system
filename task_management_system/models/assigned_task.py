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

    title = db.Column(
        db.String(255),
        nullable=False
    )

    description = db.Column(
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

    @property
    def is_overdue(self):

        from datetime import datetime

        return (
            self.status != TaskStatus.COMPLETED
            and
            datetime.utcnow().date() > self.due_date
        )

    def complete(self):

        self.status = TaskStatus.COMPLETED

        self.completed_at = datetime.utcnow()

    def verify(
        self,
        manager,
        notes=None
    ):

        self.status = TaskStatus.VERIFIED

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