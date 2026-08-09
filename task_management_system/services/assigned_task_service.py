from datetime import datetime, date

from extensions import db
from models.user import User
from models.assigned_task import AssignedTask
from models.task_progress_update import TaskProgressUpdate
from models.enums import UserRole, TaskStatus, NotificationType, NotificationPriority
from utils.enum_map import priority_from_fe, task_status_from_fe
from services.performance_service import PerformanceService


def _find_department_manager(department_id):
    if not department_id:
        return None

    return User.query.filter_by(
        department_id=department_id, role=UserRole.OPERATIONAL_MANAGER, deleted_at=None
    ).first()


class AssignedTaskService:

    @staticmethod
    def scoped_query(current_user):
        query = AssignedTask.query

        if current_user.role == UserRole.STAFF:
            return query.filter(AssignedTask.employee_id == current_user.id)

        if current_user.role == UserRole.OPERATIONAL_MANAGER:
            return query.join(User, AssignedTask.employee_id == User.id).filter(
                User.department_id == current_user.department_id
            )

        return query

    @staticmethod
    def apply_filters(query, args):
        employee_id = args.get("employee_id") or args.get("assignee_id")
        status = args.get("status")
        priority = args.get("priority")

        if employee_id:
            query = query.filter(AssignedTask.employee_id == employee_id)

        if status:
            query = query.filter(AssignedTask.status == task_status_from_fe(status))

        if priority:
            query = query.filter(AssignedTask.priority == priority_from_fe(priority))

        return query.order_by(AssignedTask.due_date.asc(), AssignedTask.created_at.desc())

    @staticmethod
    def create_task(data, manager):
        """Manager/Super Admin assigns a task directly — the assigner's own
        authority is the approval, so it starts ready to work (PENDING)."""

        due_date = datetime.fromisoformat(data["due_date"]).date()

        task = AssignedTask(
            employee_id=data["employee_id"],
            manager_id=manager.id,
            title=data["title"].strip(),
            description=data.get("description"),
            assigned_date=date.today(),
            assigned_time=datetime.utcnow().time(),
            due_date=due_date,
            priority=priority_from_fe(data.get("priority")),
            status=TaskStatus.PENDING,
        )

        db.session.add(task)
        db.session.commit()

        PerformanceService.recalculate(task.employee)

        return task

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

        manager = _find_department_manager(staff.department_id)

        if not manager:
            raise ValueError(
                "No Operational Manager is assigned to your department yet. "
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
            assigned_date=date.today(),
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
