from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash
)

from flask_login import (
    login_required,
    current_user
)


from models.enums import UserRole

from models.user import User

from models.performance_summary import PerformanceSummary

from services.performance_summary_service import (
    calculate_summary,
    get_or_create_summary
)


from services.assigned_task_performance_service import (
    get_top_performers,
    get_low_performers
)


from models.performance import Performance



performance_bp = Blueprint(

    "performance",

    __name__,

    url_prefix="/performance"

)



# ==========================================================
# ACCESS CONTROL
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
# EMPLOYEE PERFORMANCE DASHBOARD
# ==========================================================


@performance_bp.route("/dashboard")
@login_required
def dashboard():


    performance = calculate_summary(

        current_user

    )


    return render_template(

        "performance/dashboard.html",

        performance=performance

    )



# ==========================================================
# MANAGER PERFORMANCE OVERVIEW
# ==========================================================


@performance_bp.route("/overview")
@login_required
def overview():


    if not manager_required():

        return redirect(

            url_for(
                "dashboard.index"
            )

        )


    employees = PerformanceSummary.query.order_by(

        PerformanceSummary.overall_percentage.desc()

    ).all()



    return render_template(

        "performance/overview.html",

        employees=employees

    )




# ==========================================================
# SINGLE EMPLOYEE PERFORMANCE
# ==========================================================


@performance_bp.route(
    "/employee/<int:employee_id>"
)
@login_required
def employee_performance(employee_id):


    if not manager_required():

        return redirect(

            url_for(
                "dashboard.index"
            )

        )


    employee = User.query.get_or_404(

        employee_id

    )


    performance = calculate_summary(

        employee

    )



    return render_template(

        "performance/employee.html",

        employee=employee,

        performance=performance

    )





# ==========================================================
# COMPANY RANKINGS
# ==========================================================


@performance_bp.route("/rankings")
@login_required
def rankings():


    if not manager_required():

        return redirect(

            url_for(
                "dashboard.index"
            )

        )


    rankings = PerformanceSummary.query.order_by(

        PerformanceSummary.overall_percentage.desc()

    ).all()



    return render_template(

        "performance/rankings.html",

        rankings=rankings

    )





# ==========================================================
# TOP PERFORMERS
# ==========================================================


@performance_bp.route("/top-performers")
@login_required
def top_performers():


    if not manager_required():

        return redirect(

            url_for(
                "dashboard.index"
            )

        )


    performers = get_top_performers()



    return render_template(

        "performance/top.html",

        performers=performers

    )





# ==========================================================
# LOW PERFORMERS
# ==========================================================


@performance_bp.route("/low-performers")
@login_required
def low_performers():


    if not manager_required():

        return redirect(

            url_for(
                "dashboard.index"
            )

        )


    performers = get_low_performers()



    return render_template(

        "performance/low.html",

        performers=performers

    )





# ==========================================================
# NORMAL ACTIVITY REPORT
# ==========================================================


@performance_bp.route(
    "/activities/<int:employee_id>"
)
@login_required
def activity_report(employee_id):


    if not manager_required():

        return redirect(

            url_for(
                "dashboard.index"
            )

        )


    employee = User.query.get_or_404(

        employee_id

    )


    activities = Performance.query.filter_by(

        employee_id=employee.id

    ).order_by(

        Performance.created_at.desc()

    ).all()



    return render_template(

        "performance/activity_report.html",

        employee=employee,

        activities=activities

    )





# ==========================================================
# ASSIGNED TASK REPORT
# ==========================================================


@performance_bp.route(
    "/assigned/<int:employee_id>"
)
@login_required
def assigned_task_report(employee_id):


    if not manager_required():

        return redirect(

            url_for(
                "dashboard.index"
            )

        )


    employee = User.query.get_or_404(

        employee_id

    )


    performance = employee.assigned_task_performance



    return render_template(

        "performance/assigned_report.html",

        employee=employee,

        performance=performance

    )