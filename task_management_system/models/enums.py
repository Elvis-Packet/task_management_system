from enum import Enum


# ==========================================================
# USER MANAGEMENT
# ==========================================================

class UserRole(Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    OPERATIONAL_MANAGER = "OPERATIONAL_MANAGER"
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
