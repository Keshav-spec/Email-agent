"""
Data models for Email Deadline Agent.
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


class EmailMessage(BaseModel):
    """Represents a fetched email message with cleaned content."""
    id: str = Field(description="Unique message identifier or sequence number")
    subject: str = Field(default="(No Subject)", description="Decoded email subject")
    sender: str = Field(default="Unknown", description="Sender email or name")
    date_str: Optional[str] = Field(default=None, description="Raw Date header string")
    date: Optional[datetime] = Field(default=None, description="Parsed sender timestamp")
    body: str = Field(default="", description="Cleaned plain text body")
    is_read: bool = Field(default=False, description="Read state on server")
    message_id: Optional[str] = Field(default=None, description="RFC 2822 Message-ID header")


class DeadlineItem(BaseModel):
    """Represents an extracted deadline or time-sensitive event item."""
    id: str = Field(
        default="", 
        description="Unique identifier for the deadline item"
    )
    event_name: str = Field(
        ..., 
        description="Name of the event, registration, competition, webinar, or task"
    )
    deadline_iso: Optional[str] = Field(
        default=None, 
        description="Normalized ISO 8601 deadline (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD)"
    )
    deadline_text: str = Field(
        ..., 
        description="Verbatim or original phrase detected in email (e.g. 'Oct 15, 2026 at 11:59 PM')"
    )
    action_link: Optional[str] = Field(
        default=None, 
        description="Registration URL, RSVP link, or primary call-to-action link"
    )
    urgency: str = Field(
        default="Upcoming", 
        description="Priority/Urgency level: Urgent, Upcoming, Later, Expired, or Unknown"
    )
    days_remaining: Optional[float] = Field(
        default=None, 
        description="Number of days remaining until deadline relative to run time"
    )
    summary: str = Field(
        default="", 
        description="Brief 1-2 sentence context or instructions extracted from email"
    )
    source_subject: str = Field(
        default="", 
        description="Subject of the source email"
    )
    source_sender: str = Field(
        default="", 
        description="Sender of the source email"
    )
    source_date: Optional[str] = Field(
        default=None, 
        description="Date the source email was received"
    )
    confidence: float = Field(
        default=1.0, 
        description="Confidence score between 0.0 and 1.0"
    )
    is_completed: bool = Field(
        default=False,
        description="Whether the user marked this deadline as completed"
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="Timestamp when task was marked as completed"
    )
    last_alerted_at: Optional[str] = Field(
        default=None,
        description="Timestamp of when the 1-hour approaching alert was triggered"
    )

    def generate_id(self) -> str:
        """Generates deterministic unique ID from event name and deadline."""
        seed = f"{self.event_name.strip().lower()}|{self.deadline_iso or self.deadline_text.strip().lower()}"
        self.id = hashlib.md5(seed.encode("utf-8")).hexdigest()[:8]
        return self.id

    def is_alert_due(self, window_seconds: int = 3600, ref_time: Optional[datetime] = None) -> bool:
        """Checks if deadline is approaching within window_seconds (default 1 hour) and not yet alerted."""
        if self.is_completed or not self.deadline_iso:
            return False

        if ref_time is None:
            ref_time = datetime.now(timezone.utc)

        try:
            dt_clean = self.deadline_iso.replace("Z", "+00:00")
            parsed_dt = datetime.fromisoformat(dt_clean)
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)

            remaining_sec = (parsed_dt - ref_time).total_seconds()
            # Alert if between 0 and window_seconds (e.g. 1 hour)
            if 0 <= remaining_sec <= window_seconds:
                return self.last_alerted_at is None
            return False
        except Exception:
            return False

    def compute_urgency(self, ref_time: Optional[datetime] = None) -> None:
        """Computes days_remaining and urgency category relative to reference time."""
        if not self.deadline_iso:
            self.urgency = "Unknown"
            self.days_remaining = None
            return

        if ref_time is None:
            ref_time = datetime.now(timezone.utc)

        try:
            # Parse ISO string
            dt_clean = self.deadline_iso.replace("Z", "+00:00")
            parsed_dt = datetime.fromisoformat(dt_clean)
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)

            delta = (parsed_dt - ref_time).total_seconds() / 86400.0
            self.days_remaining = round(delta, 1)

            if delta < 0:
                self.urgency = "Expired"
            elif delta <= 2:
                self.urgency = "Urgent"
            elif delta <= 7:
                self.urgency = "Upcoming"
            else:
                self.urgency = "Later"
        except Exception:
            self.urgency = "Unknown"
            self.days_remaining = None


class AgentRunSummary(BaseModel):
    """Aggregate summary of a single scanning run."""
    run_timestamp: str
    total_scanned: int
    emails_with_deadlines: int
    total_deadlines: int
    urgent_count: int = 0
    upcoming_count: int = 0
    later_count: int = 0
    expired_count: int = 0
    items: List[DeadlineItem] = Field(default_factory=list)
