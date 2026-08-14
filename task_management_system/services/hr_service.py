from datetime import date, datetime, timedelta

from models.user import User
from models.department import Department
from models.assigned_task import AssignedTask
from models.task_query import TaskQuery
from models.enums import UserRole, TaskStatus, QueryStatus
from services.assigned_task_service import CLOSED_STATUSES
from services.task_query_service import TaskQueryService


def _pct(numerator, denominator):
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


# ==========================================================
# FLAG RULES
#
# Every rule below is derived from data the system ALREADY records — task
# status, due_date, completed_at, and the manager-query lifecycle. Nothing
# here is hand-entered, and nothing invents a new performance concept: the
# thresholds simply put a line under the existing "overdue" and "unanswered
# query" facts so HR sees the same numbers a manager would.
#
# Thresholds are module-level constants rather than magic numbers so the
# business can retune them in one place without touching the logic.
# ==========================================================

# One overdue task is noise; a persistent pile is a pattern.
OVERDUE_WATCH_THRESHOLD = 1
OVERDUE_CONCERN_THRESHOLD = 3

# Ignoring the manager is the strongest single signal, so it trips low.
UNANSWERED_QUERY_WATCH_THRESHOLD = 1
UNANSWERED_QUERY_CONCERN_THRESHOLD = 3

# Below this completion rate, with a meaningful workload behind it.
LOW_COMPLETION_RATE = 50.0
MIN_TASKS_FOR_RATE_FLAG = 4

# How stale an untouched, still-open task has to be to count as stalled.
STALLED_TASK_DAYS = 7

SEVERITY_ORDER = {"none": 0, "watch": 1, "concern": 2, "critical": 3}


def _worse(a, b):
    return a if SEVERITY_ORDER[a] >= SEVERITY_ORDER[b] else b


class HRService:
    """Read-only people-operations view over the existing task data.

    HR does not manage tasks and does not replace the manager — this service
    only surfaces, per employee, what the task records already say, plus the
    flags derived from them. It writes nothing."""

    @staticmethod
    def _staff_query(department_id=None, search=None):
        query = User.query.filter(
            User.role == UserRole.STAFF,
            User.deleted_at.is_(None),
        )

        if department_id:
            query = query.filter(User.department_id == department_id)

        if search:
            like = f"%{search}%"
            query = query.filter(
                User.first_name.ilike(like)
                | User.last_name.ilike(like)
                | User.email.ilike(like)
                | User.employee_number.ilike(like)
            )

        return query.order_by(User.first_name.asc(), User.last_name.asc())

    @staticmethod
    def _flags_for(metrics):
        """Turns one employee's counted metrics into concrete, explainable
        flags. Each flag carries its own reason text so the HR dashboard can
        show *why* somebody was flagged rather than an opaque score."""

        flags = []

        overdue = metrics["overdue_tasks"]
        unanswered = metrics["unanswered_queries"]

        if overdue >= OVERDUE_CONCERN_THRESHOLD:
            flags.append({
                "code": "repeated_overdue",
                "label": "Repeated overdue tasks",
                "severity": "critical",
                "reason": f"{overdue} tasks are past their due date and still incomplete.",
            })
        elif overdue >= OVERDUE_WATCH_THRESHOLD:
            flags.append({
                "code": "overdue",
                "label": "Overdue task",
                "severity": "watch",
                "reason": f"{overdue} task{'s are' if overdue != 1 else ' is'} past the due date.",
            })

        if unanswered >= UNANSWERED_QUERY_CONCERN_THRESHOLD:
            flags.append({
                "code": "ignoring_queries",
                "label": "Not responding to manager queries",
                "severity": "critical",
                "reason": f"{unanswered} manager status requests have gone unanswered.",
            })
        elif unanswered >= UNANSWERED_QUERY_WATCH_THRESHOLD:
            flags.append({
                "code": "unanswered_query",
                "label": "Unanswered manager query",
                "severity": "concern",
                "reason": f"{unanswered} manager status request{'s are' if unanswered != 1 else ' is'} awaiting a response.",
            })

        if (
            metrics["total_tasks"] >= MIN_TASKS_FOR_RATE_FLAG
            and metrics["completion_rate"] < LOW_COMPLETION_RATE
        ):
            flags.append({
                "code": "low_completion",
                "label": "Low completion rate",
                "severity": "concern",
                "reason": (
                    f"Only {metrics['completion_rate']}% of {metrics['total_tasks']} "
                    f"assigned tasks have been completed."
                ),
            })

        if metrics["stalled_tasks"]:
            flags.append({
                "code": "stalled",
                "label": "Stalled work",
                "severity": "watch",
                "reason": (
                    f"{metrics['stalled_tasks']} task(s) have had no progress update "
                    f"in over {STALLED_TASK_DAYS} days."
                ),
            })

        if metrics["queries_raised"] >= UNANSWERED_QUERY_CONCERN_THRESHOLD and not any(
            f["code"] == "ignoring_queries" for f in flags
        ):
            flags.append({
                "code": "repeated_queries",
                "label": "Repeatedly chased by manager",
                "severity": "watch",
                "reason": f"The manager has raised {metrics['queries_raised']} status requests against this employee.",
            })

        return flags

    @staticmethod
    def _metrics_for(employee, tasks, unanswered, raised, today):
        completed = [t for t in tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.VERIFIED)]
        verified = [t for t in tasks if t.status == TaskStatus.VERIFIED]
        pending = [t for t in tasks if t.status == TaskStatus.PENDING]
        in_progress = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]
        submitted = [t for t in tasks if t.status == TaskStatus.SUBMITTED]

        overdue = [
            t for t in tasks
            if t.status not in CLOSED_STATUSES and t.due_date and t.due_date < today
        ]

        stall_cutoff = datetime.utcnow() - timedelta(days=STALLED_TASK_DAYS)
        stalled = [
            t for t in tasks
            if t.status not in CLOSED_STATUSES
            and t.updated_at
            and t.updated_at < stall_cutoff
        ]

        late_completions = [
            t for t in completed
            if t.completed_at and t.due_date and t.completed_at.date() > t.due_date
        ]

        last_completed = max(
            (t.completed_at for t in completed if t.completed_at),
            default=None,
        )

        return {
            "total_tasks": len(tasks),
            "completed_tasks": len(completed),
            "verified_tasks": len(verified),
            "pending_tasks": len(pending),
            "in_progress_tasks": len(in_progress),
            "submitted_tasks": len(submitted),
            "overdue_tasks": len(overdue),
            "stalled_tasks": len(stalled),
            "late_completions": len(late_completions),
            "unanswered_queries": unanswered,
            "queries_raised": raised,
            "completion_rate": _pct(len(completed), len(tasks)),
            "on_time_rate": _pct(len(completed) - len(late_completions), len(completed)),
            "last_completed_at": last_completed,
            "oldest_overdue_date": min((t.due_date for t in overdue), default=None),
        }

    @staticmethod
    def employee_performance(department_id=None, search=None, flagged_only=False,
                             start_date=None, end_date=None):
        """One row per staff member: their real task counts over the window,
        their unanswered-query count, and the flags those numbers trip.

        Loads every task for the cohort in a single query and groups in
        memory rather than querying per employee — the dashboard is a table
        of the whole organization, so an N+1 here would be the difference
        between one query and hundreds."""

        today = date.today()

        staff = HRService._staff_query(department_id, search).all()
        staff_ids = [u.id for u in staff]

        if staff_ids:
            task_query = AssignedTask.query.filter(AssignedTask.employee_id.in_(staff_ids))

            if start_date:
                task_query = task_query.filter(AssignedTask.assigned_date >= start_date)
            if end_date:
                task_query = task_query.filter(AssignedTask.assigned_date <= end_date)

            all_tasks = task_query.all()
        else:
            all_tasks = []

        tasks_by_employee = {}
        for task in all_tasks:
            tasks_by_employee.setdefault(task.employee_id, []).append(task)

        unanswered_by_employee = TaskQueryService.unanswered_counts(staff_ids)
        raised_by_employee = TaskQueryService.raised_counts(staff_ids)

        rows = []

        for employee in staff:
            metrics = HRService._metrics_for(
                employee,
                tasks_by_employee.get(employee.id, []),
                unanswered_by_employee.get(employee.id, 0),
                raised_by_employee.get(employee.id, 0),
                today,
            )

            flags = HRService._flags_for(metrics)

            severity = "none"
            for flag in flags:
                severity = _worse(severity, flag["severity"])

            rows.append({
                "employee_id": employee.id,
                "employee_number": employee.employee_number,
                "name": employee.full_name,
                "email": employee.email,
                "job_title": employee.job_title,
                "department_id": employee.department_id,
                "department": employee.department.department_name if employee.department else None,
                "status": employee.status.value.lower(),
                "performance_score": round(employee.performance.overall_average, 2) if employee.performance else 0,
                "last_login": employee.last_login.isoformat() + "Z" if employee.last_login else None,
                "last_completed_at": (
                    metrics["last_completed_at"].isoformat() + "Z"
                    if metrics["last_completed_at"] else None
                ),
                "oldest_overdue_date": (
                    metrics["oldest_overdue_date"].isoformat()
                    if metrics["oldest_overdue_date"] else None
                ),
                "total_tasks": metrics["total_tasks"],
                "completed_tasks": metrics["completed_tasks"],
                "verified_tasks": metrics["verified_tasks"],
                "pending_tasks": metrics["pending_tasks"],
                "in_progress_tasks": metrics["in_progress_tasks"],
                "submitted_tasks": metrics["submitted_tasks"],
                "overdue_tasks": metrics["overdue_tasks"],
                "stalled_tasks": metrics["stalled_tasks"],
                "late_completions": metrics["late_completions"],
                "unanswered_queries": metrics["unanswered_queries"],
                "queries_raised": metrics["queries_raised"],
                "completion_rate": metrics["completion_rate"],
                "on_time_rate": metrics["on_time_rate"],
                "flags": flags,
                "flag_count": len(flags),
                "severity": severity,
            })

        if flagged_only:
            rows = [r for r in rows if r["flags"]]

        # Worst first — the whole point of the dashboard is who needs
        # attention, so the ordering is the answer, not a detail.
        rows.sort(
            key=lambda r: (
                SEVERITY_ORDER[r["severity"]],
                r["unanswered_queries"],
                r["overdue_tasks"],
            ),
            reverse=True,
        )

        return rows

    @staticmethod
    def summary(rows):
        """Headline counters for the HR dashboard, computed from the same rows
        the table renders so the two can never disagree."""

        return {
            "total_employees": len(rows),
            "flagged_employees": sum(1 for r in rows if r["flags"]),
            "critical_employees": sum(1 for r in rows if r["severity"] == "critical"),
            "concern_employees": sum(1 for r in rows if r["severity"] == "concern"),
            "watch_employees": sum(1 for r in rows if r["severity"] == "watch"),
            "total_tasks": sum(r["total_tasks"] for r in rows),
            "completed_tasks": sum(r["completed_tasks"] for r in rows),
            "overdue_tasks": sum(r["overdue_tasks"] for r in rows),
            "unanswered_queries": sum(r["unanswered_queries"] for r in rows),
            "completion_rate": _pct(
                sum(r["completed_tasks"] for r in rows),
                sum(r["total_tasks"] for r in rows),
            ),
        }

    @staticmethod
    def department_breakdown(rows):
        """Same rows, grouped by department — lets HR see whether a problem is
        one person or one team."""

        buckets = {}

        for row in rows:
            key = row["department"] or "Unassigned"

            bucket = buckets.setdefault(key, {
                "department": key,
                "department_id": row["department_id"],
                "employees": 0,
                "flagged": 0,
                "total_tasks": 0,
                "completed_tasks": 0,
                "overdue_tasks": 0,
                "unanswered_queries": 0,
            })

            bucket["employees"] += 1
            bucket["flagged"] += 1 if row["flags"] else 0
            bucket["total_tasks"] += row["total_tasks"]
            bucket["completed_tasks"] += row["completed_tasks"]
            bucket["overdue_tasks"] += row["overdue_tasks"]
            bucket["unanswered_queries"] += row["unanswered_queries"]

        for bucket in buckets.values():
            bucket["completion_rate"] = _pct(bucket["completed_tasks"], bucket["total_tasks"])

        return sorted(buckets.values(), key=lambda b: b["flagged"], reverse=True)

    @staticmethod
    def employee_detail(employee, start_date=None, end_date=None):
        """Everything HR needs on one person: their metrics, their flags, the
        actual overdue tasks behind the numbers, and the manager's own record
        — queries raised and non-completion reasons already logged against
        their tasks. Reuses the existing serializers throughout."""

        from utils.serializers import serialize_task, serialize_task_query, serialize_task_exception

        today = date.today()

        task_query = AssignedTask.query.filter(AssignedTask.employee_id == employee.id)

        if start_date:
            task_query = task_query.filter(AssignedTask.assigned_date >= start_date)
        if end_date:
            task_query = task_query.filter(AssignedTask.assigned_date <= end_date)

        tasks = task_query.order_by(AssignedTask.due_date.asc()).all()

        unanswered = TaskQueryService.unanswered_counts([employee.id]).get(employee.id, 0)
        raised = TaskQueryService.raised_counts([employee.id]).get(employee.id, 0)

        metrics = HRService._metrics_for(employee, tasks, unanswered, raised, today)
        flags = HRService._flags_for(metrics)

        overdue_tasks = [
            t for t in tasks
            if t.status not in CLOSED_STATUSES and t.due_date and t.due_date < today
        ]

        queries = (
            TaskQuery.query.filter(TaskQuery.employee_id == employee.id)
            .order_by(TaskQuery.created_at.desc())
            .all()
        )

        exceptions = []
        for task in tasks:
            exceptions.extend(task.exceptions)
        exceptions.sort(key=lambda e: e.created_at, reverse=True)

        severity = "none"
        for flag in flags:
            severity = _worse(severity, flag["severity"])

        return {
            "employee": {
                "id": employee.id,
                "employee_number": employee.employee_number,
                "name": employee.full_name,
                "email": employee.email,
                "phone": employee.phone,
                "job_title": employee.job_title,
                "department": employee.department.department_name if employee.department else None,
                "department_id": employee.department_id,
                "status": employee.status.value.lower(),
            },
            "metrics": {
                key: value for key, value in metrics.items()
                if key not in ("last_completed_at", "oldest_overdue_date")
            },
            "flags": flags,
            "severity": severity,
            "overdue_tasks": [serialize_task(t) for t in overdue_tasks],
            "queries": [serialize_task_query(q) for q in queries],
            "manager_reasons": [serialize_task_exception(e) for e in exceptions],
        }

    @staticmethod
    def departments():
        return Department.query.order_by(Department.department_name.asc()).all()
