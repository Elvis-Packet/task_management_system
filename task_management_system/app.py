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
from models.leave_type import LeaveType
from models.leave_request import LeaveRequest, LeaveAttachment
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
from routes.leave import leave_bp


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
app.register_blueprint(leave_bp, url_prefix=f"{API_PREFIX}/leave")


@app.get(f"{API_PREFIX}/health")
def health():
    from services.email_service import last_delivery_status

    """Reports which build is actually serving, not just that something is.

    Without this, "is the fix deployed?" is unanswerable from outside, and
    a silently failing build looks identical to a bug in the new code —
    the platform keeps serving the last good deploy either way. commit
    comes from RENDER_GIT_COMMIT, which Render injects; mail_configured
    distinguishes "email disabled, logging instead" from a real send
    attempt, which is the difference between two very different faults."""

    return jsonify({
        "success": True,
        "message": "API is healthy",
        "data": {
            "app": Config.APP_NAME,
            "version": Config.APP_VERSION,
            "commit": (os.getenv("RENDER_GIT_COMMIT") or "local")[:7],
            "mail_configured": bool(Config.MAIL_SERVER),
            "mail_settings": {
                # Presence only, never values. Missing MAIL_DEFAULT_SENDER is
                # a silent killer: Flask-Mail refuses a message with no
                # sender, and with delivery on a thread that refusal is
                # invisible to the caller.
                "server": Config.MAIL_SERVER or None,
                "port": Config.MAIL_PORT,
                "use_tls": Config.MAIL_USE_TLS,
                "use_ssl": Config.MAIL_USE_SSL,
                "username_set": bool(Config.MAIL_USERNAME),
                "password_set": bool(Config.MAIL_PASSWORD),
                "default_sender_set": bool(Config.MAIL_DEFAULT_SENDER),
            },
            "last_mail_delivery": last_delivery_status(),
        },
    })


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
    Matched on employee_number, never duplicated — no throwaway/demo accounts
    are seeded.

    One account per role that cannot be created from inside the app: the
    Super Admin (who creates everyone else), the single central Operational
    Manager, and HR. Staff are always created through User Management.

    The employee number, not the address, is what identifies a bootstrap
    account, so changing a SEED_*_EMAIL in the environment moves the existing
    account to the new address on the next boot. Matching on email instead
    would leave an already-seeded database stranded on the old address: the
    lookup misses, the insert then collides with the unique employee_number,
    and the caller's except swallows it as "database not ready yet".

    Only the address is reconciled. Passwords are left alone once the row
    exists, so a password the holder has since changed in-app is never
    silently reset back to the environment value on restart."""

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

    changed_any = False

    for data in seeds:

        if not data["email"] or not data["password"]:
            continue

        email = data["email"].strip().lower()

        existing = User.query.filter_by(employee_number=data["employee_number"]).first()

        if existing:

            if existing.email == email:
                continue

            # Somebody else already holds the new address — taking it would
            # break the unique index, so leave the account as it is and say
            # so rather than failing the whole boot-time seed.
            if User.query.filter_by(email=email).first():
                print(
                    f"Cannot move {data['employee_number']} to {email}: "
                    "another user already has that email"
                )
                continue

            print(f"Moved {data['employee_number']} from {existing.email} to {email}")

            existing.email = email

            changed_any = True

            continue

        # No account under this employee number yet, but the address may
        # already belong to a user created through User Management.
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

        changed_any = True

        print(f"Seeded {data['role'].value} account: {email}")

    if changed_any:
        db.session.commit()


def create_seed_leave_types():
    """The starting leave catalogue, taken from the company's own leave
    application form. Idempotent and matched on code, exactly like the
    account seeds above — HR owns the list from here on, and nothing in the
    code refers to any of these types by name."""

    from services.leave_service import LeaveTypeService

    created = LeaveTypeService.seed_defaults()

    if created:
        print(f"Seeded {created} leave type(s)")


with app.app_context():
    try:
        create_seed_accounts()
        create_seed_leave_types()
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
