from datetime import datetime, timedelta

from extensions import db
from models.performance import Performance
from models.assigned_task import AssignedTask
from models.weekly_plan import WeeklyPlan
from models.enums import TaskStatus, PlanStatus


def _pct(numerator, denominator):
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


class PerformanceService:
    """Performance is always derived from real AssignedTask/WeeklyPlan rows —
    no stored percentage is ever hand-set. recalculate() is called after every
    task/plan write so `Performance` is a cheap-to-read cache of a value that
    is 100% reproducible from the source tables at any time."""

    @staticmethod
    def recalculate(user):
        tasks = AssignedTask.query.filter_by(employee_id=user.id).all()

        total = len(tasks)
        verified = sum(1 for t in tasks if t.status == TaskStatus.VERIFIED)

        now = datetime.utcnow()

        week_start = now - timedelta(days=now.weekday())
        week_tasks = [t for t in tasks if t.created_at and t.created_at >= week_start]
        weekly_pct = _pct(
            sum(1 for t in week_tasks if t.status == TaskStatus.VERIFIED),
            len(week_tasks),
        )

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_tasks = [t for t in tasks if t.created_at and t.created_at >= month_start]
        monthly_pct = _pct(
            sum(1 for t in month_tasks if t.status == TaskStatus.VERIFIED),
            len(month_tasks),
        )

        overall_pct = _pct(verified, total)

        plans = WeeklyPlan.query.filter_by(employee_id=user.id).all()
        total_plans = len(plans)
        completed_plans = sum(
            1 for p in plans if p.status in (PlanStatus.APPROVED, PlanStatus.COMPLETED)
        )

        performance = user.performance

        if performance is None:
            performance = Performance(employee_id=user.id)
            db.session.add(performance)

        performance.total_plans = total_plans
        performance.completed_plans = completed_plans
        performance.total_activities = total
        performance.completed_activities = verified
        performance.weekly_average = weekly_pct
        performance.monthly_average = monthly_pct
        performance.yearly_average = overall_pct
        performance.overall_average = overall_pct
        performance.last_calculated = now

        db.session.commit()

        return performance

    @staticmethod
    def task_counts(employee_id):
        """Live task status breakdown for an employee — used by dashboards/reports
        so the numbers can never drift from the cached Performance row."""

        tasks = AssignedTask.query.filter_by(employee_id=employee_id).all()

        counts = {
            "assigned": len(tasks), "submitted": 0, "completed": 0,
            "pending": 0, "overdue": 0, "verified": 0,
        }

        for task in tasks:
            if task.status == TaskStatus.VERIFIED:
                counts["verified"] += 1
                counts["completed"] += 1
            elif task.status == TaskStatus.COMPLETED:
                counts["completed"] += 1
            elif task.is_overdue:
                counts["overdue"] += 1
            elif task.status == TaskStatus.SUBMITTED:
                counts["submitted"] += 1
            elif task.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
                counts["pending"] += 1

        return counts
