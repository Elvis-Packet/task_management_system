from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request
)

from flask_login import (
    login_required,
    current_user
)

from models.enums import (
    UserRole
)

from models.activity import Activity

from services.manager_review_service import (
    get_manager_dashboard,
    get_pending_reviews,
    get_review_plan,
    approve_activity,
    reject_activity,
    approve_plan,
    return_plan,
    manager_owns_plan
)

manager_review_bp = Blueprint(

    "manager_review",

    __name__,

    url_prefix="/manager/reviews"

)


# ==========================================================
# MANAGER GUARD
# ==========================================================

def manager_required():

    if current_user.role not in [

        UserRole.OPERATIONS_MANAGER,

        UserRole.SUPER_ADMIN

    ]:

        flash(

            "You are not authorized to access this page.",

            "danger"

        )

        return False

    return True


# ==========================================================
# DASHBOARD
# ==========================================================

@manager_review_bp.route("/")
@login_required
def dashboard():

    if not manager_required():

        return redirect(

            url_for("dashboard.admin_dashboard")

        )

    stats = get_manager_dashboard(

        current_user

    )

    plans = get_pending_reviews(

        current_user

    )

    return render_template(

        "manager_review/dashboard.html",

        stats=stats,

        plans=plans

    )


# ==========================================================
# REVIEW PLAN
# ==========================================================

@manager_review_bp.route("/<int:plan_id>")
@login_required
def review(plan_id):

    if not manager_required():

        return redirect(

            url_for("dashboard.admin_dashboard")

        )

    plan = get_review_plan(plan_id)


    if not manager_owns_plan(plan, current_user):

        flash(
            "You are not authorized to review this plan.",
            "danger"
        )

        return redirect(
            url_for(
                "manager_review.dashboard"
            )
        )
            

    return render_template(

        "manager_review/review_plan.html",

        plan=plan

    )


# ==========================================================
# APPROVE ACTIVITY
# ==========================================================

@manager_review_bp.route(

    "/activity/<int:activity_id>/approve"

)

@login_required
def approve_activity_route(activity_id):

    if not manager_required():

        return redirect(

            url_for("dashboard.admin_dashboard")

        )

    activity = Activity.query.get_or_404(

        activity_id

    )

    success, message = approve_activity(

        activity,

        current_user

    )

    flash(

        message,

        "success" if success else "danger"

    )

    return redirect(

        url_for(

            "manager_review.review",

            plan_id=activity.plan_id

        )

    )


# ==========================================================
# REJECT ACTIVITY
# ==========================================================

@manager_review_bp.route(

    "/activity/<int:activity_id>/reject",

    methods=[

        "POST"

    ]

)

@login_required
def reject_activity_route(activity_id):

    if not manager_required():

        return redirect(

            url_for("dashboard.admin_dashboard")

        )

    activity = Activity.query.get_or_404(

        activity_id

    )

    comments = request.form.get(

        "comments"

    )

    success, message = reject_activity(

        activity,

        current_user,

        comments

    )

    flash(

        message,

        "success" if success else "danger"

    )

    return redirect(

        url_for(

            "manager_review.review",

            plan_id=activity.plan_id

        )

    )


# ==========================================================
# APPROVE PLAN
# ==========================================================

@manager_review_bp.route(

    "/plan/<int:plan_id>/approve"

)

@login_required
def approve_plan_route(plan_id):

    if not manager_required():

        return redirect(

            url_for("dashboard.admin_dashboard")

        )

    plan = get_review_plan(

        plan_id

    )

    success, message = approve_plan(

        plan,

        current_user

    )

    flash(

        message,

        "success"

    )

    return redirect(

        url_for(

            "manager_review.dashboard"

        )

    )


# ==========================================================
# RETURN PLAN
# ==========================================================

@manager_review_bp.route(

    "/plan/<int:plan_id>/return",

    methods=[

        "POST"

    ]

)

@login_required
def return_plan_route(plan_id):

    if not manager_required():

        return redirect(

            url_for("dashboard.admin_dashboard")

        )

    plan = get_review_plan(

        plan_id

    )

    comments = request.form.get(

        "comments"

    )

    success, message = return_plan(

        plan,

        current_user,

        comments

    )

    flash(

        message,

        "warning"

    )

    return redirect(

        url_for(

            "manager_review.dashboard"

        )

    )