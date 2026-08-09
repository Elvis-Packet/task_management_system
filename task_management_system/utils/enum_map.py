"""
Translates between backend enum values (models/enums.py, always UPPER_CASE)
and the vocabulary the existing frontend constants already use
(frontend/src/constants/statuses.js — lower_snake_case). Keeping this mapping
in one place means the frontend's existing status badges / filters / labels
never had to be rewritten to match the backend.
"""

from models.enums import TaskPriority, TaskStatus, PlanStatus, UserStatus

# --- Priority --------------------------------------------------------------
# Frontend has low/medium/high/critical. Backend has LOW/NORMAL/HIGH/CRITICAL.
PRIORITY_TO_FE = {
    TaskPriority.LOW: "low",
    TaskPriority.NORMAL: "medium",
    TaskPriority.HIGH: "high",
    TaskPriority.CRITICAL: "critical",
}

FE_TO_PRIORITY = {v: k for k, v in PRIORITY_TO_FE.items()}


def priority_to_fe(priority):
    return PRIORITY_TO_FE.get(priority, "medium") if priority else "medium"


def priority_from_fe(value, default=TaskPriority.NORMAL):
    if not value:
        return default
    return FE_TO_PRIORITY.get(str(value).lower(), default)


# --- Task status -------------------------------------------------------------
# 1:1 name match once lowercased.
def task_status_to_fe(status):
    return status.value.lower() if status else None


def task_status_from_fe(value, default=TaskStatus.PENDING):
    if not value:
        return default
    try:
        return TaskStatus[str(value).upper()]
    except KeyError:
        return default


# --- Plan status ---------------------------------------------------------
def plan_status_to_fe(status):
    return status.value.lower() if status else None


def plan_status_from_fe(value, default=PlanStatus.DRAFT):
    if not value:
        return default
    try:
        return PlanStatus[str(value).upper()]
    except KeyError:
        return default


# --- User status -----------------------------------------------------------
# Business language in the UI is "suspend"/"activate" a user, so INACTIVE
# is presented to the frontend as "suspended".
USER_STATUS_TO_FE = {
    UserStatus.ACTIVE: "active",
    UserStatus.INACTIVE: "suspended",
    UserStatus.LOCKED: "locked",
}

FE_TO_USER_STATUS = {v: k for k, v in USER_STATUS_TO_FE.items()}


def user_status_to_fe(status):
    return USER_STATUS_TO_FE.get(status, "active") if status else "active"


def user_status_from_fe(value, default=UserStatus.ACTIVE):
    if not value:
        return default
    return FE_TO_USER_STATUS.get(str(value).lower(), default)
