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

        Best-effort by design: send() already swallows delivery failures and
        no-ops when no transport is configured, so a mail problem can never
        cost someone the in-app record, which is the durable one."""

        if not recipient or not recipient.email:
            return False

        greeting = f"Hello {recipient.first_name}," if recipient.first_name else "Hello,"

        # Callers pass the same path the in-app notification links to, e.g.
        # "/my-leave". That resolves inside the app but means nothing in an
        # inbox, where a bare path is not a link at all — so it is made
        # absolute against the deployed frontend before it goes in an email.
        link = action_url
        if link and link.startswith("/"):
            link = f"{current_app.config['FRONTEND_URL']}{link}"

        lines = [greeting, "", message]

        if link:
            lines += ["", link]

        html_action = (
            f'<p><a href="{escape(link)}">{escape(link)}</a></p>'
            if link else ""
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
    def send_tasks_assigned(tasks):
        """One assignment email covering every task just given to a single
        employee.

        Grouped per employee rather than per task, matching how the route
        layer raises its in-app notifications — laying out somebody's whole
        week produces one email listing five tasks, not five emails.

        Caller passes tasks belonging to one employee; the first one supplies
        the recipient and the assigning manager."""

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
        manager = tasks[0].manager
        task_url = f"{current_app.config['FRONTEND_URL']}/staff/tasks"

        count = len(tasks)
        opening = (
            "A new task has been assigned to you"
            if count == 1
            else f"{count} new tasks have been assigned to you"
        )
        if manager:
            opening += f" by {manager.full_name}"

        def _due(task):
            due = task.due_date.strftime("%d %b %Y")
            if task.due_time:
                due += f" at {task.due_time.strftime('%H:%M')}"
            return due

        def _priority(task):
            return task.priority.value.title() if task.priority else "Normal"

        lines = [f"Hello {employee.full_name},", "", f"{opening}."]

        for task in tasks:
            lines += [
                "",
                "-" * 52,
                f"Title      : {task.title}",
                f"Priority   : {_priority(task)}",
                f"Assigned   : {task.assigned_date.strftime('%d %b %Y')}",
                f"Due        : {_due(task)}",
            ]
            if task.description:
                lines += ["", "Description:", task.description]
            if task.expected_outcome:
                lines += ["", "Expected outcome:", task.expected_outcome]

        lines += [
            "",
            "-" * 52,
            "",
            "Open your tasks here:",
            task_url,
            "",
            "--",
            app_name,
            "This is an automated message, please do not reply.",
        ]

        # Table-per-task, inline-styled: the same construction the other two
        # senders here use, for the same reason — a mail client applies no
        # stylesheet and understands no layout beyond a table.
        row = (
            '<tr><td style="padding:10px 16px;color:#7b8794;width:150px;'
            'border-top:1px solid #f0f2f4;vertical-align:top">{label}</td>'
            '<td style="padding:10px 16px;border-top:1px solid #f0f2f4;'
            'line-height:1.6;color:#3e4c59">{value}</td></tr>'
        )

        cards = []
        for task in tasks:
            rows = [
                '<tr><td colspan="2" style="padding:14px 16px;background:#f7f9fb;'
                'border-bottom:1px solid #e4e7eb"><strong style="font-size:15px">'
                f"{escape(task.title)}</strong></td></tr>",
                row.format(label="Priority", value=escape(_priority(task))),
                row.format(
                    label="Assigned",
                    value=escape(task.assigned_date.strftime("%d %b %Y")),
                ),
                row.format(label="Due", value=f"<strong>{escape(_due(task))}</strong>"),
            ]
            if task.description:
                rows.append(row.format(label="Description", value=escape(task.description)))
            if task.expected_outcome:
                rows.append(
                    row.format(label="Expected outcome", value=escape(task.expected_outcome))
                )

            cards.append(
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"'
                ' style="border:1px solid #e4e7eb;border-radius:6px;font-size:14px;'
                'margin-bottom:14px">' + "".join(rows) + "</table>"
            )

        html = f"""\
<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5;color:#1f2937">
  <p>Hello {escape(employee.full_name)},</p>
  <p>{escape(opening)}. Please review the details below.</p>
  {"".join(cards)}
  <p style="margin:26px 0 8px">
    <a href="{escape(task_url)}"
       style="display:inline-block;background:#0b3d63;color:#ffffff;text-decoration:none;
              padding:12px 24px;border-radius:6px;font-size:14px;font-weight:600">
      View my tasks
    </a>
  </p>
  <p style="margin:16px 0 0;font-size:12px;color:#9aa5b1;word-break:break-all">
    Or paste this link into your browser: {escape(task_url)}
  </p>
  <p style="margin-top:20px;font-size:12px;color:#9aa5b1">
    This is an automated message from {escape(app_name or "")}. Please do not reply.
  </p>
</div>"""

        subject = (
            f"{app_name} — New Task Assigned: {tasks[0].title}"
            if count == 1
            else f"{app_name} — {count} New Tasks Assigned"
        )

        return EmailService.send(
            to=employee.email,
            subject=subject,
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

        reset_link = f"{current_app.config['FRONTEND_URL']}/reset-password?token={raw_token}"

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
