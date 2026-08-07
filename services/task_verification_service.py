from datetime import datetime

from extensions import db

from models.assigned_task import AssignedTask
from models.enums import TaskStatus



# =====================================================
# GET TASKS WAITING FOR VERIFICATION
# =====================================================


def get_tasks_for_verification(manager):


    return AssignedTask.query.filter_by(

        manager_id=manager.id,

        status=TaskStatus.COMPLETED

    ).order_by(

        AssignedTask.completed_at.asc()

    ).all()




# =====================================================
# VERIFY TASK
# =====================================================


def verify_task(

    task,

    manager,

    feedback=None

):


    if task.status != TaskStatus.COMPLETED:

        return False, (
            "Only completed tasks can be verified."
        )



    task.verify(

        manager,

        feedback

    )


    db.session.commit()


    return True, (
        "Task verified successfully."
    )




# =====================================================
# RETURN TASK
# =====================================================


def return_task(

    task,

    manager,

    reason

):


    if task.status != TaskStatus.COMPLETED:

        return False, (
            "Task is not ready for review."
        )



    task.return_to_employee(

        reason

    )


    task.verified_by = manager.id

    task.verified_at = datetime.utcnow()



    db.session.commit()


    return True, (
        "Task returned to employee."
    )




# =====================================================
# MANAGER DASHBOARD COUNT
# =====================================================


def pending_task_reviews(manager):


    return AssignedTask.query.filter_by(

        manager_id=manager.id,

        status=TaskStatus.COMPLETED

    ).count()