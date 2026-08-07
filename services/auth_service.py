from datetime import datetime

from flask_login import login_user, logout_user

from extensions import db

from models.user import User
from models.enums import UserStatus


class AuthService:

    @staticmethod
    def authenticate(email, password, remember=False):
        """
        Authenticate a user.
        Returns:
            (True, user) on success
            (False, message) on failure
        """

        email = email.strip().lower()

        user = User.query.filter_by(email=email).first()

        if not user:
            return False, "Invalid email or password."

        if user.status == UserStatus.INACTIVE:
            return False, "Your account has been deactivated."

        if user.status == UserStatus.LOCKED:
            return False, "Your account has been locked. Please contact the administrator."

        if not user.check_password(password):
            user.failed_login_attempts += 1

            db.session.commit()

            return False, "Invalid email or password."

        # Reset failed attempts
        user.failed_login_attempts = 0

        user.last_login = datetime.utcnow()

        user.last_activity = datetime.utcnow()

        login_user(
            user,
            remember=remember
        )

        db.session.commit()

        return True, user

    @staticmethod
    def logout():

        logout_user()

    @staticmethod
    def update_last_activity(user):

        user.last_activity = datetime.utcnow()

        db.session.commit()

    @staticmethod
    def change_password(user, new_password):

        user.set_password(new_password)

        user.password_changed_at = datetime.utcnow()

        db.session.commit()