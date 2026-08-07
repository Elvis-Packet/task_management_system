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

        db.ForeignKey(
            "users.id"
        ),

        nullable=False

    )


    employee_number = db.Column(

        db.String(20),

        nullable=False

    )


    # ===============================
    # PERIOD
    # ===============================

    period_type = db.Column(

        db.String(20),

        nullable=False

    )
    # WEEKLY
    # MONTHLY
    # QUARTERLY
    # YEARLY



    period_name = db.Column(

        db.String(50),

        nullable=False

    )


    year = db.Column(

        db.Integer,

        nullable=False

    )


    month = db.Column(

        db.Integer

    )


    quarter = db.Column(

        db.Integer

    )


    # ===============================
    # PERFORMANCE METRICS
    # ===============================


    total_tasks = db.Column(

        db.Integer,

        default=0

    )


    completed_tasks = db.Column(

        db.Integer,

        default=0

    )


    verified_tasks = db.Column(

        db.Integer,

        default=0

    )


    average_rating = db.Column(

        db.Float,

        default=0

    )


    performance_percentage = db.Column(

        db.Float,

        default=0

    )


    manager_comment = db.Column(

        db.Text

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

        back_populates="performance"

    )
