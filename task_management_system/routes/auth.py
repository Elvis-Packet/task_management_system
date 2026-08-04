from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from flask_login import (
    current_user,
    login_required
)

from services.auth_service import AuthService
from models.enums import UserRole

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth"
)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:

        if current_user.role == UserRole.SUPER_ADMIN:
            return redirect(url_for("admin.dashboard"))

        elif current_user.role == UserRole.OPERATIONS_MANAGER:
            return redirect(url_for("manager.dashboard"))

        return redirect(url_for("employee.dashboard"))

    if request.method == "POST":

        email = request.form.get("email", "").strip()

        password = request.form.get("password", "")

        remember = request.form.get("remember") == "on"

        success, result = AuthService.authenticate(
            email=email,
            password=password,
            remember=remember
        )

        if success:

            user = result

            flash(
                f"Welcome back, {user.full_name}.",
                "success"
            )

            if user.role == UserRole.SUPER_ADMIN:
                return redirect(url_for("admin.dashboard"))

            elif user.role == UserRole.OPERATIONS_MANAGER:
                return redirect(url_for("manager.dashboard"))

            return redirect(url_for("dashboard.employee_dashboard"))

        flash(result, "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():

    AuthService.logout()

    flash(
        "You have been logged out successfully.",
        "success"
    )

    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password")
def forgot_password():

    return render_template("auth/forgot_password.html")


@auth_bp.route("/verify-otp")
def verify_otp():

    return render_template("auth/verify_otp.html")


@auth_bp.route("/reset-password")
def reset_password():

    return render_template("auth/reset_password.html")