from datetime import datetime, timedelta

from models.user import User
from models.department import Department
from models.assigned_task import AssignedTask
from models.weekly_plan import WeeklyPlan
from models.enums import UserRole, UserStatus, TaskStatus, PlanStatus


def _pct(numerator, denominator):
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


class DashboardService:

    def __init__(self, user):
        self.user = user

    def _scope_staff(self):
        query = User.query.filter(User.role == UserRole.STAFF, User.deleted_at.is_(None))

        if self.user.role == UserRole.STAFF:
            return query.filter(User.id == self.user.id).all()

        if self.user.role == UserRole.OPERATIONAL_MANAGER:
            return query.filter(User.department_id == self.user.department_id).all()

        return query.all()

    def _scope_task_query(self):
        staff_ids = [u.id for u in self._scope_staff()]
        if not staff_ids:
            return AssignedTask.query.filter(AssignedTask.id.is_(None))  # empty result set
        return AssignedTask.query.filter(AssignedTask.employee_id.in_(staff_ids))

    def _scope_plan_query(self):
        staff_ids = [u.id for u in self._scope_staff()]
        if not staff_ids:
            return WeeklyPlan.query.filter(WeeklyPlan.id.is_(None))
        return WeeklyPlan.query.filter(WeeklyPlan.employee_id.in_(staff_ids))

    def stats(self):
        staff = self._scope_staff()
        tasks = self._scope_task_query().all()

        total = len(tasks)
        verified = sum(1 for t in tasks if t.status == TaskStatus.VERIFIED)
        completed = sum(1 for t in tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.VERIFIED))
        pending = sum(1 for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS))
        overdue = sum(1 for t in tasks if t.is_overdue)
        awaiting_verification = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        submitted = sum(1 for t in tasks if t.status == TaskStatus.SUBMITTED)

        avg_performance = round(
            sum((u.performance.overall_average if u.performance else 0) for u in staff) / len(staff), 2
        ) if staff else 0

        # Weekly Plans awaiting the manager's review — the PLANNING stage.
        # Once approved, a plan's items become real AssignedTasks (the
        # EXECUTION stage), which is what tasks_pending_verification/
        # pending_tasks/etc below track — kept deliberately separate so a
        # dashboard reader can tell "plans I need to review" apart from
        # "task work already underway."
        plans_pending_review = self._scope_plan_query().filter(
            WeeklyPlan.status == PlanStatus.SUBMITTED
        ).count()

        data = {
            "total_tasks": total,
            "completed_tasks": completed,
            "pending_tasks": pending,
            "overdue_tasks": overdue,
            "verified_tasks": verified,
            "submitted_tasks": submitted,
            "avg_performance": avg_performance,
            "team_members": len(staff),
            "plans_pending_review": plans_pending_review,
            "tasks_pending_verification": awaiting_verification,
            "tasks_pending_approval": submitted,
            "weekly_plan_status": None,
        }

        if self.user.role == UserRole.STAFF:
            own_plan = WeeklyPlan.query.filter_by(employee_id=self.user.id).order_by(
                WeeklyPlan.year.desc(), WeeklyPlan.week_number.desc()
            ).first()
            data["weekly_plan_status"] = own_plan.status.value.lower() if own_plan else None

        if self.user.role == UserRole.SUPER_ADMIN:
            month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            data.update({
                "total_employees": User.query.filter(
                    User.role == UserRole.STAFF, User.deleted_at.is_(None)
                ).count(),
                "total_managers": User.query.filter(
                    User.role == UserRole.OPERATIONAL_MANAGER, User.deleted_at.is_(None)
                ).count(),
                "total_departments": Department.query.count(),
                "departments": Department.query.count(),
                "active_users": User.query.filter(
                    User.status == UserStatus.ACTIVE, User.deleted_at.is_(None)
                ).count(),
                "suspended_users": User.query.filter(
                    User.status == UserStatus.INACTIVE, User.deleted_at.is_(None)
                ).count(),
                "tasks_completed_this_month": AssignedTask.query.filter(
                    AssignedTask.status.in_([TaskStatus.COMPLETED, TaskStatus.VERIFIED]),
                    AssignedTask.completed_at >= month_start,
                ).count(),
                "total_employees_count": len(staff),
            })

        return data

    def performance_trends(self, range_="weekly"):
        buckets = 12 if range_ == "monthly" else 8
        step_days = 30 if range_ == "monthly" else 7

        staff_ids = [u.id for u in self._scope_staff()]

        labels, completion, on_time = [], [], []

        now = datetime.utcnow()

        for i in range(buckets - 1, -1, -1):
            bucket_end = now - timedelta(days=i * step_days)
            bucket_start = bucket_end - timedelta(days=step_days)

            if not staff_ids:
                labels.append(bucket_end.strftime("%b %d"))
                completion.append(0)
                on_time.append(0)
                continue

            bucket_tasks = AssignedTask.query.filter(
                AssignedTask.employee_id.in_(staff_ids),
                AssignedTask.created_at >= bucket_start,
                AssignedTask.created_at < bucket_end,
            ).all()

            total = len(bucket_tasks)
            done = sum(1 for t in bucket_tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.VERIFIED))
            on_time_count = sum(
                1 for t in bucket_tasks
                if t.completed_at and t.due_date and t.completed_at.date() <= t.due_date
            )

            labels.append(bucket_end.strftime("%b %d"))
            completion.append(_pct(done, total))
            on_time.append(_pct(on_time_count, total))

        return {"labels": labels, "completion": completion, "onTime": on_time}

    def department_performance(self):
        departments = Department.query.order_by(Department.department_name.asc()).all()

        labels, values = [], []

        for dept in departments:
            staff = [u for u in dept.users if u.role == UserRole.STAFF and u.deleted_at is None]
            if not staff:
                labels.append(dept.department_name)
                values.append(0)
                continue

            avg = sum((u.performance.overall_average if u.performance else 0) for u in staff) / len(staff)
            labels.append(dept.department_name)
            values.append(round(avg, 2))

        return {"labels": labels, "values": values}

    def recent_activities(self, limit=6):
        from services.activity_service import ActivityService

        return ActivityService.recent_activities(self.user, limit=limit)

    def upcoming_tasks(self, days=14):
        from utils.serializers import serialize_task

        cutoff = datetime.utcnow().date() + timedelta(days=days)

        tasks = self._scope_task_query().filter(
            AssignedTask.due_date <= cutoff,
            AssignedTask.status.notin_([
                TaskStatus.COMPLETED, TaskStatus.VERIFIED, TaskStatus.CANCELLED, TaskStatus.REJECTED,
            ]),
        ).order_by(AssignedTask.due_date.asc()).limit(10).all()

        # Reuses the same serializer every other task view uses (rather than
        # a second, thinner shape) so "self-assigned vs manager-assigned"
        # (created_by) and every other field stay consistent everywhere.
        return [serialize_task(t) for t in tasks]

    def employee_rankings(self):
        staff = self._scope_staff()

        ranked = sorted(
            staff,
            key=lambda u: (u.performance.overall_average if u.performance else 0),
            reverse=True,
        )

        return [
            {
                "id": u.id,
                "name": u.full_name,
                "department": u.department.department_name if u.department else None,
                "score": round(u.performance.overall_average, 2) if u.performance else 0,
                "tasks_completed": u.performance.completed_activities if u.performance else 0,
            }
            for u in ranked
        ]
