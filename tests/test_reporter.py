"""
Tests for MarkdownReporter and summary generation.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from src.models import DeadlineItem
from src.reporter import MarkdownReporter


class TestMarkdownReporter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_path = Path(self.temp_dir.name) / "test_deadlines.md"
        self.reporter = MarkdownReporter(str(self.output_path))
        self.ref_time = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_markdown_generation(self):
        items = [
            DeadlineItem(
                event_name="AI Agents Hackathon",
                deadline_iso="2026-10-02T18:00:00+00:00",
                deadline_text="October 02, 2026 at 18:00 UTC",
                action_link="https://aiagents.io/register",
                summary="Register for AI hackathon.",
                source_subject="AI Hackathon Announcement",
                source_sender="team@aiagents.io",
            ),
            DeadlineItem(
                event_name="PyData Conference",
                deadline_iso="2026-10-15T23:59:00+00:00",
                deadline_text="October 15, 2026",
                action_link="https://pydata.org/tickets",
                summary="Early bird ticket closing.",
                source_subject="PyData Tickets",
                source_sender="tickets@pydata.org",
            ),
        ]

        summary = self.reporter.generate_summary(items, total_scanned=5, ref_time=self.ref_time)
        self.assertEqual(summary.total_deadlines, 2)
        self.assertEqual(summary.urgent_count, 1)  # Due tomorrow = Urgent

        md_content = self.reporter.write_markdown(summary)
        self.assertTrue(self.output_path.exists())
        self.assertIn("# Email Deadline & Event Summary Report", md_content)
        self.assertIn("AI Agents Hackathon", md_content)
        self.assertIn("PyData Conference", md_content)
        self.assertIn("https://aiagents.io/register", md_content)


if __name__ == "__main__":
    unittest.main()
