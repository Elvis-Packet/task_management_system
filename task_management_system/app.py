import os

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from config import Config

from extensions import (
    db,
    migrate,
    mail,
    jwt,
    bcrypt,
    cors
)

# Models — imported so db.create_all()/migrations see every table.
from models.user import User
from models.department import Department
from models.weekly_plan import WeeklyPlan
from models.activity import Activity
from models.assigned_task import AssignedTask
from models.task_progress_update import TaskProgressUpdate
from models.notification import Notification
from models.performance import Performance
from models.audit_log import AuditLog
from models.login_history import LoginHistory
from models.comment import Comment
from models.generated_report import GeneratedReport
from models.task_exception import TaskException
from models.task_query import TaskQuery
from models.enums import UserRole, UserStatus

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.users import users_bp
from routes.departments import departments_bp
from routes.assigned_task import tasks_bp
from routes.weekly_plans import plans_bp
from routes.notifications import notifications_bp
from routes.reports import reports_bp
from routes.audit import audit_bp
from routes.queries import queries_bp
from routes.hr import hr_bp


app = Flask(__name__)

app.config.from_object(Config)


# =====================================================
# Initialize Extensions
# =====================================================

db.init_app(app)

migrate.init_app(app, db)

mail.init_app(app)

jwt.init_app(app)

bcrypt.init_app(app)

cors.init_app(
    app,
    resources={r"/api/*": {"origins": Config.CORS_ORIGINS}},
    supports_credentials=False,
)


# =====================================================
# JWT error handlers — keep the JSON envelope consistent
# even for auth failures raised by flask-jwt-extended itself.
# =====================================================

def _jwt_error_response(message, status):
    return jsonify({"success": False, "message": message, "errors": None}), status


@jwt.unauthorized_loader
def _missing_token(reason):
    return _jwt_error_response("Authentication token is missing.", 401)


@jwt.invalid_token_loader
def _invalid_token(reason):
    return _jwt_error_response("Authentication token is invalid.", 401)


@jwt.expired_token_loader
def _expired_token(jwt_header, jwt_payload):
    return _jwt_error_response("Authentication token has expired.", 401)


@jwt.revoked_token_loader
def _revoked_token(jwt_header, jwt_payload):
    return _jwt_error_response("Authentication token has been revoked.", 401)


# =====================================================
# Register Blueprints
# =====================================================

API_PREFIX = "/api/v1"

app.register_blueprint(auth_bp, url_prefix=f"{API_PREFIX}/auth")
app.register_blueprint(dashboard_bp, url_prefix=f"{API_PREFIX}/dashboard")
app.register_blueprint(users_bp, url_prefix=f"{API_PREFIX}/users")
app.register_blueprint(departments_bp, url_prefix=f"{API_PREFIX}/departments")
app.register_blueprint(tasks_bp, url_prefix=f"{API_PREFIX}/tasks")
app.register_blueprint(plans_bp, url_prefix=f"{API_PREFIX}/plans")
app.register_blueprint(notifications_bp, url_prefix=f"{API_PREFIX}/notifications")
app.register_blueprint(reports_bp, url_prefix=f"{API_PREFIX}/reports")
app.register_blueprint(audit_bp, url_prefix=f"{API_PREFIX}/audit")
app.register_blueprint(queries_bp, url_prefix=f"{API_PREFIX}/queries")
app.register_blueprint(hr_bp, url_prefix=f"{API_PREFIX}/hr")


@app.get(f"{API_PREFIX}/health")
def health():
    return jsonify({"success": True, "message": "API is healthy", "data": {"app": Config.APP_NAME}})


# =====================================================
# Generic error handlers
# =====================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "message": "Resource not found.", "errors": None}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"success": False, "message": "Method not allowed.", "errors": None}), 405


@app.errorhandler(500)
def server_error(e):
    return jsonify({"success": False, "message": "Internal server error.", "errors": None}), 500


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    """Catch-all for any werkzeug HTTPException not covered by a specific
    handler above (400/403/409/422/etc. raised outside utils.response.err) —
    every API error stays JSON, never Flask/Werkzeug's default HTML page."""
    return jsonify({"success": False, "message": e.description or e.name, "errors": None}), e.code


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    """Last-resort net for a genuinely unhandled exception (a real bug). No
    traceback or exception detail ever reaches the client — only logged
    server-side — so nothing internal ever leaks over the API."""
    app.logger.exception("Unhandled exception")
    return jsonify({"success": False, "message": "Internal server error.", "errors": None}), 500


# =====================================================
# Seed Bootstrap Accounts
# =====================================================

def create_seed_accounts():
    """Idempotently create the real bootstrap accounts from the spec.
    Checked by email, never duplicated — no throwaway/demo accounts are seeded.

    One account per role that cannot be created from inside the app: the
    Super Admin (who creates everyone else), the single central Operational
    Manager, and HR. Staff are always created through User Management."""

    seeds = [
        {
            "employee_number": "SA001",
            "first_name": "Rhoda",
            "last_name": "Muthoni",
            "email": Config.SEED_SUPER_ADMIN_EMAIL,
            "password": Config.SEED_SUPER_ADMIN_PASSWORD,
            "role": UserRole.SUPER_ADMIN,
            "job_title": "System Administrator",
        },
        {
            "employee_number": "OM001",
            "first_name": "Mwangangi",
            "last_name": "M.",
            "email": Config.SEED_MANAGER_EMAIL,
            "password": Config.SEED_MANAGER_PASSWORD,
            "role": UserRole.OPERATIONAL_MANAGER,
            "job_title": "Operational Manager",
        },
        {
            "employee_number": "HR001",
            "first_name": "Survitec",
            "last_name": "Equipment Ltd",
            "email": Config.SEED_HR_EMAIL,
            "password": Config.SEED_HR_PASSWORD,
            "role": UserRole.HR,
            "job_title": "Human Resources",
        },
    ]

    created_any = False

    for data in seeds:

        if not data["email"] or not data["password"]:
            continue

        email = data["email"].strip().lower()

        if User.query.filter_by(email=email).first():
            continue

        user = User(
            employee_number=data["employee_number"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=email,
            role=data["role"],
            job_title=data.get("job_title"),
            status=UserStatus.ACTIVE,
            is_first_login=True,
        )

        user.set_password(data["password"])

        db.session.add(user)

        created_any = True

        print(f"Seeded {data['role'].value} account: {email}")

    if created_any:
        db.session.commit()


with app.app_context():
    try:
        create_seed_accounts()
    except Exception as exc:  # pragma: no cover
        # Tables don't exist yet (e.g. this import is happening as part of
        # `flask db migrate`/`upgrade` before the schema exists). Migrations
        # own schema creation; seeding just no-ops until they've run.
        db.session.rollback()
        print(f"Skipping seed (database not ready yet): {exc}")


# =====================================================
# Run
# =====================================================

if __name__ == "__main__":

    app.run(
        debug=os.getenv("FLASK_DEBUG", "False") == "True",
        port=int(os.getenv("PORT", 5000)),
    )
