from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app
)

from flask_login import (
    login_required,
    current_user
)

from models.enums import PlanStatus

from services.weekly_plan_service import (
    create_weekly_plan,
    get_employee_weekly_dashboard,
    get_current_week,
    get_weekly_plan,
    submit_weekly_plan,
    update_weekly_plan
)


# ==========================================================
# BLUEPRINT
# ==========================================================

weekly_plan_bp = Blueprint(
    "weekly_plan",
    __name__,
    url_prefix="/weekly-plans"
)


# ==========================================================
# EMPLOYEE DASHBOARD
# ==========================================================

@weekly_plan_bp.route("/")
@login_required
def dashboard():

    data = get_employee_weekly_dashboard(
        current_user
    )

    return render_template(
        "weekly_plan/dashboard.html",
        **data
    )


# ==========================================================
# CREATE WEEKLY PLAN
# ==========================================================

@weekly_plan_bp.route(
    "/create",
    methods=["GET", "POST"]
)
@login_required
def create():

    week_start, week_end = get_current_week()


    if request.method == "POST":


        objectives = request.form.get(
            "objectives"
        )

        notes = request.form.get(
            "notes"
        )


        # -----------------------------------------
        # ACTIVITIES COLLECTION
        # -----------------------------------------

        activities = []


        titles = request.form.getlist(
            "activity_title[]"
        )

        descriptions = request.form.getlist(
            "activity_description[]"
        )

        dates = request.form.getlist(
            "activity_date[]"
        )

        priorities = request.form.getlist(
            "activity_priority[]"
        )


        rows = len(titles)


        for i in range(rows):

            if not titles[i].strip():
                continue


            activities.append({

                "employee_number":
                    current_user.employee_number,


                "title":
                    titles[i].strip(),


                "description":
                    descriptions[i].strip()
                    if i < len(descriptions)
                    else "",


                "activity_date":
                    dates[i]
                    if i < len(dates)
                    else None,


                "priority":
                    priorities[i]
                    if i < len(priorities)
                    else "NORMAL"

            })



        # -----------------------------------------
        # CREATE PLAN
        # -----------------------------------------

        success, message, plan = create_weekly_plan(

            employee=current_user,

            objectives=objectives,

            notes=notes,

            activities=activities

        )


        flash(

            message,

            "success"
            if success
            else "danger"

        )


        if success:

            return redirect(

                url_for(

                    "weekly_plan.view",

                    plan_id=plan.id

                )

            )


    return render_template(

        "weekly_plan/create.html",

        week_start=week_start,

        week_end=week_end

    )



# ==========================================================
# VIEW PLAN
# ==========================================================

@weekly_plan_bp.route(
    "/<int:plan_id>"
)
@login_required
def view(plan_id):


    plan = get_weekly_plan(
        plan_id
    )


    if (

        plan.employee_id != current_user.id

        and not current_user.is_manager

        and not current_user.is_super_admin

    ):

        flash(

            "You are not authorized to view this plan.",

            "danger"

        )

        return redirect(

            url_for(
                "weekly_plan.dashboard"
            )

        )


    return render_template(

        "weekly_plan/view.html",

        plan=plan

    )



# ==========================================================
# EDIT PLAN
# ==========================================================

@weekly_plan_bp.route(
    "/<int:plan_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit(plan_id):


    plan = get_weekly_plan(
        plan_id
    )


    if plan.employee_id != current_user.id:


        flash(

            "You cannot edit this plan.",

            "danger"

        )

        return redirect(

            url_for(
                "weekly_plan.dashboard"
            )

        )


    if plan.status != PlanStatus.DRAFT:


        flash(

            "Only draft plans can be edited.",

            "warning"

        )


        return redirect(

            url_for(

                "weekly_plan.view",

                plan_id=plan.id

            )

        )



    if request.method == "POST":


        objectives = request.form.get(
            "objectives"
        )

        notes = request.form.get(
            "notes"
        )


        activity_ids = request.form.getlist(
            "activity_id[]"
        )

        titles = request.form.getlist(
            "activity_title[]"
        )

        descriptions = request.form.getlist(
            "activity_description[]"
        )

        dates = request.form.getlist(
            "activity_date[]"
        )

        priorities = request.form.getlist(
            "activity_priority[]"
        )


        activities=[]


        for i,title in enumerate(titles):


            if not title.strip():

                continue


            activities.append({

                "id":
                    activity_ids[i]
                    if i < len(activity_ids)
                    else None,


                "employee_number":
                    current_user.employee_number,


                "title":
                    title.strip(),


                "description":
                    descriptions[i]
                    if i < len(descriptions)
                    else "",


                "activity_date":
                    dates[i]
                    if i < len(dates)
                    else None,


                "priority":
                    priorities[i]
                    if i < len(priorities)
                    else "NORMAL"

            })



        success,message = update_weekly_plan(

            plan,

            objectives,

            notes,

            activities

        )


        flash(

            message,

            "success"
            if success
            else "danger"

        )


        if success:

            return redirect(

                url_for(

                    "weekly_plan.view",

                    plan_id=plan.id

                )

            )



    return render_template(

        "weekly_plan/edit.html",

        plan=plan

    )



# ==========================================================
# SUBMIT PLAN
# ==========================================================

@weekly_plan_bp.route(
    "/<int:plan_id>/submit"
)
@login_required
def submit(plan_id):


    plan = get_weekly_plan(
        plan_id
    )


    if plan.employee_id != current_user.id:


        flash(

            "You cannot submit this plan.",

            "danger"

        )


        return redirect(

            url_for(
                "weekly_plan.dashboard"
            )

        )



    if plan.status != PlanStatus.DRAFT:


        flash(

            "Only draft plans can be submitted.",

            "warning"

        )


        return redirect(

            url_for(

                "weekly_plan.view",

                plan_id=plan.id

            )

        )



    success,message = submit_weekly_plan(
        plan
    )



    flash(

        message,

        "success"
        if success
        else "danger"

    )


    return redirect(

        url_for(

            "weekly_plan.view",

            plan_id=plan.id

        )

    )

from datetime import datetime

from flask import (
    request,
    redirect,
    url_for,
    flash
)

from flask_login import (
    login_required,
    current_user
)

from extensions import db

from models.activity import Activity
from models.enums import ActivityStatus


@weekly_plan_bp.route(
    "/activity/<int:activity_id>/complete",
    methods=["POST"]
)
@login_required
def complete_activity(activity_id):

    activity = Activity.query.get_or_404(activity_id)

    # Ensure employee owns the activity
    if activity.plan.employee_id != current_user.id:
        flash(
            "You are not authorized to update this activity.",
            "danger"
        )
        return redirect(
            url_for("weekly_plan.dashboard")
        )

    status = request.form.get("status")

    notes = request.form.get("completion_notes")

    if status == "DONE":

        activity.employee_status = ActivityStatus.DONE

        activity.completed_at = datetime.utcnow()

    else:

        activity.employee_status = ActivityStatus.NOT_DONE

    activity.completion_notes = notes

    # Optional evidence upload
    file = request.files.get("evidence")

    if file and file.filename:

        filename = file.filename

        file.save(
            f"{current_app.config['EVIDENCE_FOLDER']}/{filename}"
        )

        activity.evidence_file = filename

    db.session.commit()

    flash(
        "Activity updated successfully.",
        "success"
    )

    return redirect(
        url_for(
            "weekly_plan.view",
            plan_id=activity.plan_id
        )
    )