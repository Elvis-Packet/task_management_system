from datetime import datetime

from sqlalchemy import func

from extensions import db
from models.task_query import TaskQuery
from models.assigned_task import AssignedTask
from models.enums import QueryStatus, TaskStatus
from utils.enum_map import task_status_to_fe
from services.assigned_task_service import CLOSED_STATUSES


class TaskQueryService:
    """Manager status requests against incomplete tasks, and the staff
    responses to them.

    Built on the existing task/notification/audit machinery rather than a
    parallel messaging system: raising a query notifies through
    NotificationService, records through AuditService, and shows up in the
    task's existing activity timeline. What it adds that nothing else could
    express is the open/answered lifecycle."""

    @staticmethod
    def can_raise_on(task):
        """Only an incomplete task can be queried — asking someone for a
        progress update on work that's already finished, verified, rejected
        or cancelled is meaningless. Returns None when allowed, otherwise the
        refusal message."""

        if task.status in CLOSED_STATUSES:
            return "This task is already closed — there is no outstanding work to query."

        return None

    @staticmethod
    def raise_query(task, manager, message):
        """Records the request against this one specific task. The employee is
        taken from the task itself, never from the request body, so a query
        can never be filed against somebody who isn't the assignee."""

        query = TaskQuery(
            task_id=task.id,
            manager_id=manager.id,
            employee_id=task.employee_id,
            message=message.strip(),
            status=QueryStatus.OPEN,
            task_status_at_query=task_status_to_fe(task.status),
        )

        db.session.add(query)
        db.session.commit()

        return query

    @staticmethod
    def respond(query, body):
        query.respond(body.strip())

        db.session.commit()

        return query

    @staticmethod
    def close(query, actor):
        query.close(actor)

        db.session.commit()

        return query

    @staticmethod
    def for_task(task_id):
        return TaskQuery.query.filter_by(task_id=task_id).order_by(
            TaskQuery.created_at.asc()
        ).all()

    @staticmethod
    def scoped_query(current_user, has_org_scope_flag):
        """Every query in the organization for an org-scoped role; only the
        ones addressed to them for a staff member. Deliberately takes the
        scope decision as an argument so this service never re-derives an
        authorization rule that utils.rbac already owns."""

        query = TaskQuery.query

        if not has_org_scope_flag:
            query = query.filter(TaskQuery.employee_id == current_user.id)

        return query

    @staticmethod
    def apply_filters(query, args):
        status = args.get("status")
        employee_id = args.get("employee_id")
        task_id = args.get("task_id")

        if status:
            try:
                query = query.filter(TaskQuery.status == QueryStatus[str(status).upper()])
            except KeyError:
                pass

        if employee_id:
            query = query.filter(TaskQuery.employee_id == employee_id)

        if task_id:
            query = query.filter(TaskQuery.task_id == task_id)

        return query.order_by(TaskQuery.created_at.desc())

    @staticmethod
    def unanswered_counts(employee_ids):
        """{employee_id: number of still-unanswered queries} in one grouped
        query — the HR dashboard needs this for every employee at once and
        must not issue a count per row."""

        if not employee_ids:
            return {}

        rows = (
            db.session.query(TaskQuery.employee_id, func.count(TaskQuery.id))
            .filter(
                TaskQuery.employee_id.in_(employee_ids),
                TaskQuery.status == QueryStatus.OPEN,
            )
            .group_by(TaskQuery.employee_id)
            .all()
        )

        return {employee_id: count for employee_id, count in rows}

    @staticmethod
    def raised_counts(employee_ids):
        """{employee_id: total queries ever raised against them}. Repeated
        chasing is itself a performance signal, independent of whether the
        employee eventually answered."""

        if not employee_ids:
            return {}

        rows = (
            db.session.query(TaskQuery.employee_id, func.count(TaskQuery.id))
            .filter(TaskQuery.employee_id.in_(employee_ids))
            .group_by(TaskQuery.employee_id)
            .all()
        )

        return {employee_id: count for employee_id, count in rows}
