from flask import Blueprint, request, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)

from services.auth_service import AuthService
from services.audit_service import AuditService
from services.email_service import EmailService
from models.user import User
from models.enums import AuditAction
from utils.response import ok, err
from utils.rbac import require_auth, get_current_user
from utils.serializers import serialize_user

auth_bp = Blueprint("auth", __name__)


def _issue_tokens(user):
    claims = {"role": user.role.value}
    access_token = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims=claims)
    return access_token, refresh_token


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}

    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""

    if not email or not password:
        return err("Email and password are required.", 422)

    success, result = AuthService.authenticate(email, password)

    if not success:
        failing_user = User.query.filter_by(email=email.lower()).first()
        if failing_user:
            AuditService.record_login(failing_user, success=False, failure_reason=result)
            AuditService.log_action(failing_user, AuditAction.LOGIN_FAILED, result)
        return err(result, 401)

    user = result

    access_token, refresh_token = _issue_tokens(user)

    AuditService.record_login(user, success=True)
    AuditService.log_action(user, AuditAction.LOGIN, "User logged in.")

    return ok(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": serialize_user(user),
        },
        message="Login successful.",
    )


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id)) if user_id else None

    if not user or user.is_deleted or not user.is_active:
        return err("Authentication token is invalid.", 401)

    access_token, _ = _issue_tokens(user)

    return ok({"access_token": access_token}, message="Token refreshed.")


@auth_bp.post("/logout")
@require_auth
def logout():
    user = get_current_user()

    AuditService.record_logout(user)
    AuditService.log_action(user, AuditAction.LOGOUT, "User logged out.")

    return ok(message="Logged out successfully.")


@auth_bp.get("/me")
@require_auth
def me():
    return ok({"user": serialize_user(get_current_user())})


@auth_bp.post("/change-password")
@require_auth
def change_password():
    user = get_current_user()
    payload = request.get_json(silent=True) or {}

    current_password = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""

    if len(new_password) < 8:
        return err("New password must be at least 8 characters.", 422)

    success, message = AuthService.change_password(user, current_password, new_password)

    if not success:
        return err(message, 400)

    AuditService.log_action(user, AuditAction.UPDATE, "Password changed.")

    return ok(message=message)


@auth_bp.post("/forgot-password")
def forgot_password():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()

    generic_message = "If an account with that email exists, a reset link has been sent."

    if not email:
        return err("Email is required.", 422)

    user, raw_token = AuthService.request_password_reset(email)

    if user and raw_token:
        frontend_origin = (current_app.config.get("CORS_ORIGINS") or ["http://localhost:5173"])[0]
        reset_link = f"{frontend_origin}/reset-password?token={raw_token}"

        EmailService.send(
            to=user.email,
            subject=f"{current_app.config.get('APP_NAME')} — Password Reset",
            body=(
                f"Hello {user.first_name},\n\n"
                f"Use the link below to reset your password. It expires in 1 hour.\n\n"
                f"{reset_link}\n\n"
                f"If you did not request this, you can ignore this email."
            ),
        )

    return ok(message=generic_message)


@auth_bp.post("/reset-password")
def reset_password():
    payload = request.get_json(silent=True) or {}

    token = payload.get("token") or ""
    new_password = payload.get("new_password") or ""

    if len(new_password) < 8:
        return err("New password must be at least 8 characters.", 422)

    success, message = AuthService.reset_password(token, new_password)

    if not success:
        return err(message, 400)

    return ok(message=message)
