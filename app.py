from flask import Flask

from config import Config

from extensions import (
    db,
    migrate,
    login_manager,
    mail,
    
)


from models.user import User
from models.department import Department
from models.weekly_plan import WeeklyPlan
from models.activity import Activity
from models.assigned_task import AssignedTask
from models.notification import Notification
from models.performance_summary import PerformanceSummary
from models.enums import (
    UserRole,
    UserStatus
)

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.manager import manager_bp
from routes.admin import admin_bp
from routes.weekly_plan import weekly_plan_bp
from routes.department import department_bp
from routes.user import user_bp
from routes.manager_review import manager_review_bp
from routes.assigned_task import assigned_task_bp
from routes.manager_review import manager_review_bp
from routes.manager_review import manager_review_bp
from routes.task_review import task_review_bp
from routes.performance_routes import performance_bp

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
app.register_blueprint(department_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(manager_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(weekly_plan_bp)
app.register_blueprint(user_bp)
app.register_blueprint(manager_review_bp)
app.register_blueprint(assigned_task_bp)
app.register_blueprint(
    task_review_bp
)
app.register_blueprint(
    performance_bp
)

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
        },

        {
            "employee_number": "SA0011",
            "first_name": "Systemo",
            "last_name": "Administratoro",
            "email": "admino@tpms.com",
            "phone": "0700000011",
            "role": UserRole.SUPER_ADMIN
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
    print("Email: adminA@tpms.com")
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


from flask import jsonify
from sqlalchemy import text
from extensions import db


@app.route("/migrate-users-table")
def migrate_users_table():

    statements = [

        """
        ALTER TABLE users
        ADD COLUMN manager_id INTEGER
        """,

        """
        ALTER TABLE users
        ADD COLUMN failed_login_attempts INTEGER
        DEFAULT 0
        """,

        """
        ALTER TABLE users
        ADD COLUMN password_changed_at DATETIME
        """,

        """
        ALTER TABLE users
        ADD COLUMN last_activity DATETIME
        """,

        """
        ALTER TABLE users
        ADD COLUMN last_ip_address VARCHAR(50)
        """,

        """
        ALTER TABLE users
        ADD COLUMN last_device VARCHAR(150)
        """,

        """
        ALTER TABLE users
        ADD COLUMN last_browser VARCHAR(150)
        """,

        """
        ALTER TABLE users
        ADD COLUMN is_first_login BOOLEAN
        DEFAULT 1
        """

    ]

    added = []

    skipped = []

    with db.engine.begin() as connection:

        for sql in statements:

            column = sql.split("ADD COLUMN")[1].strip().split()[0]

            try:

                connection.execute(text(sql))

                added.append(column)

            except Exception as e:

                skipped.append({
                    "column": column,
                    "reason": str(e)
                })

    return jsonify({

        "status": "completed",

        "added": added,

        "skipped": skipped

    })

    
with app.app_context():

    db.create_all()

    create_default_users()


from extensions import db

from models.department import Department


# @app.route("/rebuild-assignment_table")
# def rebuild_assigned_task_table():

#     AssignedTask.__table__.drop(
#         db.engine,
#         checkfirst=True
#     )

#     AssignedTask.__table__.create(
#         db.engine,
#         checkfirst=True
#     )

#     return "AssignedTask table recreated successfully."

# =====================================================
# Run
# =====================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )