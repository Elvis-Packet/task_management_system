from extensions import db
from models.task_exception import TaskException


class TaskExceptionService:
    """Manager-recorded reasons for a task not being completed on time.
    Append-only — recording a new reason never edits or removes a prior
    one, so the full explanation history for a task is always preserved."""

    @staticmethod
    def record_reason(task, manager, category, explanation, resolution=None):
        exception = TaskException(
            task_id=task.id,
            manager_id=manager.id,
            reason_category=category,
            explanation=explanation.strip(),
            resolution=resolution,
        )

        db.session.add(exception)
        db.session.commit()

        return exception

    @staticmethod
    def history_for_task(task_id):
        return TaskException.query.filter_by(task_id=task_id).order_by(
            TaskException.created_at.asc()
        ).all()

    @staticmethod
    def latest_for_task(task_id):
        return TaskException.query.filter_by(task_id=task_id).order_by(
            TaskException.created_at.desc()
        ).first()

    @staticmethod
    def task_ids_with_reason(task_ids):
        """Which of these task ids have at least one recorded reason —
        used to split Overdue into With/Without Reason without an N+1
        query per task."""

        if not task_ids:
            return set()

        rows = db.session.query(TaskException.task_id).filter(
            TaskException.task_id.in_(task_ids)
        ).distinct().all()

        return {row[0] for row in rows}
