"""
Mock email dataset for zero-risk offline testing and demonstration.
Provides diverse scenarios: conferences, hackathons, assignments, webinars,
multi-date emails, and negative non-deadline newsletters.
"""

from datetime import datetime, timezone
from typing import List
from .models import EmailMessage


def get_mock_emails() -> List[EmailMessage]:
    """Returns a list of synthetic EmailMessage objects for parser testing."""
    return [
        EmailMessage(
            id="mock-101",
            subject="[Action Required] AI Agents Global Hackathon 2026: Registration Closes Soon!",
            sender="hackathon-team@aiagents.io",
            date_str="Wed, 30 Sep 2026 14:22:00 +0000",
            date=datetime(2026, 9, 30, 14, 22, tzinfo=timezone.utc),
            body="""Hi Builder,

Get ready to build next-generation autonomous agents! Over $50,000 in bounties are up for grabs.

Important Timelines:
- Team Registration Deadline: October 15, 2026 at 23:59 UTC
- Opening Ceremony: October 18, 2026

Please register your team before the deadline closes. Late submissions will not be accepted.

Register your team here: https://aiagents.io/hackathon/register-2026

Best regards,
The AI Agents Organizing Committee""",
            is_read=False,
            message_id="<mock-hackathon-101@aiagents.io>"
        ),
        EmailMessage(
            id="mock-102",
            subject="Early Bird Tickets Ending: PyData Global Conference 2026",
            sender="tickets@pydataglobal.org",
            date_str="Thu, 01 Oct 2026 09:15:00 +0000",
            date=datetime(2026, 10, 1, 9, 15, tzinfo=timezone.utc),
            body="""Hello Python Enthusiast,

This is a friendly reminder that Early Bird pricing for PyData Global 2026 closes on October 08, 2026 at 18:00 EST.

After this deadline, ticket prices will increase by 40%. Don't miss talks on PyTorch, Polars, and Agentic Workflows.

Secure your ticket now:
https://pydata.org/global2026/tickets?discount=EARLYBIRD

See you online!
PyData Team""",
            is_read=False,
            message_id="<mock-pydata-102@pydataglobal.org>"
        ),
        EmailMessage(
            id="mock-103",
            subject="CS610: Final Project Proposal - Due Date Announcement",
            sender="course-staff@university.edu",
            date_str="Thu, 01 Oct 2026 11:00:00 +0000",
            date=datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc),
            body="""Students,

Your Final Project Proposal is due by October 05, 2026, 11:59 PM EST.
Late days CANNOT be used for this submission.

Submit your proposal PDF via Gradescope:
https://www.gradescope.com/courses/610452/assignments/39481

Ensure you have formed your 3-person group in the portal prior to submission.

- Prof. Davis""",
            is_read=False,
            message_id="<mock-cs610-103@university.edu>"
        ),
        EmailMessage(
            id="mock-104",
            subject="Exclusive Executive Briefing: Cloud Security in 2027 (RSVP Required)",
            sender="events@cloudsecurityforum.com",
            date_str="Thu, 01 Oct 2026 08:30:00 +0000",
            date=datetime(2026, 10, 1, 8, 30, tzinfo=timezone.utc),
            body="""Dear Colleague,

You are invited to an exclusive roundtable on Zero Trust architecture.
Seats are strictly limited to 30 enterprise leaders.

Event Date: October 22, 2026
RSVP Deadline: Please register by October 03, 2026 at 5:00 PM PDT to confirm catering and access passes.

Confirm your attendance:
https://cloudsecurityforum.com/events/executive-briefing/rsvp?token=ab8394

Regards,
Security Forum Events""",
            is_read=False,
            message_id="<mock-briefing-104@cloudsecurityforum.com>"
        ),
        EmailMessage(
            id="mock-105",
            subject="Python Weekly Newsletter #412: Best Practices & Design Patterns",
            sender="newsletter@pythonweekly.com",
            date_str="Wed, 30 Sep 2026 17:00:00 +0000",
            date=datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc),
            body="""Welcome to issue #412 of Python Weekly!

Articles this week:
1. Structuring Clean Python Projects in 2026
2. Understanding asyncio and uvloop performance
3. 10 Data Science tools you probably haven't heard of

Check out the full issue on our web archive:
https://pythonweekly.com/archive/412

Unsubscribe anytime by clicking the link in footer.""",
            is_read=True,
            message_id="<mock-newsletter-105@pythonweekly.com>"
        ),
        EmailMessage(
            id="mock-106",
            subject="Notice: Annual Grant Application Closes on November 01, 2026",
            sender="grants-office@foundation.org",
            date_str="Tue, 29 Sep 2026 16:45:00 +0000",
            date=datetime(2026, 9, 29, 16, 45, tzinfo=timezone.utc),
            body="""Dear Researcher,

The Foundation's 2026-2027 Research Grant cycle is currently open for submissions.
The application portal closes on November 01, 2026 at 17:00 UTC.

Eligibility criteria and application submission guidelines can be reviewed at:
https://foundation.org/grants/apply-2026

Award notifications will be announced on December 15, 2026.

Office of Research Grants""",
            is_read=False,
            message_id="<mock-grant-106@foundation.org>"
        ),
    ]
