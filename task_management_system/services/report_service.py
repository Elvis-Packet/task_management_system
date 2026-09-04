from datetime import datetime, date, timedelta

from extensions import db
from models.user import User
from models.department import Department
from models.assigned_task import AssignedTask
from models.weekly_plan import WeeklyPlan
from models.comment import Comment
from models.generated_report import GeneratedReport
from models.enums import UserRole, UserStatus, TaskStatus, PlanStatus, CommentTargetType


def _pct(numerator, denominator):
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _last_day_of_month(d):
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def _parse_iso_date(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def resolve_report_period(period, start_raw=None, end_raw=None):
    """Same Monday..Sunday ISO-week convention Weekly Plans/Staff Performance
    already use (week_bounds_for), so 'current week' means the same thing
    everywhere in the app — never a separately hardcoded range."""

    from services.weekly_plan_service import week_bounds_for

    today = date.today()

    if period == "current_week":
        start, end, _, _ = week_bounds_for(today)
    elif period == "previous_week":
        start, end, _, _ = week_bounds_for(today - timedelta(days=7))
    elif period == "current_month":
        start = today.replace(day=1)
        end = _last_day_of_month(start)
    elif period == "previous_month":
        first_this_month = today.replace(day=1)
        last_of_prev_month = first_this_month - timedelta(days=1)
        start = last_of_prev_month.replace(day=1)
        end = last_of_prev_month
    elif period == "custom":
        start = _parse_iso_date(start_raw)
        end = _parse_iso_date(end_raw)
    else:
        start = end = None

    return start, end


class ReportService:

    @staticmethod
    def list_reports(filters):
        query = GeneratedReport.query.order_by(GeneratedReport.generated_at.desc())

        report_type = filters.get("type")
        if report_type:
            query = query.filter(GeneratedReport.type == report_type)

        department_id = filters.get("department_id")
        if department_id:
            query = query.filter(GeneratedReport.department_id == department_id)

        return query.all()

    @staticmethod
    def generate_department_report(department, manager, period_label, start_date, end_date):
        """Records that a manager generated a department report snapshot, at
        this real timestamp, for this exact date window — the underlying
        numbers are still always recomputed live from AssignedTask (never
        frozen/duplicated here), but re-opening this same GeneratedReport
        row later replays the same window instead of drifting."""

        if start_date and end_date:
            title = f"Department Report — {department.department_name} ({start_date.isoformat()} to {end_date.isoformat()})"
        else:
            title = f"Department Report — {department.department_name} (All time)"

        report = GeneratedReport(
            title=title,
            type="department",
            period=period_label or "all_time",
            status="published",
            generated_by=manager.id,
            department_id=department.id,
            period_start=start_date,
            period_end=end_date,
        )

        db.session.add(report)
        db.session.commit()

        return report

    @staticmethod
    def generate_report(data, user):
        report = GeneratedReport(
            title=data["title"].strip(),
            type=data.get("type", "performance"),
            period=data.get("period"),
            status="published",
            generated_by=user.id,
        )

        db.session.add(report)
        db.session.commit()

        return report

    @staticmethod
    def org_kpis():
        staff = User.query.filter(User.role == UserRole.STAFF, User.deleted_at.is_(None)).all()

        active_employees = sum(1 for u in staff if u.status == UserStatus.ACTIVE)
        avg_performance = round(
            sum((u.performance.overall_average if u.performance else 0) for u in staff) / len(staff), 2
        ) if staff else 0

        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        tasks_completed_this_month = AssignedTask.query.filter(
            AssignedTask.status.in_([TaskStatus.COMPLETED, TaskStatus.VERIFIED]),
            AssignedTask.completed_at >= month_start,
        ).count()

        tasks_pending = AssignedTask.query.filter(
            AssignedTask.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS])
        ).count()

        reviewed_plans = WeeklyPlan.query.filter(
            WeeklyPlan.status.in_([PlanStatus.APPROVED, PlanStatus.REJECTED])
        ).all()
        approved = sum(1 for p in reviewed_plans if p.status == PlanStatus.APPROVED)

        return {
            "total_employees": len(staff),
            "active_employees": active_employees,
            "departments": Department.query.count(),
            "avg_performance": avg_performance,
            "tasks_completed_this_month": tasks_completed_this_month,
            "tasks_pending": tasks_pending,
            "plans_approved_rate": _pct(approved, len(reviewed_plans)),
        }

    @staticmethod
    def weekly_report(employee, week_number, year):
        from datetime import date, timedelta

        # Always compute the real ISO week's date range directly — never
        # depend on a WeeklyPlan row existing, otherwise a week with no
        # plan silently falls back to all-time task counts instead of 0.
        week_start = date.fromisocalendar(year, week_number, 1)  # Monday
        week_end = week_start + timedelta(days=6)  # Sunday

        plan = WeeklyPlan.query.filter_by(
            employee_id=employee.id, week_number=week_number, year=year
        ).first()

        tasks = AssignedTask.query.filter(
            AssignedTask.employee_id == employee.id,
            AssignedTask.assigned_date >= week_start,
            AssignedTask.assigned_date <= week_end,
        ).all()

        assigned = len(tasks)
        submitted = sum(1 for t in tasks if t.status == TaskStatus.SUBMITTED)
        completed = sum(1 for t in tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.VERIFIED))
        pending = sum(1 for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS))
        overdue = sum(1 for t in tasks if t.is_overdue)
        verified = sum(1 for t in tasks if t.status == TaskStatus.VERIFIED)
        rejected = sum(1 for t in tasks if t.status == TaskStatus.REJECTED)

        manager = User.query.filter_by(
            department_id=employee.department_id, role=UserRole.OPERATIONAL_MANAGER, deleted_at=None
        ).first()

        comments = []
        if plan:
            comments = Comment.query.filter_by(
                target_type=CommentTargetType.WEEKLY_PLAN, target_id=plan.id
            ).order_by(Comment.created_at.asc()).all()

        from utils.serializers import serialize_comment

        return {
            "employee_id": employee.id,
            "employee_name": employee.full_name,
            "department": employee.department.department_name if employee.department else None,
            "manager": manager.full_name if manager else None,
            "week_number": week_number,
            "year": year,
            "week_label": f"Week {week_number}, {year}",
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "tasks_assigned": assigned,
            "tasks_submitted": submitted,
            "tasks_completed": completed,
            "tasks_pending": pending,
            "tasks_overdue": overdue,
            "tasks_verified": verified,
            "tasks_rejected": rejected,
            "completion_rate": _pct(completed, assigned),
            "verification_rate": _pct(verified, completed),
            "weekly_performance": _pct(verified, assigned),
            "manager_comments": [
                serialize_comment(c) for c in comments if c.author and c.author.role == UserRole.OPERATIONAL_MANAGER
            ],
            "super_admin_comments": [
                serialize_comment(c) for c in comments if c.author and c.author.role == UserRole.SUPER_ADMIN
            ],
            "status": plan.status.value.lower() if plan else "no_plan",
        }

    @staticmethod
    def weekly_history(employee, weeks=8):
        """The last N ISO weeks (including the current one) for an employee —
        reuses weekly_report() for each, so it's the exact same formula,
        just queryable across a range instead of one week at a time."""

        from datetime import date, timedelta

        today = date.today()
        current_year, current_week, _ = today.isocalendar()

        history = []
        cursor = date.fromisocalendar(current_year, current_week, 1)

        for _ in range(weeks):
            iso_year, iso_week, _ = cursor.isocalendar()
            history.append(ReportService.weekly_report(employee, iso_week, iso_year))
            cursor -= timedelta(days=7)

        return history

    @staticmethod
    def department_report(department, start_date=None, end_date=None):
        """A real, DB-derived operational report — every count below is
        computed from the actual AssignedTask rows for this department's
        staff (optionally scoped to a date range by assigned_date, the same
        field weekly_report()/the day planner already use), never cached
        or hand-set."""

        from services.task_exception_service import TaskExceptionService
        from utils.serializers import serialize_task

        staff = [u for u in department.users if u.role == UserRole.STAFF and u.deleted_at is None]
        staff_ids = [u.id for u in staff]

        query = (
            AssignedTask.query.filter(AssignedTask.employee_id.in_(staff_ids))
            if staff_ids else AssignedTask.query.filter(AssignedTask.id.is_(None))
        )

        if start_date:
            query = query.filter(AssignedTask.assigned_date >= start_date)
        if end_date:
            query = query.filter(AssignedTask.assigned_date <= end_date)

        tasks = query.order_by(AssignedTask.due_date.asc()).all()

        manager = User.query.filter_by(
            department_id=department.id, role=UserRole.OPERATIONAL_MANAGER, deleted_at=None
        ).first()

        submitted = [t for t in tasks if t.status == TaskStatus.SUBMITTED]
        not_started = [t for t in tasks if t.status == TaskStatus.PENDING]
        in_progress = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]
        awaiting_verification = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        verified = [t for t in tasks if t.status == TaskStatus.VERIFIED]
        rejected = [t for t in tasks if t.status == TaskStatus.REJECTED]
        completed_all = awaiting_verification + verified
        overdue_tasks = [t for t in tasks if t.is_overdue]

        on_time_ids = {
            t.id for t in completed_all if t.completed_at and t.completed_at.date() <= t.due_date
        }
        late = [t for t in completed_all if t.id not in on_time_ids]

        overdue_ids = [t.id for t in overdue_tasks]
        ids_with_reason = TaskExceptionService.task_ids_with_reason(overdue_ids)
        overdue_with_reason = [t for t in overdue_tasks if t.id in ids_with_reason]
        overdue_without_reason = [t for t in overdue_tasks if t.id not in ids_with_reason]

        assigned = len(tasks)
        completed = len(completed_all)

        summary = {
            "total_tasks": assigned,
            "submitted": len(submitted),
            "not_started": len(not_started),
            "in_progress": len(in_progress),
            "completed": completed,
            "awaiting_verification": len(awaiting_verification),
            "verified": len(verified),
            "rejected": len(rejected),
            "overdue": len(overdue_tasks),
            "completed_on_time": len(on_time_ids),
            "completed_late": len(late),
            "overdue_with_reason": len(overdue_with_reason),
            "overdue_without_reason": len(overdue_without_reason),
            "completion_rate": _pct(completed, assigned),
            "verification_rate": _pct(len(verified), completed),
        }

        employees = []
        for u in staff:
            u_tasks = [t for t in tasks if t.employee_id == u.id]
            u_completed = sum(1 for t in u_tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.VERIFIED))
            u_verified = sum(1 for t in u_tasks if t.status == TaskStatus.VERIFIED)
            u_in_progress = sum(1 for t in u_tasks if t.status == TaskStatus.IN_PROGRESS)
            u_not_started = sum(1 for t in u_tasks if t.status == TaskStatus.PENDING)
            u_overdue = sum(1 for t in u_tasks if t.is_overdue)

            employees.append({
                "id": u.id,
                "name": u.full_name,
                "tasks": len(u_tasks),
                "completed": u_completed,
                "verified": u_verified,
                "in_progress": u_in_progress,
                "not_started": u_not_started,
                "pending": u_not_started + u_in_progress,
                "overdue": u_overdue,
                "completion_rate": _pct(u_completed, len(u_tasks)),
                "weekly_performance": round(u.performance.weekly_average, 2) if u.performance else 0,
                "overall_performance": round(u.performance.overall_average, 2) if u.performance else 0,
            })

        dept_performance = (
            round(sum(e["overall_performance"] for e in employees) / len(employees), 2)
            if employees else 0
        )

        return {
            "department_id": department.id,
            "department": department.department_name,
            "manager": manager.full_name if manager else None,
            "staff_count": len(staff),
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
            # Kept exactly as before — organization_report() reads these.
            "tasks_assigned": assigned,
            "tasks_completed": completed,
            "tasks_pending": len(not_started) + len(in_progress),
            "tasks_overdue": len(overdue_tasks),
            "tasks_verified": len(verified),
            "completion_rate": summary["completion_rate"],
            "department_performance": dept_performance,
            "employees": employees,
            "summary": summary,
            "tasks": {
                "completed_verified": [serialize_task(t) for t in verified],
                "awaiting_verification": [serialize_task(t) for t in awaiting_verification],
                "in_progress": [serialize_task(t) for t in in_progress],
                "not_started": [serialize_task(t) for t in not_started],
                "submitted": [serialize_task(t) for t in submitted],
                "overdue": [serialize_task(t) for t in overdue_tasks],
            },
        }

    @staticmethod
    def organization_report():
        departments = Department.query.all()
        dept_reports = [ReportService.department_report(d) for d in departments]

        total_assigned = sum(d["tasks_assigned"] for d in dept_reports)
        total_completed = sum(d["tasks_completed"] for d in dept_reports)
        total_overdue = sum(d["tasks_overdue"] for d in dept_reports)
        total_verified = sum(d["tasks_verified"] for d in dept_reports)

        return {
            "departments": dept_reports,
            "tasks_assigned": total_assigned,
            "tasks_completed": total_completed,
            "tasks_overdue": total_overdue,
            "tasks_verified": total_verified,
            "task_completion_rate": _pct(total_completed, total_assigned),
            "task_verification_rate": _pct(total_verified, total_completed),
            "kpis": ReportService.org_kpis(),
        }
