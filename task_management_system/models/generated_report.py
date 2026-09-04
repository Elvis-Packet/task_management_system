from datetime import datetime

from extensions import db


class GeneratedReport(db.Model):
    """A catalog entry for an on-demand generated report. The report's numbers
    are never frozen here — they're always recomputed live from the source
    tables via ReportService, so the same (type, period) is always reproducible.
    This row just records that someone generated one, when, and of what kind."""

    __tablename__ = "generated_reports"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(255), nullable=False)

    type = db.Column(db.String(50), nullable=False)

    period = db.Column(db.String(50))

    status = db.Column(db.String(20), default="published", nullable=False)

    generated_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    generated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Which department this snapshot is about, and the exact date window it
    # was generated for — stored so re-opening/downloading it later replays
    # the same window rather than "current week" silently drifting.
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), index=True)

    period_start = db.Column(db.Date)

    period_end = db.Column(db.Date)

    generator = db.relationship("User", foreign_keys=[generated_by])

    department = db.relationship("Department")

    def __repr__(self):
        return f"<GeneratedReport {self.title}>"
