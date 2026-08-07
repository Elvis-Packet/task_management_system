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


from models.activity import Activity

from models.enums import (
    VerificationStatus
)

from services.review_service import review_activity



task_review_bp = Blueprint(

    "task_review",

    __name__,

    url_prefix="/task-review"

)



# =====================================================
# MANAGER REVIEW DASHBOARD
# =====================================================


@task_review_bp.route("/")
@login_required
def index():


    activities = Activity.query.filter(

        Activity.verification_status ==
        VerificationStatus.PENDING,

        Activity.employee_status != "PENDING"

    ).order_by(

        Activity.activity_date.desc()

    ).all()



    return render_template(

        "task_review/index.html",

        activities=activities

    )





# =====================================================
# REVIEW SINGLE ACTIVITY
# =====================================================


@task_review_bp.route(
    "/activity/<int:id>",
    methods=[
        "GET",
        "POST"
    ]
)
@login_required
def review(id):


    activity = Activity.query.get_or_404(id)



    if request.method == "POST":


        verification = request.form.get(
            "verification"
        )


        quality = request.form.get(
            "quality_rating"
        )


        timeliness = request.form.get(
            "timeliness_rating"
        )


        comments = request.form.get(
            "comments"
        )



        review_activity(

            activity,

            current_user,

            VerificationStatus[
                verification
            ],

            quality,

            timeliness,

            comments

        )



        flash(

            "Activity reviewed successfully.",

            "success"

        )



        return redirect(

            url_for(
                "task_review.index"
            )

        )




    return render_template(

        "task_review/review.html",

        activity=activity

    )
