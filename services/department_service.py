from extensions import db

from models.department import Department


# ==========================================================
# CREATE DEPARTMENT
# ==========================================================

def create_department(
    department_name,
    department_code,
    description=None
):
    """
    Creates a new department.
    """

    department_name = department_name.strip()
    department_code = department_code.strip().upper()

    existing_name = Department.query.filter_by(
        department_name=department_name
    ).first()

    if existing_name:
        return (
            False,
            "A department with this name already exists."
        )

    existing_code = Department.query.filter_by(
        department_code=department_code
    ).first()

    if existing_code:
        return (
            False,
            "A department with this code already exists."
        )

    department = Department(

        department_name=department_name,

        department_code=department_code,

        description=description

    )

    db.session.add(department)

    db.session.commit()

    return (
        True,
        "Department created successfully."
    )


# ==========================================================
# GET ALL DEPARTMENTS
# ==========================================================

def get_departments():

    return Department.query.order_by(
        Department.department_name.asc()
    ).all()


# ==========================================================
# GET ONE DEPARTMENT
# ==========================================================

def get_department(department_id):

    return Department.query.get_or_404(
        department_id
    )


# ==========================================================
# UPDATE DEPARTMENT
# ==========================================================

def update_department(

    department,

    department_name,

    department_code,

    description

):

    department_name = department_name.strip()

    department_code = department_code.strip().upper()

    duplicate_name = Department.query.filter(

        Department.department_name == department_name,

        Department.id != department.id

    ).first()

    if duplicate_name:

        return (
            False,
            "Department name already exists."
        )

    duplicate_code = Department.query.filter(

        Department.department_code == department_code,

        Department.id != department.id

    ).first()

    if duplicate_code:

        return (
            False,
            "Department code already exists."
        )

    department.department_name = department_name

    department.department_code = department_code

    department.description = description

    db.session.commit()

    return (
        True,
        "Department updated successfully."
    )


# ==========================================================
# ACTIVATE
# ==========================================================

def activate_department(department):

    department.active = True

    db.session.commit()

    return (
        True,
        "Department activated."
    )


# ==========================================================
# DEACTIVATE
# ==========================================================

def deactivate_department(department):

    department.active = False

    db.session.commit()

    return (
        True,
        "Department deactivated."
    )


# ==========================================================
# DELETE
# ==========================================================

def delete_department(department):

    if department.users:

        return (
            False,
            "Cannot delete a department that has users."
        )

    db.session.delete(department)

    db.session.commit()

    return (
        True,
        "Department deleted successfully."
    )


# ==========================================================
# SEARCH
# ==========================================================

def search_departments(search):

    return Department.query.filter(

        Department.department_name.ilike(
            f"%{search}%"
        )

    ).order_by(

        Department.department_name

    ).all()


# ==========================================================
# DASHBOARD STATS
# ==========================================================

def department_statistics():

    total_departments = Department.query.count()

    active_departments = Department.query.filter_by(
        active=True
    ).count()

    inactive_departments = Department.query.filter_by(
        active=False
    ).count()

    return {

        "total": total_departments,

        "active": active_departments,

        "inactive": inactive_departments

    }