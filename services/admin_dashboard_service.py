from models.user import User
from models.department import Department
from models.weekly_plan import WeeklyPlan
from models.activity import Activity
from models.assigned_task import AssignedTask
from models.notification import Notification
from models.audit_log import AuditLog
from models.login_history import LoginHistory

from models.enums import (
    UserRole,
    PlanStatus,
    VerificationStatus
)


def get_admin_dashboard():

    total_users = User.query.count()

    employees = User.query.filter_by(
        role=UserRole.EMPLOYEE
    ).count()

    managers = User.query.filter_by(
        role=UserRole.OPERATIONS_MANAGER
    ).count()

    admins = User.query.filter_by(
        role=UserRole.SUPER_ADMIN
    ).count()

    departments = Department.query.count()

    active_plans = WeeklyPlan.query.filter(
        WeeklyPlan.status ==
        PlanStatus.ACTIVE
    ).count()

    completed_plans = WeeklyPlan.query.filter(
        WeeklyPlan.status ==
        PlanStatus.COMPLETED
    ).count()

    pending_reviews = Activity.query.filter(
        Activity.verification_status ==
        VerificationStatus.PENDING
    ).count()

    assigned_tasks = AssignedTask.query.count()

    notifications = Notification.query.count()

    audit_logs = AuditLog.query.order_by(
        AuditLog.created_at.desc()
    ).limit(20).all()

    recent_logins = LoginHistory.query.order_by(
        LoginHistory.login_time.desc()
    ).limit(20).all()

    latest_users = User.query.order_by(
        User.id.desc()
    ).limit(10).all()

    return {

        "total_users": total_users,

        "employees": employees,

        "managers": managers,

        "admins": admins,

        "departments": departments,

        "active_plans": active_plans,

        "completed_plans": completed_plans,

        "pending_reviews": pending_reviews,

        "assigned_tasks": assigned_tasks,

        "notifications": notifications,

        "audit_logs": audit_logs,

        "recent_logins": recent_logins,

        "latest_users": latest_users

    }