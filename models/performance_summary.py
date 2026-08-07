from datetime import datetime

from extensions import db


class PerformanceSummary(db.Model):

    __tablename__ = "performance_summary"


    id = db.Column(
        db.Integer,
        primary_key=True
    )


    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        unique=True
    )


    employee_number = db.Column(
        db.String(30),
        nullable=False
    )


    # ============================
    # COMPONENT SCORES
    # ============================


    activity_score = db.Column(
        db.Float,
        default=0
    )


    assigned_task_score = db.Column(
        db.Float,
        default=0
    )


    # ============================
    # FINAL SCORE
    # ============================


    overall_percentage = db.Column(
        db.Float,
        default=0
    )


    grade = db.Column(
        db.String(2)
    )


    company_rank = db.Column(
        db.Integer
    )


    department_rank = db.Column(
        db.Integer
    )


    # ============================
    # PERIOD
    # ============================


    period = db.Column(
        db.String(50)
    )


    year = db.Column(
        db.Integer
    )


    month = db.Column(
        db.Integer
    )


    created_at=db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


    updated_at=db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


    employee=db.relationship(
        "User",
        back_populates="performance_summary"
    )



    @property
    def performance_grade(self):

        score=self.overall_percentage


        if score >=90:
            return "A"


        elif score >=80:
            return "B"


        elif score >=70:
            return "C"


        elif score >=60:
            return "D"


        return "E"