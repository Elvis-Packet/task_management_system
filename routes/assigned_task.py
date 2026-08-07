from datetime import datetime

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

from models.enums import (
    UserRole,
    TaskPriority
)

from services.user_service import (
    get_department_employees
)

from services.assigned_task_service import (
    create_task,
    update_task,
    delete_task,
    get_task,
    get_manager_tasks,
    get_employee_tasks,
    complete_task,
    verify_task,
    return_task,
    dashboard_cards,
    get_tasks_waiting_review
)

assigned_task_bp = Blueprint(
    "assigned_task",
    __name__,
    url_prefix="/assigned-tasks"
)


# ==========================================================
# MANAGER GUARD
# ==========================================================

def manager_required():

    if current_user.role not in (
        UserRole.OPERATIONS_MANAGER,
        UserRole.SUPER_ADMIN
    ):

        flash(
            "Access denied.",
            "danger"
        )

        return False

    return True


# ==========================================================
# MANAGER DASHBOARD
# ==========================================================

@assigned_task_bp.route("/")
@login_required
def index():

    if not manager_required():
        return redirect(url_for("dashboard.index"))

    tasks = get_manager_tasks(current_user.id)

    cards = dashboard_cards(current_user.id)

    return render_template(
        "assigned_tasks/index.html",
        tasks=tasks,
        cards=cards
    )


# ==========================================================
# CREATE TASK
# ==========================================================

@assigned_task_bp.route(
    "/create",
    methods=["GET", "POST"]
)
@login_required
def create():

    if not manager_required():
        return redirect(url_for("dashboard.index"))

    employees = get_department_employees(
        current_user.department_id
    )

    if request.method == "POST":

        success, message, task = create_task(

            employee_id=request.form["employee_id"],

            manager_id=current_user.id,

            department_id=current_user.department_id,

            title=request.form["title"],

            description=request.form.get("description"),

            assigned_date=datetime.today().date(),

            assigned_time=datetime.now().time(),

            due_date=datetime.strptime(
                request.form["due_date"],
                "%Y-%m-%d"
            ).date(),

            due_time=datetime.strptime(
                request.form["due_time"],
                "%H:%M"
            ).time(),

            priority=request.form["priority"]

        )

        flash(
            message,
            "success" if success else "danger"
        )

        if success:

            return redirect(
                url_for("assigned_task.index")
            )

    return render_template(
        "assigned_tasks/create.html",
        employees=employees,
        priorities=TaskPriority
    )


# ==========================================================
# VIEW
# ==========================================================

@assigned_task_bp.route("/<int:task_id>")
@login_required
def view(task_id):

    task = get_task(task_id)

    return render_template(
        "assigned_tasks/view.html",
        task=task
    )


# ==========================================================
# EDIT
# ==========================================================

@assigned_task_bp.route(
    "/<int:task_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit(task_id):

    task = get_task(task_id)

    employees = get_department_employees(
        current_user.department_id
    )

    if request.method == "POST":

        success, message = update_task(

            task=task,

            employee_id=request.form["employee_id"],

            title=request.form["title"],

            description=request.form.get("description"),

            due_date=datetime.strptime(
                request.form["due_date"],
                "%Y-%m-%d"
            ).date(),

            due_time=datetime.strptime(
                request.form["due_time"],
                "%H:%M"
            ).time(),

            priority=request.form["priority"]

        )

        flash(
            message,
            "success" if success else "danger"
        )

        if success:

            return redirect(
                url_for(
                    "assigned_task.view",
                    task_id=task.id
                )
            )

    return render_template(
        "assigned_tasks/edit.html",
        task=task,
        employees=employees,
        priorities=TaskPriority
    )


# ==========================================================
# DELETE
# ==========================================================

@assigned_task_bp.route("/<int:task_id>/delete")
@login_required
def delete(task_id):

    task = get_task(task_id)

    success, message = delete_task(task)

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("assigned_task.index")
    )


# ==========================================================
# EMPLOYEE TASKS
# ==========================================================

@assigned_task_bp.route("/my-tasks")
@login_required
def my_tasks():

    tasks = get_employee_tasks(
        current_user.id
    )

    return render_template(
        "assigned_tasks/my_tasks.html",
        tasks=tasks
    )


# ==========================================================
# EMPLOYEE COMPLETE
# ==========================================================

@assigned_task_bp.route(
    "/<int:task_id>/complete",
    methods=["POST"]
)
@login_required
def complete(task_id):

    task = get_task(task_id)

    success, message = complete_task(

        task=task,

        employee=current_user,

        notes=request.form.get(
            "completion_notes"
        ),

        evidence=request.form.get(
            "evidence_file"
        )

    )

    flash(
        message,
        "success" if success else "danger"
    )

    return redirect(
        url_for("assigned_task.my_tasks")
    )


# ==========================================================
# REVIEW QUEUE
# ==========================================================

@assigned_task_bp.route("/review")
@login_required
def review_queue():

    if not manager_required():
        return redirect(url_for("dashboard.index"))

    tasks = get_tasks_waiting_review(
        current_user.id
    )

    return render_template(
        "assigned_tasks/review_queue.html",
        tasks=tasks
    )


# ==========================================================
# VERIFY TASK
# ==========================================================

@assigned_task_bp.route(
    "/<int:task_id>/review",
    methods=["GET", "POST"]
)
@login_required
def review(task_id):

    if not manager_required():
        return redirect(url_for("dashboard.index"))

    task = get_task(task_id)

    if request.method == "POST":

        decision = request.form.get("decision")

        if decision == "approve":

            success, message = verify_task(

                task=task,

                manager=current_user,

                quality_rating=int(
                    request.form["quality_rating"]
                ),

                timeliness_rating=int(
                    request.form["timeliness_rating"]
                ),

                feedback=request.form.get(
                    "feedback"
                ),

                notes=request.form.get(
                    "verification_notes"
                )

            )

        else:

            success, message = return_task(

                task=task,

                manager=current_user,

                reason=request.form.get(
                    "return_reason"
                )

            )

        flash(
            message,
            "success" if success else "danger"
        )

        if success:

            return redirect(
                url_for(
                    "assigned_task.review_queue"
                )
            )

    return render_template(
        "assigned_tasks/review.html",
        task=task
    )