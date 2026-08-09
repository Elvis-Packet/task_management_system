from functools import wraps

from flask import g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

from models.user import User
from utils.response import err


def _load_current_user():
    user_id = get_jwt_identity()

    if user_id is None:
        return None

    return User.query.get(int(user_id))


def get_current_user():
    """Only valid inside a request already guarded by @require_auth/@require_roles."""
    return getattr(g, "current_user", None)


def require_auth(fn):
    """Any authenticated, active, non-deleted user."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()

        user = _load_current_user()

        if user is None or user.is_deleted:
            return err("Authentication token is invalid.", 401)

        if not user.is_active:
            return err("Your account is not active. Contact an administrator.", 403)

        g.current_user = user

        return fn(*args, **kwargs)

    return wrapper


def require_roles(*roles):
    """Authenticated + active + role in `roles`. Use in place of @require_auth."""

    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()

            user = _load_current_user()

            if user is None or user.is_deleted:
                return err("Authentication token is invalid.", 401)

            if not user.is_active:
                return err("Your account is not active. Contact an administrator.", 403)

            if user.role not in roles:
                return err("You do not have permission to perform this action.", 403)

            g.current_user = user

            return fn(*args, **kwargs)

        return wrapper

    return decorator
