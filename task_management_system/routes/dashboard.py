from flask import Blueprint, request

from services.dashboard_service import DashboardService
from utils.response import ok
from utils.rbac import require_auth, get_current_user

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/stats")
@require_auth
def stats():
    service = DashboardService(get_current_user())
    return ok(service.stats())


@dashboard_bp.get("/performance-trends")
@require_auth
def performance_trends():
    service = DashboardService(get_current_user())
    range_ = request.args.get("range", "weekly")
    return ok(service.performance_trends(range_))


@dashboard_bp.get("/department-performance")
@require_auth
def department_performance():
    service = DashboardService(get_current_user())
    return ok(service.department_performance())


@dashboard_bp.get("/recent-activities")
@require_auth
def recent_activities():
    service = DashboardService(get_current_user())
    limit = request.args.get("limit", 6, type=int)
    return ok(service.recent_activities(limit))


@dashboard_bp.get("/upcoming-tasks")
@require_auth
def upcoming_tasks():
    service = DashboardService(get_current_user())
    return ok(service.upcoming_tasks())


@dashboard_bp.get("/employee-rankings")
@require_auth
def employee_rankings():
    service = DashboardService(get_current_user())
    return ok(service.employee_rankings())
