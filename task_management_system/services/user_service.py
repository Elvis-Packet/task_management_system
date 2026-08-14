from datetime import datetime

from sqlalchemy import or_, func

from extensions import db
from models.user import User
from models.enums import UserRole, UserStatus
from utils.enum_map import user_status_from_fe
from utils.rbac import has_org_scope

_ROLE_PREFIX = {
    UserRole.SUPER_ADMIN: "SA",
    UserRole.OPERATIONAL_MANAGER: "OM",
    UserRole.HR: "HR",
    UserRole.STAFF: "STF",
}


def _next_employee_number(role):
    count = db.session.query(func.count(User.id)).scalar() or 0
    return f"{_ROLE_PREFIX.get(role, 'USR')}{count + 1:04d}"


class UserService:

    @staticmethod
    def scoped_query(current_user):
        """RBAC: the org-scoped roles (SUPER_ADMIN, the central OPERATIONAL_
        MANAGER, HR) see every user in the organization; everyone else — i.e.
        STAFF — sees only their own record. Soft-deleted users are excluded
        by default. Scope is decided by utils.rbac.has_org_scope() so this
        rule is stated in exactly one place across the whole codebase."""

        query = User.query.filter(User.deleted_at.is_(None))

        if not has_org_scope(current_user):
            query = query.filter(User.id == current_user.id)

        return query

    @staticmethod
    def apply_filters(query, args):
        role = args.get("role")
        department_id = args.get("department_id")
        status = args.get("status")
        search = args.get("search")

        if role:
            try:
                query = query.filter(User.role == UserRole[role.upper()])
            except KeyError:
                pass

        if department_id:
            query = query.filter(User.department_id == department_id)

        if status:
            query = query.filter(User.status == user_status_from_fe(status))

        if search:
            like = f"%{search}%"
            query = query.filter(
                or_(
                    User.first_name.ilike(like),
                    User.last_name.ilike(like),
                    User.email.ilike(like),
                    User.employee_number.ilike(like),
                )
            )

        return query.order_by(User.created_at.desc())

    @staticmethod
    def create_user(data, created_by):
        role = UserRole[data["role"].upper()]

        user = User(
            employee_number=_next_employee_number(role),
            first_name=data["first_name"].strip(),
            middle_name=(data.get("middle_name") or "").strip() or None,
            last_name=data["last_name"].strip(),
            email=data["email"].strip().lower(),
            phone=data.get("phone"),
            job_title=(data.get("job_title") or "").strip() or None,
            role=role,
            department_id=data.get("department_id") or None,
            status=UserStatus.ACTIVE,
            created_by=created_by.id,
            is_first_login=True,
        )

        user.set_password(data["password"])

        db.session.add(user)
        db.session.commit()

        return user

    # Profile fields an authorized administrator may change on someone else's
    # account. Deliberately excludes everything security-sensitive or
    # system-owned: password_hash / reset_token_* (password changes go through
    # AuthService's reset flow only), employee_number, id, created_by,
    # created_at, deleted_at, failed_login_attempts and the last_* telemetry
    # columns are all written by the system, never by a form.
    EDITABLE_FIELDS = ("first_name", "middle_name", "last_name", "phone", "job_title", "profile_photo")

    @staticmethod
    def update_user(user, data):
        """Applies an administrative edit. Authorization (may this actor touch
        this account, may they change this role) is decided by the route via
        utils.rbac before we ever get here — this method only writes."""

        for field in UserService.EDITABLE_FIELDS:
            if field not in data:
                continue

            value = data[field]

            if isinstance(value, str):
                value = value.strip() or None

            # first_name/last_name are NOT NULL — an empty string in the form
            # means "unchanged", never "wipe the name".
            if value is None and field in ("first_name", "last_name"):
                continue

            setattr(user, field, value)

        if data.get("email"):
            user.email = data["email"].strip().lower()

        if data.get("role"):
            user.role = UserRole[data["role"].upper()]

        if "department_id" in data:
            user.department_id = data["department_id"] or None

        if data.get("status"):
            new_status = user_status_from_fe(data["status"], default=None)
            if new_status is not None:
                user.status = new_status
                if new_status == UserStatus.ACTIVE:
                    user.failed_login_attempts = 0

        db.session.commit()

        return user

    @staticmethod
    def suspend_user(user):
        user.status = UserStatus.INACTIVE
        db.session.commit()
        return user

    @staticmethod
    def activate_user(user):
        user.status = UserStatus.ACTIVE
        user.failed_login_attempts = 0
        db.session.commit()
        return user

    @staticmethod
    def soft_delete_user(user):
        user.deleted_at = datetime.utcnow()
        user.status = UserStatus.INACTIVE
        db.session.commit()
        return user

    # What a user may change about themselves. Strictly narrower than
    # EDITABLE_FIELDS: no role, no status, no department — those are
    # administrative decisions, and letting a user set them on their own
    # profile would be a self-service privilege escalation.
    SELF_EDITABLE_FIELDS = ("first_name", "middle_name", "last_name", "phone", "profile_photo")

    @staticmethod
    def update_profile(user, data):
        for field in UserService.SELF_EDITABLE_FIELDS:
            if field in data and data[field] is not None:
                setattr(user, field, data[field].strip() if isinstance(data[field], str) else data[field])

        db.session.commit()

        return user
