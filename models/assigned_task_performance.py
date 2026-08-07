from datetime import datetime

from extensions import db


class AssignedTaskPerformance(db.Model):

    __tablename__ = "assigned_task_performance"

    # ==========================================================
    # PRIMARY KEY
    # ==========================================================

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # ==========================================================
    # EMPLOYEE
    # ==========================================================

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        unique=True,
        index=True
    )

    employee_number = db.Column(
        db.String(30),
        nullable=False,
        unique=True,
        index=True
    )

    # ==========================================================
    # TASK COUNTS
    # ==========================================================

    total_tasks = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    acknowledged_tasks = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    started_tasks = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    completed_tasks = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    verified_tasks = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    rejected_tasks = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    returned_tasks = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    overdue_tasks = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    # ==========================================================
    # PERCENTAGES
    # ==========================================================

    completion_percentage = db.Column(
        db.Float,
        default=0
    )

    verification_percentage = db.Column(
        db.Float,
        default=0
    )

    success_percentage = db.Column(
        db.Float,
        default=0
    )

    # ==========================================================
    # MANAGER RATINGS
    # ==========================================================

    average_quality = db.Column(
        db.Float,
        default=0
    )

    average_timeliness = db.Column(
        db.Float,
        default=0
    )

    overall_rating = db.Column(
        db.Float,
        default=0
    )

    # ==========================================================
    # COMPANY RANKING
    # ==========================================================

    department_rank = db.Column(
        db.Integer
    )

    company_rank = db.Column(
        db.Integer
    )

    # ==========================================================
    # GRADE
    # ==========================================================

    performance_grade = db.Column(
        db.String(2)
    )

    # ==========================================================
    # BEST STREAK
    # ==========================================================

    current_success_streak = db.Column(
        db.Integer,
        default=0
    )

    best_success_streak = db.Column(
        db.Integer,
        default=0
    )

    # ==========================================================
    # LAST TASK
    # ==========================================================

    last_task_completed = db.Column(
        db.DateTime
    )

    last_task_verified = db.Column(
        db.DateTime
    )

    # ==========================================================
    # AUDIT
    # ==========================================================

    last_calculated = db.Column(
        db.DateTime,
        default=datetime.utcnow
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

    # ==========================================================
    # RELATIONSHIP
    # ==========================================================

    employee = db.relationship(
        "User",
        back_populates="assigned_task_performance"
    )

    # ==========================================================
    # HELPERS
    # ==========================================================

    @property
    def grade(self):

        score = self.overall_rating

        if score >= 4.5:
            return "A"

        elif score >= 4:
            return "B"

        elif score >= 3:
            return "C"

        elif score >= 2:
            return "D"

        return "E"

    @property
    def stars(self):

        return round(
            self.overall_rating,
            1
        )

    @property
    def completion_rate(self):

        if self.total_tasks == 0:

            return 0

        return round(

            (

                self.completed_tasks

                /

                self.total_tasks

            ) * 100,

            2

        )

    @property
    def verification_rate(self):

        if self.completed_tasks == 0:

            return 0

        return round(

            (

                self.verified_tasks

                /

                self.completed_tasks

            ) * 100,

            2

        )

    @property
    def rejection_rate(self):

        if self.total_tasks == 0:

            return 0

        return round(

            (

                self.rejected_tasks

                /

                self.total_tasks

            ) * 100,

            2

        )

    def __repr__(self):

        return (

            f"<AssignedTaskPerformance "

            f"{self.employee_number} "

            f"Rating={self.overall_rating}>"

        )