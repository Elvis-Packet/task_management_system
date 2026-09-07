from threading import Thread

from flask import current_app, render_template
from flask_mail import Message

from extensions import mail


class EmailService:

    @staticmethod
    def _dispatch(app, message):
        """Runs on a worker thread, so a slow or dead SMTP server never
        holds up the request that triggered it."""

        with app.app_context():
            try:
                mail.send(message)
                app.logger.info(
                    "Email sent to %s | %s",
                    ", ".join(message.recipients), message.subject,
                )
            except Exception as exc:
                app.logger.error(
                    "Failed to send email to %s: %s",
                    ", ".join(message.recipients), exc,
                )

    @staticmethod
    def send(to, subject, body, html=None, async_send=True):
        """`html` and `async_send` are optional so the existing plain-text
        callers (password reset, leave requests) keep working unchanged."""

        recipients = [to] if isinstance(to, str) else [a for a in (to or []) if a]

        if not recipients:
            current_app.logger.warning("Email skipped — no recipient | %s", subject)
            return False

        if not current_app.config.get("MAIL_SERVER"):
            current_app.logger.info(
                "[email disabled — MAIL_SERVER not configured] To: %s | Subject: %s\n%s",
                ", ".join(recipients), subject, body,
            )
            return False

        message = Message(
            subject=subject,
            recipients=recipients,
            body=body,
            html=html,
            sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
        )

        app = current_app._get_current_object()

        if async_send:
            Thread(target=EmailService._dispatch, args=(app, message), daemon=True).start()
            return True

        EmailService._dispatch(app, message)
        return True

    @staticmethod
    def send_tasks_assigned(tasks):
        """One assignment email covering every task just given to a single
        employee — matching how the route layer groups its notifications."""

        tasks = [t for t in tasks if t]

        if not tasks:
            return False

        employee = tasks[0].employee

        if not employee or not employee.email:
            current_app.logger.warning(
                "Assignment email skipped — employee has no address (task %s).",
                tasks[0].id,
            )
            return False

        app_name = current_app.config.get("APP_NAME")
        base_url = current_app.config.get("FRONTEND_BASE_URL", "").rstrip("/")

        context = {
            "tasks": tasks,
            "employee": employee,
            "manager": tasks[0].manager,
            "app_name": app_name,
            "task_url": f"{base_url}/staff/tasks",
        }

        subject = (
            f"{app_name} — New Task Assigned: {tasks[0].title}"
            if len(tasks) == 1
            else f"{app_name} — {len(tasks)} New Tasks Assigned"
        )

        return EmailService.send(
            to=employee.email,
            subject=subject,
            body=render_template("emails/task_assigned.txt", **context),
            html=render_template("emails/task_assigned.html", **context),
        )
