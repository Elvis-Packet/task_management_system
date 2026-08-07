from flask import (
    Blueprint,
    render_template
)

from flask_login import (
    login_required,
    current_user
)

from models.enums import UserRole

from services.manager_dashboard_service import (
    get_manager_dashboard,
    get_managers
)

manager_bp = Blueprint(
    "manager",
    __name__,
    url_prefix="/manager"
)


@manager_bp.route("/dashboard")
@login_required
def dashboard():

    if current_user.role != UserRole.OPERATIONS_MANAGER:
        return "Unauthorized", 403


    data = get_manager_dashboard(current_user)

    managers = get_managers()


    return render_template(
        "dashboard/manager_dashboard.html",
        managers=managers,
        **data
    )