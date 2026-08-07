from datetime import datetime

from extensions import db

from models.enums import (
    NotificationType,
    NotificationPriority,
    NotificationDeliveryStatus
)


class Notification(db.Model):

    __tablename__ = "notifications"

    __table_args__ = (
        db.Index("idx_notification_recipient", "recipient_id"),
        db.Index("idx_notification_read", "read"),
        db.Index("idx_notification_created", "created_at"),
        db.Index("idx_notification_delivery", "delivery_status"),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    title = db.Column(
        db.String(255),
        nullable=False
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    notification_type = db.Column(
        db.Enum(NotificationType),
        default=NotificationType.SYSTEM,
        nullable=False
    )

    priority = db.Column(
        db.Enum(NotificationPriority),
        default=NotificationPriority.NORMAL,
        nullable=False
    )

    action_url = db.Column(
        db.String(255)
    )

    # ==========================================
    # Delivery Tracking
    # ==========================================

    delivery_status = db.Column(
        db.Enum(NotificationDeliveryStatus),
        default=NotificationDeliveryStatus.PENDING,
        nullable=False
    )

    delivery_attempts = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    last_delivery_attempt = db.Column(
        db.DateTime
    )

    delivered_at = db.Column(
        db.DateTime
    )

    failure_reason = db.Column(
        db.Text
    )

    # ==========================================
    # Read Tracking
    # ==========================================

    read = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    read_at = db.Column(
        db.DateTime
    )

    # ==========================================
    # Archive
    # ==========================================

    archived = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    archived_at = db.Column(
        db.DateTime
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # ==========================================
    # Relationships
    # ==========================================

    recipient = db.relationship(
        "User",
        foreign_keys=[recipient_id],
        back_populates="notifications_received"
    )

    sender = db.relationship(
        "User",
        foreign_keys=[sender_id],
        back_populates="notifications_sent"
    )

    # ==========================================
    # Helper Methods
    # ==========================================

    def mark_as_read(self):
        self.read = True
        self.read_at = datetime.utcnow()

    def archive(self):
        self.archived = True
        self.archived_at = datetime.utcnow()

    def mark_as_delivered(self):
        self.delivery_status = NotificationDeliveryStatus.DELIVERED
        self.delivered_at = datetime.utcnow()

    def mark_as_sent(self):
        self.delivery_status = NotificationDeliveryStatus.SENT
        self.last_delivery_attempt = datetime.utcnow()
        self.delivery_attempts += 1

    def mark_as_failed(self, reason):
        self.delivery_status = NotificationDeliveryStatus.FAILED
        self.failure_reason = reason
        self.last_delivery_attempt = datetime.utcnow()
        self.delivery_attempts += 1

    @property
    def is_read(self):
        return self.read

    @property
    def is_archived(self):
        return self.archived

    @property
    def is_delivered(self):
        return self.delivery_status == NotificationDeliveryStatus.DELIVERED

    def __repr__(self):
        return (
            f"<Notification #{self.id} "
            f"to={self.recipient_id} "
            f"type={self.notification_type.value}>"
        )