from datetime import datetime

from flask import Blueprint, request

from extensions import db
from models.user import User
from models.assigned_task import AssignedTask
from models.comment import Comment
from models.enums import (
    UserRole,
    TaskStatus,
    AuditAction,
    CommentTargetType,
    NotificationType,
    NotificationPriority,
    NonCompletionReasonCategory,
    TaskResolution,
)
from models.enums import QueryStatus
from services.assigned_task_service import AssignedTaskService
from services.audit_service import AuditService
from services.notification_service import NotificationService
from services.task_exception_service import TaskExceptionService
from services.task_query_service import TaskQueryService
from services.weekly_plan_service import WeeklyPlanService
from utils.response import ok, err
from utils.rbac import (
    Permission,
    require_auth,
    require_roles,
    require_permission,
    get_current_user,
)
from utils.serializers import serialize_task, serialize_comment, serialize_task_query
from utils.pagination import paginate

tasks_bp = Blueprint("tasks", __name__)

MANAGE_ROLES = (UserRole.SUPER_ADMIN, UserRole.OPERATIONAL_MANAGER)


def _visible_task(task_id, current_user):
    return AssignedTaskService.scoped_query(current_user).filter(AssignedTask.id == task_id).first()


def _task_comments(task_id):
    return Comment.query.filter_by(
        target_type=CommentTargetType.TASK, target_id=task_id
    ).order_by(Comment.created_at.asc()).all()


def _staff_plan_lock_error(task):
    """Shared gate for a STAFF member editing/deleting one of their own
    weekly-plan tasks: the week must still be the current one, and the
    plan it belongs to must not already be submitted/approved (day_lock_reason
    checks both). Returns an error response to return immediately, or None
    if the change is allowed. Only applies to plan-linked tasks — the
    standalone Assigned Tasks flow has no day-planning concept and isn't
    subject to this rule."""

    if not task.plan_id:
        return err("You can only edit or delete tasks that are part of your weekly plan.", 403)

    lock_reason = WeeklyPlanService.day_lock_reason(task.assigned_date, task.plan)
    if lock_reason:
        return err(lock_reason, 409)

    return None


@tasks_bp.get("")
@require_auth
def list_tasks():
    current_user = get_current_user()
    query = AssignedTaskService.scoped_query(current_user)
    query = AssignedTaskService.apply_filters(query, request.args)
    return ok(paginate(query, serialize_task, postprocess=AssignedTaskService.flag_overdue))


@tasks_bp.get("/<int:task_id>")
@require_auth
def get_task(task_id):
    current_user = get_current_user()
    task = _visible_task(task_id, current_user)

    if not task:
        return err("Task not found.", 404)

    AssignedTaskService.flag_overdue([task])

    return ok({
        "task": serialize_task(task, include_comments=_task_comments(task.id), include_history=True)
    })


@tasks_bp.post("")
@require_roles(*MANAGE_ROLES, UserRole.STAFF)
def create_task():
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    if "employee_id" not in data and data.get("assignee_id"):
        data["employee_id"] = data["assignee_id"]

    # Staff propose a standalone task outside of weekly planning — they
    # can't assign to anyone else, and it starts SUBMITTED (awaiting their
    # department manager's individual approval). This is deliberately
    # separate from the Weekly Plan pipeline: a plan item only ever becomes
    # a live AssignedTask via manager approval of the whole plan
    # (POST /plans/goals -> .../submit -> manager approves -> task spawned).
    # Staff cannot bypass that by attaching a day/plan here.
    if current_user.role == UserRole.STAFF:
        required = ["title", "due_date"]
        missing = [f for f in required if not data.get(f)]

        if missing:
            return err("Missing required fields.", 422, errors={f: "required" for f in missing})

        try:
            task, manager = AssignedTaskService.create_self_task(data, current_user)
        except ValueError as exc:
            return err(str(exc), 422)
        except (TypeError, KeyError):
            return err("Invalid due_date format — expected YYYY-MM-DD.", 422)

        NotificationService.notify(
            recipient=manager,
            sender=current_user,
            title="New task submitted for approval",
            message=f"{current_user.full_name} submitted a task for your approval: {task.title}",
            notification_type=NotificationType.ASSIGNED_TASK,
            priority=NotificationPriority.NORMAL,
        )

        AuditService.log_action(
            current_user, AuditAction.CREATE, f"Submitted task '{task.title}' for approval."
        )

        return ok({"task": serialize_task(task)}, message="Task submitted for approval.", status=201)

    required = ["employee_id", "title", "due_date"]
    missing = [f for f in required if not data.get(f)]

    if missing:
        return err("Missing required fields.", 422, errors={f: "required" for f in missing})

    employee = User.query.filter(User.id == data["employee_id"], User.deleted_at.is_(None)).first()

    if not employee or employee.role != UserRole.STAFF:
        return err("Employee not found.", 422, errors={"employee_id": "invalid"})

    try:
        task = AssignedTaskService.create_task(data, current_user)
    except (ValueError, KeyError):
        return err("Invalid due_date format — expected YYYY-MM-DD.", 422)

    NotificationService.notify(
        recipient=employee,
        sender=current_user,
        title="New task assigned",
        message=f"{current_user.full_name} assigned you: {task.title}",
        notification_type=NotificationType.ASSIGNED_TASK,
        priority=NotificationPriority.NORMAL,
    )

    AuditService.log_action(
        current_user, AuditAction.ASSIGN_TASK, f"Assigned task '{task.title}' to {employee.full_name}."
    )

    return ok({"task": serialize_task(task)}, message="Task assigned successfully.", status=201)


@tasks_bp.post("/bulk")
@require_permission(Permission.TASK_ASSIGN)
def create_tasks_bulk():
    """Assign several independent tasks in one go — the normal case when a
    manager lays out somebody's day (four separate tasks on 14 August, each
    with its own title, priority, due date and status). Each entry becomes
    its own AssignedTask row; nothing is rolled up per employee per day.

    Validated as a whole before anything is written, so a single bad entry
    fails the request instead of leaving a half-assigned day behind."""

    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

    entries = data.get("tasks") or []

    if not isinstance(entries, list) or not entries:
        return err("Provide at least one task to assign.", 422, errors={"tasks": "required"})

    if len(entries) > 50:
        return err("You can assign at most 50 tasks in one request.", 422, errors={"tasks": "too_many"})

    # Defaults applied to every entry that doesn't override them — lets the
    # client send "these five titles, for this person, on this date".
    shared = {
        key: data[key]
        for key in ("employee_id", "assigned_date", "due_date", "priority")
        if data.get(key) is not None
    }

    prepared = []
    employees = {}

    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            return err("Each task entry must be an object.", 422, errors={f"tasks.{index}": "invalid"})

        entry = {**shared, **{k: v for k, v in raw.items() if v is not None}}

        if "employee_id" not in entry and entry.get("assignee_id"):
            entry["employee_id"] = entry["assignee_id"]

        missing = [f for f in ("employee_id", "title", "due_date") if not entry.get(f)]
        if missing:
            return err(
                f"Task {index + 1} is missing required fields.",
                422,
                errors={f"tasks.{index}.{f}": "required" for f in missing},
            )

        employee_id = entry["employee_id"]

        if employee_id not in employees:
            employee = User.query.filter(
                User.id == employee_id, User.deleted_at.is_(None)
            ).first()

            if not employee or employee.role != UserRole.STAFF:
                return err(
                    f"Task {index + 1}: employee not found.",
                    422,
                    errors={f"tasks.{index}.employee_id": "invalid"},
                )

            employees[employee_id] = employee

        prepared.append(entry)

    try:
        tasks = AssignedTaskService.create_tasks(prepared, current_user)
    except (ValueError, KeyError, TypeError):
        return err("Invalid date format — expected YYYY-MM-DD (and HH:MM for times).", 422)

    # One notification per employee rather than one per task: assigning four
    # tasks should not fire four separate alerts at the same person.
    for employee_id, employee in employees.items():
        count = sum(1 for t in tasks if t.employee_id == employee_id)

        NotificationService.notify(
            recipient=employee,
            sender=current_user,
            title="New tasks assigned" if count > 1 else "New task assigned",
            message=(
                f"{current_user.full_name} assigned you {count} tasks."
                if count > 1
                else f"{current_user.full_name} assigned you: {tasks[0].title}"
            ),
            notification_type=NotificationType.ASSIGNED_TASK,
            priority=NotificationPriority.NORMAL,
        )

    for task in tasks:
        AuditService.log_action(
            current_user, AuditAction.ASSIGN_TASK,
            f"Assigned task '{task.title}' to {task.employee.full_name} for {task.assigned_date.isoformat()}.",
            target_type=CommentTargetType.TASK, target_id=task.id,
        )

    return ok(
        {"tasks": [serialize_task(t) for t in tasks], "count": len(tasks)},
        message=f"{len(tasks)} task{'s' if len(tasks) != 1 else ''} assigned successfully.",
        status=201,
    )


@tasks_bp.patch("/<int:task_id>")
@require_roles(*MANAGE_ROLES, UserRole.STAFF)
def update_task(task_id):
    current_user = get_current_user()

    if current_user.role == UserRole.STAFF:
        task = AssignedTask.query.filter_by(id=task_id, employee_id=current_user.id).first()
    else:
        task = _visible_task(task_id, current_user)

    if not task:
        return err("Task not found.", 404)

    if current_user.role == UserRole.STAFF:
        lock_error = _staff_plan_lock_error(task)
        if lock_error:
            return lock_error

    data = request.get_json(silent=True) or {}

    try:
        task = AssignedTaskService.update_task(task, data)
    except (ValueError, KeyError):
        return err("Invalid due_date format — expected YYYY-MM-DD.", 422)

    action_desc = f"Edited planned task '{task.title}'." if task.plan_id else f"Updated task '{task.title}'."
    AuditService.log_action(
        current_user, AuditAction.UPDATE, action_desc,
        target_type=CommentTargetType.TASK, target_id=task.id,
    )

    return ok({"task": serialize_task(task)}, message="Task updated.")


@tasks_bp.patch("/<int:task_id>/progress")
@require_roles(UserRole.STAFF)
def update_progress(task_id):
    current_user = get_current_user()
    task = AssignedTask.query.filter_by(id=task_id, employee_id=current_user.id).first()

    if not task:
        return err("Task not found.", 404)

    if task.status not in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
        return err("This task must be approved and in progress before you can update its progress.", 409)

    data = request.get_json(silent=True) or {}

    if "progress" not in data:
        return err("progress is required.", 422)

    comment = (data.get("comment") or data.get("note") or "").strip() or None

    try:
        task = AssignedTaskService.update_progress(task, current_user, data["progress"], comment=comment)
    except (TypeError, ValueError):
        return err("progress must be a number between 0 and 100.", 422)

    NotificationService.notify(
        recipient=task.manager,
        sender=current_user,
        title="Task progress updated",
        message=f"{current_user.full_name} updated '{task.title}' to {task.progress}%." + (f" \"{comment}\"" if comment else ""),
        notification_type=NotificationType.ASSIGNED_TASK,
    )

    return ok({"task": serialize_task(task)}, message="Progress updated.")


@tasks_bp.post("/<int:task_id>/complete")
@require_roles(UserRole.STAFF)
def complete_task(task_id):
    current_user = get_current_user()
    task = AssignedTask.query.filter_by(id=task_id, employee_id=current_user.id).first()

    if not task:
        return err("Task not found.", 404)

    if task.status not in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
        return err("Only an approved, in-progress task can be marked complete.", 409)

    task = AssignedTaskService.complete_task(task)

    NotificationService.notify(
        recipient=task.manager,
        sender=current_user,
        title="Task submitted for verification",
        message=f"{current_user.full_name} completed: {task.title}. Awaiting your verification.",
        notification_type=NotificationType.ASSIGNED_TASK,
        priority=NotificationPriority.NORMAL,
    )

    AuditService.log_action(current_user, AuditAction.UPDATE, f"Completed task '{task.title}'.")

    return ok({"task": serialize_task(task)}, message="Task marked as completed, awaiting verification.")


@tasks_bp.post("/<int:task_id>/verify")
@require_roles(*MANAGE_ROLES)
def verify_task(task_id):
    """Handles the manager's decision at whichever stage the task is
    currently waiting on: SUBMITTED -> approve/reject the proposal, or
    COMPLETED -> verify/reject the finished work. Same endpoint either way."""

    current_user = get_current_user()
    task = _visible_task(task_id, current_user)

    if not task:
        return err("Task not found.", 404)

    data = request.get_json(silent=True) or {}
    approved = bool(data.get("approved", True))
    notes = data.get("notes")

    if task.status == TaskStatus.SUBMITTED:
        if approved:
            task = AssignedTaskService.approve_task(task, current_user)
            title, message = "Task approved", f"{current_user.full_name} approved your task: {task.title}."
        else:
            task = AssignedTaskService.reject_submission(task, current_user, notes)
            title = "Task rejected"
            message = f"{current_user.full_name} rejected your task: {task.title}. {notes or ''}".strip()

        NotificationService.notify(
            recipient=task.employee, sender=current_user, title=title, message=message,
            notification_type=NotificationType.ASSIGNED_TASK,
            priority=NotificationPriority.NORMAL if approved else NotificationPriority.HIGH,
        )

        AuditService.log_action(
            current_user,
            AuditAction.VERIFY if approved else AuditAction.REJECT,
            f"{'Approved' if approved else 'Rejected'} submitted task '{task.title}'.",
        )

        return ok({"task": serialize_task(task)}, message="Task submission reviewed.")

    if task.status != TaskStatus.COMPLETED:
        return err("This task is not awaiting a decision right now.", 409)

    task = AssignedTaskService.verify_task(task, current_user, approved, notes)

    NotificationService.notify(
        recipient=task.employee,
        sender=current_user,
        title="Task verified" if approved else "Task returned",
        message=(
            f"{current_user.full_name} verified your task: {task.title}."
            if approved
            else f"{current_user.full_name} returned your task for more work: {task.title}. {notes or ''}".strip()
        ),
        notification_type=NotificationType.ASSIGNED_TASK,
        priority=NotificationPriority.HIGH if not approved else NotificationPriority.NORMAL,
    )

    AuditService.log_action(
        current_user,
        AuditAction.VERIFY if approved else AuditAction.REJECT,
        f"{'Verified' if approved else 'Returned'} task '{task.title}' for more work.",
    )

    return ok({"task": serialize_task(task)}, message="Task reviewed.")


@tasks_bp.post("/<int:task_id>/comments")
@require_auth
def add_comment(task_id):
    current_user = get_current_user()
    task = _visible_task(task_id, current_user)

    if not task:
        return err("Task not found.", 404)

    data = request.get_json(silent=True) or {}
    body = (data.get("message") or data.get("body") or "").strip()

    if not body:
        return err("Comment message is required.", 422)

    comment = Comment(
        author_id=current_user.id,
        target_type=CommentTargetType.TASK,
        target_id=task.id,
        body=body,
    )

    db.session.add(comment)
    db.session.commit()

    recipient = task.employee if current_user.id != task.employee_id else task.manager

    NotificationService.notify(
        recipient=recipient,
        sender=current_user,
        title="New comment on your task",
        message=f"{current_user.full_name} commented on '{task.title}'.",
        notification_type=NotificationType.COMMENT,
    )

    AuditService.log_action(current_user, AuditAction.COMMENT, f"Commented on task '{task.title}'.")

    return ok(
        {"comments": [serialize_comment(c) for c in _task_comments(task.id)]},
        message="Comment added.",
        status=201,
    )


@tasks_bp.get("/<int:task_id>/queries")
@require_auth
def list_task_queries(task_id):
    """Every status request raised on this task. Scoped through the same
    _visible_task() gate as the task itself, so a staff member can only ever
    read the queries on a task that is theirs."""

    current_user = get_current_user()
    task = _visible_task(task_id, current_user)

    if not task:
        return err("Task not found.", 404)

    return ok({"queries": [serialize_task_query(q) for q in TaskQueryService.for_task(task.id)]})


@tasks_bp.post("/<int:task_id>/queries")
@require_permission(Permission.TASK_QUERY)
def raise_task_query(task_id):
    """Manager asks the assignee for a progress update on an incomplete task.
    The employee is read from the task, never from the payload, so a query
    can't be filed against anyone but the actual assignee."""

    current_user = get_current_user()
    task = _visible_task(task_id, current_user)

    if not task:
        return err("Task not found.", 404)

    refusal = TaskQueryService.can_raise_on(task)
    if refusal:
        return err(refusal, 409)

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or data.get("body") or "").strip()

    if not message:
        return err("A message is required to request an update.", 422, errors={"message": "required"})

    query = TaskQueryService.raise_query(task, current_user, message)

    NotificationService.notify(
        recipient=task.employee,
        sender=current_user,
        title="Update requested on your task",
        message=f"{current_user.full_name} asked for a progress update on '{task.title}': {message}",
        notification_type=NotificationType.TASK_QUERY,
        priority=NotificationPriority.HIGH,
    )

    AuditService.log_action(
        current_user, AuditAction.RAISE_QUERY,
        f"Requested a status update on task '{task.title}' from {task.employee.full_name}.",
        target_type=CommentTargetType.TASK, target_id=task.id,
    )

    return ok(
        {"query": serialize_task_query(query), "task": serialize_task(task, include_history=True)},
        message="Update requested.", status=201,
    )


@tasks_bp.post("/<int:task_id>/reason")
@require_roles(*MANAGE_ROLES)
def record_reason(task_id):
    """A manager's documented reason a task wasn't completed on time —
    a distinct, structured record from a free-text comment (never mixed
    together), and never overwrites the task's own status/progress
    history: this is always a new row, even if a reason already exists."""

    current_user = get_current_user()
    task = _visible_task(task_id, current_user)

    if not task:
        return err("Task not found.", 404)

    data = request.get_json(silent=True) or {}

    category_raw = (data.get("reason") or data.get("reason_category") or "").strip().upper()
    explanation = (data.get("explanation") or "").strip()

    if not category_raw:
        return err("A reason category is required.", 422, errors={"reason": "required"})

    try:
        category = NonCompletionReasonCategory[category_raw]
    except KeyError:
        return err("Invalid reason category.", 422, errors={"reason": "invalid"})

    if not explanation:
        return err("An explanation is required.", 422, errors={"explanation": "required"})

    resolution = None
    resolution_raw = (data.get("resolution") or "").strip().upper()
    if resolution_raw:
        try:
            resolution = TaskResolution[resolution_raw]
        except KeyError:
            return err("Invalid resolution.", 422, errors={"resolution": "invalid"})

    exception = TaskExceptionService.record_reason(task, current_user, category, explanation, resolution)

    AuditService.log_action(
        current_user, AuditAction.UPDATE,
        f"Recorded non-completion reason for task '{task.title}': {category.value}.",
        target_type=CommentTargetType.TASK, target_id=task.id,
    )

    if task.employee and task.employee_id != current_user.id:
        NotificationService.notify(
            recipient=task.employee,
            sender=current_user,
            title="Reason recorded on your task",
            message=f"{current_user.full_name} recorded a reason on '{task.title}': {explanation}",
            notification_type=NotificationType.ASSIGNED_TASK,
        )

    return ok({"task": serialize_task(task, include_history=True)}, message="Reason recorded.", status=201)


@tasks_bp.delete("/<int:task_id>")
@require_roles(*MANAGE_ROLES, UserRole.STAFF)
def delete_task(task_id):
    current_user = get_current_user()

    if current_user.role == UserRole.STAFF:
        task = AssignedTask.query.filter_by(id=task_id, employee_id=current_user.id).first()
    else:
        task = _visible_task(task_id, current_user)

    if not task:
        return err("Task not found.", 404)

    if current_user.role == UserRole.STAFF:
        lock_error = _staff_plan_lock_error(task)
        if lock_error:
            return lock_error

    title = task.title
    plan = task.plan
    AssignedTaskService.delete_task(task)

    if plan:
        AuditService.log_action(
            current_user, AuditAction.DELETE,
            f"Removed task '{title}' from weekly plan (week {plan.week_number}, {plan.year}).",
        )
    else:
        AuditService.log_action(current_user, AuditAction.DELETE, f"Deleted task '{title}'.")

    return ok(message="Task deleted.")
