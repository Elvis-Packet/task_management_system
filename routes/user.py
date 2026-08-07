from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from flask_login import (
    login_required,
    current_user
)

from models.enums import (UserRole, UserStatus)
from models.department import (Department)

from services.department_service import (
    get_departments
)

from services.user_service import (
    get_users,
    get_user,
    create_user,
    update_user,
    delete_user,
    activate_user,
    deactivate_user,
    lock_user,
    unlock_user,
    reset_password,
    search_users,
    dashboard_cards,
    generate_employee_number,
    get_managers_by_department,
    get_managers
)

user_bp = Blueprint(
    "user",
    __name__,
    url_prefix="/users"
)


# ==========================================================
# SUPER ADMIN GUARD
# ==========================================================

def super_admin_required():

    if current_user.role != UserRole.SUPER_ADMIN:

        flash(
            "You are not authorized to access this page.",
            "danger"
        )

        return False

    return True


# ==========================================================
# USER DASHBOARD
# ==========================================================

@user_bp.route("/")
@login_required
def index():

    if not super_admin_required():

        return redirect(
            url_for("dashboard.admin_dashboard")
        )

    users = get_users()

    stats = dashboard_cards()

    return render_template(

        "users/index.html",

        users=users,

        stats=stats

    )


# ==========================================================
# CREATE USER
# ==========================================================

@user_bp.route(
    "/create",
    methods=["GET", "POST"]
)
@login_required
def create():

    if not super_admin_required():

        return redirect(
            url_for("dashboard.admin_dashboard")
        )

    departments = get_departments()

    if request.method == "POST":

        # --------------------------------------------------
        # ROLE
        # --------------------------------------------------

        role = UserRole(
            request.form.get("role")
        )

        # --------------------------------------------------
        # DEPARTMENT
        # --------------------------------------------------

        department_id = request.form.get(
            "department_id"
        ) or None

        # --------------------------------------------------
        # AUTO GENERATE EMPLOYEE NUMBER
        # --------------------------------------------------

        employee_number = generate_employee_number(
            role
        )

        # --------------------------------------------------
        # AUTO PICK MANAGER
        # --------------------------------------------------

        manager_id = None

        if (
            role == UserRole.EMPLOYEE
            and department_id
        ):

            department = Department.query.get(
                department_id
            )

            if department:

                manager_id = department.manager_id

        # --------------------------------------------------
        # CREATE USER
        # --------------------------------------------------

        success, message = create_user(

            employee_number=employee_number,

            first_name=request.form.get(
                "first_name"
            ),

            middle_name=request.form.get(
                "middle_name"
            ),

            last_name=request.form.get(
                "last_name"
            ),

            email=request.form.get(
                "email"
            ),

            phone=request.form.get(
                "phone"
            ),

            password=request.form.get(
                "password"
            ),

            role=role,

            department_id=department_id,

            manager_id=manager_id,

            created_by=current_user.id

        )

        flash(
            message,
            "success" if success else "danger"
        )

        if success:

            return redirect(
                url_for("user.index")
            )

    return render_template(

        "users/create.html",

        departments=departments,

        roles=UserRole

    )


# ==========================================================
# VIEW USER
# ==========================================================

@user_bp.route("/<int:user_id>")
@login_required
def view(user_id):

    if not super_admin_required():

        return redirect(
            url_for("dashboard.admin_dashboard")
        )

    user = get_user(user_id)

    return render_template(

        "users/view.html",

        user=user

    )


# ==========================================================
# EDIT USER
# ==========================================================

@user_bp.route(
    "/<int:user_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit(user_id):

    if not super_admin_required():

        return redirect(
            url_for("dashboard.admin_dashboard")
        )


    user = get_user(user_id)

    if not user:

        flash(
            "User not found.",
            "danger"
        )

        return redirect(
            url_for("user.index")
        )


    departments = get_departments()



    if request.method == "POST":


        role = UserRole(
            request.form.get("role")
        )


        success, message = update_user(

            user=user,

            employee_number=request.form.get(
                "employee_number"
            ),

            first_name=request.form.get(
                "first_name"
            ),

            middle_name=request.form.get(
                "middle_name"
            ),

            last_name=request.form.get(
                "last_name"
            ),

            email=request.form.get(
                "email"
            ),

            phone=request.form.get(
                "phone"
            ),

            role=role,

            department_id=(
                request.form.get(
                    "department_id"
                )
                or None
            ),

            status=UserStatus(
                request.form.get("status")
            ),

            is_first_login=(
                request.form.get(
                    "is_first_login"
                ) == "1"
            ),

            password=request.form.get(
                "password"
            )

        )



        flash(
            message,
            "success" if success else "danger"
        )



        if success:

            return redirect(
                url_for(
                    "user.view",
                    user_id=user.id
                )
            )



    return render_template(

        "users/edit.html",

        user=user,

        departments=departments,

        roles=UserRole,

        statuses=UserStatus

    )


# ==========================================================
# DELETE USER
# ==========================================================

@user_bp.route("/<int:user_id>/delete")
@login_required
def delete(user_id):

    if not super_admin_required():

        return redirect(
            url_for("dashboard.admin_dashboard")
        )

    user = get_user(user_id)

    success, message = delete_user(user)

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("user.index")
    )


# ==========================================================
# ACTIVATE
# ==========================================================

@user_bp.route("/<int:user_id>/activate")
@login_required
def activate(user_id):

    user = get_user(user_id)

    success, message = activate_user(user)

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("user.index")
    )


# ==========================================================
# DEACTIVATE
# ==========================================================

@user_bp.route("/<int:user_id>/deactivate")
@login_required
def deactivate(user_id):

    user = get_user(user_id)

    success, message = deactivate_user(user)

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("user.index")
    )


# ==========================================================
# LOCK
# ==========================================================

@user_bp.route("/<int:user_id>/lock")
@login_required
def lock(user_id):

    user = get_user(user_id)

    success, message = lock_user(user)

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("user.index")
    )


# ==========================================================
# UNLOCK
# ==========================================================

@user_bp.route("/<int:user_id>/unlock")
@login_required
def unlock(user_id):

    user = get_user(user_id)

    success, message = unlock_user(user)

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("user.index")
    )


# ==========================================================
# RESET PASSWORD
# ==========================================================

@user_bp.route(
    "/<int:user_id>/reset-password",
    methods=["GET", "POST"]
)
@login_required
def reset(user_id):

    if not super_admin_required():

        return redirect(
            url_for("dashboard.admin_dashboard")
        )

    user = get_user(user_id)

    if request.method == "POST":

        success, message = reset_password(

            user,

            request.form.get(
                "password"
            )

        )

        flash(
            message,
            "success" if success else "danger"
        )

        return redirect(
            url_for("user.view", user_id=user.id)
        )

    return render_template(

        "users/reset_password.html",

        user=user

    )


# ==========================================================
# SEARCH
# ==========================================================

@user_bp.route("/search")
@login_required
def search():

    if not super_admin_required():

        return redirect(
            url_for("dashboard.admin_dashboard")
        )

    query = request.args.get(
        "q",
        ""
    )

    users = search_users(query)

    stats = dashboard_cards()

    return render_template(

        "users/index.html",

        users=users,

        stats=stats,

        query=query

    )