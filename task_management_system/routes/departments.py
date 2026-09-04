from flask import Blueprint, request

from extensions import db
from models.department import Department
from models.enums import UserRole, AuditAction
from services.department_service import DepartmentService
from services.audit_service import AuditService
from utils.response import ok, err
from utils.rbac import require_roles, require_auth, get_current_user
from utils.serializers import serialize_department
from utils.pagination import paginate

departments_bp = Blueprint("departments", __name__)


@departments_bp.get("")
@require_auth
def list_departments():
    query = Department.query.order_by(Department.department_name.asc())
    return ok(paginate(query, serialize_department))


@departments_bp.get("/<int:department_id>")
@require_auth
def get_department(department_id):
    department = Department.query.get(department_id)

    if not department:
        return err("Department not found.", 404)

    return ok({"department": serialize_department(department)})


@departments_bp.post("")
@require_roles(UserRole.SUPER_ADMIN)
def create_department():
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

    name = (data.get("department_name") or data.get("name") or "").strip()

    if not name:
        return err("Department name is required.", 422, errors={"department_name": "required"})

    filters = [Department.department_name == name]
    if data.get("department_code"):
        filters.append(Department.department_code == data["department_code"].strip().upper())

    if Department.query.filter(db.or_(*filters)).first():
        return err("A department with this name or code already exists.", 409)

    department = DepartmentService.create(data)

    AuditService.log_action(current_user, AuditAction.CREATE, f"Created department {department.department_name}.")

    return ok({"department": serialize_department(department)}, message="Department created.", status=201)


@departments_bp.patch("/<int:department_id>")
@require_roles(UserRole.SUPER_ADMIN)
def update_department(department_id):
    current_user = get_current_user()
    department = Department.query.get(department_id)

    if not department:
        return err("Department not found.", 404)

    data = request.get_json(silent=True) or {}
    department = DepartmentService.update(department, data)

    AuditService.log_action(current_user, AuditAction.UPDATE, f"Updated department {department.department_name}.")

    return ok({"department": serialize_department(department)}, message="Department updated.")


@departments_bp.delete("/<int:department_id>")
@require_roles(UserRole.SUPER_ADMIN)
def delete_department(department_id):
    current_user = get_current_user()
    department = Department.query.get(department_id)

    if not department:
        return err("Department not found.", 404)

    active_members = [u for u in department.users if u.deleted_at is None]

    if active_members:
        return err(
            f"Cannot delete a department with {len(active_members)} assigned user(s). Reassign them first.",
            409,
        )

    name = department.department_name

    DepartmentService.delete(department)

    AuditService.log_action(current_user, AuditAction.DELETE, f"Deleted department {name}.")

    return ok(message="Department deleted.")
