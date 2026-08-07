from datetime import datetime

from extensions import db

from models.assigned_task import AssignedTask
from models.user import User
from models.activity import Activity
from models.weekly_plan import WeeklyPlan

from models.enums import (
    TaskPriority,
    TaskStatus
)

from services.assigned_task_performance_service import (
    update_assigned_task_performance
)


# ==========================================================
# CREATE TASK
# ==========================================================

def create_task(
    employee_id,
    manager_id,
    department_id,
    title,
    description,
    assigned_date,
    assigned_time,
    due_date,
    due_time,
    priority,
    activity_id=None,
    weekly_plan_id=None
):

    employee = User.query.get(employee_id)

    if not employee:
        return False, "Employee not found.", None

    task = AssignedTask(

        employee_id=employee.id,

        employee_number=employee.employee_number,

        manager_id=manager_id,

        department_id=department_id,

        activity_id=activity_id,

        weekly_plan_id=weekly_plan_id,

        title=title,

        description=description,

        assigned_date=assigned_date,

        assigned_time=assigned_time,

        due_date=due_date,

        due_time=due_time,

        priority=TaskPriority[priority]

    )

    db.session.add(task)
    db.session.commit()

    return True, "Task assigned successfully.", task


# ==========================================================
# UPDATE TASK
# ==========================================================

def update_task(

    task,

    employee_id,

    title,

    description,

    due_date,

    due_time,

    priority,

    activity_id=None,

    weekly_plan_id=None

):

    employee = User.query.get(employee_id)

    if not employee:

        return False, "Employee not found."

    task.employee_id = employee.id
    task.employee_number = employee.employee_number

    task.activity_id = activity_id
    task.weekly_plan_id = weekly_plan_id

    task.title = title
    task.description = description

    task.priority = TaskPriority[priority]

    task.due_date = due_date
    task.due_time = due_time

    task.updated_at = datetime.utcnow()

    db.session.commit()

    return True, "Task updated successfully."


# ==========================================================
# DELETE TASK
# ==========================================================

def delete_task(task):

    db.session.delete(task)

    db.session.commit()

    return True, "Task deleted successfully."


# ==========================================================
# GETTERS
# ==========================================================

def get_task(task_id):

    return AssignedTask.query.get_or_404(task_id)


def get_tasks():

    return AssignedTask.query.order_by(

        AssignedTask.created_at.desc()

    ).all()


def get_employee_tasks(employee_id):

    return AssignedTask.query.filter_by(

        employee_id=employee_id

    ).order_by(

        AssignedTask.created_at.desc()

    ).all()


def get_manager_tasks(manager_id):

    return AssignedTask.query.filter_by(

        manager_id=manager_id

    ).order_by(

        AssignedTask.created_at.desc()

    ).all()


def get_completed_tasks(manager_id):

    return AssignedTask.query.filter(

        AssignedTask.manager_id == manager_id,

        AssignedTask.status == TaskStatus.COMPLETED

    ).order_by(

        AssignedTask.completed_at.desc()

    ).all()


# ==========================================================
# EMPLOYEE ACTIONS
# ==========================================================

def acknowledge_task(task, employee):

    if task.employee_id != employee.id:

        return False, "Unauthorized."

    task.acknowledge()

    db.session.commit()

    return True, "Task acknowledged."


def start_task(task, employee):

    if task.employee_id != employee.id:

        return False, "Unauthorized."

    task.start()

    db.session.commit()

    return True, "Task started."


def complete_task(

    task,

    employee,

    notes=None,

    evidence=None

):

    if task.employee_id != employee.id:

        return False, "Unauthorized."

    task.complete(

        notes,

        evidence

    )

    db.session.commit()

    return True, "Task submitted successfully."


# ==========================================================
# MANAGER REVIEW
# ==========================================================

def verify_task(

    task,

    manager,

    quality_rating,

    timeliness_rating,

    feedback=None,

    notes=None

):

    if task.manager_id != manager.id:

        return False, "Unauthorized."

    if task.status != TaskStatus.COMPLETED:

        return False, "Task has not been completed."

    task.verify(

        manager=manager,

        quality_rating=quality_rating,

        timeliness_rating=timeliness_rating,

        feedback=feedback,

        notes=notes

    )

    db.session.commit()

    update_assigned_task_performance(
        task.employee
    )


    from services.performance_summary_service import (
        calculate_summary
    )


    calculate_summary(
        task.employee
    )

    return True, "Task verified successfully."


def reject_task(

    task,

    manager,

    reason

):

    if task.manager_id != manager.id:

        return False, "Unauthorized."

    task.reject(

        manager,

        reason

    )

    db.session.commit()

    update_assigned_task_performance(

        task.employee

    )

    return True, "Task rejected."


def return_task(

    task,

    manager,

    reason

):

    if task.manager_id != manager.id:

        return False, "Unauthorized."

    task.return_to_employee(reason)

    db.session.commit()

    return True, "Task returned to employee."


# ==========================================================
# SEARCH
# ==========================================================

def search_tasks(query):

    return AssignedTask.query.filter(

        AssignedTask.title.ilike(

            f"%{query}%"

        )

    ).order_by(

        AssignedTask.created_at.desc()

    ).all()


# ==========================================================
# DASHBOARD
# ==========================================================

def dashboard_cards(manager_id):

    tasks = AssignedTask.query.filter_by(

        manager_id=manager_id

    ).all()

    return {

        "total": len(tasks),

        "pending": len(

            [

                t

                for t in tasks

                if t.status == TaskStatus.PENDING

            ]

        ),

        "progress": len(

            [

                t

                for t in tasks

                if t.status == TaskStatus.IN_PROGRESS

            ]

        ),

        "completed": len(

            [

                t

                for t in tasks

                if t.status == TaskStatus.COMPLETED

            ]

        ),

        "verified": len(

            [

                t

                for t in tasks

                if t.status == TaskStatus.VERIFIED

            ]

        ),

        "rejected": len(

            [

                t

                for t in tasks

                if t.status == TaskStatus.REJECTED

            ]

        ),

        "returned": len(

            [

                t

                for t in tasks

                if t.returned

            ]

        ),

        "overdue": len(

            [

                t

                for t in tasks

                if t.is_overdue

            ]

        )

    }


# ==========================================================
# ACTIVITIES
# ==========================================================

def get_department_pending_activities(

    department_id

):

    return (

        Activity.query

        .join(

            WeeklyPlan,

            Activity.plan_id == WeeklyPlan.id

        )

        .join(

            User,

            WeeklyPlan.employee_id == User.id

        )

        .filter(

            User.department_id == department_id

        )

        .all()

    )


# ==========================================================
# MANAGER REVIEW QUEUE
# ==========================================================

def get_tasks_waiting_review(manager_id):

    return AssignedTask.query.filter(

        AssignedTask.manager_id == manager_id,

        AssignedTask.status == TaskStatus.COMPLETED

    ).order_by(

        AssignedTask.completed_at.desc()

    ).all()


def get_verified_tasks(manager_id):

    return AssignedTask.query.filter(

        AssignedTask.manager_id == manager_id,

        AssignedTask.status == TaskStatus.VERIFIED

    ).all()


def get_returned_tasks(manager_id):

    return AssignedTask.query.filter(

        AssignedTask.manager_id == manager_id,

        AssignedTask.returned == True

    ).all()


def get_rejected_tasks(manager_id):

    return AssignedTask.query.filter(

        AssignedTask.manager_id == manager_id,

        AssignedTask.status == TaskStatus.REJECTED

    ).all()