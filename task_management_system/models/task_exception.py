from datetime import datetime

from extensions import db

from models.enums import NonCompletionReasonCategory, TaskResolution


class TaskException(db.Model):
    """A manager's recorded reason for a task not being completed on time —
    append-only (a new row per recording), so the task's own status/progress
    history is never overwritten and every explanation given over the
    task's life stays visible."""

    __tablename__ = "task_exceptions"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    task_id = db.Column(
        db.Integer,
        db.ForeignKey("assigned_tasks.id"),
        nullable=False,
        index=True
    )

    manager_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    reason_category = db.Column(
        db.Enum(NonCompletionReasonCategory),
        nullable=False
    )

    explanation = db.Column(
        db.Text,
        nullable=False
    )

    resolution = db.Column(
        db.Enum(TaskResolution)
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    task = db.relationship(
        "AssignedTask",
        backref=db.backref("exceptions", order_by="TaskException.created_at.asc()")
    )

    manager = db.relationship(
        "User",
        foreign_keys=[manager_id]
    )

    def __repr__(self):
        return f"<TaskException task={self.task_id} {self.reason_category.value}>"
