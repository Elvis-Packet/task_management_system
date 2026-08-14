from datetime import datetime

from extensions import db

from models.enums import QueryStatus


class TaskQuery(db.Model):
    """A manager's status request against one specific incomplete task, and
    the staff member's answer to it.

    Deliberately NOT a Comment: a comment is a free-text remark with no
    lifecycle, whereas a query is a request that is either answered or left
    hanging. That distinction is what makes "queries the employee never
    responded to" a countable, auditable fact — which is exactly what the
    HR performance flags are derived from. Append-only in spirit: a query is
    never rewritten, only answered (once) and then optionally closed."""

    __tablename__ = "task_queries"

    __table_args__ = (
        db.Index("idx_task_query_task_status", "task_id", "status"),
        db.Index("idx_task_query_employee_status", "employee_id", "status"),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    task_id = db.Column(
        db.Integer,
        db.ForeignKey("assigned_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Who raised it. Named manager_id to match AssignedTask.manager_id, but a
    # SUPER_ADMIN may raise one too — the column records the actual actor.
    manager_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    # Denormalised from the task at creation time so "unanswered queries for
    # this employee" is a single indexed lookup rather than a join through
    # assigned_tasks on every HR dashboard row.
    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    status = db.Column(
        db.Enum(QueryStatus),
        default=QueryStatus.OPEN,
        nullable=False
    )

    # The status of the task at the moment the query was raised — preserved
    # so the record still reads correctly after the task moves on.
    task_status_at_query = db.Column(
        db.String(30)
    )

    response = db.Column(
        db.Text
    )

    responded_at = db.Column(
        db.DateTime
    )

    closed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    closed_at = db.Column(
        db.DateTime
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    task = db.relationship(
        "AssignedTask",
        backref=db.backref(
            "queries",
            order_by="TaskQuery.created_at.asc()",
            cascade="all, delete-orphan",
        ),
    )

    manager = db.relationship(
        "User",
        foreign_keys=[manager_id]
    )

    employee = db.relationship(
        "User",
        foreign_keys=[employee_id]
    )

    closer = db.relationship(
        "User",
        foreign_keys=[closed_by]
    )

    @property
    def is_open(self):
        return self.status == QueryStatus.OPEN

    @property
    def is_answered(self):
        return self.status in (QueryStatus.ANSWERED, QueryStatus.CLOSED)

    def respond(self, body):
        """OPEN -> ANSWERED. A query is answered exactly once; further updates
        belong on the task itself (progress updates / comments)."""

        self.response = body

        self.responded_at = datetime.utcnow()

        self.status = QueryStatus.ANSWERED

    def close(self, actor):
        """Manager acknowledges the thread is done. Answered or not — closing
        an unanswered query is how a manager withdraws a request without
        leaving it counting against the employee forever."""

        self.status = QueryStatus.CLOSED

        self.closed_by = actor.id

        self.closed_at = datetime.utcnow()

    def __repr__(self):
        return f"<TaskQuery task={self.task_id} {self.status.value}>"
