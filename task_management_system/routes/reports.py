from flask import Blueprint, request

from extensions import db
from models.user import User
from models.department import Department
from models.comment import Comment
from models.enums import UserRole, AuditAction, CommentTargetType
from services.report_service import ReportService, resolve_report_period
from services.audit_service import AuditService
from utils.response import ok, err
from utils.rbac import require_roles, require_auth, get_current_user
from utils.serializers import serialize_generated_report, serialize_comment

reports_bp = Blueprint("reports", __name__)

MANAGE_ROLES = (UserRole.SUPER_ADMIN, UserRole.OPERATIONAL_MANAGER)


def _report_comments(report_id):
    return Comment.query.filter_by(
        target_type=CommentTargetType.REPORT, target_id=report_id
    ).order_by(Comment.created_at.asc()).all()


def _visible_report(report_id):
    """Both roles that can reach these routes (Super Admin and the central
    Operational Manager) now oversee every department, so a report is either
    found or it isn't — there is no per-department visibility split left."""

    from models.generated_report import GeneratedReport

    report = GeneratedReport.query.get(report_id)

    if not report:
        return None, err("Report not found.", 404)

    return report, None


@reports_bp.get("")
@require_roles(*MANAGE_ROLES)
def list_reports():
    # The central Operational Manager oversees every department, so reports
    # are no longer force-filtered to the caller's own department — a
    # department_id may still be passed explicitly as a filter.
    args = request.args.to_dict()

    reports = ReportService.list_reports(args)
    return ok({"items": [serialize_generated_report(r) for r in reports], "total": len(reports)})


@reports_bp.get("/<int:report_id>")
@require_roles(*MANAGE_ROLES)
def get_report(report_id):
    report, error = _visible_report(report_id)

    if error:
        return error

    return ok({"report": serialize_generated_report(report, include_data=True, include_comments=True)})


@reports_bp.post("/generate")
@require_roles(UserRole.SUPER_ADMIN)
def generate_report():
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

    if not data.get("title"):
        return err("Report title is required.", 422)

    report = ReportService.generate_report(data, current_user)

    AuditService.log_action(current_user, AuditAction.CREATE, f"Generated report '{report.title}'.")

    return ok({"report": serialize_generated_report(report)}, message="Report generated.", status=201)


@reports_bp.post("/department/<int:department_id>/generate")
@require_roles(*MANAGE_ROLES)
def generate_department_report(department_id):
    """Snapshot-record a department report right now, under this manager's
    name, for a specific date window — the numbers themselves are always
    recomputed live (never frozen here) whenever the report is reopened."""

    current_user = get_current_user()

    department = Department.query.get(department_id)

    if not department:
        return err("Department not found.", 404)

    data = request.get_json(silent=True) or {}
    period = data.get("period")
    start_date, end_date = resolve_report_period(
        period, data.get("start"), data.get("end")
    ) if period else (None, None)

    report = ReportService.generate_department_report(department, current_user, period, start_date, end_date)

    AuditService.log_action(
        current_user, AuditAction.CREATE,
        f"Generated department report for {department.department_name}.",
    )

    return ok(
        {"report": serialize_generated_report(report, include_data=True, include_comments=True)},
        message="Report generated.", status=201,
    )


@reports_bp.post("/<int:report_id>/comments")
@require_roles(*MANAGE_ROLES)
def add_report_comment(report_id):
    current_user = get_current_user()
    report, error = _visible_report(report_id)

    if error:
        return error

    data = request.get_json(silent=True) or {}
    body = (data.get("message") or data.get("body") or "").strip()

    if not body:
        return err("Comment message is required.", 422)

    comment = Comment(
        author_id=current_user.id,
        target_type=CommentTargetType.REPORT,
        target_id=report.id,
        body=body,
    )

    db.session.add(comment)
    db.session.commit()

    AuditService.log_action(current_user, AuditAction.COMMENT, f"Commented on report '{report.title}'.")

    return ok(
        {"comments": [serialize_comment(c) for c in _report_comments(report.id)]},
        message="Comment added.", status=201,
    )


@reports_bp.get("/org-kpis")
@require_roles(*MANAGE_ROLES)
def org_kpis():
    return ok(ReportService.org_kpis())


@reports_bp.get("/weekly")
@require_roles(*MANAGE_ROLES, UserRole.STAFF)
def weekly_report():
    current_user = get_current_user()

    employee_id = request.args.get("employee_id", type=int)
    week = request.args.get("week", type=int)
    year = request.args.get("year", type=int)

    if current_user.role == UserRole.STAFF:
        employee_id = current_user.id
    elif not employee_id:
        return err("employee_id is required.", 422)

    employee = User.query.filter_by(id=employee_id, deleted_at=None).first()

    if not employee:
        return err("Employee not found.", 404)

    from datetime import date
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()

    week = week or iso_week
    year = year or iso_year

    return ok(ReportService.weekly_report(employee, week, year))


@reports_bp.get("/weekly-history")
@require_roles(*MANAGE_ROLES, UserRole.STAFF)
def weekly_history():
    current_user = get_current_user()

    employee_id = request.args.get("employee_id", type=int)
    weeks = min(max(request.args.get("weeks", 8, type=int), 1), 26)

    if current_user.role == UserRole.STAFF:
        employee_id = current_user.id
    elif not employee_id:
        return err("employee_id is required.", 422)

    employee = User.query.filter_by(id=employee_id, deleted_at=None).first()

    if not employee:
        return err("Employee not found.", 404)

    return ok({"weeks": ReportService.weekly_history(employee, weeks)})


@reports_bp.get("/department/<int:department_id>")
@require_roles(*MANAGE_ROLES)
def department_report(department_id):
    department = Department.query.get(department_id)

    if not department:
        return err("Department not found.", 404)

    period = request.args.get("period")
    start_date, end_date = resolve_report_period(
        period, request.args.get("start"), request.args.get("end")
    ) if period else (None, None)

    return ok(ReportService.department_report(department, start_date, end_date))


@reports_bp.get("/organization")
@require_roles(UserRole.SUPER_ADMIN)
def organization_report():
    return ok(ReportService.organization_report())
