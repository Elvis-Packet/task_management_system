from flask import request
from user_agents import parse as parse_user_agent

from extensions import db
from models.audit_log import AuditLog
from models.login_history import LoginHistory


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def _client_agent():
    ua_string = request.headers.get("User-Agent", "")
    try:
        ua = parse_user_agent(ua_string)
        browser = f"{ua.browser.family} {ua.browser.version_string}".strip()
        device = ua.device.family if ua.device.family != "Other" else (
            "Mobile" if ua.is_mobile else "Tablet" if ua.is_tablet else "Desktop"
        )
        os_name = f"{ua.os.family} {ua.os.version_string}".strip()
    except Exception:
        browser, device, os_name = ua_string[:120], "Unknown", "Unknown"
    return browser, device, os_name


class AuditService:

    @staticmethod
    def log_action(user, action, description="", target_type=None, target_id=None):
        browser, device, _os_name = _client_agent()

        entry = AuditLog(
            user_id=user.id if user else None,
            action=action.value if hasattr(action, "value") else action,
            description=description,
            ip_address=_client_ip(),
            device=device,
            browser=browser,
            target_type=target_type,
            target_id=target_id,
        )

        db.session.add(entry)
        db.session.commit()

        return entry

    @staticmethod
    def record_login(user, success, failure_reason=None):
        browser, device, os_name = _client_agent()

        entry = LoginHistory(
            user_id=user.id,
            ip_address=_client_ip(),
            browser=browser,
            operating_system=os_name,
            device=device,
            login_successful=success,
            failure_reason=failure_reason,
        )

        db.session.add(entry)
        db.session.commit()

        return entry

    @staticmethod
    def record_logout(user):
        last = (
            LoginHistory.query.filter_by(user_id=user.id, logout_time=None)
            .order_by(LoginHistory.login_time.desc())
            .first()
        )

        if last:
            from datetime import datetime

            last.logout_time = datetime.utcnow()
            db.session.commit()
