import json
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime
from html import escape

from flask import current_app
from flask_mail import Message

from extensions import mail
from services.auth_service import RESET_TOKEN_TTL

# Mail leaves over HTTPS in production because outbound SMTP does not leave
# at all: a connect to port 587 from the deployed host times out at the
# network level (TimeoutError: [Errno 110]), which is how the platform's
# free tier discourages spam. Identical credentials connect in 1.6s from a
# developer machine, so this is a property of where the code runs, not of
# the code or the mailbox.
#
# SMTP is kept as the fallback transport rather than deleted: it is what
# works locally, needs no third-party account, and its console-logging
# branch is how the reset link is read when nothing is configured at all.
RESEND_ENDPOINT = "https://api.resend.com/emails"

# Explicit, and short. An unbounded network call inside a request is what
# produced the original 500 here, by outlasting gunicorn's worker timeout.
RESEND_TIMEOUT_SECONDS = 15

# Delivery now happens on a background thread, so a failure is invisible to
# whoever triggered it — the request succeeded, and only the platform log
# holds the reason. That log is not always reachable, which is exactly the
# situation this exists for: the last outcome is kept in memory and reported
# by /health, so "it says sent but nothing arrives" is diagnosable from
# outside the box.
#
# In-process and per-worker: it survives no restart and is not a record of
# anything. It is a diagnostic, not a mail log.
_last_delivery = {"at": None, "ok": None, "error": None}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _redact(text):
    """/health is public, so an address must never reach it."""
    return _EMAIL_RE.sub("<address>", str(text))[:300]


def last_delivery_status():
    return dict(_last_delivery)


def active_transport():
    """Which way mail leaves, decided by what is configured. Reported by
    /health so "which path did that send take" is never a guess."""

    if current_app.config.get("RESEND_API_KEY"):
        return "resend"

    if current_app.config.get("MAIL_SERVER"):
        return "smtp"

    return "disabled"


def _record(ok, error=None):
    _last_delivery.update(
        at=datetime.utcnow().isoformat(timespec="seconds"),
        ok=ok,
        error=error,
    )


def _send_via_resend(api_key, sender, to, subject, body, html):
    """One HTTPS POST. Raises on any non-2xx so the caller records it."""

    payload = {"from": sender, "to": [to], "subject": subject, "text": body}

    if html:
        payload["html"] = html

    request = urllib.request.Request(
        RESEND_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=RESEND_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


class EmailService:

    @staticmethod
    def send(to, subject, body, html=None):
        """`body` is the plain-text part and is always required — it is what
        gets logged when delivery is disabled, and what clients that refuse
        HTML fall back to. `html` is an optional richer version of the same
        message, never a different one."""

        transport = active_transport()

        if transport == "disabled":
            current_app.logger.info(
                "[email disabled — no RESEND_API_KEY or MAIL_SERVER] To: %s | Subject: %s\n%s",
                to, subject, body,
            )
            return False

        # Whichever transport, the network call happens off the request
        # thread. Waiting inline is what produced the original 500: a
        # connect that never completes outlasts gunicorn's 30s worker
        # timeout, and the worker is killed before any except clause can
        # run — so the caller gets a 500 from a request whose real work had
        # already committed.
        app = current_app._get_current_object()
        api_key = current_app.config.get("RESEND_API_KEY")
        sender = current_app.config.get("MAIL_DEFAULT_SENDER")

        # Built here, while the request context still exists: a flask_mail
        # Message resolves its sender from it.
        message = None if transport == "resend" else Message(
            subject=subject, recipients=[to], body=body, html=html
        )

        def deliver():
            with app.app_context():
                try:
                    if transport == "resend":
                        _send_via_resend(api_key, sender, to, subject, body, html)
                    else:
                        mail.send(message)

                    _record(ok=True)

                except urllib.error.HTTPError as exc:
                    # Resend puts the actual reason in the body — an
                    # unverified sending domain or a bad key reads as a bare
                    # 40x otherwise, which says nothing.
                    try:
                        detail = exc.read().decode("utf-8", "replace")
                    except Exception:
                        detail = ""
                    app.logger.error("Resend rejected mail to %s: %s %s", to, exc.code, detail)
                    _record(ok=False, error=f"HTTP {exc.code}: {_redact(detail)}")

                except Exception as exc:
                    app.logger.error("Failed to send email to %s: %s", to, exc)
                    _record(ok=False, error=f"{type(exc).__name__}: {_redact(exc)}")

        threading.Thread(target=deliver, name=f"mail:{to}", daemon=True).start()

        # "Handed off", not "delivered" — nobody can know the latter yet, and
        # no caller should block to find out.
        return True

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
        # escape() raises on None. first_name is NOT NULL today, but this
        # function must not be the thing that 500s if that ever stops being
        # true — the same guard the greeting in send_notification already has.
        name_html = escape(user.first_name or "")

        html = f"""\
<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5;color:#1f2937">
  <p>Hello {name_html},</p>
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
