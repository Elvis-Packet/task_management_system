from datetime import date

from models.user import User
from models.weekly_plan import WeeklyPlan
from models.activity import Activity
from models.assigned_task import AssignedTask
from models.notification import Notification

from models.enums import (
    PlanStatus,
    VerificationStatus,
    TaskStatus
)

def get_managers():

    return User.query.filter_by(
        role="MANAGER"
    ).order_by(
        User.first_name.asc()
    ).all()

def get_manager_dashboard(manager):

    today = date.today()

    employees = User.query.filter_by(
        role="EMPLOYEE"
    ).count()

    active_plans = WeeklyPlan.query.filter(
        WeeklyPlan.status == PlanStatus.ACTIVE
    ).count()

    submitted_plans = WeeklyPlan.query.filter(
        WeeklyPlan.status == PlanStatus.SUBMITTED
    ).count()

    pending_reviews = Activity.query.filter(
        Activity.verification_status ==
        VerificationStatus.PENDING
    ).count()

    verified_activities = Activity.query.filter(
        Activity.verification_status ==
        VerificationStatus.VERIFIED
    ).count()

    assigned_tasks = AssignedTask.query.count()

    due_today = AssignedTask.query.filter(
        AssignedTask.assigned_date == today
    ).count()

    overdue_tasks = AssignedTask.query.filter(
        AssignedTask.status ==
        TaskStatus.OVERDUE
    ).count()

    notifications = Notification.query.filter_by(
        recipient_id=manager.id,
        read=False
    ).count()

    recent_plans = WeeklyPlan.query.order_by(
        WeeklyPlan.created_at.desc()
    ).limit(10).all()

    recent_tasks = AssignedTask.query.order_by(
        AssignedTask.created_at.desc()
    ).limit(10).all()

    recent_notifications = Notification.query.filter_by(
        recipient_id=manager.id
    ).order_by(
        Notification.created_at.desc()
    ).limit(10).all()

    return {

        "employees": employees,

        "active_plans": active_plans,

        "submitted_plans": submitted_plans,

        "pending_reviews": pending_reviews,

        "verified_activities": verified_activities,

        "assigned_tasks": assigned_tasks,

        "due_today": due_today,

        "overdue_tasks": overdue_tasks,

        "notifications": notifications,

        "recent_plans": recent_plans,

        "recent_tasks": recent_tasks,

        "recent_notifications": recent_notifications

    }