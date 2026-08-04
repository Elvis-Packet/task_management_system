from flask import (
    Blueprint,
    render_template
)

from flask_login import (
    login_required,
    current_user
)

from services.dashboard_service import DashboardService

dashboard_bp = Blueprint(

    "dashboard",

    __name__,

    url_prefix="/dashboard"

)


@dashboard_bp.route("/")
@login_required
def employee_dashboard():

    service = DashboardService(current_user)

    return render_template(

        "dashboard/employee_dashboard.html",

        greeting=service.greeting(),

        user=current_user,

        active_week=service.get_active_week(),

        cards=service.dashboard_cards(),

        activities=service.planned_activities(),

        assigned_tasks=service.assigned_tasks(),

        notifications=service.notifications()

    )