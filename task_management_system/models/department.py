from datetime import datetime
from extensions import db


class Department(db.Model):

    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)

    department_name = db.Column(db.String(120), nullable=False, unique=True)

    department_code = db.Column(db.String(20), nullable=False, unique=True)

    description = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    users = db.relationship(
        "User",
        back_populates="department",
        lazy=True
    )

    def __repr__(self):
        return f"<Department {self.department_name}>"