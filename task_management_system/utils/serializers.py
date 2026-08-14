from datetime import date as _date, datetime as _datetime

from models.user import User
from models.enums import UserRole, TaskStatus, ActivityStatus, VerificationStatus
from utils.enum_map import (
    priority_to_fe,
    task_status_to_fe,
    plan_status_to_fe,
    user_status_to_fe,
)

# A manager can only query a task that is still outstanding — mirrors
# TaskQueryService.can_raise_on(), which is what the API actually enforces.
_QUERYABLE_EXCLUDED = (
    TaskStatus.COMPLETED,
    TaskStatus.VERIFIED,
    TaskStatus.REJECTED,
    TaskStatus.CANCELLED,
)

_SEVERITY_BY_ACTION = {
    "DELETE": "high",
    "RESET_PASSWORD": "high",
    "SUSPEND": "high",
    "LOGIN_FAILED": "medium",
    "CREATE": "medium",
    "UPDATE": "medium",
    "ACTIVATE": "medium",
    "VERIFY": "medium",
    "REJECT": "medium",
    "ASSIGN_TASK": "medium",
    "REVIEW_PLAN": "medium",
}


def _iso(dt):
    """All datetimes in this app are stored naive-but-UTC (datetime.utcnow()).
    Without an explicit UTC marker, JS `new Date(isoString)` silently
    reinterprets a naive ISO string as local time — so every *datetime*
    must be tagged 'Z' here, once, for the whole app to be timezone-correct.
    Plain `date` values (due_date, week_start, ...) are left bare — JS
    already treats a bare YYYY-MM-DD string as UTC, so appending 'Z' there
    would actually produce an invalid/non-standard string."""
    if not dt:
        return None
    if isinstance(dt, _datetime):
        return dt.isoformat() + "Z"
    return dt.isoformat()


def department_manager_name(department_id):
    if not department_id:
        return None

    manager = User.query.filter_by(
        department_id=department_id, role=UserRole.OPERATIONAL_MANAGER, deleted_at=None
    ).first()

    return manager.full_name if manager else None


def serialize_user(user, include_performance=True):
    if user is None:
        return None

    overall_performance = 0
    if include_performance and user.performance:
        overall_performance = round(user.performance.overall_average or 0, 2)

    return {
        "id": user.id,
        "employee_number": user.employee_number,
        "first_name": user.first_name,
        "middle_name": user.middle_name,
        "last_name": user.last_name,
        "name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "job_title": user.job_title,
        # The UI (ProfileCard, employee tables) has always read `title` for
        # the person's position — it was simply never sent. Same value, both
        # keys, so nothing has to change on the frontend to start working.
        "title": user.job_title,
        "role": user.role.value,
        "department_id": user.department_id,
        "department": user.department.department_name if user.department else None,
        "status": user_status_to_fe(user.status),
        "profile_photo": user.profile_photo,
        "is_first_login": user.is_first_login,
        "created_at": _iso(user.created_at),
        "joined_at": _iso(user.created_at),
        "last_login": _iso(user.last_login),
        "last_activity": _iso(user.last_activity),
        "performance": overall_performance,
        "deleted": user.is_deleted,
    }


def serialize_department(department):
    if department is None:
        return None

    active_staff = [
        u for u in department.users if u.deleted_at is None and u.role == UserRole.STAFF
    ]
    staff_count = len(active_staff)

    avg_performance = 0
    if active_staff:
        avg_performance = round(
            sum((u.performance.overall_average if u.performance else 0) for u in active_staff)
            / len(active_staff),
            2,
        )

    manager_name = department_manager_name(department.id)

    return {
        "id": department.id,
        "department_name": department.department_name,
        "name": department.department_name,
        "department_code": department.department_code,
        "description": department.description,
        "budget": float(department.budget) if department.budget is not None else 0,
        "created_at": _iso(department.created_at),
        "staff_count": staff_count,
        "member_count": staff_count,
        "manager": manager_name,
        "head": manager_name,
        "avg_performance": avg_performance,
    }


def serialize_task_progress_update(update):
    if update is None:
        return None

    return {
        "id": update.id,
        "task_id": update.task_id,
        "user_id": update.user_id,
        "user_name": update.user.full_name if update.user else None,
        "previous_progress": update.previous_progress,
        "new_progress": update.new_progress,
        "comment": update.comment,
        "created_at": _iso(update.created_at),
    }


def serialize_task_exception(exception):
    if exception is None:
        return None

    return {
        "id": exception.id,
        "task_id": exception.task_id,
        "manager_id": exception.manager_id,
        "manager_name": exception.manager.full_name if exception.manager else None,
        "reason_category": exception.reason_category.value.lower(),
        "explanation": exception.explanation,
        "resolution": exception.resolution.value.lower() if exception.resolution else None,
        "created_at": _iso(exception.created_at),
    }


def serialize_task_query(query):
    if query is None:
        return None

    return {
        "id": query.id,
        "task_id": query.task_id,
        "task_title": query.task.title if query.task else None,
        "manager_id": query.manager_id,
        "manager_name": query.manager.full_name if query.manager else None,
        "employee_id": query.employee_id,
        "employee_name": query.employee.full_name if query.employee else None,
        "department": (
            query.employee.department.department_name
            if query.employee and query.employee.department else None
        ),
        "message": query.message,
        "status": query.status.value.lower(),
        "task_status_at_query": query.task_status_at_query,
        "current_task_status": task_status_to_fe(query.task.status) if query.task else None,
        "response": query.response,
        "responded_at": _iso(query.responded_at),
        "closed_by": query.closed_by,
        "closed_by_name": query.closer.full_name if query.closer else None,
        "closed_at": _iso(query.closed_at),
        "created_at": _iso(query.created_at),
        "raised_at": _iso(query.created_at),
        "awaiting_response": query.is_open,
    }


def _overdue_duration(task):
    if not task.is_overdue:
        return None

    from datetime import time as _time

    due_dt = _datetime.combine(task.due_date, task.due_time or _time(23, 59, 59))
    delta = _datetime.utcnow() - due_dt

    total_hours = max(delta.total_seconds() / 3600, 0)

    return {
        "days": int(total_hours // 24),
        "hours": int(total_hours % 24),
        "total_hours": round(total_hours, 1),
    }


def serialize_task(task, include_comments=None, include_history=False):
    if task is None:
        return None

    latest_exception = task.exceptions[-1] if task.exceptions else None

    data = {
        "id": task.id,
        "employee_id": task.employee_id,
        "assignee_id": task.employee_id,
        "employee_name": task.employee.full_name if task.employee else None,
        "department": task.employee.department.department_name if task.employee and task.employee.department else None,
        "department_id": task.employee.department_id if task.employee else None,
        "manager_id": task.manager_id,
        "assigner_id": task.manager_id,
        "manager_name": task.manager.full_name if task.manager else None,
        "assigner_name": task.manager.full_name if task.manager else None,
        "created_by": "staff" if task.submitted_at else "manager",
        "title": task.title,
        "description": task.description,
        "expected_outcome": task.expected_outcome,
        "priority": priority_to_fe(task.priority),
        "status": task_status_to_fe(task.status),
        "progress": task.progress,
        "verified": task.status == TaskStatus.VERIFIED,
        "assigned_date": _iso(task.assigned_date) if task.assigned_date else None,
        "assigned_time": task.assigned_time.strftime("%H:%M") if task.assigned_time else None,
        "due_date": _iso(task.due_date) if task.due_date else None,
        "due_time": task.due_time.strftime("%H:%M") if task.due_time else None,
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
        "submitted_at": _iso(task.submitted_at),
        "approved_at": _iso(task.approved_at),
        "completed_at": _iso(task.completed_at),
        "verified_at": _iso(task.verified_at),
        "verified_by": task.verified_by,
        "verification_notes": task.verification_notes,
        "is_overdue": task.is_overdue,
        "overdue_duration": _overdue_duration(task),
        "related_activity_id": task.related_activity_id,
        "goal_id": task.related_activity_id,
        "plan_id": task.plan_id,
        "latest_exception": serialize_task_exception(latest_exception),
        "has_reason": latest_exception is not None,
        # Manager status requests. open_query_count is on every task row (not
        # just the detail view) so a list can badge "awaiting your response"
        # without a second request per task.
        "open_query_count": sum(1 for q in task.queries if q.is_open),
        "query_count": len(task.queries),
        "can_be_queried": task.status not in _QUERYABLE_EXCLUDED,
    }

    if include_comments is not None:
        data["comments"] = [serialize_comment(c) for c in include_comments]

    if include_history:
        data["progress_history"] = [
            serialize_task_progress_update(u) for u in task.progress_updates
        ]
        data["timeline"] = build_task_timeline(task)
        data["exceptions"] = [serialize_task_exception(e) for e in task.exceptions]
        data["queries"] = [serialize_task_query(q) for q in task.queries]

    return data


def build_task_timeline(task):
    """Merges the task's own lifecycle timestamps, its progress-update
    history, and any AuditLog rows tagged to it into one chronological
    activity feed — reusing existing data rather than a parallel log."""

    from models.audit_log import AuditLog
    from models.enums import CommentTargetType

    events = []

    if task.created_at:
        if task.related_activity_id:
            description = "Assigned Task created from an approved Weekly Plan item."
        elif task.submitted_at:
            description = f"Task created and submitted by {task.employee.full_name if task.employee else 'unknown'}."
        else:
            description = f"Task created by {task.employee.full_name if task.employee else 'unknown'}."

        events.append({
            "type": "created",
            "description": description,
            "actor_name": task.employee.full_name if task.employee else None,
            "timestamp": _iso(task.created_at),
        })

    if task.approved_at:
        events.append({
            "type": "approved",
            "description": "Task approved.",
            "actor_name": task.manager.full_name if task.manager else None,
            "timestamp": _iso(task.approved_at),
        })

    for update in task.progress_updates:
        events.append({
            "type": "progress",
            "description": f"Progress updated to {update.new_progress}%." + (f" \"{update.comment}\"" if update.comment else ""),
            "actor_name": update.user.full_name if update.user else None,
            "timestamp": _iso(update.created_at),
        })

    if task.completed_at:
        events.append({
            "type": "completed",
            "description": "Marked complete — submitted for verification.",
            "actor_name": task.employee.full_name if task.employee else None,
            "timestamp": _iso(task.completed_at),
        })

    if task.verified_at:
        # REJECTED only ever comes from a SUBMITTED proposal being declined
        # outright (reject_submission) — terminal. Anything else with a
        # verified_at set (IN_PROGRESS, COMPLETED, ...) reflects a COMPLETED
        # verification that was returned for more work, not a dead end.
        if task.status == TaskStatus.VERIFIED:
            event_type, description = "verified", "Verified."
        elif task.status == TaskStatus.REJECTED:
            event_type, description = "rejected", f"Rejected.{' ' + task.verification_notes if task.verification_notes else ''}"
        else:
            event_type, description = "returned", f"Returned for more work.{' ' + task.verification_notes if task.verification_notes else ''}"

        events.append({
            "type": event_type,
            "description": description,
            "actor_name": task.verifier.full_name if task.verifier else None,
            "timestamp": _iso(task.verified_at),
        })

    for query in task.queries:
        events.append({
            "type": "query_raised",
            "description": f"Status update requested: \"{query.message}\"",
            "actor_name": query.manager.full_name if query.manager else None,
            "timestamp": _iso(query.created_at),
        })

        if query.responded_at:
            events.append({
                "type": "query_answered",
                "description": f"Update provided: \"{query.response}\"",
                "actor_name": query.employee.full_name if query.employee else None,
                "timestamp": _iso(query.responded_at),
            })

        if query.closed_at:
            events.append({
                "type": "query_closed",
                "description": "Status request closed.",
                "actor_name": query.closer.full_name if query.closer else None,
                "timestamp": _iso(query.closed_at),
            })

    for exception in task.exceptions:
        resolution_label = (" " + exception.resolution.value.replace("_", " ").title()) if exception.resolution else ""
        events.append({
            "type": "reason_recorded",
            "description": (
                f"Reason recorded ({exception.reason_category.value.replace('_', ' ').title()}): "
                f"\"{exception.explanation}\".{(' Resolution:' + resolution_label) if resolution_label else ''}"
            ),
            "actor_name": exception.manager.full_name if exception.manager else None,
            "timestamp": _iso(exception.created_at),
        })

    audit_events = AuditLog.query.filter_by(
        target_type=CommentTargetType.TASK, target_id=task.id
    ).order_by(AuditLog.created_at.asc()).all()

    for log in audit_events:
        events.append({
            "type": log.action.lower(),
            "description": log.description,
            "actor_name": log.user.full_name if log.user else "System",
            "timestamp": _iso(log.created_at),
        })

    events.sort(key=lambda e: e["timestamp"] or "")

    return events


def serialize_activity(activity):
    if activity is None:
        return None

    return {
        "id": activity.id,
        "plan_id": activity.plan_id,
        "activity_date": _iso(activity.activity_date) if activity.activity_date else None,
        "title": activity.title,
        "description": activity.description,
        "priority": priority_to_fe(activity.priority),
        "employee_status": activity.employee_status.value.lower(),
        "verification_status": activity.verification_status.value.lower(),
        "final_status": activity.final_status.value.lower(),
        "manager_comments": activity.manager_comments,
        "manager_override": activity.manager_override,
        "verified_by": activity.verified_by,
        "verified_at": _iso(activity.verified_at),
    }


def serialize_linked_task_summary(task):
    if task is None:
        return None

    return {
        "id": task.id,
        "title": task.title,
        "status": task_status_to_fe(task.status),
        "progress": task.progress,
        "due_date": _iso(task.due_date) if task.due_date else None,
        "is_overdue": task.is_overdue,
    }


def serialize_goal(activity, include_comments=None):
    """A weekly-plan PLANNING item — 'what the employee intends to work on' —
    distinct from the AssignedTask it spawns on approval ('what's actually
    being executed'). linked_task, once present, is that traceable
    WeeklyPlanItem -> AssignedTask reference (related_activity_id)."""

    if activity is None:
        return None

    from models.assigned_task import AssignedTask

    linked_task = AssignedTask.query.filter_by(related_activity_id=activity.id).first()

    data = {
        "id": activity.id,
        "plan_id": activity.plan_id,
        "text": activity.title,
        "title": activity.title,
        "description": activity.description,
        "expected_outcome": activity.expected_outcome,
        "planned_date": _iso(activity.activity_date) if activity.activity_date else None,
        "day_name": activity.activity_date.strftime("%A") if activity.activity_date else None,
        "due_time": activity.due_time.strftime("%H:%M") if activity.due_time else None,
        "priority": priority_to_fe(activity.priority),
        "tasks": activity.task_count,
        "weight": activity.weight,
        "done": activity.employee_status == ActivityStatus.DONE,
        "employee_status": activity.employee_status.value.lower(),
        "verification_status": activity.verification_status.value.lower(),
        "verified": activity.verification_status == VerificationStatus.VERIFIED,
        "manager_comments": activity.manager_comments,
        "completed_at": _iso(activity.completed_at),
        "verified_at": _iso(activity.verified_at),
        "verified_by": activity.verified_by,
        "verifier_name": activity.verifier.full_name if activity.verifier else None,
        "created_at": _iso(activity.created_at),
        "updated_at": _iso(activity.updated_at),
        "linked_task": serialize_linked_task_summary(linked_task),
    }

    if include_comments is not None:
        data["comments"] = [serialize_comment(c) for c in include_comments]

    return data


def serialize_goal_for_verification(goal):
    """Same goal shape as serialize_goal, plus the plan/employee context a
    manager needs to act on it from a flat cross-plan list."""

    data = serialize_goal(goal)
    plan = goal.plan

    data.update({
        "plan_id": plan.id,
        "week_number": plan.week_number,
        "year": plan.year,
        "week_label": f"Week {plan.week_number}, {plan.year}",
        "employee_id": plan.employee_id,
        "employee_name": plan.employee.full_name if plan.employee else None,
        "department": plan.employee.department.department_name if plan.employee and plan.employee.department else None,
    })

    return data


def build_plan_timeline(plan):
    """Same pattern as build_task_timeline — merges the plan's own lifecycle
    timestamps with each goal's completion/verification events into one
    chronological record, so a manager can see exactly what happened and
    when without a parallel logging system."""

    events = []

    if plan.created_at:
        events.append({
            "type": "created",
            "description": "Weekly plan created.",
            "actor_name": plan.employee.full_name if plan.employee else None,
            "timestamp": _iso(plan.created_at),
        })

    if plan.submitted_at:
        events.append({
            "type": "submitted",
            "description": "Submitted for review.",
            "actor_name": plan.employee.full_name if plan.employee else None,
            "timestamp": _iso(plan.submitted_at),
        })

    if plan.reviewed_at:
        approved = plan.status.value == "APPROVED"
        events.append({
            "type": "approved" if approved else "rejected",
            "description": ("Approved." if approved else "Rejected.") + (f" {plan.review_notes}" if plan.review_notes else ""),
            "actor_name": plan.reviewer.full_name if plan.reviewer else None,
            "timestamp": _iso(plan.reviewed_at),
        })

    for goal in plan.activities:
        if goal.completed_at:
            events.append({
                "type": "goal_done",
                "description": f"Marked goal done: \"{goal.title}\".",
                "actor_name": plan.employee.full_name if plan.employee else None,
                "timestamp": _iso(goal.completed_at),
            })
        if goal.verified_at:
            verified = goal.verification_status == VerificationStatus.VERIFIED
            events.append({
                "type": "goal_verified" if verified else "goal_rejected",
                "description": (
                    f"{'Verified' if verified else 'Rejected'} goal: \"{goal.title}\"."
                    + (f" {goal.manager_comments}" if goal.manager_comments else "")
                ),
                "actor_name": goal.verifier.full_name if goal.verifier else None,
                "timestamp": _iso(goal.verified_at),
            })

    events.sort(key=lambda e: e["timestamp"] or "")

    return events


def serialize_plan(plan, include_goals=True, comments=None, include_timeline=False, include_goal_comments=False):
    if plan is None:
        return None

    from models.assigned_task import AssignedTask

    linked_task_count = AssignedTask.query.filter_by(plan_id=plan.id).count()

    data = {
        "id": plan.id,
        "employee_id": plan.employee_id,
        "owner_id": plan.employee_id,
        "owner_name": plan.employee.full_name if plan.employee else None,
        "department": plan.employee.department.department_name if plan.employee and plan.employee.department else None,
        "department_id": plan.employee.department_id if plan.employee else None,
        "manager": department_manager_name(plan.employee.department_id) if plan.employee else None,
        "week_number": plan.week_number,
        "year": plan.year,
        "week_label": f"Week {plan.week_number}, {plan.year}",
        "week_start": _iso(plan.week_start) if plan.week_start else None,
        "week_end": _iso(plan.week_end) if plan.week_end else None,
        "status": plan_status_to_fe(plan.status),
        "submitted": plan.submitted,
        "submitted_at": _iso(plan.submitted_at),
        "reviewed": plan.reviewed,
        "reviewed_by": plan.reviewed_by,
        "reviewer_name": plan.reviewer.full_name if plan.reviewer else None,
        "reviewed_at": _iso(plan.reviewed_at),
        "review_notes": plan.review_notes,
        "completion_percentage": plan.completion_percentage,
        "task_count": linked_task_count,
        "created_at": _iso(plan.created_at),
        "updated_at": _iso(plan.updated_at),
    }

    if include_goals:
        if include_goal_comments:
            from models.comment import Comment
            from models.enums import CommentTargetType

            data["goals"] = [
                serialize_goal(
                    a,
                    include_comments=Comment.query.filter_by(
                        target_type=CommentTargetType.ACTIVITY, target_id=a.id
                    ).order_by(Comment.created_at.asc()).all(),
                )
                for a in plan.activities
            ]
        else:
            data["goals"] = [serialize_goal(a) for a in plan.activities]

    if comments is not None:
        data["comments"] = [serialize_comment(c) for c in comments]

    if include_timeline:
        data["timeline"] = build_plan_timeline(plan)

    return data


def serialize_notification(notification):
    if notification is None:
        return None

    return {
        "id": notification.id,
        "recipient_id": notification.recipient_id,
        "sender_id": notification.sender_id,
        "sender_name": notification.sender.full_name if notification.sender else "System",
        "title": notification.title,
        "message": notification.message,
        "type": notification.notification_type.value.lower(),
        "priority": notification.priority.value.lower(),
        "action_url": notification.action_url,
        "read": notification.read,
        "read_at": _iso(notification.read_at),
        "archived": notification.archived,
        "created_at": _iso(notification.created_at),
    }


def serialize_comment(comment):
    if comment is None:
        return None

    return {
        "id": comment.id,
        "author_id": comment.author_id,
        "author_name": comment.author.full_name if comment.author else None,
        "role": comment.author.role.value if comment.author else None,
        "author_role": comment.author.role.value if comment.author else None,
        "target_type": comment.target_type.value.lower(),
        "target_id": comment.target_id,
        "message": comment.body,
        "body": comment.body,
        "created_at": _iso(comment.created_at),
    }


def serialize_audit_log(log):
    if log is None:
        return None

    return {
        "id": log.id,
        "user_id": log.user_id,
        "actor_name": log.user.full_name if log.user else "System",
        "actor": log.user.email if log.user else "system",
        "actor_email": log.user.email if log.user else None,
        "action": log.action,
        "target_name": None,
        "severity": _SEVERITY_BY_ACTION.get(log.action, "low"),
        "description": log.description,
        "details": log.description,
        "ip_address": log.ip_address,
        "device": log.device,
        "browser": log.browser,
        "created_at": _iso(log.created_at),
        "timestamp": _iso(log.created_at),
    }


def serialize_login_history(entry):
    if entry is None:
        return None

    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "user_name": entry.user.full_name if entry.user else None,
        "user": entry.user.email if entry.user else None,
        "role": entry.user.role.value if entry.user else None,
        "location": None,
        "login_time": _iso(entry.login_time),
        "logout_time": _iso(entry.logout_time),
        "timestamp": _iso(entry.login_time),
        "ip_address": entry.ip_address,
        "browser": entry.browser,
        "operating_system": entry.operating_system,
        "device": entry.device,
        "status": "success" if entry.login_successful else "failed",
        "login_successful": entry.login_successful,
        "failure_reason": entry.failure_reason,
    }


def serialize_generated_report(report, include_data=False, include_comments=False):
    if report is None:
        return None

    data = {
        "id": report.id,
        "title": report.title,
        "type": report.type,
        "period": report.period,
        "period_start": _iso(report.period_start) if report.period_start else None,
        "period_end": _iso(report.period_end) if report.period_end else None,
        "status": report.status,
        "generated_by": report.generator.full_name if report.generator else "System",
        "generated_by_id": report.generated_by,
        "generated_at": _iso(report.generated_at),
        "department_id": report.department_id,
        "department_name": report.department.department_name if report.department else None,
        "format": "CSV",
    }

    if include_data and report.department:
        from services.report_service import ReportService
        data["data"] = ReportService.department_report(report.department, report.period_start, report.period_end)

    if include_comments:
        from models.comment import Comment
        from models.enums import CommentTargetType

        comments = Comment.query.filter_by(
            target_type=CommentTargetType.REPORT, target_id=report.id
        ).order_by(Comment.created_at.asc()).all()

        data["comments"] = [serialize_comment(c) for c in comments]

    return data


def serialize_performance(performance):
    if performance is None:
        return {
            "total_plans": 0,
            "completed_plans": 0,
            "total_activities": 0,
            "completed_activities": 0,
            "weekly_average": 0,
            "monthly_average": 0,
            "yearly_average": 0,
            "overall_average": 0,
            "rank_position": None,
            "last_calculated": None,
        }

    return {
        "total_plans": performance.total_plans,
        "completed_plans": performance.completed_plans,
        "total_activities": performance.total_activities,
        "completed_activities": performance.completed_activities,
        "weekly_average": round(performance.weekly_average or 0, 2),
        "monthly_average": round(performance.monthly_average or 0, 2),
        "yearly_average": round(performance.yearly_average or 0, 2),
        "overall_average": round(performance.overall_average or 0, 2),
        "rank_position": performance.rank_position,
        "last_calculated": _iso(performance.last_calculated),
    }
