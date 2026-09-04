from extensions import db
from models.notification import Notification
from models.enums import NotificationType, NotificationPriority


class NotificationService:

    @staticmethod
    def notify(
        recipient,
        title,
        message,
        sender=None,
        notification_type=NotificationType.SYSTEM,
        priority=NotificationPriority.NORMAL,
        action_url=None,
    ):
        if recipient is None:
            return None

        notification = Notification(
            recipient_id=recipient.id,
            sender_id=sender.id if sender else None,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            action_url=action_url,
        )

        db.session.add(notification)
        db.session.commit()

        return notification
