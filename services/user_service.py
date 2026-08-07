from datetime import datetime

from sqlalchemy import or_

from extensions import db

from models.user import User
from models.department import Department

from models.enums import (
    UserRole,
    UserStatus
)

from werkzeug.security import generate_password_hash


# ==========================================================
# BASIC QUERIES
# ==========================================================

def get_users():

    return User.query.order_by(
        User.first_name.asc(),
        User.last_name.asc()
    ).all()


def get_user(user_id):

    return User.query.get(user_id)


def get_user_by_employee_number(employee_number):

    return User.query.filter_by(
        employee_number=employee_number
    ).first()


def get_user_by_email(email):

    return User.query.filter_by(
        email=email
    ).first()


# ==========================================================
# ROLE QUERIES
# ==========================================================

def get_super_admins():

    return User.query.filter_by(
        role=UserRole.SUPER_ADMIN
    ).all()


def get_managers():

    return User.query.filter_by(
        role=UserRole.OPERATIONS_MANAGER
    ).order_by(
        User.first_name
    ).all()


def get_employees():

    return User.query.filter_by(
        role=UserRole.EMPLOYEE
    ).order_by(
        User.first_name
    ).all()


# ==========================================================
# DEPARTMENT QUERIES
# ==========================================================

def get_department_users(department_id):

    return User.query.filter_by(
        department_id=department_id
    ).all()


def get_department_managers(department_id):

    return User.query.filter(

        User.department_id == department_id,

        User.role == UserRole.OPERATIONS_MANAGER

    ).all()


def get_department_employees(department_id):

    return User.query.filter(

        User.department_id == department_id,

        User.role == UserRole.EMPLOYEE

    ).all()


# ==========================================================
# ACTIVE USERS
# ==========================================================

def get_active_users():

    return User.query.filter_by(
        status=UserStatus.ACTIVE
    ).all()


def get_locked_users():

    return User.query.filter_by(
        status=UserStatus.LOCKED
    ).all()


def get_inactive_users():

    return User.query.filter_by(
        status=UserStatus.INACTIVE
    ).all()


# ==========================================================
# SEARCH
# ==========================================================

def search_users(query):

    return User.query.filter(

        or_(

            User.first_name.ilike(f"%{query}%"),

            User.middle_name.ilike(f"%{query}%"),

            User.last_name.ilike(f"%{query}%"),

            User.employee_number.ilike(f"%{query}%"),

            User.email.ilike(f"%{query}%")

        )

    ).order_by(

        User.first_name.asc()

    ).all()


# ==========================================================
# STATISTICS
# ==========================================================

def user_statistics():

    return {

        "total":

            User.query.count(),

        "super_admins":

            User.query.filter_by(
                role=UserRole.SUPER_ADMIN
            ).count(),

        "managers":

            User.query.filter_by(
                role=UserRole.OPERATIONS_MANAGER
            ).count(),

        "employees":

            User.query.filter_by(
                role=UserRole.EMPLOYEE
            ).count(),

        "active":

            User.query.filter_by(
                status=UserStatus.ACTIVE
            ).count(),

        "inactive":

            User.query.filter_by(
                status=UserStatus.INACTIVE
            ).count(),

        "locked":

            User.query.filter_by(
                status=UserStatus.LOCKED
            ).count()

    }

# ==========================================================
# CREATE USER
# ==========================================================

def create_user(
    employee_number,
    first_name,
    middle_name,
    last_name,
    email,
    phone,
    password,
    role,
    department_id=None,
    manager_id=None,
    created_by=None
):
    """
    Creates a new system user.

    Rules:
    - Super Admin has no department or manager.
    - Operations Manager belongs to one department.
    - Employee gets manager automatically from department.
    """

    try:

        # --------------------------------------------------
        # CHECK DUPLICATE EMPLOYEE NUMBER
        # --------------------------------------------------

        existing_employee = User.query.filter_by(
            employee_number=employee_number
        ).first()


        if existing_employee:

            return False, (
                "Employee number already exists."
            )



        # --------------------------------------------------
        # CHECK DUPLICATE EMAIL
        # --------------------------------------------------

        existing_email = User.query.filter_by(
            email=email.lower().strip()
        ).first()


        if existing_email:

            return False, (
                "Email address already exists."
            )



        # --------------------------------------------------
        # NORMALIZE IDS
        # --------------------------------------------------

        if department_id:

            department_id = int(department_id)


        if manager_id:

            manager_id = int(manager_id)



        # --------------------------------------------------
        # DEPARTMENT VALIDATION
        # --------------------------------------------------

        department = None


        if role != UserRole.SUPER_ADMIN:


            if not department_id:

                return False, (
                    "Department is required."
                )


            department = Department.query.get(
                department_id
            )


            if not department:

                return False, (
                    "Department not found."
                )



        # --------------------------------------------------
        # EMPLOYEE MANAGER ASSIGNMENT
        # --------------------------------------------------

        if role == UserRole.EMPLOYEE:


            # Always pick manager from department

            manager_id = department.manager_id



            if not manager_id:

                return False, (
                    "This department has no assigned manager."
                )



            manager = User.query.get(
                manager_id
            )


            if not manager:

                return False, (
                    "Department manager does not exist."
                )



            if manager.role != UserRole.OPERATIONS_MANAGER:

                return False, (
                    "Department manager must be an Operations Manager."
                )



        # --------------------------------------------------
        # OPERATIONS MANAGER VALIDATION
        # --------------------------------------------------

        if role == UserRole.OPERATIONS_MANAGER:


            existing_manager = User.query.filter_by(
                department_id=department_id,
                role=UserRole.OPERATIONS_MANAGER
            ).first()



            if existing_manager:

                return False, (
                    "This department already has an Operations Manager."
                )



            manager_id = None



        # --------------------------------------------------
        # SUPER ADMIN RULE
        # --------------------------------------------------

        if role == UserRole.SUPER_ADMIN:

            department_id = None

            manager_id = None



        # --------------------------------------------------
        # CREATE USER
        # --------------------------------------------------

        user = User(

            employee_number=employee_number,

            first_name=first_name.strip(),

            middle_name=(
                middle_name.strip()
                if middle_name
                else None
            ),

            last_name=last_name.strip(),

            email=email.lower().strip(),

            phone=phone,

            role=role,

            department_id=department_id,

            manager_id=manager_id,

            created_by=created_by,

            status=UserStatus.ACTIVE,

            created_at=datetime.utcnow()

        )



        user.set_password(password)



        db.session.add(user)

        db.session.flush()



        # --------------------------------------------------
        # LINK OPERATIONS MANAGER TO DEPARTMENT
        # --------------------------------------------------

        if (
            role == UserRole.OPERATIONS_MANAGER
            and department_id
        ):


            department.manager_id = user.id



        # --------------------------------------------------
        # FINAL COMMIT FOR ALL USERS
        # --------------------------------------------------

        db.session.commit()



        return True, (
            f"{role.value.replace('_',' ').title()} "
            "created successfully."
        )



    except Exception as e:


        db.session.rollback()


        return False, (
            f"User creation failed: {str(e)}"
        )


# ==========================================================
# UPDATE USER
# ==========================================================

def update_user(
    user,
    employee_number,
    first_name,
    middle_name,
    last_name,
    email,
    phone,
    role,
    department_id=None,
    status=None,
    is_first_login=None,
    password=None
):
    """
    Updates an existing user.

    Rules:
    - SUPER_ADMIN has no department or manager.
    - OPERATIONS_MANAGER owns a department.
    - EMPLOYEE gets manager automatically from department.
    """

    try:


        # --------------------------------------------------
        # DUPLICATE EMPLOYEE NUMBER
        # --------------------------------------------------

        existing = User.query.filter(
            User.employee_number == employee_number,
            User.id != user.id
        ).first()


        if existing:

            return False, (
                "Employee number already exists."
            )



        # --------------------------------------------------
        # DUPLICATE EMAIL
        # --------------------------------------------------

        existing = User.query.filter(
            User.email == email.lower().strip(),
            User.id != user.id
        ).first()


        if existing:

            return False, (
                "Email address already exists."
            )



        # --------------------------------------------------
        # NORMALIZE IDS
        # --------------------------------------------------

        if department_id:

            department_id = int(department_id)



        # --------------------------------------------------
        # SUPER ADMIN
        # --------------------------------------------------

        if role == UserRole.SUPER_ADMIN:


            department_id = None

            manager_id = None



        # --------------------------------------------------
        # OPERATIONS MANAGER
        # --------------------------------------------------

        elif role == UserRole.OPERATIONS_MANAGER:


            if not department_id:

                return False, (
                    "Operations Manager requires a department."
                )


            # Prevent two managers in same department

            existing_manager = User.query.filter(
                User.department_id == department_id,
                User.role == UserRole.OPERATIONS_MANAGER,
                User.id != user.id
            ).first()


            if existing_manager:

                return False, (
                    "This department already has an Operations Manager."
                )


            manager_id = None



        # --------------------------------------------------
        # EMPLOYEE
        # --------------------------------------------------

        elif role == UserRole.EMPLOYEE:


            if not department_id:

                return False, (
                    "Employee requires a department."
                )


            department = Department.query.get(
                department_id
            )


            if not department:

                return False, (
                    "Department not found."
                )


            # Automatically assign manager

            manager_id = department.manager_id


            if not manager_id:

                return False, (
                    "This department has no assigned manager."
                )



        # --------------------------------------------------
        # UPDATE USER DATA
        # --------------------------------------------------

        user.employee_number = employee_number

        user.first_name = first_name.strip()

        user.middle_name = (
            middle_name.strip()
            if middle_name
            else None
        )
        user.status = status


        if is_first_login is not None:

            user.is_first_login = is_first_login



        if password:

            user.set_password(password)
        user.last_name = last_name.strip()

        user.email = email.lower().strip()

        user.phone = phone

        user.role = role

        user.department_id = department_id

        user.manager_id = manager_id



        # --------------------------------------------------
        # IF USER BECOMES MANAGER UPDATE DEPARTMENT
        # --------------------------------------------------

        if (
            role == UserRole.OPERATIONS_MANAGER
            and department_id
        ):

            department = Department.query.get(
                department_id
            )

            if department:

                department.manager_id = user.id



        db.session.commit()


        return True, (
            "User updated successfully."
        )


    except Exception as e:


        db.session.rollback()


        return False, str(e)


# ==========================================================
# DELETE USER
# ==========================================================

def delete_user(user):
    """
    Deletes a user.
    """

    try:

        db.session.delete(user)

        db.session.commit()

        return True, "User deleted successfully."

    except Exception as e:

        db.session.rollback()

        return False, str(e)

    
# ==========================================================
# ACTIVATE USER
# ==========================================================

def activate_user(user):
    """
    Activates a user account.
    """

    try:

        user.status = UserStatus.ACTIVE

        db.session.commit()

        return True, "User account activated successfully."

    except Exception as e:

        db.session.rollback()

        return False, str(e)


# ==========================================================
# DEACTIVATE USER
# ==========================================================

def deactivate_user(user):
    """
    Deactivates a user account.
    """

    try:

        user.status = UserStatus.INACTIVE

        db.session.commit()

        return True, "User account deactivated successfully."

    except Exception as e:

        db.session.rollback()

        return False, str(e)


# ==========================================================
# LOCK USER
# ==========================================================

def lock_user(user):
    """
    Locks a user account.
    """

    try:

        user.status = UserStatus.LOCKED

        db.session.commit()

        return True, "User account locked successfully."

    except Exception as e:

        db.session.rollback()

        return False, str(e)


# ==========================================================
# UNLOCK USER
# ==========================================================

def unlock_user(user):
    """
    Unlocks a user account.
    """

    try:

        user.status = UserStatus.ACTIVE

        user.failed_login_attempts = 0

        db.session.commit()

        return True, "User account unlocked successfully."

    except Exception as e:

        db.session.rollback()

        return False, str(e)


# ==========================================================
# RESET PASSWORD
# ==========================================================

def reset_password(user, new_password):
    """
    Resets a user's password.
    """

    try:

        user.set_password(new_password)

        user.password_changed_at = datetime.utcnow()

        user.failed_login_attempts = 0

        user.is_first_login = True

        db.session.commit()

        return True, "Password reset successfully."

    except Exception as e:

        db.session.rollback()

        return False, str(e)


# ==========================================================
# CHANGE PASSWORD
# ==========================================================

def change_password(
    user,
    current_password,
    new_password
):
    """
    Allows a user to change their own password.
    """

    try:

        if not user.check_password(current_password):

            return False, "Current password is incorrect."

        user.set_password(new_password)

        user.password_changed_at = datetime.utcnow()

        user.is_first_login = False

        db.session.commit()

        return True, "Password changed successfully."

    except Exception as e:

        db.session.rollback()

        return False, str(e)


# ==========================================================
# UPDATE LOGIN INFORMATION
# ==========================================================

def update_login_information(
    user,
    ip_address=None,
    browser=None,
    device=None
):
    """
    Updates login metadata after a successful login.
    """

    try:

        user.last_login = datetime.utcnow()

        user.last_activity = datetime.utcnow()

        user.last_ip_address = ip_address

        user.last_browser = browser

        user.last_device = device

        user.failed_login_attempts = 0

        db.session.commit()

    except Exception:

        db.session.rollback()


# ==========================================================
# RECORD FAILED LOGIN
# ==========================================================

def record_failed_login(
    user,
    maximum_attempts=5
):
    """
    Records a failed login attempt and locks the account
    if the maximum number of attempts is reached.
    """

    try:

        user.failed_login_attempts += 1

        if user.failed_login_attempts >= maximum_attempts:

            user.status = UserStatus.LOCKED

        db.session.commit()

    except Exception:

        db.session.rollback()

# ==========================================================
# EMPLOYEE NUMBER GENERATOR
# ==========================================================

from models.user import User
from models.enums import UserRole

def generate_employee_number(role):

    if role == UserRole.SUPER_ADMIN:
        prefix = "ADM"

    elif role == UserRole.OPERATIONS_MANAGER:
        prefix = "MGR"

    else:
        prefix = "EMP"

    last_user = (
        User.query
        .filter(
            User.employee_number.like(f"{prefix}%")
        )
        .order_by(User.id.desc())
        .first()
    )

    if last_user:

        last = int(last_user.employee_number.replace(prefix, ""))

        number = last + 1

    else:

        number = 1

    return f"{prefix}{number:04d}"


# ==========================================================
# VALIDATION HELPERS
# ==========================================================

def email_exists(email):

    return User.query.filter_by(
        email=email.lower().strip()
    ).first() is not None


def employee_number_exists(employee_number):

    return User.query.filter_by(
        employee_number=employee_number
    ).first() is not None


# ==========================================================
# ROLE FILTERS
# ==========================================================

def get_users_by_role(role):

    return User.query.filter_by(
        role=role
    ).order_by(
        User.first_name.asc()
    ).all()


# ==========================================================
# DEPARTMENT FILTERS
# ==========================================================

def get_users_by_department(department_id):

    return User.query.filter_by(
        department_id=department_id
    ).order_by(
        User.first_name.asc()
    ).all()


def get_managers_by_department(department_id):

    return User.query.filter(

        User.department_id == department_id,

        User.role == UserRole.OPERATIONS_MANAGER,

        User.is_active

    ).order_by(

        User.first_name,

        User.last_name

    ).all()


# ==========================================================
# RECENT USERS
# ==========================================================

def recent_users(limit=10):

    return User.query.order_by(

        User.created_at.desc()

    ).limit(limit).all()


# ==========================================================
# LOGIN REPORTS
# ==========================================================

def recently_logged_in(limit=10):

    return User.query.filter(

        User.last_login.isnot(None)

    ).order_by(

        User.last_login.desc()

    ).limit(limit).all()


# ==========================================================
# DASHBOARD HELPERS
# ==========================================================

def total_users():

    return User.query.count()


def total_managers():

    return User.query.filter_by(

        role=UserRole.OPERATIONS_MANAGER

    ).count()


def total_employees():

    return User.query.filter_by(

        role=UserRole.EMPLOYEE

    ).count()


def total_super_admins():

    return User.query.filter_by(

        role=UserRole.SUPER_ADMIN

    ).count()


def total_active_users():

    return User.query.filter_by(

        status=UserStatus.ACTIVE

    ).count()


def total_locked_users():

    return User.query.filter_by(

        status=UserStatus.LOCKED

    ).count()


def total_inactive_users():

    return User.query.filter_by(

        status=UserStatus.INACTIVE

    ).count()


# ==========================================================
# USER DASHBOARD CARDS
# ==========================================================

def dashboard_cards():

    return {

        "total_users": total_users(),

        "super_admins": total_super_admins(),

        "managers": total_managers(),

        "employees": total_employees(),

        "active": total_active_users(),

        "inactive": total_inactive_users(),

        "locked": total_locked_users()

    }