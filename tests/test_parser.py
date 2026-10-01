"""
Tests for DeadlineParser and extraction accuracy.
"""

import unittest
from datetime import datetime, timezone
from src.config import AgentConfig
from src.mock_data import get_mock_emails
from src.parser import DeadlineParser


class TestDeadlineParser(unittest.TestCase):
    def setUp(self):
        self.config = AgentConfig()
        self.config.gemini_api_key = ""
        self.config.llm_provider = "heuristic"
        self.parser = DeadlineParser(self.config)
        self.ref_time = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
        self.mock_emails = get_mock_emails()

    def test_mock_emails_extraction_count(self):
        """Validates that non-deadline newsletter is skipped while deadline emails are caught."""
        results = self.parser.parse_batch(self.mock_emails, ref_time=self.ref_time)
        # We have 6 emails in mock dataset: 5 with deadlines, 1 newsletter with none
        self.assertGreaterEqual(len(results), 4)

        # Check that newsletter was not falsely identified
        subjects = [item.source_subject for item in results]
        self.assertFalse(any("Python Weekly Newsletter" in s for s in subjects))

    def test_hackathon_extraction(self):
        hackathon_msg = self.mock_emails[0]
        results = self.parser.parse_email(hackathon_msg, ref_time=self.ref_time)
        self.assertEqual(len(results), 1)
        item = results[0]

        self.assertIn("Hackathon", item.event_name)
        self.assertIsNotNone(item.deadline_iso)
        self.assertIn("2026-10-15", item.deadline_iso)
        self.assertIn("aiagents.io", item.action_link)

    def test_chronological_ordering(self):
        results = self.parser.parse_batch(self.mock_emails, ref_time=self.ref_time)
        iso_dates = [it.deadline_iso for it in results if it.deadline_iso]
    def test_online_test_and_assessment_extraction(self):
        """Validates that online test/exam emails with link and start time are parsed correctly."""
        from src.models import EmailMessage
        msg = EmailMessage(
            id="test_online",
            subject="Kind Attention!! Axxela Research & Analytics Applied students!!",
            sender="'No Reply CDC Info' via VITIANS CDC Group",
            date_str="Thu, 01 Oct 2026 13:54:00 +0530",
            body="""Kind Attention!!
Axxela Research & Analytics Applied students!!
Test 1 : 7:00 PM
Fresh link for test today -
Link - https://tests.mettl.com/authenticateKey/a3km6ni6f4
Time - 7:00 PM
*Link will be valid for only 5 minutes, so please ask the students to join at sharp 7:00 PM
Note: Students can attempt the test at their own locations,No RECAT will be given to the students
"""
        )
        results = self.parser.parse_email(msg, ref_time=self.ref_time)
        self.assertEqual(len(results), 1)
        self.assertIn("Axxela", results[0].event_name)
        self.assertIn("tests.mettl.com", results[0].action_link)
        self.assertIn("19:00", results[0].deadline_iso)

if __name__ == "__main__":
    unittest.main()
