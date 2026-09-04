import hashlib
import secrets
from datetime import datetime, timedelta

from extensions import db, bcrypt
from models.user import User
from models.enums import UserStatus

RESET_TOKEN_TTL = timedelta(hours=1)


def _hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class AuthService:

    @staticmethod
    def authenticate(email, password):
        """
        Returns:
            (True, user) on success
            (False, message) on failure
        """

        email = (email or "").strip().lower()

        user = User.query.filter_by(email=email).first()

        if not user or user.is_deleted:
            return False, "Invalid email or password."

        if user.status == UserStatus.INACTIVE:
            return False, "Your account has been suspended. Contact an administrator."

        if user.status == UserStatus.LOCKED:
            return False, "Your account has been locked. Contact an administrator."

        if not user.check_password(password):
            user.failed_login_attempts += 1

            if user.failed_login_attempts >= 5:
                user.status = UserStatus.LOCKED

            db.session.commit()

            return False, "Invalid email or password."

        user.failed_login_attempts = 0
        user.last_login = datetime.utcnow()
        user.last_activity = datetime.utcnow()

        db.session.commit()

        return True, user

    @staticmethod
    def update_last_activity(user):
        user.last_activity = datetime.utcnow()
        db.session.commit()

    @staticmethod
    def change_password(user, current_password, new_password):
        if not user.check_password(current_password):
            return False, "Current password is incorrect."

        user.set_password(new_password)
        user.password_changed_at = datetime.utcnow()
        user.is_first_login = False
        db.session.commit()

        return True, "Password changed successfully."

    @staticmethod
    def request_password_reset(email):
        """Always returns a generic outcome to the caller (no user-enumeration),
        but returns the raw token internally so the route can email/log it
        only when a matching, active account actually exists."""

        email = (email or "").strip().lower()

        user = User.query.filter_by(email=email).first()

        if not user or user.is_deleted or user.status != UserStatus.ACTIVE:
            return None, None

        raw_token = secrets.token_urlsafe(32)

        user.reset_token_hash = _hash_token(raw_token)
        user.reset_token_expires_at = datetime.utcnow() + RESET_TOKEN_TTL

        db.session.commit()

        return user, raw_token

    @staticmethod
    def reset_password(token, new_password):
        if not token:
            return False, "Invalid or expired reset token."

        token_hash = _hash_token(token)

        user = User.query.filter_by(reset_token_hash=token_hash).first()

        if (
            not user
            or user.is_deleted
            or not user.reset_token_expires_at
            or user.reset_token_expires_at < datetime.utcnow()
        ):
            return False, "Invalid or expired reset token."

        user.set_password(new_password)
        user.reset_token_hash = None
        user.reset_token_expires_at = None
        user.password_changed_at = datetime.utcnow()
        user.failed_login_attempts = 0

        if user.status == UserStatus.LOCKED:
            user.status = UserStatus.ACTIVE

        db.session.commit()

        return True, "Password reset successfully."
