from datetime import datetime

from extensions import db

from models.enums import (
    TaskPriority,
    ActivityStatus,
    VerificationStatus,
    FinalStatus
)


class Activity(db.Model):

    __tablename__ = "activities"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # ==========================================================
    # PARENT WEEK PLAN
    # ==========================================================

    plan_id = db.Column(
        db.Integer,
        db.ForeignKey("weekly_plans.id"),
        nullable=False,
        index=True
    )

    employee_number = db.Column(
        db.String(20),
        nullable=False,
        index=True
    )

    # ==========================================================
    # ACTIVITY DETAILS
    # ==========================================================

    activity_date = db.Column(
        db.Date,
        nullable=False,
        index=True
    )

    title = db.Column(
        db.String(250),
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

    # ==========================================================
    # EMPLOYEE SECTION
    # ==========================================================

    employee_status = db.Column(
        db.Enum(ActivityStatus),
        default=ActivityStatus.PENDING,
        nullable=False
    )

    started_at = db.Column(
        db.DateTime
    )

    completed_at = db.Column(
        db.DateTime
    )

    completion_notes = db.Column(
        db.Text
    )

    evidence_file = db.Column(
        db.String(255)
    )

    # ==========================================================
    # MANAGER REVIEW
    # ==========================================================

    verification_status = db.Column(
        db.Enum(VerificationStatus),
        default=VerificationStatus.PENDING,
        nullable=False
    )

    final_status = db.Column(
        db.Enum(FinalStatus),
        default=FinalStatus.PENDING,
        nullable=False
    )

    reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    reviewed_at = db.Column(
        db.DateTime
    )

    manager_comments = db.Column(
        db.Text
    )

    # ==========================================================
    # PERFORMANCE METRICS
    # ==========================================================

    quality_rating = db.Column(
        db.Integer,
        default=0
    )

    timeliness_rating = db.Column(
        db.Integer,
        default=0
    )

    activity_score = db.Column(
        db.Float,
        default=0
    )

    # ==========================================================
    # AUDIT
    # ==========================================================

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # ==========================================================
    # RELATIONSHIPS
    # ==========================================================

    plan = db.relationship(
        "WeeklyPlan",
        back_populates="activities"
    )

    reviewer = db.relationship(
        "User",
        foreign_keys=[reviewed_by]
    )

    # ==========================================================
    # EMPLOYEE ACTIONS
    # ==========================================================

    def mark_done(self, notes=None):

        self.employee_status = ActivityStatus.DONE

        self.completed_at = datetime.utcnow()

        self.completion_notes = notes

    def mark_not_done(self, notes=None):

        self.employee_status = ActivityStatus.NOT_DONE

        self.completion_notes = notes

    # ==========================================================
    # MANAGER REVIEW
    # ==========================================================

    def review(
        self,
        manager,
        verification_status,
        quality_rating,
        timeliness_rating,
        comments=None
    ):

        self.reviewed_by = manager.id

        self.reviewed_at = datetime.utcnow()

        self.verification_status = verification_status

        self.manager_comments = comments

        self.quality_rating = quality_rating

        self.timeliness_rating = timeliness_rating

        self.activity_score = round(
            (quality_rating + timeliness_rating) / 2,
            2
        )

        if verification_status == VerificationStatus.VERIFIED:

            self.final_status = FinalStatus.SUCCESSFUL

        elif verification_status == VerificationStatus.REJECTED:

            self.final_status = FinalStatus.UNSUCCESSFUL

        else:

            self.final_status = FinalStatus.PENDING

    # ==========================================================
    # HELPERS
    # ==========================================================

    @property
    def is_completed(self):

        return self.employee_status == ActivityStatus.DONE

    @property
    def is_verified(self):

        return self.verification_status == VerificationStatus.VERIFIED

    @property
    def average_rating(self):

        return round(
            (self.quality_rating +
             self.timeliness_rating) / 2,
            2
        )

    def __repr__(self):

        return (
            f"<Activity "
            f"{self.title} "
            f"{self.employee_number}>"
        )