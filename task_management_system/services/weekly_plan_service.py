from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from extensions import db
from models.user import User
from models.weekly_plan import WeeklyPlan
from models.activity import Activity
from models.enums import UserRole, PlanStatus, ActivityStatus, VerificationStatus
from utils.appdate import app_today
from utils.rbac import has_org_scope

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _parse_date(value, fallback):
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return fallback


def week_bounds_for(target_date):
    """Monday..Sunday for the ISO week containing target_date — the single
    convention every week-scoped view (planner, reports, dashboard) shares."""

    week_start = target_date - timedelta(days=target_date.weekday())
    week_end = week_start + timedelta(days=6)
    iso_year, iso_week, _ = target_date.isocalendar()

    return week_start, week_end, iso_week, iso_year


def _week_bounds(week_start_raw, week_end_raw):
    today = app_today()
    default_start = today - timedelta(days=today.weekday())
    default_end = default_start + timedelta(days=6)

    week_start = _parse_date(week_start_raw, default_start)
    week_end = _parse_date(week_end_raw, week_start + timedelta(days=6))

    return week_start, week_end


class WeeklyPlanService:

    @staticmethod
    def scoped_query(current_user):
        """Same rule as every other scoped_query: org-scoped roles see every
        department's plans, everyone else sees only their own."""

        query = WeeklyPlan.query

        if not has_org_scope(current_user):
            return query.filter(WeeklyPlan.employee_id == current_user.id)

        return query

    @staticmethod
    def apply_filters(query, args):
        owner_id = args.get("owner_id") or args.get("employee_id")
        status = args.get("status")
        department_id = args.get("department_id")

        if owner_id:
            query = query.filter(WeeklyPlan.employee_id == owner_id)

        if status:
            try:
                query = query.filter(WeeklyPlan.status == PlanStatus[status.upper()])
            except KeyError:
                pass

        if department_id:
            query = query.join(User, WeeklyPlan.employee_id == User.id).filter(
                User.department_id == department_id
            )

        return query.order_by(WeeklyPlan.year.desc(), WeeklyPlan.week_number.desc())

    @staticmethod
    def _sync_goals(plan, goals):
        Activity.query.filter_by(plan_id=plan.id).delete()

        for goal in goals or []:
            text = (goal.get("text") or "").strip()
            if not text:
                continue

            try:
                weight = int(goal.get("weight") or 0)
            except (TypeError, ValueError):
                weight = 0

            try:
                task_count = max(int(goal.get("tasks") or 1), 1)
            except (TypeError, ValueError):
                task_count = 1

            db.session.add(
                Activity(
                    plan_id=plan.id,
                    activity_date=plan.week_start,
                    title=text,
                    weight=weight,
                    task_count=task_count,
                )
            )

    @staticmethod
    def create_plan(data, staff_user):
        week_start, week_end = _week_bounds(data.get("week_start"), data.get("week_end"))
        iso_year, iso_week, _ = week_start.isocalendar()

        plan = WeeklyPlan(
            employee_id=staff_user.id,
            week_number=iso_week,
            year=iso_year,
            week_start=week_start,
            week_end=week_end,
            status=PlanStatus.DRAFT,
        )

        db.session.add(plan)
        db.session.flush()

        WeeklyPlanService._sync_goals(plan, data.get("goals"))

        db.session.commit()

        return plan

    @staticmethod
    def update_plan(plan, data):
        if data.get("week_start") or data.get("week_end"):
            week_start, week_end = _week_bounds(
                data.get("week_start") or plan.week_start.isoformat(),
                data.get("week_end") or plan.week_end.isoformat(),
            )
            plan.week_start = week_start
            plan.week_end = week_end
            plan.week_number, plan.year = week_start.isocalendar()[1], week_start.isocalendar()[0]

        if "goals" in data:
            WeeklyPlanService._sync_goals(plan, data.get("goals"))

        db.session.commit()

        return plan

    @staticmethod
    def submit_plan(plan):
        plan.status = PlanStatus.SUBMITTED
        plan.submitted = True
        plan.submitted_at = datetime.utcnow()

        # Resubmitting a returned plan starts a fresh review — the old
        # return notes shouldn't linger next to a new submission.
        plan.reviewed = False
        plan.reviewed_by = None
        plan.reviewed_at = None
        plan.review_notes = None

        db.session.commit()

        return plan

    @staticmethod
    def review_plan(plan, manager, approved, notes=None):
        plan.status = PlanStatus.APPROVED if approved else PlanStatus.REJECTED
        plan.reviewed = True
        plan.reviewed_by = manager.id
        plan.reviewed_at = datetime.utcnow()
        plan.review_notes = notes

        db.session.commit()

        return plan

    @staticmethod
    def goals_pending_verification(current_user):
        """Goals the staff has marked done but the manager hasn't verified yet —
        same scoping rules as scoped_query, just joined the other direction
        (Activity -> WeeklyPlan) since this is queried by goal, not by plan."""

        query = Activity.query.join(WeeklyPlan, Activity.plan_id == WeeklyPlan.id).filter(
            Activity.employee_status == ActivityStatus.DONE,
            Activity.verification_status == VerificationStatus.PENDING,
        )

        if not has_org_scope(current_user):
            query = query.filter(WeeklyPlan.employee_id == current_user.id)

        return query.order_by(Activity.completed_at.desc()).all()

    @staticmethod
    def delete_plan(plan):
        db.session.delete(plan)
        db.session.commit()

    @staticmethod
    def day_lock_reason(day_date, plan=None):
        """The single rule behind every planning-window requirement at once.

        A staff member fills in their whole week — any day of it, in any
        order — in one sitting and submits once; the calendar date within
        the current week doesn't freeze individual days on its own. What
        actually freezes a day is either:
          - the week itself no longer being the current one (a previous
            week has fully passed; a future week isn't open yet), or
          - the plan it belongs to already being submitted/approved, which
            is the real "I'm done planning, don't let me rewrite this"
            boundary (mirrors DRAFT/REJECTED being the only editable plan
            statuses everywhere else).

        Returns None when the day is open, otherwise the exact rejection
        message to surface."""

        today = app_today()
        current_week_start, current_week_end, _, _ = week_bounds_for(today)

        if day_date < current_week_start:
            return "Planning for this week is closed because it has already passed."

        if day_date > current_week_end:
            return "You can only plan the current week — future weeks aren't open for planning yet."

        if plan and plan.status not in (PlanStatus.DRAFT, PlanStatus.REJECTED):
            return "Your weekly plan has already been submitted — you can't modify it until it's returned."

        return None

    @staticmethod
    def is_day_open(day_date, plan=None):
        return WeeklyPlanService.day_lock_reason(day_date, plan) is None

    @staticmethod
    def get_or_create_plan_for_date(employee, target_date):
        """The container for the day-by-day planner — resolved lazily the
        first time a staff member adds a task to a given week, never by
        merely viewing it. The unique (employee_id, week_number, year)
        constraint is the real guard against duplicates; the flush/retry
        here just makes a same-week race harmless instead of a 500."""

        week_start, week_end, iso_week, iso_year = week_bounds_for(target_date)

        plan = WeeklyPlan.query.filter_by(
            employee_id=employee.id, week_number=iso_week, year=iso_year
        ).first()

        if plan:
            return plan

        plan = WeeklyPlan(
            employee_id=employee.id,
            week_number=iso_week,
            year=iso_year,
            week_start=week_start,
            week_end=week_end,
            status=PlanStatus.DRAFT,
        )
        db.session.add(plan)

        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            plan = WeeklyPlan.query.filter_by(
                employee_id=employee.id, week_number=iso_week, year=iso_year
            ).first()
            return plan

        from services.audit_service import AuditService
        from models.enums import AuditAction

        AuditService.log_action(
            employee, AuditAction.CREATE,
            f"Weekly plan created for week {iso_week}, {iso_year}.",
        )

        return plan

    @staticmethod
    def week_view(employee, target_date):
        """The seven-day breakdown of a weekly PLAN — every planning item
        (Activity) for that ISO week, bucketed by day. This is intentionally
        about planned items, not AssignedTasks: before approval a day's
        entries aren't executable work yet, so showing them here (rather
        than a second, task-shaped view) keeps 'what I intend to work on'
        and 'what's actually being executed' from blurring together."""

        week_start, week_end, iso_week, iso_year = week_bounds_for(target_date)

        plan = WeeklyPlan.query.filter_by(
            employee_id=employee.id, week_number=iso_week, year=iso_year
        ).first()

        goals = plan.activities if plan else []
        today = app_today()

        days = []
        for i in range(7):
            day_date = week_start + timedelta(days=i)
            lock_reason = WeeklyPlanService.day_lock_reason(day_date, plan)
            days.append({
                "date": day_date,
                "day_name": DAY_NAMES[i],
                "is_today": day_date == today,
                "is_open": lock_reason is None,
                "lock_reason": lock_reason,
                "goals": [g for g in goals if g.activity_date == day_date],
            })

        return {
            "plan": plan,
            "week_start": week_start,
            "week_end": week_end,
            "week_number": iso_week,
            "year": iso_year,
            "days": days,
        }

    @staticmethod
    def get_goal(plan, goal_id):
        return Activity.query.filter_by(id=goal_id, plan_id=plan.id).first()

    @staticmethod
    def goal_edit_permission(goal, current_user):
        """Who may change a planning item's own fields (title/description/
        outcome/day/time), and when:
          - STAFF: only their own plan, only while it's still DRAFT/REJECTED,
            and only for a day within the open planning window (day_lock_reason
            already folds in both the week and plan-status checks).
          - OPERATIONAL_MANAGER/SUPER_ADMIN: only while the plan is SUBMITTED
            (the review stage) — not before (that's the employee's private
            draft) and not after approval (tasks already exist by then).
        Returns None if allowed, otherwise the exact rejection message."""

        plan = goal.plan

        if current_user.role == UserRole.STAFF:
            if plan.employee_id != current_user.id:
                return "You can only edit your own weekly plan."
            return WeeklyPlanService.day_lock_reason(goal.activity_date, plan)

        # The central Operational Manager and the Super Admin both oversee
        # every department, so the only remaining constraint is the review
        # window itself. HR has no editing rights here at all and falls
        # through to the refusal below.
        if current_user.role in (UserRole.OPERATIONAL_MANAGER, UserRole.SUPER_ADMIN):
            if plan.status != PlanStatus.SUBMITTED:
                return "You can only edit a weekly plan while it's awaiting review."
            return None

        return "You don't have permission to edit this weekly plan."

    @staticmethod
    def create_goal_item(plan, data):
        target_date = datetime.fromisoformat(data["planned_date"]).date()

        due_time = None
        if data.get("due_time"):
            due_time = datetime.strptime(data["due_time"], "%H:%M").time()

        goal = Activity(
            plan_id=plan.id,
            activity_date=target_date,
            title=data["title"].strip(),
            description=data.get("description"),
            expected_outcome=data.get("expected_outcome"),
            due_time=due_time,
            weight=0,
            task_count=1,
        )

        db.session.add(goal)
        db.session.commit()

        return goal

    @staticmethod
    def update_goal_item(goal, data):
        if data.get("title"):
            goal.title = data["title"].strip()

        if "description" in data:
            goal.description = data.get("description")

        if "expected_outcome" in data:
            goal.expected_outcome = data.get("expected_outcome")

        if data.get("planned_date"):
            goal.activity_date = datetime.fromisoformat(data["planned_date"]).date()

        if "due_time" in data:
            goal.due_time = datetime.strptime(data["due_time"], "%H:%M").time() if data.get("due_time") else None

        db.session.commit()

        return goal

    @staticmethod
    def delete_goal_item(goal):
        db.session.delete(goal)
        db.session.commit()

    @staticmethod
    def generate_tasks_from_plan(plan, manager):
        """The traceable Weekly-Plan-item -> Assigned-Task step: fires once,
        on approval. Each Activity becomes exactly one AssignedTask (linked
        via related_activity_id, the FK that already existed for this),
        ready to work on (PENDING) — never a duplicate, since it's only
        called from the SUBMITTED->APPROVED transition, which itself can
        only ever happen once per plan."""

        from models.assigned_task import AssignedTask
        from models.enums import TaskStatus
        from services.performance_service import PerformanceService

        created = []

        for goal in plan.activities:
            existing = AssignedTask.query.filter_by(related_activity_id=goal.id).first()
            if existing:
                continue

            due_date = goal.activity_date

            task = AssignedTask(
                employee_id=plan.employee_id,
                manager_id=manager.id,
                plan_id=plan.id,
                related_activity_id=goal.id,
                title=goal.title,
                description=goal.description,
                expected_outcome=goal.expected_outcome,
                assigned_date=goal.activity_date,
                assigned_time=datetime.utcnow().time(),
                due_date=due_date,
                due_time=goal.due_time,
                priority=goal.priority,
                status=TaskStatus.PENDING,
                submitted_at=datetime.utcnow(),
            )
            db.session.add(task)
            created.append(task)

        db.session.commit()

        if created and plan.employee:
            PerformanceService.recalculate(plan.employee)

        return created

    @staticmethod
    def _recalculate_completion(plan):
        goals = plan.activities
        total_weight = sum(g.weight for g in goals) or 1
        done_weight = sum(g.weight for g in goals if g.employee_status == ActivityStatus.DONE)
        plan.completion_percentage = round((done_weight / total_weight) * 100, 2)

    @staticmethod
    def mark_goal(goal, done):
        """Staff records whether a goal within their approved plan is done —
        the same real-timestamped completion record AssignedTask uses,
        just via Activity's own (previously unwired) status fields."""

        if done:
            goal.mark_completed()
        else:
            goal.mark_not_completed()

        WeeklyPlanService._recalculate_completion(goal.plan)

        db.session.commit()

        return goal

    @staticmethod
    def verify_goal(goal, manager, verified, comments=None):
        status = VerificationStatus.VERIFIED if verified else VerificationStatus.REJECTED
        goal.verify(manager, status, comments=comments)

        db.session.commit()

        return goal
