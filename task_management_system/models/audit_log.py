from datetime import datetime

from extensions import db

from models.enums import CommentTargetType


class AuditLog(db.Model):

    __tablename__ = "audit_logs"

    __table_args__ = (
        db.Index("idx_audit_log_target", "target_type", "target_id"),
    )

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

    # Optional link to the specific record this action was about (e.g. a
    # task or weekly plan) — reuses CommentTargetType so a task's activity
    # timeline can be built by querying AuditLog the same way task/plan
    # comments already are, instead of a parallel logging mechanism.
    target_type = db.Column(
        db.Enum(CommentTargetType),
        nullable=True
    )

    target_id = db.Column(
        db.Integer,
        nullable=True
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