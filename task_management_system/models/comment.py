from datetime import datetime

from extensions import db

from models.enums import CommentTargetType


class Comment(db.Model):

    __tablename__ = "comments"

    __table_args__ = (
        db.Index("idx_comment_target", "target_type", "target_id"),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    author_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    target_type = db.Column(
        db.Enum(CommentTargetType),
        nullable=False
    )

    target_id = db.Column(
        db.Integer,
        nullable=False,
        index=True
    )

    body = db.Column(
        db.Text,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    author = db.relationship(
        "User",
        foreign_keys=[author_id]
    )

    def __repr__(self):
        return f"<Comment {self.target_type.value}:{self.target_id} by={self.author_id}>"
