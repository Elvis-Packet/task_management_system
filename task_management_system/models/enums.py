from enum import Enum


# ==========================================================
# USER MANAGEMENT
# ==========================================================

class UserRole(Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    # The single central Operational Manager — oversees every department and
    # every user, not one department. Department membership on this account
    # is informational only; scope comes from utils.rbac.has_org_scope().
    OPERATIONAL_MANAGER = "OPERATIONAL_MANAGER"
    # Read-mostly people-operations role: sees organization-wide task
    # performance and escalation flags, never manages users or tasks.
    HR = "HR"
    STAFF = "STAFF"


class UserStatus(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    LOCKED = "LOCKED"


# ==========================================================
# WEEKLY PLAN
# ==========================================================

class PlanStatus(Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    ACTIVE = "ACTIVE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


# ==========================================================
# PRIORITY
# Used by Activities & Assigned Tasks
# ==========================================================

class TaskPriority(Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ==========================================================
# ASSIGNED TASK STATUS
# Used ONLY by AssignedTask
# ==========================================================

class TaskStatus(Enum):
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    OVERDUE = "OVERDUE"


# ==========================================================
# ACTIVITY STATUS
# Used internally by Activity workflow
# ==========================================================

class ActivityStatus(Enum):
    PENDING = "PENDING"
    DONE = "DONE"
    NOT_DONE = "NOT_DONE"


# ==========================================================
# MANAGER VERIFICATION
# ==========================================================

class VerificationStatus(Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    OVERRIDDEN = "OVERRIDDEN"


# ==========================================================
# FINAL SYSTEM RESULT
# ==========================================================

class FinalStatus(Enum):
    PENDING = "PENDING"
    SUCCESSFUL = "SUCCESSFUL"
    UNSUCCESSFUL = "UNSUCCESSFUL"
    MANAGER_OVERRIDE = "MANAGER_OVERRIDE"


# ==========================================================
# NOTIFICATIONS
# ==========================================================

class NotificationType(Enum):
    SYSTEM = "SYSTEM"
    ASSIGNED_TASK = "ASSIGNED_TASK"
    TASK_QUERY = "TASK_QUERY"
    WEEKLY_PLAN = "WEEKLY_PLAN"
    PLAN_REVIEW = "PLAN_REVIEW"
    PERFORMANCE = "PERFORMANCE"
    REMINDER = "REMINDER"
    SECURITY = "SECURITY"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    COMMENT = "COMMENT"


class NotificationPriority(Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class NotificationDeliveryStatus(Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


# ==========================================================
# AUDIT
# ==========================================================

class AuditAction(Enum):
    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SUSPEND = "SUSPEND"
    ACTIVATE = "ACTIVATE"
    RESET_PASSWORD = "RESET_PASSWORD"
    VERIFY = "VERIFY"
    REJECT = "REJECT"
    ASSIGN_TASK = "ASSIGN_TASK"
    SUBMIT_PLAN = "SUBMIT_PLAN"
    REVIEW_PLAN = "REVIEW_PLAN"
    COMMENT = "COMMENT"
    RAISE_QUERY = "RAISE_QUERY"
    RESPOND_QUERY = "RESPOND_QUERY"
    CLOSE_QUERY = "CLOSE_QUERY"


# ==========================================================
# COMMENTS
# ==========================================================

class CommentTargetType(Enum):
    TASK = "TASK"
    WEEKLY_PLAN = "WEEKLY_PLAN"
    REPORT = "REPORT"
    ACTIVITY = "ACTIVITY"


# ==========================================================
# NON-COMPLETION / OVERDUE EXCEPTION HANDLING
# Recorded by a manager against a specific task — append-only,
# never overwrites the task's own history.
# ==========================================================

class NonCompletionReasonCategory(Enum):
    CUSTOMER_DELAY = "CUSTOMER_DELAY"
    SYSTEM_DOWNTIME = "SYSTEM_DOWNTIME"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    INSUFFICIENT_RESOURCES = "INSUFFICIENT_RESOURCES"
    STAFF_UNAVAILABLE = "STAFF_UNAVAILABLE"
    EXTERNAL_DEPENDENCY = "EXTERNAL_DEPENDENCY"
    EMERGENCY = "EMERGENCY"
    OTHER = "OTHER"


class TaskResolution(Enum):
    RESCHEDULED = "RESCHEDULED"
    PENDING_DEPENDENCY = "PENDING_DEPENDENCY"
    ESCALATED = "ESCALATED"
    WAIVED = "WAIVED"
    CONTINUE_MONITORING = "CONTINUE_MONITORING"


# ==========================================================
# MANAGER STATUS QUERY ON AN INCOMPLETE TASK
# A manager asks the assignee for a progress update; the staff
# member answers on the same record, so "asked but never answered"
# is a first-class, countable state (HR flags depend on it).
# ==========================================================

class QueryStatus(Enum):
    OPEN = "OPEN"
    ANSWERED = "ANSWERED"
    CLOSED = "CLOSED"
