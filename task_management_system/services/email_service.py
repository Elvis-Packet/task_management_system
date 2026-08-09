from flask import current_app
from flask_mail import Message

from extensions import mail


class EmailService:

    @staticmethod
    def send(to, subject, body):
        if not current_app.config.get("MAIL_SERVER"):
            current_app.logger.info(
                "[email disabled — MAIL_SERVER not configured] To: %s | Subject: %s\n%s",
                to, subject, body,
            )
            return False

        try:
            mail.send(Message(subject=subject, recipients=[to], body=body))
            return True
        except Exception as exc:  # SMTP misconfig shouldn't 500 the request
            current_app.logger.error("Failed to send email to %s: %s", to, exc)
            return False
