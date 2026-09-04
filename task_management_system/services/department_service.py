import re

from extensions import db
from models.department import Department


def _generate_code(name):
    base = re.sub(r"[^A-Z0-9]", "", name.upper())[:4] or "DEPT"

    code = base
    suffix = 1
    while Department.query.filter_by(department_code=code).first():
        suffix += 1
        code = f"{base}{suffix}"

    return code


class DepartmentService:

    @staticmethod
    def create(data):
        name = (data.get("department_name") or data.get("name") or "").strip()
        code = (data.get("department_code") or "").strip().upper() or _generate_code(name)

        department = Department(
            department_name=name,
            department_code=code,
            description=data.get("description"),
            budget=data.get("budget") or 0,
        )

        db.session.add(department)
        db.session.commit()

        return department

    @staticmethod
    def update(department, data):
        name = data.get("department_name") or data.get("name")
        if name:
            department.department_name = name.strip()

        if data.get("department_code"):
            department.department_code = data["department_code"].strip().upper()

        if "description" in data:
            department.description = data.get("description")

        if "budget" in data:
            department.budget = data.get("budget") or 0

        db.session.commit()

        return department

    @staticmethod
    def delete(department):
        db.session.delete(department)
        db.session.commit()
