from threading import Thread

from flask import (
    current_app,
    render_template
)

from flask_mail import Message

from extensions import mail


# ==========================================================
# INTERNAL SENDER
# ==========================================================

def _dispatch(app, message):

    with app.app_context():

        try:

            mail.send(message)

            app.logger.info(
                "Email sent to %s | %s",
                ", ".join(message.recipients),
                message.subject
            )

        except Exception as error:

            # SMTP problems must never break the request
            app.logger.error(
                "Failed to send email to %s | %s | %s",
                ", ".join(message.recipients),
                message.subject,
                error
            )


# ==========================================================
# PUBLIC SENDER
# ==========================================================

def send_email(
    recipients,
    subject,
    text_body,
    html_body=None,
    async_send=True
):

    if isinstance(recipients, str):
        recipients = [recipients]

    recipients = [
        address for address in recipients
        if address
    ]

    if not recipients:

        current_app.logger.warning(
            "Email skipped - no recipient | %s",
            subject
        )

        return False

    if not current_app.config.get("MAIL_SERVER"):

        current_app.logger.info(
            "Email disabled - MAIL_SERVER not configured | To: %s | %s\n%s",
            ", ".join(recipients),
            subject,
            text_body
        )

        return False

    message = Message(
        subject=subject,
        recipients=recipients,
        body=text_body,
        html=html_body,
        sender=current_app.config.get("MAIL_DEFAULT_SENDER")
    )

    app = current_app._get_current_object()

    if async_send:

        Thread(
            target=_dispatch,
            args=(app, message),
            daemon=True
        ).start()

        return True

    _dispatch(app, message)

    return True


# ==========================================================
# TASK ASSIGNED NOTIFICATION
# ==========================================================

def send_task_assigned_email(task):

    employee = task.employee

    if not employee or not employee.email:

        current_app.logger.warning(
            "Task %s assigned notification skipped - employee has no email.",
            task.id
        )

        return False

    app_name = current_app.config.get("APP_NAME")

    base_url = current_app.config.get("APP_BASE_URL", "").rstrip("/")

    task_url = f"{base_url}/assigned-tasks/{task.id}"

    context = {
        "task": task,
        "employee": employee,
        "manager": task.manager,
        "app_name": app_name,
        "task_url": task_url
    }

    return send_email(

        recipients=employee.email,

        subject=f"{app_name} - New Task Assigned: {task.title}",

        text_body=render_template(
            "emails/task_assigned.txt",
            **context
        ),

        html_body=render_template(
            "emails/task_assigned.html",
            **context
        )

    )
