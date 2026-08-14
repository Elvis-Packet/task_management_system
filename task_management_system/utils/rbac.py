from functools import wraps

from flask import g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

from models.user import User
from models.enums import UserRole
from utils.response import err


def _load_current_user():
    user_id = get_jwt_identity()

    if user_id is None:
        return None

    return User.query.get(int(user_id))


def get_current_user():
    """Only valid inside a request already guarded by @require_auth/@require_roles."""
    return getattr(g, "current_user", None)


# ==========================================================
# PERMISSIONS
#
# The single source of truth for "who may do what". Routes ask for a
# capability (@require_permission(Permission.USER_EDIT)) rather than naming
# roles, so granting the central Manager parity with the Admin is one edit
# to the table below instead of a change at every call site.
#
# This is deliberately the ONLY place role -> capability is decided; the
# frontend's utils/permissions.js mirrors it for display purposes only and
# is never trusted.
# ==========================================================

class Permission:

    # User management
    USER_VIEW = "user:view"
    USER_CREATE = "user:create"
    USER_EDIT = "user:edit"
    USER_SUSPEND = "user:suspend"
    USER_DELETE = "user:delete"
    USER_RESET_PASSWORD = "user:reset_password"

    # Organization structure
    DEPARTMENT_MANAGE = "department:manage"

    # Task lifecycle
    TASK_ASSIGN = "task:assign"
    TASK_VERIFY = "task:verify"
    TASK_QUERY = "task:query"

    # Visibility
    REPORT_VIEW = "report:view"
    REPORT_GENERATE = "report:generate"
    AUDIT_VIEW = "audit:view"
    HR_DASHBOARD = "hr:dashboard"


_ADMIN_PERMISSIONS = frozenset({
    Permission.USER_VIEW,
    Permission.USER_CREATE,
    Permission.USER_EDIT,
    Permission.USER_SUSPEND,
    Permission.USER_DELETE,
    Permission.USER_RESET_PASSWORD,
    Permission.DEPARTMENT_MANAGE,
    Permission.TASK_ASSIGN,
    Permission.TASK_VERIFY,
    Permission.TASK_QUERY,
    Permission.REPORT_VIEW,
    Permission.REPORT_GENERATE,
    Permission.AUDIT_VIEW,
    Permission.HR_DASHBOARD,
})

# The central Operational Manager has the same user-management capabilities
# as the Admin, plus the task-operations ones the Admin also holds. What it
# does NOT get is system administration: departments, audit logs, and
# minting/altering SUPER_ADMIN accounts (enforced in can_manage_user below).
_MANAGER_PERMISSIONS = frozenset({
    Permission.USER_VIEW,
    Permission.USER_CREATE,
    Permission.USER_EDIT,
    Permission.USER_SUSPEND,
    Permission.USER_DELETE,
    Permission.USER_RESET_PASSWORD,
    Permission.TASK_ASSIGN,
    Permission.TASK_VERIFY,
    Permission.TASK_QUERY,
    Permission.REPORT_VIEW,
    Permission.REPORT_GENERATE,
    Permission.HR_DASHBOARD,
})

# HR is visibility-only: it can read people/performance data organization-wide
# but cannot create, edit, suspend or delete anyone, cannot assign or verify
# work, and cannot raise queries. Escalation would have to happen here, in
# writing, not by accident.
_HR_PERMISSIONS = frozenset({
    Permission.USER_VIEW,
    Permission.REPORT_VIEW,
    Permission.HR_DASHBOARD,
})

ROLE_PERMISSIONS = {
    UserRole.SUPER_ADMIN: _ADMIN_PERMISSIONS,
    UserRole.OPERATIONAL_MANAGER: _MANAGER_PERMISSIONS,
    UserRole.HR: _HR_PERMISSIONS,
    UserRole.STAFF: frozenset(),
}


def permissions_for(role):
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(user, *permissions):
    """True only if the user holds EVERY permission asked for."""

    if user is None:
        return False

    granted = permissions_for(user.role)

    return all(permission in granted for permission in permissions)


# ==========================================================
# SCOPE
# ==========================================================

# Roles whose visibility spans the whole organization rather than one
# department. OPERATIONAL_MANAGER is here because the business runs a single
# central manager overseeing every department — every scoped_query() in the
# services layer defers to this, so the rule is stated once.
ORG_SCOPED_ROLES = frozenset({
    UserRole.SUPER_ADMIN,
    UserRole.OPERATIONAL_MANAGER,
    UserRole.HR,
})


def has_org_scope(user):
    return user is not None and user.role in ORG_SCOPED_ROLES


# ==========================================================
# USER-ON-USER AUTHORIZATION
# ==========================================================

def can_manage_user(actor, target, permission):
    """Whether `actor` may perform `permission` against the specific account
    `target`. Returns None when allowed, otherwise the exact refusal message.

    Guards, in order:
      1. the actor must hold the capability at all;
      2. only a SUPER_ADMIN may act on another SUPER_ADMIN — the central
         Manager has admin-equivalent powers over everyone else, but cannot
         edit, suspend, delete or reset the account of the system owner;
      3. nobody may suspend or delete themselves (locking the last admin out
         of their own system is not a recoverable mistake).
    Role *escalation* is checked separately in assert_role_change_allowed,
    because it depends on the payload rather than the target."""

    if not has_permission(actor, permission):
        return "You do not have permission to perform this action."

    if target.role == UserRole.SUPER_ADMIN and actor.role != UserRole.SUPER_ADMIN:
        return "Only a Super Admin can manage another Super Admin account."

    if actor.id == target.id and permission in (Permission.USER_SUSPEND, Permission.USER_DELETE):
        return "You cannot suspend or delete your own account."

    return None


def assert_role_change_allowed(actor, target, new_role):
    """Privilege-escalation gate for a role change. Only a SUPER_ADMIN may
    create or revoke SUPER_ADMIN. A Manager promoting someone (including
    themselves) to Super Admin would be a straight privilege escalation, so
    it is refused server-side regardless of what the client sent.

    Returns None when allowed, otherwise the refusal message."""

    if new_role is None or new_role == target.role:
        return None

    if actor.role == UserRole.SUPER_ADMIN:
        return None

    if new_role == UserRole.SUPER_ADMIN:
        return "Only a Super Admin can grant the Super Admin role."

    if target.role == UserRole.SUPER_ADMIN:
        return "Only a Super Admin can change a Super Admin's role."

    if actor.id == target.id:
        return "You cannot change your own role."

    return None


# ==========================================================
# DECORATORS
# ==========================================================

def _authenticate():
    """Shared front half of every guard: valid token, live account. Returns
    (user, None) on success or (None, response) on failure."""

    verify_jwt_in_request()

    user = _load_current_user()

    if user is None or user.is_deleted:
        return None, err("Authentication token is invalid.", 401)

    if not user.is_active:
        return None, err("Your account is not active. Contact an administrator.", 403)

    return user, None


def require_auth(fn):
    """Any authenticated, active, non-deleted user."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, error = _authenticate()

        if error:
            return error

        g.current_user = user

        return fn(*args, **kwargs)

    return wrapper


def require_roles(*roles):
    """Authenticated + active + role in `roles`. Use in place of @require_auth."""

    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):
            user, error = _authenticate()

            if error:
                return error

            if user.role not in roles:
                return err("You do not have permission to perform this action.", 403)

            g.current_user = user

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_permission(*permissions):
    """Authenticated + active + holds every listed capability. Preferred over
    @require_roles for anything new: it keeps the role -> capability mapping
    in ROLE_PERMISSIONS instead of scattering role names across routes."""

    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):
            user, error = _authenticate()

            if error:
                return error

            if not has_permission(user, *permissions):
                return err("You do not have permission to perform this action.", 403)

            g.current_user = user

            return fn(*args, **kwargs)

        return wrapper

    return decorator
