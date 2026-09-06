from flask import current_app

from extensions import db

from models.notification import Notification

from models.enums import (
    NotificationType,
    NotificationPriority,
    TaskPriority
)

from services.email_service import (
    send_task_assigned_email
)


# ==========================================================
# PRIORITY MAPPING
# ==========================================================

TASK_TO_NOTIFICATION_PRIORITY = {

    TaskPriority.LOW: NotificationPriority.LOW,

    TaskPriority.NORMAL: NotificationPriority.NORMAL,

    TaskPriority.MEDIUM: NotificationPriority.NORMAL,

    TaskPriority.HIGH: NotificationPriority.HIGH,

    TaskPriority.CRITICAL: NotificationPriority.URGENT

}


# ==========================================================
# CREATE
# ==========================================================

def create_notification(

    recipient_id,

    title,

    message,

    notification_type=NotificationType.SYSTEM,

    priority=NotificationPriority.NORMAL,

    sender_id=None,

    action_url=None,

    commit=True

):

    notification = Notification(

        recipient_id=recipient_id,

        sender_id=sender_id,

        title=title,

        message=message,

        notification_type=notification_type,

        priority=priority,

        action_url=action_url

    )

    db.session.add(notification)

    if commit:
        db.session.commit()

    return notification


# ==========================================================
# TASK ASSIGNED
# ==========================================================

def notify_task_assigned(task):
    """
    Creates the in-app notification for a newly assigned
    task and sends the matching email.

    Never raises - a notification failure must not roll back
    the task that was just saved.
    """

    try:

        due = task.due_date.strftime("%d %b %Y")

        if task.due_time:
            due = f"{due} at {task.due_time.strftime('%H:%M')}"

        manager_name = (
            task.manager.full_name
            if task.manager
            else "your manager"
        )

        notification = create_notification(

            recipient_id=task.employee_id,

            sender_id=task.manager_id,

            title="New task assigned",

            message=(
                f"{manager_name} assigned you \"{task.title}\". "
                f"Due {due}."
            ),

            notification_type=NotificationType.ASSIGNED_TASK,

            priority=TASK_TO_NOTIFICATION_PRIORITY.get(
                task.priority,
                NotificationPriority.NORMAL
            ),

            action_url=f"/assigned-tasks/{task.id}"

        )

        try:

            emailed = send_task_assigned_email(task)

            failure = (
                "Email not sent - recipient has no address "
                "or SMTP is not configured."
            )

        except Exception as error:

            # A broken template or SMTP fault must still be
            # recorded on the notification, not swallowed.
            emailed = False

            failure = f"Email failed: {error}"

            current_app.logger.error(
                "Assignment email failed for task %s | %s",
                task.id,
                error
            )

        if emailed:

            # Handed to SMTP - real delivery is confirmed
            # by the mail server, not by us.
            notification.mark_as_sent()

        else:

            notification.mark_as_failed(failure)

        db.session.commit()

        return notification

    except Exception as error:

        db.session.rollback()

        current_app.logger.error(
            "Failed to create assignment notification for task %s | %s",
            getattr(task, "id", None),
            error
        )

        return None


# ==========================================================
# READERS
# ==========================================================

def get_notifications(user_id, limit=20, include_archived=False):

    query = Notification.query.filter_by(
        recipient_id=user_id
    )

    if not include_archived:

        query = query.filter_by(archived=False)

    return query.order_by(

        Notification.created_at.desc()

    ).limit(limit).all()


def get_unread_count(user_id):

    return Notification.query.filter_by(

        recipient_id=user_id,

        read=False,

        archived=False

    ).count()


# ==========================================================
# STATE CHANGES
# ==========================================================

def mark_as_read(notification_id, user_id):

    notification = Notification.query.filter_by(

        id=notification_id,

        recipient_id=user_id

    ).first()

    if not notification:

        return False, "Notification not found."

    notification.mark_as_read()

    db.session.commit()

    return True, "Notification marked as read."


def mark_all_as_read(user_id):

    notifications = Notification.query.filter_by(

        recipient_id=user_id,

        read=False

    ).all()

    for notification in notifications:

        notification.mark_as_read()

    db.session.commit()

    return len(notifications)
