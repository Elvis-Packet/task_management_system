from datetime import datetime

from extensions import db


class LoginHistory(db.Model):

    __tablename__ = "login_history"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    login_time = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    logout_time = db.Column(
        db.DateTime
    )

    ip_address = db.Column(
        db.String(50)
    )

    browser = db.Column(
        db.String(120)
    )

    operating_system = db.Column(
        db.String(120)
    )

    device = db.Column(
        db.String(120)
    )

    login_successful = db.Column(
        db.Boolean,
        default=True
    )

    failure_reason = db.Column(
        db.Text
    )

    session_id = db.Column(
        db.String(255)
    )

    user = db.relationship(
        "User",
        back_populates="login_history"
    )

    @property
    def session_duration(self):

        if not self.logout_time:
            return None

        return self.logout_time - self.login_time

    def __repr__(self):
        return f"<LoginHistory {self.user_id}>"