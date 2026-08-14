from flask import Blueprint, request

from models.user import User
from models.enums import UserRole
from services.hr_service import HRService
from services.report_service import resolve_report_period
from utils.response import ok, err
from utils.rbac import Permission, require_permission, get_current_user
from utils.serializers import serialize_department

hr_bp = Blueprint("hr", __name__)


def _period_from_args(args):
    """Same period vocabulary the reports module already uses
    (current_week / previous_week / current_month / previous_month / custom),
    so a date range means the same thing on the HR dashboard as it does on a
    department report."""

    period = args.get("period")

    if not period or period == "all_time":
        return None, None

    return resolve_report_period(period, args.get("start"), args.get("end"))


def _truthy(value):
    return str(value).lower() in ("1", "true", "yes")


@hr_bp.get("/dashboard")
@require_permission(Permission.HR_DASHBOARD)
def dashboard():
    """The whole HR view in one request: headline counters, per-department
    rollup, and the per-employee rows with their derived flags.

    Everything here is computed live from the existing AssignedTask and
    TaskQuery records — there is no separate flag table to fall out of sync,
    and HR never enters a flag by hand."""

    start_date, end_date = _period_from_args(request.args)

    rows = HRService.employee_performance(
        department_id=request.args.get("department_id", type=int),
        search=request.args.get("search"),
        flagged_only=_truthy(request.args.get("flagged_only")),
        start_date=start_date,
        end_date=end_date,
    )

    return ok({
        "summary": HRService.summary(rows),
        "departments": HRService.department_breakdown(rows),
        "employees": rows,
        "period": {
            "label": request.args.get("period") or "all_time",
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None,
        },
        "department_options": [serialize_department(d) for d in HRService.departments()],
    })


@hr_bp.get("/employees")
@require_permission(Permission.HR_DASHBOARD)
def employees():
    """The flagged-employee table on its own — same rows as /dashboard, for
    when only the list needs refreshing."""

    start_date, end_date = _period_from_args(request.args)

    rows = HRService.employee_performance(
        department_id=request.args.get("department_id", type=int),
        search=request.args.get("search"),
        flagged_only=_truthy(request.args.get("flagged_only")),
        start_date=start_date,
        end_date=end_date,
    )

    return ok({"items": rows, "total": len(rows)})


@hr_bp.get("/employees/<int:employee_id>")
@require_permission(Permission.HR_DASHBOARD)
def employee_detail(employee_id):
    """One employee's full escalation picture: metrics, flags, the actual
    overdue tasks, every manager query raised against them and how they
    answered, plus the manager's own recorded non-completion reasons."""

    employee = User.query.filter(
        User.id == employee_id,
        User.deleted_at.is_(None),
        User.role == UserRole.STAFF,
    ).first()

    if not employee:
        return err("Employee not found.", 404)

    start_date, end_date = _period_from_args(request.args)

    return ok(HRService.employee_detail(employee, start_date, end_date))
