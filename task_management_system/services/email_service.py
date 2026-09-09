from html import escape

from flask import current_app
from flask_mail import Message

from extensions import mail
from services.auth_service import RESET_TOKEN_TTL


class EmailService:

    @staticmethod
    def send(to, subject, body, html=None):
        """`body` is the plain-text part and is always required — it is what
        gets logged when delivery is disabled, and what clients that refuse
        HTML fall back to. `html` is an optional richer version of the same
        message, never a different one."""

        if not current_app.config.get("MAIL_SERVER"):
            current_app.logger.info(
                "[email disabled — MAIL_SERVER not configured] To: %s | Subject: %s\n%s",
                to, subject, body,
            )
            return False

        try:
            mail.send(Message(subject=subject, recipients=[to], body=body, html=html))
            return True
        except Exception as exc:  # SMTP misconfig shouldn't 500 the request
            current_app.logger.error("Failed to send email to %s: %s", to, exc)
            return False

    @staticmethod
    def send_notification(recipient, title, message, action_url=None):
        """The email counterpart of an in-app notification. Called from
        NotificationService.notify so the two always carry the same words —
        the subject is the notification's title, the body its message, and
        neither is composed twice in two places.

        Best-effort by design: send() already swallows SMTP failures and
        no-ops when MAIL_SERVER is unconfigured, so a mail problem can
        never cost someone the in-app record, which is the durable one."""

        if not recipient or not recipient.email:
            return False

        greeting = f"Hello {recipient.first_name}," if recipient.first_name else "Hello,"

        lines = [greeting, "", message]

        if action_url:
            lines += ["", action_url]

        html_action = (
            f'<p><a href="{escape(action_url)}">{escape(action_url)}</a></p>'
            if action_url else ""
        )

        html = f"""\
<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5;color:#1f2937">
  <p>{escape(greeting)}</p>
  <p><strong>{escape(title)}</strong></p>
  <p>{escape(message)}</p>
  {html_action}
</div>"""

        return EmailService.send(
            to=recipient.email,
            subject=f"{current_app.config.get('APP_NAME')} — {title}",
            body="\n".join(lines),
            html=html,
        )

    @staticmethod
    def send_password_reset(user, raw_token, reason, closing=None):
        """The one place a raw reset token becomes the email a user actually
        receives. Every route that issues a link — self-service forgot-password,
        an administrator's reset, an administrator changing the account's email
        address — goes through here so the token, the link and the stated
        expiry can never drift apart between them.

        The token is shown on its own, in bold, because the reset page asks the
        user to paste it into a field rather than reading it from the URL. The
        link is offered as well for clients that make it clickable.

        `reason` is the single line explaining why the message arrived."""

        frontend_origin = (current_app.config.get("CORS_ORIGINS") or ["http://localhost:5173"])[0]
        reset_link = f"{frontend_origin}/reset-password?token={raw_token}"

        # Stated in one place, derived from the constant that actually governs
        # expiry, so the wording cannot outlive a change to the TTL.
        minutes = max(1, round(RESET_TOKEN_TTL.total_seconds() / 60))
        expiry = f"This token expires in {minutes} minute{'s' if minutes != 1 else ''}."

        lines = [
            f"Hello {user.first_name},",
            "",
            reason,
            "",
            "Your reset token:",
            "",
            f"    {raw_token}",
            "",
            "Paste it into the “Reset token” field on the reset page:",
            reset_link,
            "",
            expiry,
        ]

        if closing:
            lines += ["", closing]

        token_html = escape(raw_token)
        link_html = escape(reset_link)

        html = f"""\
<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5;color:#1f2937">
  <p>Hello {escape(user.first_name)},</p>
  <p>{escape(reason)}</p>
  <p style="margin-bottom:6px">Your reset token:</p>
  <p style="margin-top:0">
    <strong style="display:inline-block;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
                   font-size:17px;letter-spacing:.5px;word-break:break-all;
                   background:#f3f4f6;border:1px solid #d1d5db;border-radius:6px;padding:10px 14px">
      {token_html}
    </strong>
  </p>
  <p>Paste it into the &ldquo;Reset token&rdquo; field on the reset page:<br>
    <a href="{link_html}">{link_html}</a>
  </p>
  <p><strong>{escape(expiry)}</strong></p>
  {f"<p>{escape(closing)}</p>" if closing else ""}
</div>"""

        return EmailService.send(
            to=user.email,
            subject=f"{current_app.config.get('APP_NAME')} — Password Reset",
            body="\n".join(lines),
            html=html,
        )
