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

from models.enums import UserRole

from services.department_service import (
    create_department,
    get_departments,
    get_department,
    update_department,
    delete_department,
    activate_department,
    deactivate_department,
    search_departments,
    department_statistics
)

department_bp = Blueprint(
    "department",
    __name__,
    url_prefix="/departments"
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
# DASHBOARD
# ==========================================================

@department_bp.route("/")
@login_required
def index():

    if not super_admin_required():
        return redirect(url_for("dashboard.index"))

    departments = get_departments()

    stats = department_statistics()

    return render_template(

        "departments/index.html",

        departments=departments,

        stats=stats

    )


# ==========================================================
# CREATE
# ==========================================================

@department_bp.route(
    "/create",
    methods=["GET", "POST"]
)
@login_required
def create():

    if not super_admin_required():
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":

        success, message = create_department(

            department_name=request.form.get(
                "department_name"
            ),

            department_code=request.form.get(
                "department_code"
            ),

            description=request.form.get(
                "description"
            )

        )

        flash(
            message,
            "success" if success else "danger"
        )

        if success:

            return redirect(
                url_for("department.index")
            )

    return render_template(
        "departments/create.html"
    )


# ==========================================================
# EDIT
# ==========================================================

@department_bp.route(
    "/<int:department_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit(department_id):

    if not super_admin_required():
        return redirect(url_for("dashboard.index"))

    department = get_department(
        department_id
    )

    if request.method == "POST":

        success, message = update_department(

            department,

            request.form.get("department_name"),

            request.form.get("department_code"),

            request.form.get("description")

        )

        flash(
            message,
            "success" if success else "danger"
        )

        if success:

            return redirect(
                url_for("department.index")
            )

    return render_template(

        "departments/edit.html",

        department=department

    )


# ==========================================================
# ACTIVATE
# ==========================================================

@department_bp.route(
    "/<int:department_id>/activate"
)
@login_required
def activate(department_id):

    if not super_admin_required():
        return redirect(url_for("dashboard.index"))

    department = get_department(
        department_id
    )

    success, message = activate_department(
        department
    )

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("department.index")
    )


# ==========================================================
# DEACTIVATE
# ==========================================================

@department_bp.route(
    "/<int:department_id>/deactivate"
)
@login_required
def deactivate(department_id):

    if not super_admin_required():
        return redirect(url_for("dashboard.index"))

    department = get_department(
        department_id
    )

    success, message = deactivate_department(
        department
    )

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("department.index")
    )


# ==========================================================
# DELETE
# ==========================================================

@department_bp.route(
    "/<int:department_id>/delete"
)
@login_required
def delete(department_id):

    if not super_admin_required():
        return redirect(url_for("dashboard.index"))

    department = get_department(
        department_id
    )

    success, message = delete_department(
        department
    )

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("department.index")
    )


# ==========================================================
# SEARCH
# ==========================================================

@department_bp.route("/search")
@login_required
def search():

    if not super_admin_required():
        return redirect(url_for("dashboard.index"))

    query = request.args.get(
        "q",
        ""
    )

    departments = search_departments(
        query
    )

    stats = department_statistics()

    return render_template(

        "departments/index.html",

        departments=departments,

        stats=stats,

        query=query

    )