from flask import (
    Blueprint,
    render_template
)

from flask_login import (
    login_required,
    current_user
)

from models.enums import UserRole

from services.admin_dashboard_service import (
    get_admin_dashboard
)

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin"
)


@admin_bp.route("/dashboard")
@login_required
def dashboard():

    if current_user.role != UserRole.SUPER_ADMIN:
        return "Unauthorized", 403

    data = get_admin_dashboard()

    return render_template(
        "dashboard/admin_dashboard.html",
        **data
    )