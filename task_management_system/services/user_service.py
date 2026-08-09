from datetime import datetime

from sqlalchemy import or_, func

from extensions import db
from models.user import User
from models.enums import UserRole, UserStatus
from utils.enum_map import user_status_from_fe

_ROLE_PREFIX = {
    UserRole.SUPER_ADMIN: "SA",
    UserRole.OPERATIONAL_MANAGER: "OM",
    UserRole.STAFF: "STF",
}


def _next_employee_number(role):
    count = db.session.query(func.count(User.id)).scalar() or 0
    return f"{_ROLE_PREFIX.get(role, 'USR')}{count + 1:04d}"


class UserService:

    @staticmethod
    def scoped_query(current_user):
        """RBAC: STAFF never lists users; MANAGER sees only STAFF in their own
        department; SUPER_ADMIN sees everyone. Soft-deleted users excluded by default."""

        query = User.query.filter(User.deleted_at.is_(None))

        if current_user.role == UserRole.OPERATIONAL_MANAGER:
            query = query.filter(
                User.department_id == current_user.department_id,
                User.role == UserRole.STAFF,
            )
        elif current_user.role == UserRole.STAFF:
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
            last_name=data["last_name"].strip(),
            email=data["email"].strip().lower(),
            phone=data.get("phone"),
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

    @staticmethod
    def update_user(user, data):
        for field in ("first_name", "last_name", "phone", "profile_photo"):
            if field in data and data[field] is not None:
                setattr(user, field, data[field].strip() if isinstance(data[field], str) else data[field])

        if data.get("email"):
            user.email = data["email"].strip().lower()

        if data.get("role"):
            user.role = UserRole[data["role"].upper()]

        if "department_id" in data:
            user.department_id = data["department_id"] or None

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

    @staticmethod
    def update_profile(user, data):
        for field in ("first_name", "last_name", "phone", "profile_photo"):
            if field in data and data[field] is not None:
                setattr(user, field, data[field].strip() if isinstance(data[field], str) else data[field])

        db.session.commit()

        return user
