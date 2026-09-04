from flask import Blueprint, request

from models.task_query import TaskQuery
from models.enums import (
    QueryStatus,
    AuditAction,
    CommentTargetType,
    NotificationType,
    NotificationPriority,
)
from services.task_query_service import TaskQueryService
from services.audit_service import AuditService
from services.notification_service import NotificationService
from utils.response import ok, err
from utils.rbac import (
    Permission,
    require_auth,
    require_permission,
    get_current_user,
    has_org_scope,
    has_permission,
)
from utils.serializers import serialize_task_query, serialize_task
from utils.pagination import paginate

queries_bp = Blueprint("queries", __name__)


def _visible_query(query_id, current_user):
    """A query is visible to the org-scoped roles (Super Admin, the central
    Manager, HR) and to the staff member it was addressed to — nobody else.
    Reuses TaskQueryService.scoped_query so the rule lives in one place and
    an arbitrary id can never be walked into a readable record."""

    return TaskQueryService.scoped_query(
        current_user, has_org_scope(current_user)
    ).filter(TaskQuery.id == query_id).first()


@queries_bp.get("")
@require_auth
def list_queries():
    """Staff get their own inbox; Manager/Admin/HR get every query raised in
    the organization. Filterable by status/employee/task."""

    current_user = get_current_user()

    query = TaskQueryService.scoped_query(current_user, has_org_scope(current_user))
    query = TaskQueryService.apply_filters(query, request.args)

    return ok(paginate(query, serialize_task_query))


@queries_bp.get("/<int:query_id>")
@require_auth
def get_query(query_id):
    current_user = get_current_user()
    query = _visible_query(query_id, current_user)

    if not query:
        return err("Query not found.", 404)

    return ok({"query": serialize_task_query(query)})


@queries_bp.post("/<int:query_id>/respond")
@require_auth
def respond_to_query(query_id):
    """The staff member's answer. Only the employee the query was addressed to
    may answer it — a manager or admin cannot write the response on somebody
    else's behalf, or the record would stop meaning anything."""

    current_user = get_current_user()
    query = _visible_query(query_id, current_user)

    if not query:
        return err("Query not found.", 404)

    if query.employee_id != current_user.id:
        return err("Only the assignee can respond to this update request.", 403)

    if query.status != QueryStatus.OPEN:
        return err("This update request has already been answered.", 409)

    data = request.get_json(silent=True) or {}
    body = (data.get("response") or data.get("message") or "").strip()

    if not body:
        return err("A response is required.", 422, errors={"response": "required"})

    query = TaskQueryService.respond(query, body)

    NotificationService.notify(
        recipient=query.manager,
        sender=current_user,
        title="Update provided",
        message=f"{current_user.full_name} responded on '{query.task.title}': {body}",
        notification_type=NotificationType.TASK_QUERY,
        priority=NotificationPriority.NORMAL,
    )

    AuditService.log_action(
        current_user, AuditAction.RESPOND_QUERY,
        f"Responded to a status request on task '{query.task.title}'.",
        target_type=CommentTargetType.TASK, target_id=query.task_id,
    )

    return ok(
        {"query": serialize_task_query(query), "task": serialize_task(query.task, include_history=True)},
        message="Update sent to your manager.",
    )


@queries_bp.post("/<int:query_id>/close")
@require_permission(Permission.TASK_QUERY)
def close_query(query_id):
    """Manager acknowledges the thread. Closing is also how an unanswered
    request is withdrawn, so it stops counting against the employee on the
    HR dashboard — which is exactly why only someone with TASK_QUERY may do
    it, and never the employee being measured."""

    current_user = get_current_user()
    query = _visible_query(query_id, current_user)

    if not query:
        return err("Query not found.", 404)

    if query.status == QueryStatus.CLOSED:
        return err("This update request is already closed.", 409)

    query = TaskQueryService.close(query, current_user)

    AuditService.log_action(
        current_user, AuditAction.CLOSE_QUERY,
        f"Closed a status request on task '{query.task.title}'.",
        target_type=CommentTargetType.TASK, target_id=query.task_id,
    )

    return ok({"query": serialize_task_query(query)}, message="Update request closed.")
