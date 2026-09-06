from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    flash
)

from flask_login import (
    login_required,
    current_user
)

from services.notification_service import (
    get_notifications,
    get_unread_count,
    mark_as_read,
    mark_all_as_read
)


notification_bp = Blueprint(
    "notification",
    __name__,
    url_prefix="/notifications"
)


# ==========================================================
# FULL PAGE
# ==========================================================

@notification_bp.route("/")
@login_required
def index():

    return render_template(

        "notifications/index.html",

        notifications=get_notifications(
            current_user.id,
            limit=100
        ),

        unread_count=get_unread_count(current_user.id)

    )


# ==========================================================
# UNREAD COUNT (polled by the navbar)
# ==========================================================

@notification_bp.route("/unread-count")
@login_required
def unread_count():

    return jsonify({
        "count": get_unread_count(current_user.id)
    })


# ==========================================================
# MARK ONE AS READ
# ==========================================================

@notification_bp.route(
    "/<int:notification_id>/read",
    methods=["POST"]
)
@login_required
def read(notification_id):

    success, message = mark_as_read(
        notification_id,
        current_user.id
    )

    if _wants_json():

        return jsonify({
            "success": success,
            "message": message,
            "count": get_unread_count(current_user.id)
        }), (200 if success else 404)

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("notification.index")
    )


# ==========================================================
# MARK ALL AS READ
# ==========================================================

@notification_bp.route(
    "/read-all",
    methods=["POST"]
)
@login_required
def read_all():

    updated = mark_all_as_read(current_user.id)

    if _wants_json():

        return jsonify({
            "success": True,
            "updated": updated,
            "count": 0
        })

    flash(
        f"{updated} notification(s) marked as read.",
        "success"
    )

    return redirect(
        url_for("notification.index")
    )


# ==========================================================
# OPEN - marks read, then follows the action_url
# ==========================================================

@notification_bp.route("/<int:notification_id>/open")
@login_required
def open_notification(notification_id):

    from models.notification import Notification

    notification = Notification.query.filter_by(
        id=notification_id,
        recipient_id=current_user.id
    ).first()

    if not notification:

        flash("Notification not found.", "danger")

        return redirect(url_for("notification.index"))

    if not notification.read:

        mark_as_read(notification.id, current_user.id)

    return redirect(
        notification.action_url
        or url_for("notification.index")
    )


# ==========================================================
# HELPERS
# ==========================================================

def _wants_json():

    return (
        request.accept_mimetypes.best == "application/json"
        or
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )
