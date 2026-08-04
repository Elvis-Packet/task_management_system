from datetime import datetime

from extensions import db


class AuditLog(db.Model):

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="audit_logs"
    )

    action = db.Column(
        db.String(100),
        nullable=False
    )

    description = db.Column(
        db.Text
    )

    ip_address = db.Column(
        db.String(100)
    )

    device = db.Column(
        db.String(255)
    )

    browser = db.Column(
        db.String(255)
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )



    def __repr__(self):
        return f"<AuditLog {self.action}>"