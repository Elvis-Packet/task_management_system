from models.assigned_task import AssignedTask
from models.weekly_plan import WeeklyPlan
from services.assigned_task_service import AssignedTaskService
from services.weekly_plan_service import WeeklyPlanService
from utils.serializers import build_task_timeline, build_plan_timeline


class ActivityService:
    """Builds the 'Recent Activities' feed from the exact same real,
    timestamped data the task/plan detail timelines already use — created,
    submitted, approved, each progress update, completed, verified/rejected
    — instead of a coarser, separately-maintained audit-log scan. Nothing
    here is a new source of truth; it's a merge of what already exists."""

    @staticmethod
    def recent_activities(current_user, limit=10):
        events = []

        tasks = (
            AssignedTaskService.scoped_query(current_user)
            .order_by(AssignedTask.updated_at.desc())
            .limit(50)
            .all()
        )

        for task in tasks:
            for i, event in enumerate(build_task_timeline(task)):
                events.append({
                    "id": f"task-{task.id}-{i}",
                    "type": event["type"],
                    "text": f"Task: {task.title} — {event['description']}",
                    "actor": event["actor_name"] or "System",
                    "timestamp": event["timestamp"],
                })

        plans = (
            WeeklyPlanService.scoped_query(current_user)
            .order_by(WeeklyPlan.updated_at.desc())
            .limit(20)
            .all()
        )

        for plan in plans:
            for i, event in enumerate(build_plan_timeline(plan)):
                events.append({
                    "id": f"plan-{plan.id}-{i}",
                    "type": event["type"],
                    "text": f"Week {plan.week_number}, {plan.year} plan — {event['description']}",
                    "actor": event["actor_name"] or "System",
                    "timestamp": event["timestamp"],
                })

        events.sort(key=lambda e: e["timestamp"] or "", reverse=True)

        return events[:limit]
