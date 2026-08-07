from datetime import datetime

from extensions import db


class Department(db.Model):

    __tablename__ = "departments"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    department_name = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
        index=True
    )

    department_code = db.Column(
        db.String(20),
        unique=True,
        nullable=False,
        index=True
    )

    description = db.Column(
        db.Text
    )

    active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    # =====================================================
    # Department Manager
    # =====================================================

    manager_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
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

    # =====================================================
    # Relationships
    # =====================================================

    users = db.relationship(
        "User",
        back_populates="department",
        foreign_keys="User.department_id",
        lazy=True
    )

    manager = db.relationship(
        "User",
        foreign_keys=[manager_id],
        uselist=False,
        post_update=True
    )

    # =====================================================
    # Helper Properties
    # =====================================================

    @property
    def manager_name(self):
        if self.manager:
            return self.manager.full_name
        return "Not Assigned"

    @property
    def employee_count(self):
        return len([
            user for user in self.users
            if user.is_employee
        ])

    @property
    def total_users(self):
        return len(self.users)

    # =====================================================
    # Utility Methods
    # =====================================================

    def activate(self):
        self.active = True

    def deactivate(self):
        self.active = False

    # =====================================================
    # Representation
    # =====================================================

    def __repr__(self):
        return (
            f"<Department "
            f"{self.department_code} - "
            f"{self.department_name}>"
        )