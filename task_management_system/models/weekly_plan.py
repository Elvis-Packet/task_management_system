from datetime import datetime

from extensions import db

from models.enums import PlanStatus

class WeeklyPlan(db.Model):

    __tablename__ = "weekly_plans"

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

    week_number = db.Column(
        db.Integer,
        nullable=False,
        index=True
    )

    year = db.Column(
        db.Integer,
        nullable=False,
        index=True
    )

    week_start = db.Column(
        db.Date,
        nullable=False
    )

    week_end = db.Column(
        db.Date,
        nullable=False
    )

    status = db.Column(
        db.Enum(PlanStatus),
        default=PlanStatus.DRAFT,
        nullable=False
    )

    submitted = db.Column(
        db.Boolean,
        default=False
    )

    submitted_at = db.Column(
        db.DateTime
    )

    reviewed = db.Column(
        db.Boolean,
        default=False
    )

    reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    reviewed_at = db.Column(
        db.DateTime
    )

    completion_percentage = db.Column(
        db.Float,
        default=0
    )

    review_notes = db.Column(
        db.Text
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
        back_populates="weekly_plans"
    )

    reviewer = db.relationship(
        "User",
        foreign_keys=[reviewed_by]
    )

    activities = db.relationship(
        "Activity",
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy=True
    )

    __table_args__ = (

        db.UniqueConstraint(
            "employee_id",
            "week_number",
            "year",
            name="unique_employee_week"
        ),

    )