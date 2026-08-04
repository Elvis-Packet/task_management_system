from datetime import datetime

from extensions import db


class Performance(db.Model):

    __tablename__ = "performance"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        unique=True,
        index=True
    )

    total_plans = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    completed_plans = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    total_activities = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    completed_activities = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    weekly_average = db.Column(
        db.Float,
        default=0
    )

    monthly_average = db.Column(
        db.Float,
        default=0
    )

    yearly_average = db.Column(
        db.Float,
        default=0
    )

    overall_average = db.Column(
        db.Float,
        default=0
    )

    rank_position = db.Column(
        db.Integer
    )

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

    employee = db.relationship(
        "User",
        back_populates="performance"
    )

    performance = db.relationship(
        "Performance",
        back_populates="employee",
        uselist=False,
        cascade="all, delete-orphan"
    )

    @property
    def completion_rate(self):
        if self.total_activities == 0:
            return 0

        return round(
            (self.completed_activities / self.total_activities) * 100,
            2
        )

    def __repr__(self):
        return f"<Performance {self.employee.full_name}>"