from datetime import datetime

from extensions import db

from models.user import User
from models.activity import Activity
from models.weekly_plan import WeeklyPlan

from models.enums import (
    PlanStatus,
    VerificationStatus,
    ActivityStatus
)



# =====================================================
# DASHBOARD
# =====================================================

def get_manager_dashboard(manager):


    employees = User.query.filter_by(
        manager_id=manager.id
    ).all()


    employee_ids = [
        e.id for e in employees
    ]


    pending_plans = WeeklyPlan.query.filter(

        WeeklyPlan.employee_id.in_(employee_ids),

        WeeklyPlan.status == PlanStatus.SUBMITTED

    ).count()



    active_plans = WeeklyPlan.query.filter(

        WeeklyPlan.employee_id.in_(employee_ids),

        WeeklyPlan.status == PlanStatus.ACTIVE

    ).count()



    completed_plans = WeeklyPlan.query.filter(

        WeeklyPlan.employee_id.in_(employee_ids),

        WeeklyPlan.status == PlanStatus.COMPLETED

    ).count()



    pending_reviews = Activity.query.join(

        WeeklyPlan

    ).filter(

        WeeklyPlan.employee_id.in_(employee_ids),

        Activity.verification_status ==
        VerificationStatus.PENDING

    ).count()



    return {

        "employees": len(employee_ids),

        "pending_plans": pending_plans,

        "active_plans": active_plans,

        "completed_plans": completed_plans,

        "pending_reviews": pending_reviews

    }




# =====================================================
# PLANS WAITING FOR MANAGER REVIEW
# =====================================================

def get_pending_reviews(manager):


    employees = User.query.filter_by(
        manager_id=manager.id
    ).all()


    employee_ids = [
        e.id for e in employees
    ]


    return WeeklyPlan.query.filter(

        WeeklyPlan.employee_id.in_(employee_ids),

        WeeklyPlan.status == PlanStatus.SUBMITTED

    ).order_by(

        WeeklyPlan.created_at.asc()

    ).all()




# =====================================================
# GET SINGLE PLAN
# =====================================================

def get_review_plan(plan_id):

    return WeeklyPlan.query.get_or_404(
        plan_id
    )




# =====================================================
# APPROVE ACTIVITY
# =====================================================

def approve_activity(activity, manager):


    activity.verify(

        manager=manager,

        verification_status=
        VerificationStatus.VERIFIED

    )


    db.session.commit()


    return True, "Activity verified successfully."





# =====================================================
# REJECT ACTIVITY
# =====================================================

def reject_activity(

    activity,

    manager,

    comments=None

):


    activity.verify(

        manager=manager,

        verification_status=
        VerificationStatus.REJECTED,

        comments=comments

    )


    db.session.commit()


    return True, "Activity rejected."





# =====================================================
# APPROVE WEEKLY PLAN
# =====================================================

def approve_plan(plan, manager):


    plan.status = PlanStatus.ACTIVE


    plan.reviewed = True


    plan.reviewed_by = manager.id


    plan.reviewed_at = datetime.utcnow()



    db.session.commit()


    return True, "Weekly plan approved."





# =====================================================
# RETURN PLAN
# =====================================================

def return_plan(

    plan,

    manager,

    comments=None

):


    plan.status = PlanStatus.DRAFT


    plan.reviewed = True


    plan.reviewed_by = manager.id


    plan.reviewed_at = datetime.utcnow()


    plan.manager_comments = comments



    db.session.commit()



    return True, "Plan returned for correction."

def manager_owns_plan(plan, manager):

    return (
        plan.employee.manager_id == manager.id
    )