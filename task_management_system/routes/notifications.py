from flask import Blueprint

from extensions import db
from models.notification import Notification
from utils.response import ok, err
from utils.rbac import require_auth, get_current_user
from utils.serializers import serialize_notification
from utils.pagination import paginate

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.get("")
@require_auth
def list_notifications():
    current_user = get_current_user()

    query = Notification.query.filter_by(
        recipient_id=current_user.id, archived=False
    ).order_by(Notification.created_at.desc())

    return ok(paginate(query, serialize_notification))


@notifications_bp.patch("/<int:notification_id>/read")
@require_auth
def mark_read(notification_id):
    current_user = get_current_user()

    notification = Notification.query.filter_by(
        id=notification_id, recipient_id=current_user.id
    ).first()

    if not notification:
        return err("Notification not found.", 404)

    notification.mark_as_read()
    db.session.commit()

    return ok({"notification": serialize_notification(notification)}, message="Marked as read.")


@notifications_bp.post("/read-all")
@require_auth
def mark_all_read():
    current_user = get_current_user()

    Notification.query.filter_by(recipient_id=current_user.id, read=False).update(
        {"read": True}
    )
    db.session.commit()

    return ok(message="All notifications marked as read.")


@notifications_bp.delete("/<int:notification_id>")
@require_auth
def delete_notification(notification_id):
    current_user = get_current_user()

    notification = Notification.query.filter_by(
        id=notification_id, recipient_id=current_user.id
    ).first()

    if not notification:
        return err("Notification not found.", 404)

    db.session.delete(notification)
    db.session.commit()

    return ok(message="Notification deleted.")
