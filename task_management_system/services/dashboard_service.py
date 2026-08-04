from datetime import date

from sqlalchemy import func

from extensions import db

from models.user import User
from models.weekly_plan import WeeklyPlan
from models.activity import Activity
from models.assigned_task import AssignedTask
from models.notification import Notification

from models.enums import (
    PlanStatus,
    ActivityStatus,
    TaskStatus
)


class DashboardService:

    def __init__(self, user):

        self.user = user

    # -------------------------------------------------
    # Current Active Weekly Plan
    # -------------------------------------------------

    def get_active_week(self):

        return WeeklyPlan.query.filter(

            WeeklyPlan.employee_id == self.user.id,

            WeeklyPlan.week_start <= date.today(),

            WeeklyPlan.week_end >= date.today()

        ).first()

    # -------------------------------------------------
    # Planned Activities
    # -------------------------------------------------

    def planned_activities(self):

        week = self.get_active_week()

        if not week:
            return []

        return Activity.query.filter_by(
            plan_id=week.id
        ).order_by(
            Activity.activity_date.asc()
        ).all()

    # -------------------------------------------------
    # Assigned Tasks
    # -------------------------------------------------

    def assigned_tasks(self):

        return AssignedTask.query.filter(

            AssignedTask.employee_id == self.user.id

        ).order_by(

            AssignedTask.assigned_date.asc()

        ).all()

    # -------------------------------------------------
    # Notifications
    # -------------------------------------------------

    def notifications(self, limit=8):

        return Notification.query.filter_by(

            recipient_id=self.user.id

        ).order_by(

            Notification.created_at.desc()

        ).limit(limit).all()

    # -------------------------------------------------
    # Unread Notifications
    # -------------------------------------------------

    def unread_notifications(self):

        return Notification.query.filter_by(

            recipient_id=self.user.id,

            read=False

        ).count()

    # -------------------------------------------------
    # Completed Activities
    # -------------------------------------------------

    def completed_activities(self):

        week = self.get_active_week()

        if not week:
            return 0

        return Activity.query.filter(

            Activity.plan_id == week.id,

            Activity.manager_status == ActivityStatus.DONE

        ).count()

    # -------------------------------------------------
    # Pending Activities
    # -------------------------------------------------

    def pending_activities(self):

        week = self.get_active_week()

        if not week:
            return 0

        return Activity.query.filter(

            Activity.plan_id == week.id,

            Activity.manager_status == ActivityStatus.PENDING

        ).count()

    # -------------------------------------------------
    # Total Activities
    # -------------------------------------------------

    def total_activities(self):

        week = self.get_active_week()

        if not week:
            return 0

        return Activity.query.filter_by(

            plan_id=week.id

        ).count()

    # -------------------------------------------------
    # Weekly Completion %
    # -------------------------------------------------

    def completion_percentage(self):

        total = self.total_activities()

        if total == 0:
            return 0

        completed = self.completed_activities()

        return round((completed / total) * 100, 2)

    # -------------------------------------------------
    # Dashboard Cards
    # -------------------------------------------------

    def dashboard_cards(self):

        return {

            "activities": self.total_activities(),

            "completed": self.completed_activities(),

            "pending": self.pending_activities(),

            "assigned": len(self.assigned_tasks()),

            "notifications": self.unread_notifications(),

            "completion": self.completion_percentage()

        }

    # -------------------------------------------------
    # Greeting
    # -------------------------------------------------

    def greeting(self):

        from datetime import datetime

        hour = datetime.now().hour

        if hour < 12:
            return "Good Morning"

        elif hour < 17:
            return "Good Afternoon"

        return "Good Evening"