from datetime import datetime

from extensions import db

from models.enums import PlanStatus


class WeeklyPlan(db.Model):

    __tablename__ = "weekly_plans"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # =====================================================
    # OWNER
    # =====================================================

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    employee_number = db.Column(
        db.String(20),
        nullable=False,
        index=True
    )

    # =====================================================
    # WEEK INFORMATION
    # =====================================================

    week_number = db.Column(
        db.Integer,
        nullable=False
    )

    year = db.Column(
        db.Integer,
        nullable=False
    )

    week_start = db.Column(
        db.Date,
        nullable=False
    )

    week_end = db.Column(
        db.Date,
        nullable=False
    )

    # =====================================================
    # PLAN DETAILS
    # =====================================================

    objectives = db.Column(
        db.Text,
        nullable=False
    )

    notes = db.Column(
        db.Text
    )

    # =====================================================
    # WORKFLOW
    # =====================================================

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

    review_comments = db.Column(
        db.Text
    )

    # =====================================================
    # SUMMARY
    # =====================================================

    total_activities = db.Column(
        db.Integer,
        default=0
    )

    completed_activities = db.Column(
        db.Integer,
        default=0
    )

    verified_activities = db.Column(
        db.Integer,
        default=0
    )

    completion_percentage = db.Column(
        db.Float,
        default=0
    )

    average_rating = db.Column(
        db.Float,
        default=0
    )

    # =====================================================
    # TIMESTAMPS
    # =====================================================

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

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

    # =====================================================
    # CONSTRAINT
    # =====================================================

    __table_args__ = (

        db.UniqueConstraint(
            "employee_number",
            "week_number",
            "year",
            name="uq_employee_week"
        ),

    )

    # =====================================================
    # HELPERS
    # =====================================================

    @property
    def progress(self):

        if self.total_activities == 0:
            return 0

        return round(

            (self.completed_activities /
             self.total_activities) * 100,

            2

        )

    @property
    def verification_progress(self):

        if self.total_activities == 0:
            return 0

        return round(

            (self.verified_activities /
             self.total_activities) * 100,

            2

        )

    def __repr__(self):

        return (
            f"<WeeklyPlan "
            f"{self.employee_number} "
            f"Week {self.week_number}>"
        )