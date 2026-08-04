from flask import Flask

from config import Config

from extensions import (
    db,
    migrate,
    login_manager,
    mail
)
from models.user import User
from models.department import Department
from models.weekly_plan import WeeklyPlan
from models.activity import Activity
from models.assigned_task import AssignedTask
from models.notification import Notification
from models.enums import (
    UserRole,
    UserStatus
)

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp


app = Flask(__name__)

app.config.from_object(Config)


# =====================================================
# Initialize Extensions
# =====================================================

db.init_app(app)

migrate.init_app(app, db)

login_manager.init_app(app)

mail.init_app(app)


# =====================================================
# Flask Login
# =====================================================

login_manager.login_view = "auth.login"

login_manager.login_message = "Please log in to continue."

login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):

    return User.query.get(int(user_id))


# =====================================================
# Register Blueprints
# =====================================================

app.register_blueprint(auth_bp)

app.register_blueprint(dashboard_bp)


# =====================================================
# Seed Default Users
# =====================================================

def create_default_users():

    if User.query.count() > 0:
        return

    print("Creating default TPMS users...")

    users = [

        {
            "employee_number": "SA001",
            "first_name": "System",
            "last_name": "Administrator",
            "email": "admin@tpms.com",
            "phone": "0700000001",
            "role": UserRole.SUPER_ADMIN
        },

        {
            "employee_number": "OM001",
            "first_name": "Operations",
            "last_name": "Manager",
            "email": "manager@tpms.com",
            "phone": "0700000002",
            "role": UserRole.OPERATIONS_MANAGER
        },

        {
            "employee_number": "EMP001",
            "first_name": "John",
            "last_name": "Employee",
            "email": "employee@tpms.com",
            "phone": "0700000003",
            "role": UserRole.EMPLOYEE
        }

    ]

    for data in users:

        user = User(

            employee_number=data["employee_number"],

            first_name=data["first_name"],

            last_name=data["last_name"],

            email=data["email"],

            phone=data["phone"],

            role=data["role"],

            status=UserStatus.ACTIVE

        )

        user.set_password("123456")

        db.session.add(user)

    db.session.commit()

    print("=" * 60)
    print("Default Users Created Successfully")
    print("=" * 60)
    print("SUPER ADMIN")
    print("Email: admin@tpms.com")
    print("Password: 123456")
    print()

    print("OPERATIONS MANAGER")
    print("Email: manager@tpms.com")
    print("Password: 123456")
    print()

    print("EMPLOYEE")
    print("Email: employee@tpms.com")
    print("Password: 123456")
    print("=" * 60)


# =====================================================
# Create Database
# =====================================================

with app.app_context():

    db.create_all()

    create_default_users()


# =====================================================
# Run
# =====================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )