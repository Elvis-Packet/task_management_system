from datetime import datetime, date

from extensions import db
from models.user import User
from models.assigned_task import AssignedTask
from models.task_progress_update import TaskProgressUpdate
from models.enums import UserRole, TaskStatus, NotificationType, NotificationPriority
from utils.enum_map import priority_from_fe, task_status_from_fe
from utils.rbac import has_org_scope
from services.performance_service import PerformanceService

# Statuses that mean "this task is finished or abandoned" — the complement is
# "still outstanding". Defined once here because the overdue check, the
# manager's query gate and the HR flags must all agree on what counts as
# incomplete.
CLOSED_STATUSES = (
    TaskStatus.COMPLETED,
    TaskStatus.VERIFIED,
    TaskStatus.REJECTED,
    TaskStatus.CANCELLED,
)


def _find_department_manager(department_id):
    if not department_id:
        return None

    return User.query.filter_by(
        department_id=department_id, role=UserRole.OPERATIONAL_MANAGER, deleted_at=None
    ).first()


def resolve_manager_for(employee):
    """The manager who owns an employee's work: their own department's
    Operational Manager if one is assigned, otherwise the central Operational
    Manager (who oversees every department and is the fallback owner for any
    department that has no dedicated manager of its own).

    This exists because the organization now runs one central manager who may
    not be attached to any department — without the fallback, staff in an
    unmanaged department could not submit a task at all."""

    manager = _find_department_manager(employee.department_id)

    if manager:
        return manager

    return (
        User.query.filter_by(role=UserRole.OPERATIONAL_MANAGER, deleted_at=None)
        .order_by(User.id.asc())
        .first()
    )


def _parse_date(value):
    if not value:
        return None

    return datetime.fromisoformat(str(value)).date()


class AssignedTaskService:

    @staticmethod
    def scoped_query(current_user):
        """STAFF see only their own tasks. Every org-scoped role — SUPER_ADMIN,
        the central OPERATIONAL_MANAGER and HR — sees tasks across every
        department; write access is gated separately by permission."""

        query = AssignedTask.query

        if not has_org_scope(current_user):
            return query.filter(AssignedTask.employee_id == current_user.id)

        return query

    @staticmethod
    def apply_filters(query, args):
        employee_id = args.get("employee_id") or args.get("assignee_id")
        status = args.get("status")
        priority = args.get("priority")
        department_id = args.get("department_id")
        assigned_date = args.get("assigned_date") or args.get("date")
        date_from = args.get("date_from")
        date_to = args.get("date_to")
        search = args.get("search")
        overdue = args.get("overdue")
        incomplete = args.get("incomplete")

        if employee_id:
            query = query.filter(AssignedTask.employee_id == employee_id)

        if status:
            query = query.filter(AssignedTask.status == task_status_from_fe(status))

        if priority:
            query = query.filter(AssignedTask.priority == priority_from_fe(priority))

        if department_id:
            query = query.join(User, AssignedTask.employee_id == User.id).filter(
                User.department_id == department_id
            )

        # A single working day — the "John, 14 August" view, where several
        # independent tasks share one date.
        for raw, column_filter in (
            (assigned_date, lambda d: AssignedTask.assigned_date == d),
            (date_from, lambda d: AssignedTask.assigned_date >= d),
            (date_to, lambda d: AssignedTask.assigned_date <= d),
        ):
            if raw:
                try:
                    query = query.filter(column_filter(_parse_date(raw)))
                except (TypeError, ValueError):
                    pass

        if search:
            like = f"%{search}%"
            query = query.filter(
                db.or_(AssignedTask.title.ilike(like), AssignedTask.description.ilike(like))
            )

        # Overdue is a derived property (status + due_date vs today), so it
        # has to be expressed as SQL here rather than reusing task.is_overdue.
        if str(overdue).lower() in ("1", "true", "yes"):
            query = query.filter(
                AssignedTask.status.notin_(CLOSED_STATUSES),
                AssignedTask.due_date < date.today(),
            )

        if str(incomplete).lower() in ("1", "true", "yes"):
            query = query.filter(AssignedTask.status.notin_(CLOSED_STATUSES))

        return query.order_by(
            AssignedTask.assigned_date.desc(),
            AssignedTask.due_date.asc(),
            AssignedTask.created_at.desc(),
        )

    @staticmethod
    def _build_task(data, manager):
        """One AssignedTask row from one payload. Every call creates a fresh,
        fully independent record — an employee can hold any number of these
        for the same assigned_date, each with its own title, description,
        priority, due date, status and progress. There is no per-employee,
        per-day rollup anywhere in this model."""

        due_date = datetime.fromisoformat(data["due_date"]).date()

        # The working day the task belongs to. Defaults to today (the previous
        # behaviour) but a manager can now assign several tasks onto a
        # specific future date in one sitting.
        assigned_date = _parse_date(data.get("assigned_date")) or date.today()

        due_time = None
        if data.get("due_time"):
            due_time = datetime.strptime(data["due_time"], "%H:%M").time()

        return AssignedTask(
            employee_id=data["employee_id"],
            manager_id=manager.id,
            title=data["title"].strip(),
            description=data.get("description"),
            expected_outcome=data.get("expected_outcome"),
            assigned_date=assigned_date,
            assigned_time=datetime.utcnow().time(),
            due_date=due_date,
            due_time=due_time,
            priority=priority_from_fe(data.get("priority")),
            status=TaskStatus.PENDING,
        )

    @staticmethod
    def create_task(data, manager):
        """Manager/Super Admin assigns a task directly — the assigner's own
        authority is the approval, so it starts ready to work (PENDING)."""

        task = AssignedTaskService._build_task(data, manager)

        db.session.add(task)
        db.session.commit()

        PerformanceService.recalculate(task.employee)

        return task

    @staticmethod
    def create_tasks(entries, manager):
        """Assign several independent tasks in one request — the normal case
        when a manager plans out somebody's day. Committed as a single
        transaction so a bad entry can't leave a half-assigned day behind;
        each entry still becomes its own separate task record."""

        tasks = [AssignedTaskService._build_task(entry, manager) for entry in entries]

        db.session.add_all(tasks)
        db.session.commit()

        for employee in {t.employee for t in tasks if t.employee}:
            PerformanceService.recalculate(employee)

        return tasks

    @staticmethod
    def create_self_task(data, staff):
        """Staff proposes a standalone task outside of weekly planning —
        routed to the Operational Manager of the staff member's own
        department (same department-based lookup used everywhere else;
        never hardcoded), starting SUBMITTED pending that manager's
        individual approval.

        This is deliberately the ONLY way a staff member creates a task
        directly: a Weekly Plan item (Activity) becomes an AssignedTask
        exclusively via WeeklyPlanService.generate_tasks_from_plan(), fired
        once when a manager approves the whole plan — never by a staff
        member calling this directly for a planned day."""

        manager = resolve_manager_for(staff)

        if not manager:
            raise ValueError(
                "No Operational Manager has been set up yet. "
                "Contact your Super Admin before submitting tasks."
            )

        due_date = datetime.fromisoformat(data["due_date"]).date()
        now = datetime.utcnow()

        task = AssignedTask(
            employee_id=staff.id,
            manager_id=manager.id,
            title=data["title"].strip(),
            description=data.get("description"),
            expected_outcome=data.get("expected_outcome"),
            assigned_date=_parse_date(data.get("assigned_date")) or date.today(),
            assigned_time=now.time(),
            due_date=due_date,
            priority=priority_from_fe(data.get("priority")),
            status=TaskStatus.SUBMITTED,
            submitted_at=now,
        )

        db.session.add(task)
        db.session.commit()

        PerformanceService.recalculate(staff)

        return task, manager

    @staticmethod
    def update_task(task, data):
        if data.get("title"):
            task.title = data["title"].strip()

        if "description" in data:
            task.description = data.get("description")

        if "expected_outcome" in data:
            task.expected_outcome = data.get("expected_outcome")

        if data.get("due_date"):
            task.due_date = datetime.fromisoformat(data["due_date"]).date()

        if "due_time" in data:
            task.due_time = datetime.strptime(data["due_time"], "%H:%M").time() if data.get("due_time") else None

        if data.get("priority"):
            task.priority = priority_from_fe(data["priority"])

        db.session.commit()

        return task

    @staticmethod
    def approve_task(task, manager):
        task.approve(manager)
        db.session.commit()

        return task

    @staticmethod
    def reject_submission(task, manager, notes=None):
        task.reject_submission(manager, notes=notes)
        db.session.commit()

        PerformanceService.recalculate(task.employee)

        return task

    @staticmethod
    def update_progress(task, user, progress, comment=None):
        progress = max(0, min(100, int(progress)))
        previous = task.progress

        task.progress = progress

        if task.status == TaskStatus.PENDING and progress > 0:
            task.status = TaskStatus.IN_PROGRESS

        db.session.add(TaskProgressUpdate(
            task_id=task.id,
            user_id=user.id,
            previous_progress=previous,
            new_progress=progress,
            comment=comment,
        ))

        db.session.commit()

        PerformanceService.recalculate(task.employee)

        return task

    @staticmethod
    def complete_task(task):
        task.complete()
        db.session.commit()

        PerformanceService.recalculate(task.employee)

        return task

    @staticmethod
    def verify_task(task, manager, approved, notes=None):
        task.verify(manager, approved=approved, notes=notes)
        db.session.commit()

        PerformanceService.recalculate(task.employee)

        return task

    @staticmethod
    def delete_task(task):
        employee = task.employee
        db.session.delete(task)
        db.session.commit()

        if employee:
            PerformanceService.recalculate(employee)

    @staticmethod
    def flag_overdue(tasks):
        """Lazily fire a one-time overdue notification the first time any
        task in this result set is detected as overdue. Called from list/
        detail routes so it piggybacks on normal polling — no scheduler."""

        from services.notification_service import NotificationService

        newly_overdue = [t for t in tasks if t.is_overdue and not t.overdue_notified]

        if not newly_overdue:
            return

        for task in newly_overdue:
            task.overdue_notified = True

            NotificationService.notify(
                recipient=task.employee,
                title="Task overdue",
                message=f"'{task.title}' is now overdue (was due {task.due_date.isoformat()}).",
                notification_type=NotificationType.REMINDER,
                priority=NotificationPriority.HIGH,
            )

            if task.manager:
                NotificationService.notify(
                    recipient=task.manager,
                    title="Task overdue",
                    message=f"{task.employee.full_name}'s task '{task.title}' is now overdue.",
                    notification_type=NotificationType.REMINDER,
                    priority=NotificationPriority.HIGH,
                )

        db.session.commit()
