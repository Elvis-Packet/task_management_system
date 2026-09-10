from datetime import datetime


def timeago(value):
    """
    Renders a UTC datetime as a short relative string
    for the notification dropdown and list.
    """

    if not value:
        return ""

    seconds = (datetime.utcnow() - value).total_seconds()

    if seconds < 0:
        return "Just now"

    if seconds < 60:
        return "Just now"

    minutes = int(seconds // 60)

    if minutes < 60:
        return f"{minutes} min ago"

    hours = int(minutes // 60)

    if hours < 24:
        return f"{hours} hour{'s' if hours > 1 else ''} ago"

    days = int(hours // 24)

    if days < 7:
        return f"{days} day{'s' if days > 1 else ''} ago"

    return value.strftime("%d %b %Y")


def register_filters(app):

    app.add_template_filter(timeago, "timeago")
