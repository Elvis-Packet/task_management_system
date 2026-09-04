from flask import Blueprint, request

from models.audit_log import AuditLog
from models.login_history import LoginHistory
from models.enums import UserRole
from utils.response import ok
from utils.rbac import require_roles
from utils.serializers import serialize_audit_log, serialize_login_history
from utils.pagination import paginate

audit_bp = Blueprint("audit", __name__)


@audit_bp.get("/logs")
@require_roles(UserRole.SUPER_ADMIN)
def audit_logs():
    query = AuditLog.query.order_by(AuditLog.created_at.desc())

    action = request.args.get("action")
    if action:
        query = query.filter(AuditLog.action == action)

    severity = request.args.get("severity")
    if severity:
        from utils.serializers import _SEVERITY_BY_ACTION
        matching_actions = [a for a, s in _SEVERITY_BY_ACTION.items() if s == severity]
        query = query.filter(AuditLog.action.in_(matching_actions))

    return ok(paginate(query, serialize_audit_log))


@audit_bp.get("/logs/<int:log_id>")
@require_roles(UserRole.SUPER_ADMIN)
def audit_log_detail(log_id):
    from utils.response import err

    log = AuditLog.query.get(log_id)

    if not log:
        return err("Audit log not found.", 404)

    return ok({"log": serialize_audit_log(log)})


@audit_bp.get("/login-history")
@require_roles(UserRole.SUPER_ADMIN)
def login_history():
    query = LoginHistory.query.order_by(LoginHistory.login_time.desc())

    status = request.args.get("status")
    if status == "success":
        query = query.filter(LoginHistory.login_successful.is_(True))
    elif status == "failed":
        query = query.filter(LoginHistory.login_successful.is_(False))

    return ok(paginate(query, serialize_login_history))
