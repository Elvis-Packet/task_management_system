from datetime import datetime

from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError

from extensions import db
from models.user import User
from models.weekly_plan import WeeklyPlan
from models.assigned_task import AssignedTask
from models.comment import Comment
from models.enums import UserRole, PlanStatus, ActivityStatus, AuditAction, CommentTargetType, NotificationType
from services.weekly_plan_service import WeeklyPlanService
from services.audit_service import AuditService
from services.notification_service import NotificationService
from utils.appdate import app_today
from utils.response import ok, err
from utils.rbac import require_auth, require_roles, get_current_user
from utils.serializers import serialize_plan, serialize_comment, serialize_goal_for_verification, serialize_goal
from utils.pagination import paginate

plans_bp = Blueprint("plans", __name__)

MANAGE_ROLES = (UserRole.SUPER_ADMIN, UserRole.OPERATIONAL_MANAGER)


def _visible_plan(plan_id, current_user):
    return WeeklyPlanService.scoped_query(current_user).filter(WeeklyPlan.id == plan_id).first()


def _plan_comments(plan_id):
    return Comment.query.filter_by(
        target_type=CommentTargetType.WEEKLY_PLAN, target_id=plan_id
    ).order_by(Comment.created_at.asc()).all()


def _goal_comments(goal_id):
    return Comment.query.filter_by(
        target_type=CommentTargetType.ACTIVITY, target_id=goal_id
    ).order_by(Comment.created_at.asc()).all()


@plans_bp.get("")
@require_auth
def list_plans():
    current_user = get_current_user()
    query = WeeklyPlanService.scoped_query(current_user)
    query = WeeklyPlanService.apply_filters(query, request.args)

    paged = paginate(
        query,
        lambda p: serialize_plan(p, comments=_plan_comments(p.id)),
    )

    return ok(paged)


@plans_bp.get("/week")
@require_auth
def week_view():
    """The day-by-day planner: seven real calendar days for one ISO week,
    each with the AssignedTasks (self- or manager-assigned) whose
    assigned_date falls on that day. `date` picks which week (defaults to
    today); STAFF always see their own week, managers/admins pass
    employee_id to view a staff member's week under existing RBAC rules."""

    current_user = get_current_user()

    date_param = request.args.get("date")
    try:
        target_date = datetime.fromisoformat(date_param).date() if date_param else app_today()
    except ValueError:
        return err("Invalid date format — expected YYYY-MM-DD.", 422)

    if current_user.role == UserRole.STAFF:
        employee = current_user
    else:
        employee_id = request.args.get("employee_id", type=int)
        if not employee_id:
            return err("employee_id is required.", 422)

        employee = User.query.filter_by(id=employee_id, deleted_at=None).first()
        if not employee:
            return err("Employee not found.", 404)

    view = WeeklyPlanService.week_view(employee, target_date)
    plan = view["plan"]

    current_year, current_week, _ = app_today().isocalendar()
    is_current_week = (view["week_number"], view["year"]) == (current_week, current_year)

    # Whether the CURRENT VIEWER (not necessarily the plan's owner) may add/
    # edit/remove goals right now — staff only while drafting their own
    # plan (per-day, see day_lock_reason below); a manager/admin uniformly
    # across the whole week while it's awaiting their review.
    if current_user.role == UserRole.STAFF:
        plan_editable_by_viewer = plan is None or plan.status in (PlanStatus.DRAFT, PlanStatus.REJECTED)
    else:
        # Both org-wide reviewer roles (Super Admin and the central
        # Operational Manager) may edit any department's plan during review;
        # HR is read-only and never gets an editable view.
        can_review = current_user.role in (UserRole.SUPER_ADMIN, UserRole.OPERATIONAL_MANAGER)
        plan_editable_by_viewer = bool(can_review and plan and plan.status == PlanStatus.SUBMITTED)

    return ok({
        "plan": serialize_plan(plan) if plan else None,
        "week_number": view["week_number"],
        "year": view["year"],
        "week_label": f"Week {view['week_number']}, {view['year']}",
        "week_start": view["week_start"].isoformat(),
        "week_end": view["week_end"].isoformat(),
        "is_current_week": is_current_week,
        "plan_editable_by_viewer": plan_editable_by_viewer,
        "employee_id": employee.id,
        "employee_name": employee.full_name,
        "days": [
            {
                "date": d["date"].isoformat(),
                "day_name": d["day_name"],
                "is_today": d["is_today"],
                "is_open": d["is_open"] if current_user.role == UserRole.STAFF else plan_editable_by_viewer,
                "lock_reason": d["lock_reason"],
                "goals": [serialize_goal(g) for g in d["goals"]],
            }
            for d in view["days"]
        ],
    })


@plans_bp.get("/goals/pending-verification")
@require_auth
def goals_pending_verification():
    current_user = get_current_user()
    goals = WeeklyPlanService.goals_pending_verification(current_user)

    return ok({
        "items": [serialize_goal_for_verification(g) for g in goals],
        "total": len(goals),
    })


@plans_bp.get("/<int:plan_id>")
@require_auth
def get_plan(plan_id):
    current_user = get_current_user()
    plan = _visible_plan(plan_id, current_user)

    if not plan:
        return err("Plan not found.", 404)

    return ok({"plan": serialize_plan(plan, comments=_plan_comments(plan.id), include_timeline=True, include_goal_comments=True)})


@plans_bp.post("")
@require_roles(UserRole.STAFF)
def create_plan():
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

    try:
        plan = WeeklyPlanService.create_plan(data, current_user)
    except IntegrityError:
        db.session.rollback()
        return err("You already have a plan for that week.", 409)

    AuditService.log_action(current_user, AuditAction.CREATE, f"Created weekly plan for week {plan.week_number}, {plan.year}.")

    return ok({"plan": serialize_plan(plan)}, message="Plan saved as draft.", status=201)


@plans_bp.put("/<int:plan_id>")
@plans_bp.patch("/<int:plan_id>")
@require_roles(UserRole.STAFF)
def update_plan(plan_id):
    current_user = get_current_user()
    plan = WeeklyPlan.query.filter_by(id=plan_id, employee_id=current_user.id).first()

    if not plan:
        return err("Plan not found.", 404)

    if plan.status not in (PlanStatus.DRAFT, PlanStatus.REJECTED):
        return err("Only draft or rejected plans can be edited.", 409)

    # Editing a rejected plan is how a staff member tries again for that
    # week — it re-enters the normal draft -> submit -> review cycle
    # instead of leaving a dead-end row that blocks that week forever.
    was_rejected = plan.status == PlanStatus.REJECTED

    data = request.get_json(silent=True) or {}
    plan = WeeklyPlanService.update_plan(plan, data)

    if was_rejected:
        plan.status = PlanStatus.DRAFT
        plan.reviewed = False
        plan.reviewed_by = None
        plan.reviewed_at = None
        plan.review_notes = None
        db.session.commit()

    return ok({"plan": serialize_plan(plan)}, message="Plan updated.")


@plans_bp.post("/<int:plan_id>/submit")
@require_roles(UserRole.STAFF)
def submit_plan(plan_id):
    current_user = get_current_user()
    plan = WeeklyPlan.query.filter_by(id=plan_id, employee_id=current_user.id).first()

    if not plan:
        return err("Plan not found.", 404)

    # REJECTED is a returned plan awaiting resubmission — functionally a
    # draft in revision, not a dead end (mirrors update_plan/delete_plan,
    # which already treat DRAFT and REJECTED as the same editable state).
    if plan.status not in (PlanStatus.DRAFT, PlanStatus.REJECTED):
        return err("Only draft or returned plans can be submitted.", 409)

    # A plan's content is either legacy weighted goals (Activity) or, for
    # the day-by-day planner, tasks linked via plan_id — either counts as
    # "there's something here to review."
    has_linked_tasks = AssignedTask.query.filter_by(plan_id=plan.id).first() is not None
    if not plan.activities and not has_linked_tasks:
        return err("Add at least one planned task before submitting this plan.", 422)

    plan = WeeklyPlanService.submit_plan(plan)

    manager = None
    if current_user.department_id:
        from models.user import User
        manager = User.query.filter_by(
            department_id=current_user.department_id, role=UserRole.OPERATIONAL_MANAGER, deleted_at=None
        ).first()

    if manager:
        NotificationService.notify(
            recipient=manager,
            sender=current_user,
            title="Weekly plan submitted",
            message=f"{current_user.full_name} submitted their plan for week {plan.week_number}, {plan.year}.",
            notification_type=NotificationType.WEEKLY_PLAN,
        )

    AuditService.log_action(current_user, AuditAction.SUBMIT_PLAN, f"Submitted weekly plan for week {plan.week_number}, {plan.year}.")

    return ok({"plan": serialize_plan(plan)}, message="Plan submitted for review.")


@plans_bp.post("/<int:plan_id>/approve")
@require_roles(*MANAGE_ROLES)
def approve_plan(plan_id):
    return _review_plan(plan_id, approved=True)


@plans_bp.post("/<int:plan_id>/reject")
@require_roles(*MANAGE_ROLES)
def reject_plan(plan_id):
    return _review_plan(plan_id, approved=False)


def _review_plan(plan_id, approved):
    current_user = get_current_user()
    plan = _visible_plan(plan_id, current_user)

    if not plan:
        return err("Plan not found.", 404)

    if plan.status != PlanStatus.SUBMITTED:
        return err("Only submitted plans can be reviewed.", 409)

    data = request.get_json(silent=True) or {}
    notes = data.get("notes")

    plan = WeeklyPlanService.review_plan(plan, current_user, approved, notes)

    created_tasks = []
    if approved:
        # The moment a Weekly Plan item becomes real, tracked work: one
        # AssignedTask per planning item, linked back via related_activity_id
        # so Weekly Plan -> Assigned Task -> Progress -> Verification stays
        # traceable end to end. Never fires twice for the same plan (only
        # reachable from SUBMITTED -> APPROVED, which happens once).
        created_tasks = WeeklyPlanService.generate_tasks_from_plan(plan, current_user)

    NotificationService.notify(
        recipient=plan.employee,
        sender=current_user,
        title="Weekly plan approved" if approved else "Weekly plan returned",
        message=(
            f"{current_user.full_name} approved your week {plan.week_number} plan — "
            f"{len(created_tasks)} task{'s' if len(created_tasks) != 1 else ''} added to your Assigned Tasks."
            if approved
            else f"{current_user.full_name} returned your week {plan.week_number} plan for changes." + (f" {notes}" if notes else "")
        ),
        notification_type=NotificationType.PLAN_REVIEW,
    )

    AuditService.log_action(
        current_user,
        AuditAction.REVIEW_PLAN,
        f"{'Approved' if approved else 'Returned'} weekly plan for week {plan.week_number}, {plan.year}."
        + (f" Created {len(created_tasks)} assigned task(s)." if created_tasks else ""),
    )

    return ok({"plan": serialize_plan(plan), "tasks_created": len(created_tasks)}, message="Plan reviewed.")


@plans_bp.post("/goals")
@require_roles(UserRole.STAFF, *MANAGE_ROLES)
def create_goal():
    """Add one new planning item to a specific day. Staff auto-resolves
    (or lazily creates) their own plan for that day's ISO week — the
    week-boundary + DRAFT/REJECTED-only rule (day_lock_reason) applies.
    A manager/admin instead targets an explicit plan_id that must already
    be SUBMITTED (the review stage) and in their own department — this is
    how "Add a task if necessary" during review is implemented."""

    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    planned_date_raw = data.get("planned_date") or data.get("assigned_date")

    if not title:
        return err("Task title is required.", 422, errors={"title": "required"})
    if not planned_date_raw:
        return err("A planned day is required.", 422, errors={"planned_date": "required"})

    try:
        target_date = datetime.fromisoformat(planned_date_raw).date()
    except ValueError:
        return err("Invalid planned_date format — expected YYYY-MM-DD.", 422)

    if current_user.role == UserRole.STAFF:
        lock_reason = WeeklyPlanService.day_lock_reason(target_date)
        if lock_reason:
            return err(lock_reason, 409)

        plan = WeeklyPlanService.get_or_create_plan_for_date(current_user, target_date)

        if plan.status not in (PlanStatus.DRAFT, PlanStatus.REJECTED):
            return err("Your weekly plan has already been submitted — you can't add tasks to it until it's returned.", 409)
    else:
        plan_id = data.get("plan_id")
        if not plan_id:
            return err("plan_id is required.", 422, errors={"plan_id": "required"})

        plan = _visible_plan(plan_id, current_user)
        if not plan:
            return err("Plan not found.", 404)

        if plan.status != PlanStatus.SUBMITTED:
            return err("You can only add tasks to a weekly plan while it's awaiting your review.", 409)

    goal = WeeklyPlanService.create_goal_item(plan, {**data, "planned_date": target_date.isoformat()})

    actor = "Staff" if current_user.role == UserRole.STAFF else "Manager"
    AuditService.log_action(
        current_user, AuditAction.CREATE,
        f"{actor} added planned task '{goal.title}' to weekly plan (week {plan.week_number}, {plan.year}).",
    )

    if current_user.role != UserRole.STAFF and plan.employee and plan.employee_id != current_user.id:
        NotificationService.notify(
            recipient=plan.employee,
            sender=current_user,
            title="Manager added a task to your weekly plan",
            message=f"{current_user.full_name} added \"{goal.title}\" to your week {plan.week_number} plan.",
            notification_type=NotificationType.WEEKLY_PLAN,
        )

    return ok({"plan": serialize_plan(plan)}, message="Task added to weekly plan.", status=201)


@plans_bp.patch("/<int:plan_id>/goals/<int:goal_id>")
@require_roles(UserRole.STAFF, *MANAGE_ROLES)
def update_goal(plan_id, goal_id):
    """Edit a planning item's own fields. Backward-compatible with the
    original 'done' toggle (only meaningful on an already-APPROVED plan,
    from before this workflow existed) — any other payload is treated as
    a real field edit, gated by goal_edit_permission (staff pre-submission
    on an open day; manager only while the plan is SUBMITTED)."""

    current_user = get_current_user()
    plan = _visible_plan(plan_id, current_user)

    if not plan:
        return err("Plan not found.", 404)

    goal = WeeklyPlanService.get_goal(plan, goal_id)

    if not goal:
        return err("Goal not found.", 404)

    data = request.get_json(silent=True) or {}

    if "done" in data and not any(k in data for k in ("title", "description", "expected_outcome", "planned_date", "assigned_date", "due_time")):
        if current_user.role != UserRole.STAFF or plan.employee_id != current_user.id:
            return err("Only the plan's owner can mark a goal done.", 403)
        if plan.status != PlanStatus.APPROVED:
            return err("Only goals in an approved plan can be marked done.", 409)

        done = bool(data.get("done", True))
        goal = WeeklyPlanService.mark_goal(goal, done)

        AuditService.log_action(
            current_user, AuditAction.UPDATE,
            f"{'Marked done' if done else 'Marked not done'}: goal '{goal.title}' (week {plan.week_number}, {plan.year}).",
        )

        return ok({"plan": serialize_plan(plan, include_timeline=True, include_goal_comments=True)}, message="Goal updated.")

    permission_error = WeeklyPlanService.goal_edit_permission(goal, current_user)
    if permission_error:
        return err(permission_error, 409)

    goal = WeeklyPlanService.update_goal_item(goal, data)

    actor = "You" if current_user.id == plan.employee_id else current_user.full_name
    AuditService.log_action(
        current_user, AuditAction.UPDATE,
        f"{'Staff' if current_user.role == UserRole.STAFF else 'Manager'} edited planned task '{goal.title}' (week {plan.week_number}, {plan.year}).",
        target_type=CommentTargetType.ACTIVITY, target_id=goal.id,
    )

    if current_user.id != plan.employee_id and plan.employee:
        NotificationService.notify(
            recipient=plan.employee,
            sender=current_user,
            title="Manager edited a task in your weekly plan",
            message=f"{current_user.full_name} edited \"{goal.title}\" in your week {plan.week_number} plan.",
            notification_type=NotificationType.WEEKLY_PLAN,
        )

    return ok({"plan": serialize_plan(plan, include_timeline=True, include_goal_comments=True)}, message="Task updated.")


@plans_bp.delete("/<int:plan_id>/goals/<int:goal_id>")
@require_roles(UserRole.STAFF, *MANAGE_ROLES)
def delete_goal(plan_id, goal_id):
    current_user = get_current_user()
    plan = _visible_plan(plan_id, current_user)

    if not plan:
        return err("Plan not found.", 404)

    goal = WeeklyPlanService.get_goal(plan, goal_id)

    if not goal:
        return err("Goal not found.", 404)

    permission_error = WeeklyPlanService.goal_edit_permission(goal, current_user)
    if permission_error:
        return err(permission_error, 409)

    title = goal.title
    WeeklyPlanService.delete_goal_item(goal)

    AuditService.log_action(
        current_user, AuditAction.DELETE,
        f"{'Staff' if current_user.role == UserRole.STAFF else 'Manager'} removed planned task '{title}' (week {plan.week_number}, {plan.year}).",
    )

    if current_user.id != plan.employee_id and plan.employee:
        NotificationService.notify(
            recipient=plan.employee,
            sender=current_user,
            title="Manager removed a task from your weekly plan",
            message=f"{current_user.full_name} removed \"{title}\" from your week {plan.week_number} plan.",
            notification_type=NotificationType.WEEKLY_PLAN,
        )

    return ok({"plan": serialize_plan(plan)}, message="Task removed from weekly plan.")


@plans_bp.post("/<int:plan_id>/goals/<int:goal_id>/verify")
@require_roles(*MANAGE_ROLES)
def verify_goal(plan_id, goal_id):
    current_user = get_current_user()
    plan = _visible_plan(plan_id, current_user)

    if not plan:
        return err("Plan not found.", 404)

    goal = WeeklyPlanService.get_goal(plan, goal_id)

    if not goal:
        return err("Goal not found.", 404)

    if goal.employee_status != ActivityStatus.DONE:
        return err("This goal hasn't been marked done by the employee yet.", 409)

    data = request.get_json(silent=True) or {}
    verified = bool(data.get("verified", data.get("approved", True)))
    comments = data.get("comments") or data.get("notes")

    goal = WeeklyPlanService.verify_goal(goal, current_user, verified, comments)

    NotificationService.notify(
        recipient=plan.employee,
        sender=current_user,
        title="Goal verified" if verified else "Goal rejected",
        message=f"{current_user.full_name} {'verified' if verified else 'rejected'} \"{goal.title}\" in your week {plan.week_number} plan." + (f" {comments}" if comments else ""),
        notification_type=NotificationType.WEEKLY_PLAN,
    )

    AuditService.log_action(
        current_user, AuditAction.VERIFY if verified else AuditAction.REJECT,
        f"{'Verified' if verified else 'Rejected'} goal '{goal.title}' (week {plan.week_number}, {plan.year}).",
    )

    return ok({"plan": serialize_plan(plan, include_timeline=True, include_goal_comments=True)}, message="Goal reviewed.")


@plans_bp.post("/<int:plan_id>/goals/<int:goal_id>/comments")
@require_auth
def add_goal_comment(plan_id, goal_id):
    """Comments scoped to one specific goal — kept separate from whole-plan
    comments (CommentTargetType.WEEKLY_PLAN) so a note on Goal A never
    appears under Goal B or under the plan as a whole."""

    current_user = get_current_user()
    plan = _visible_plan(plan_id, current_user)

    if not plan:
        return err("Plan not found.", 404)

    goal = WeeklyPlanService.get_goal(plan, goal_id)

    if not goal:
        return err("Goal not found.", 404)

    data = request.get_json(silent=True) or {}
    body = (data.get("message") or data.get("body") or "").strip()

    if not body:
        return err("Comment message is required.", 422)

    comment = Comment(
        author_id=current_user.id,
        target_type=CommentTargetType.ACTIVITY,
        target_id=goal.id,
        body=body,
    )

    db.session.add(comment)
    db.session.commit()

    if current_user.id != plan.employee_id:
        NotificationService.notify(
            recipient=plan.employee,
            sender=current_user,
            title="New comment on your goal",
            message=f"{current_user.full_name} commented on \"{goal.title}\".",
            notification_type=NotificationType.COMMENT,
        )

    AuditService.log_action(
        current_user, AuditAction.COMMENT, f"Commented on goal '{goal.title}' (week {plan.week_number}, {plan.year})."
    )

    return ok(
        {"comments": [serialize_comment(c) for c in _goal_comments(goal.id)]},
        message="Comment added.",
        status=201,
    )


@plans_bp.post("/<int:plan_id>/comments")
@require_auth
def add_comment(plan_id):
    current_user = get_current_user()
    plan = _visible_plan(plan_id, current_user)

    if not plan:
        return err("Plan not found.", 404)

    data = request.get_json(silent=True) or {}
    body = (data.get("message") or data.get("body") or "").strip()

    if not body:
        return err("Comment message is required.", 422)

    comment = Comment(
        author_id=current_user.id,
        target_type=CommentTargetType.WEEKLY_PLAN,
        target_id=plan.id,
        body=body,
    )

    db.session.add(comment)
    db.session.commit()

    if current_user.id != plan.employee_id:
        NotificationService.notify(
            recipient=plan.employee,
            sender=current_user,
            title="New comment on your weekly plan",
            message=f"{current_user.full_name} commented on your week {plan.week_number} plan.",
            notification_type=NotificationType.COMMENT,
        )

    AuditService.log_action(current_user, AuditAction.COMMENT, f"Commented on weekly plan for week {plan.week_number}, {plan.year}.")

    comments = _plan_comments(plan.id)

    return ok({"comments": [serialize_comment(c) for c in comments]}, message="Comment added.", status=201)


@plans_bp.delete("/<int:plan_id>")
@require_auth
def delete_plan(plan_id):
    current_user = get_current_user()

    if current_user.role == UserRole.STAFF:
        plan = WeeklyPlan.query.filter_by(id=plan_id, employee_id=current_user.id).first()
    else:
        plan = _visible_plan(plan_id, current_user)

    if not plan:
        return err("Plan not found.", 404)

    if current_user.role == UserRole.STAFF and plan.status not in (PlanStatus.DRAFT, PlanStatus.REJECTED):
        return err("Only draft or rejected plans can be deleted.", 409)

    WeeklyPlanService.delete_plan(plan)

    AuditService.log_action(current_user, AuditAction.DELETE, f"Deleted weekly plan for week {plan.week_number}, {plan.year}.")

    return ok(message="Plan deleted.")
