from enum import Enum


# ==========================================================
# USER MANAGEMENT
# ==========================================================

class UserRole(Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    OPERATIONS_MANAGER = "OPERATIONS_MANAGER"
    EMPLOYEE = "EMPLOYEE"


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
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    CANCELLED = "CANCELLED"
    OVERDUE = "OVERDUE"


# ==========================================================
# EMPLOYEE ACTIVITY STATUS
# Used by Activity model
# ==========================================================

class EmployeeStatus(Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    NOT_COMPLETED = "NOT_COMPLETED"


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

class AssignmentStatus(Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

class AuditAction(Enum):
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    VERIFY = "VERIFY"
    ASSIGN_TASK = "ASSIGN_TASK"
    SUBMIT_PLAN = "SUBMIT_PLAN"
    REVIEW_PLAN = "REVIEW_PLAN"