from extensions import db
from models.notification import Notification
from models.enums import NotificationType, NotificationPriority
from services.email_service import EmailService


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
        email=True,
    ):
        """Records an in-app notification and, by default, emails the same
        words to the recipient.

        Email defaults to on so a new notification site is reachable by
        someone who isn't looking at the app — the failure mode of
        forgetting to opt in is silence about work that needs a decision.
        Pass email=False for high-frequency telemetry that nobody needs in
        an inbox.

        The in-app record is the durable one: it is committed first, and
        EmailService swallows SMTP failures, so a mail outage degrades to
        "no email" rather than "no notification" or a failed request."""

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

        if email:
            EmailService.send_notification(recipient, title, message, action_url)

        return notification
