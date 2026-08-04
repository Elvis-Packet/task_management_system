from datetime import datetime

from flask_login import UserMixin

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from extensions import db

from models.enums import (
    UserRole,
    UserStatus
)

class User(UserMixin, db.Model):

    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    employee_number = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
        index=True
    )

    first_name = db.Column(
        db.String(80),
        nullable=False
    )

    middle_name = db.Column(
        db.String(80)
    )

    last_name = db.Column(
        db.String(80),
        nullable=False
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
        index=True
    )

    phone = db.Column(
        db.String(20)
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    profile_photo = db.Column(
        db.String(255)
    )

    role = db.Column(
        db.Enum(UserRole),
        default=UserRole.EMPLOYEE,
        nullable=False
    )

    status = db.Column(
        db.Enum(UserStatus),
        default=UserStatus.ACTIVE,
        nullable=False
    )

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id")
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    last_login = db.Column(
        db.DateTime
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    department = db.relationship(
        "Department",
        back_populates="users"
    )

    weekly_plans = db.relationship(
        "WeeklyPlan",
        foreign_keys="WeeklyPlan.employee_id",
        back_populates="employee",
        lazy=True,
        cascade="all, delete-orphan"
    )

    assigned_tasks = db.relationship(
        "AssignedTask",
        foreign_keys="AssignedTask.employee_id",
        back_populates="employee",
        lazy=True
    )

    tasks_assigned = db.relationship(
        "AssignedTask",
        foreign_keys="AssignedTask.manager_id",
        back_populates="manager",
        lazy=True
    )



    # audit_logs = db.relationship(
    #     "AuditLog",
    #     foreign_keys="AuditLog.user_id",
    #     back_populates="user"
    # )

    # login_history = db.relationship(
    #     "LoginHistory",
    #     back_populates="user",
    #     cascade="all, delete-orphan"
    # )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(
            self.password_hash,
            password
        )

    @property
    def full_name(self):
        return " ".join(
            filter(
                None,
                [
                    self.first_name,
                    self.middle_name,
                    self.last_name
                ]
            )
        )

    @property
    def is_super_admin(self):
        return self.role == UserRole.SUPER_ADMIN

    @property
    def is_manager(self):
        return self.role == UserRole.OPERATIONS_MANAGER

    @property
    def is_employee(self):
        return self.role == UserRole.EMPLOYEE

    def __repr__(self):
        return f"<User {self.employee_number} - {self.full_name}>"

    notifications_received = db.relationship(
        "Notification",
        foreign_keys="Notification.recipient_id",
        back_populates="recipient",
        lazy="dynamic",
        cascade="all, delete-orphan"
    )

    notifications_sent = db.relationship(
        "Notification",
        foreign_keys="Notification.sender_id",
        back_populates="sender",
        lazy="dynamic"
    )

    failed_login_attempts = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    password_changed_at = db.Column(
        db.DateTime
    )

    last_activity = db.Column(
        db.DateTime
    )

    last_ip_address = db.Column(
        db.String(50)
    )

    last_device = db.Column(
        db.String(150)
    )

    last_browser = db.Column(
        db.String(150)
    )

    is_first_login = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    @property
    def is_active(self):
        return self.status == UserStatus.ACTIVE

    @property
    def is_locked(self):
        return self.status == UserStatus.LOCKED

    @property
    def is_inactive(self):
        return self.status == UserStatus.INACTIVE

    # def mark_as_read(self):

    #     self.read = True

    #     self.read_at = datetime.utcnow()

    # def archive(self):

    #     self.archived = True

    #     self.archived_at = datetime.utcnow()

    # def mark_email_sent(self):

    #     self.email_sent = True

    #     self.email_sent_at = datetime.utcnow()

    # def __repr__(self):

    #     return (
    #         f"<Notification {self.title}>"
    #     )

    # __table_args__ = (

    #     db.Index(
    #         "idx_notification_recipient",
    #         "recipient_id"
    #     ),

    #     db.Index(
    #         "idx_notification_read",
    #         "read"
    #     ),

    #     db.Index(
    #         "idx_notification_created",
    #         "created_at"
    #     ),

    # )