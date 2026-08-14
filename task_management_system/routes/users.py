from flask import Blueprint, request, current_app

from extensions import db
from models.user import User
from models.department import Department
from models.enums import UserRole, AuditAction
from services.user_service import UserService
from services.auth_service import AuthService
from services.email_service import EmailService
from services.audit_service import AuditService
from utils.response import ok, err
from utils.rbac import (
    Permission,
    require_roles,
    require_permission,
    get_current_user,
    can_manage_user,
    assert_role_change_allowed,
)
from utils.serializers import serialize_user
from utils.pagination import paginate

users_bp = Blueprint("users", __name__)


def _clean_department_id(data):
    """Coerce an incoming department_id (which may arrive as a numeric
    string depending on the client) to a real int, or None. No-ops if the
    key wasn't sent at all, so unrelated partial updates don't accidentally
    clear an existing department assignment."""
    if "department_id" not in data:
        return
    raw = data.get("department_id")
    if raw in (None, "", "null"):
        data["department_id"] = None
        return
    try:
        data["department_id"] = int(raw)
    except (TypeError, ValueError):
        data["department_id"] = None

MANAGE_ROLES = (UserRole.SUPER_ADMIN, UserRole.OPERATIONAL_MANAGER)


def _target_user(user_id):
    return User.query.filter(User.id == user_id, User.deleted_at.is_(None)).first()


def _guard(actor, target, permission):
    """Both halves of the user-on-user check in one call: does the actor hold
    the capability, and may they use it against this particular account.
    Returns an error response to return immediately, or None."""

    refusal = can_manage_user(actor, target, permission)

    if refusal:
        return err(refusal, 403)

    return None


@users_bp.get("")
@require_permission(Permission.USER_VIEW)
def list_users():
    current_user = get_current_user()

    query = UserService.scoped_query(current_user)
    query = UserService.apply_filters(query, request.args)

    return ok(paginate(query, serialize_user))


@users_bp.get("/<int:user_id>")
@require_permission(Permission.USER_VIEW)
def get_user(user_id):
    current_user = get_current_user()

    user = UserService.scoped_query(current_user).filter(User.id == user_id).first()

    if not user:
        return err("User not found.", 404)

    return ok({"user": serialize_user(user)})


@users_bp.post("")
@require_permission(Permission.USER_CREATE)
def create_user():
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

    required = ["first_name", "last_name", "email", "password", "role"]
    missing = [f for f in required if not data.get(f)]

    if missing:
        return err("Missing required fields.", 422, errors={f: "required" for f in missing})

    if data["role"].upper() not in UserRole.__members__:
        return err("Invalid role.", 422, errors={"role": "invalid"})

    # Minting a Super Admin is the one account creation that hands out more
    # authority than the creator may hold, so it stays Super-Admin-only even
    # though the Manager otherwise has full user-management parity.
    if UserRole[data["role"].upper()] == UserRole.SUPER_ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        return err("Only a Super Admin can create another Super Admin account.", 403)

    if len(data["password"]) < 8:
        return err("Password must be at least 8 characters.", 422, errors={"password": "too_short"})

    if User.query.filter_by(email=data["email"].strip().lower()).first():
        return err("A user with this email already exists.", 409)

    _clean_department_id(data)
    if data.get("department_id") and not Department.query.get(data["department_id"]):
        return err("Department not found.", 422, errors={"department_id": "invalid"})

    user = UserService.create_user(data, created_by=current_user)

    AuditService.log_action(current_user, AuditAction.CREATE, f"Created user {user.email} ({user.role.value}).")

    return ok({"user": serialize_user(user)}, message="User created successfully.", status=201)


@users_bp.patch("/profile")
@require_roles(*UserRole)
def update_profile():
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

    user = UserService.update_profile(current_user, data)

    return ok({"user": serialize_user(user)}, message="Profile updated successfully.")


@users_bp.patch("/<int:user_id>")
@require_permission(Permission.USER_EDIT)
def update_user(user_id):
    """Administrative edit of another account. Authorized for Super Admin and
    the central Operational Manager; every field written is whitelisted in
    UserService.EDITABLE_FIELDS, and both the target check and the role-change
    check below are enforced here on the server, never by the client."""

    current_user = get_current_user()
    user = _target_user(user_id)

    if not user:
        return err("User not found.", 404)

    denied = _guard(current_user, user, Permission.USER_EDIT)
    if denied:
        return denied

    data = request.get_json(silent=True) or {}

    if data.get("role") and data["role"].upper() not in UserRole.__members__:
        return err("Invalid role.", 422, errors={"role": "invalid"})

    if data.get("role"):
        refusal = assert_role_change_allowed(current_user, user, UserRole[data["role"].upper()])
        if refusal:
            return err(refusal, 403)

    if data.get("status") and str(data["status"]).lower() not in ("active", "suspended", "locked"):
        return err("Invalid status.", 422, errors={"status": "invalid"})

    # Changing your own status through this endpoint would let an admin lock
    # themselves out; status changes on your own account are simply ignored.
    if data.get("status") and current_user.id == user.id:
        return err("You cannot change your own account status.", 403)

    if data.get("email"):
        existing = User.query.filter(User.email == data["email"].strip().lower(), User.id != user.id).first()
        if existing:
            return err("A user with this email already exists.", 409)

    _clean_department_id(data)
    if data.get("department_id") and not Department.query.get(data["department_id"]):
        return err("Department not found.", 422, errors={"department_id": "invalid"})

    # Recorded before the write so the audit entry can name what actually
    # changed — a department or role move is exactly the kind of edit someone
    # will need to trace back later.
    changes = []
    if data.get("role") and UserRole[data["role"].upper()] != user.role:
        changes.append(f"role {user.role.value} -> {data['role'].upper()}")
    if "department_id" in data and data["department_id"] != user.department_id:
        previous = user.department.department_name if user.department else "none"
        new_department = Department.query.get(data["department_id"]) if data["department_id"] else None
        changes.append(f"department {previous} -> {new_department.department_name if new_department else 'none'}")
    if data.get("status"):
        changes.append(f"status -> {str(data['status']).lower()}")

    user = UserService.update_user(user, data)

    detail = f" ({'; '.join(changes)})" if changes else ""
    AuditService.log_action(current_user, AuditAction.UPDATE, f"Updated user {user.email}{detail}.")

    return ok({"user": serialize_user(user)}, message="User updated successfully.")


@users_bp.post("/<int:user_id>/suspend")
@require_permission(Permission.USER_SUSPEND)
def suspend_user(user_id):
    current_user = get_current_user()
    user = _target_user(user_id)

    if not user:
        return err("User not found.", 404)

    denied = _guard(current_user, user, Permission.USER_SUSPEND)
    if denied:
        return denied

    user = UserService.suspend_user(user)

    AuditService.log_action(current_user, AuditAction.SUSPEND, f"Suspended user {user.email}.")

    return ok({"user": serialize_user(user)}, message="User suspended.")


@users_bp.post("/<int:user_id>/activate")
@require_permission(Permission.USER_SUSPEND)
def activate_user(user_id):
    current_user = get_current_user()
    user = _target_user(user_id)

    if not user:
        return err("User not found.", 404)

    denied = _guard(current_user, user, Permission.USER_SUSPEND)
    if denied:
        return denied

    user = UserService.activate_user(user)

    AuditService.log_action(current_user, AuditAction.ACTIVATE, f"Activated user {user.email}.")

    return ok({"user": serialize_user(user)}, message="User activated.")


@users_bp.delete("/<int:user_id>")
@require_permission(Permission.USER_DELETE)
def delete_user(user_id):
    current_user = get_current_user()

    if user_id == current_user.id:
        return err("You cannot delete your own account.", 400)

    user = _target_user(user_id)

    if not user:
        return err("User not found.", 404)

    denied = _guard(current_user, user, Permission.USER_DELETE)
    if denied:
        return denied

    UserService.soft_delete_user(user)

    AuditService.log_action(current_user, AuditAction.DELETE, f"Soft-deleted user {user.email}.")

    return ok(message="User deleted.")


@users_bp.post("/<int:user_id>/reset-password")
@require_permission(Permission.USER_RESET_PASSWORD)
def admin_reset_password(user_id):
    """Triggers the existing self-service reset flow on the user's behalf — an
    administrator never sets or sees a password, they only cause a one-time
    link to be emailed. That is why password_hash is not in EDITABLE_FIELDS."""

    current_user = get_current_user()
    user = _target_user(user_id)

    if not user:
        return err("User not found.", 404)

    denied = _guard(current_user, user, Permission.USER_RESET_PASSWORD)
    if denied:
        return denied

    _, raw_token = AuthService.request_password_reset(user.email)

    if raw_token:
        frontend_origin = (current_app.config.get("CORS_ORIGINS") or ["http://localhost:5173"])[0]
        reset_link = f"{frontend_origin}/reset-password?token={raw_token}"

        EmailService.send(
            to=user.email,
            subject=f"{current_app.config.get('APP_NAME')} — Password Reset",
            body=(
                f"Hello {user.first_name},\n\n"
                f"An administrator triggered a password reset for your account.\n\n"
                f"{reset_link}\n\nThis link expires in 1 hour."
            ),
        )

    AuditService.log_action(current_user, AuditAction.RESET_PASSWORD, f"Triggered password reset for {user.email}.")

    return ok(message="A password reset link has been sent to the user's email.")
