from datetime import datetime

from extensions import db

from models.assigned_task import AssignedTask
from models.assigned_task_performance import AssignedTaskPerformance
from models.enums import TaskStatus


# ==========================================================
# GET OR CREATE PERFORMANCE RECORD
# ==========================================================

def get_or_create_performance(employee):

    performance = AssignedTaskPerformance.query.filter_by(

        employee_id=employee.id

    ).first()

    if performance:

        return performance

    performance = AssignedTaskPerformance(

        employee_id=employee.id,

        employee_number=employee.employee_number

    )

    db.session.add(performance)

    db.session.commit()

    return performance


# ==========================================================
# UPDATE PERFORMANCE
# ==========================================================

def update_assigned_task_performance(employee):

    performance = get_or_create_performance(employee)

    tasks = AssignedTask.query.filter_by(

        employee_id=employee.id

    ).all()

    performance.total_tasks = len(tasks)

    performance.acknowledged_tasks = sum(

        1 for t in tasks if t.acknowledged

    )

    performance.started_tasks = sum(

        1

        for t in tasks

        if t.status == TaskStatus.IN_PROGRESS

    )

    performance.completed_tasks = sum(

        1

        for t in tasks

        if t.status == TaskStatus.COMPLETED

    )

    performance.verified_tasks = sum(

        1

        for t in tasks

        if t.status == TaskStatus.VERIFIED

    )

    performance.rejected_tasks = sum(

        1

        for t in tasks

        if t.status == TaskStatus.REJECTED

    )

    performance.returned_tasks = sum(

        1

        for t in tasks

        if t.returned

    )

    performance.overdue_tasks = sum(

        1

        for t in tasks

        if t.is_overdue

    )

    # -----------------------------------------------------
    # COMPLETION %
    # -----------------------------------------------------

    if performance.total_tasks:

        performance.completion_percentage = round(

            (

                performance.completed_tasks

                /

                performance.total_tasks

            ) * 100,

            2

        )

    else:

        performance.completion_percentage = 0


    # -----------------------------------------------------
    # VERIFICATION %
    # -----------------------------------------------------

    if performance.completed_tasks:

        performance.verification_percentage = round(

            (

                performance.verified_tasks

                /

                performance.completed_tasks

            ) * 100,

            2

        )

    else:

        performance.verification_percentage = 0


    # -----------------------------------------------------
    # QUALITY RATING
    # -----------------------------------------------------

    verified = [

        t

        for t in tasks

        if t.quality_rating is not None

    ]

    if verified:

        performance.average_quality = round(

            sum(

                t.quality_rating

                for t in verified

            ) / len(verified),

            2

        )

    else:

        performance.average_quality = 0


    # -----------------------------------------------------
    # TIMELINESS
    # -----------------------------------------------------

    rated = [

        t

        for t in tasks

        if t.timeliness_rating is not None

    ]

    if rated:

        performance.average_timeliness = round(

            sum(

                t.timeliness_rating

                for t in rated

            ) / len(rated),

            2

        )

    else:

        performance.average_timeliness = 0


    # -----------------------------------------------------
    # OVERALL RATING
    # -----------------------------------------------------

    performance.overall_rating = round(

        (

            performance.average_quality +

            performance.average_timeliness

        ) / 2,

        2

    )


    # -----------------------------------------------------
    # SUCCESS %
    # -----------------------------------------------------

    if performance.total_tasks:

        performance.success_percentage = round(

            (

                performance.verified_tasks

                /

                performance.total_tasks

            ) * 100,

            2

        )

    else:

        performance.success_percentage = 0


    # -----------------------------------------------------
    # LAST VERIFIED
    # -----------------------------------------------------

    verified_dates = [

        t.verified_at

        for t in tasks

        if t.verified_at

    ]

    if verified_dates:

        performance.last_task_verified = max(

            verified_dates

        )


    completed_dates = [

        t.completed_at

        for t in tasks

        if t.completed_at

    ]

    if completed_dates:

        performance.last_task_completed = max(

            completed_dates

        )


    # -----------------------------------------------------
    # STREAK
    # -----------------------------------------------------

    ordered = sorted(

        tasks,

        key=lambda x: x.created_at

    )

    streak = 0

    best = 0

    for task in ordered:

        if task.status == TaskStatus.VERIFIED:

            streak += 1

            best = max(best, streak)

        else:

            streak = 0

    performance.current_success_streak = streak

    performance.best_success_streak = best


    performance.performance_grade = performance.grade

    performance.last_calculated = datetime.utcnow()

    db.session.commit()

    update_rankings()

    return performance


# ==========================================================
# COMPANY RANKINGS
# ==========================================================

def update_rankings():

    performances = AssignedTaskPerformance.query.order_by(

        AssignedTaskPerformance.overall_rating.desc()

    ).all()

    for index, performance in enumerate(

        performances,

        start=1

    ):

        performance.company_rank = index

    db.session.commit()


# ==========================================================
# EMPLOYEE DASHBOARD
# ==========================================================

def get_employee_performance(employee):

    return get_or_create_performance(employee)


# ==========================================================
# TOP PERFORMERS
# ==========================================================

def get_top_performers(limit=10):

    return AssignedTaskPerformance.query.order_by(

        AssignedTaskPerformance.overall_rating.desc()

    ).limit(limit).all()


# ==========================================================
# LOW PERFORMERS
# ==========================================================

def get_low_performers(limit=10):

    return AssignedTaskPerformance.query.order_by(

        AssignedTaskPerformance.overall_rating.asc()

    ).limit(limit).all()