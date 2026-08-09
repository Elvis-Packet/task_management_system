from datetime import datetime

from extensions import db


class TaskProgressUpdate(db.Model):
    """Append-only log of every progress change on an AssignedTask.
    Never overwritten — this is the source of truth for a task's progress
    history and the primary building block of its activity timeline."""

    __tablename__ = "task_progress_updates"

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

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    previous_progress = db.Column(
        db.Integer,
        nullable=False
    )

    new_progress = db.Column(
        db.Integer,
        nullable=False
    )

    comment = db.Column(
        db.Text
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    task = db.relationship(
        "AssignedTask",
        back_populates="progress_updates"
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id]
    )

    def __repr__(self):
        return f"<TaskProgressUpdate task={self.task_id} {self.previous_progress}->{self.new_progress}>"
