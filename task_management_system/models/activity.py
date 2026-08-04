from datetime import datetime

from extensions import db

from models.enums import (
    ActivityStatus,
    TaskPriority,
    VerificationStatus,
    FinalStatus
)


class Activity(db.Model):

    __tablename__ = "activities"

    __table_args__ = (
        db.Index("idx_activity_date", "activity_date"),
        db.Index("idx_activity_verification", "verification_status"),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    plan_id = db.Column(
        db.Integer,
        db.ForeignKey("weekly_plans.id"),
        nullable=False,
        index=True
    )

    activity_date = db.Column(
        db.Date,
        nullable=False,
        index=True
    )

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

    # ======================================================
    # Employee Response
    # ======================================================

    employee_status = db.Column(
        db.Enum(ActivityStatus),
        default=ActivityStatus.PENDING,
        nullable=False
    )

    # ======================================================
    # Manager Verification
    # ======================================================

    verification_status = db.Column(
        db.Enum(VerificationStatus),
        default=VerificationStatus.PENDING,
        nullable=False
    )

    # ======================================================
    # Final Result
    # ======================================================

    final_status = db.Column(
        db.Enum(FinalStatus),
        default=FinalStatus.PENDING,
        nullable=False
    )

    manager_comments = db.Column(
        db.Text
    )

    manager_override = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    verified_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    verified_at = db.Column(
        db.DateTime
    )

    evidence_notes = db.Column(
        db.Text
    )

    evidence_file = db.Column(
        db.String(255)
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

    # ======================================================
    # Relationships
    # ======================================================

    plan = db.relationship(
        "WeeklyPlan",
        back_populates="activities"
    )

    verifier = db.relationship(
        "User",
        foreign_keys=[verified_by]
    )

    # ======================================================
    # Employee Actions
    # ======================================================

    def mark_completed(self):
        self.employee_status = ActivityStatus.DONE

    def mark_not_completed(self):
        self.employee_status = ActivityStatus.NOT_DONE

    # ======================================================
    # Manager Verification
    # ======================================================

    def determine_final_status(self):

        if self.verification_status == VerificationStatus.OVERRIDDEN:
            return FinalStatus.MANAGER_OVERRIDE

        if self.verification_status == VerificationStatus.VERIFIED:
            return FinalStatus.SUCCESSFUL

        if self.verification_status == VerificationStatus.REJECTED:
            return FinalStatus.UNSUCCESSFUL

        return FinalStatus.PENDING

    def verify(
        self,
        manager,
        verification_status,
        comments=None,
        override=False
    ):

        self.verification_status = verification_status
        self.manager_comments = comments
        self.manager_override = override
        self.verified_by = manager.id
        self.verified_at = datetime.utcnow()

        self.final_status = self.determine_final_status()

    # ======================================================
    # Helper Properties
    # ======================================================

    @property
    def is_verified(self):
        return self.verification_status == VerificationStatus.VERIFIED

    @property
    def is_pending(self):
        return self.verification_status == VerificationStatus.PENDING

    @property
    def is_completed(self):
        return self.employee_status == ActivityStatus.DONE

    @property
    def is_successful(self):
        return self.final_status == FinalStatus.SUCCESSFUL

    @property
    def is_unsuccessful(self):
        return self.final_status == FinalStatus.UNSUCCESSFUL

    @property
    def was_overridden(self):
        return self.manager_override

    def __repr__(self):
        return (
            f"<Activity "
            f"id={self.id}, "
            f"title='{self.title}', "
            f"date={self.activity_date}>"
        )