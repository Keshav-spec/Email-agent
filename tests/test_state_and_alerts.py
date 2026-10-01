"""
Tests for StateManager and Approaching Deadline Alerts.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.alerts import check_and_trigger_alerts
from src.models import DeadlineItem
from src.state_manager import StateManager


class TestStateAndAlerts(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temp_dir.name) / "test_state.json"
        self.md_file = Path(self.temp_dir.name) / "test_deadlines.md"
        self.state_mgr = StateManager(state_file=self.state_file)
        self.ref_time = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_deadline_id_generation(self):
        item = DeadlineItem(
            event_name="AI Hackathon",
            deadline_iso="2026-10-15T23:59:00+00:00",
            deadline_text="October 15, 2026 at 23:59 UTC",
        )
        item_id = item.generate_id()
        self.assertTrue(len(item_id) >= 6)
        # Idempotent
        self.assertEqual(item.generate_id(), item_id)

    def test_1_hour_approaching_alert(self):
        """Validates that a deadline 45 minutes away triggers an alert, while 5 hours away does not."""
        near_dt = self.ref_time + timedelta(minutes=45)
        far_dt = self.ref_time + timedelta(hours=5)

        item_near = DeadlineItem(
            event_name="Imminent Proposal Submission",
            deadline_iso=near_dt.isoformat(),
            deadline_text="Due in 45 mins",
        )
        item_far = DeadlineItem(
            event_name="Future Conference",
            deadline_iso=far_dt.isoformat(),
            deadline_text="Due in 5 hours",
        )

        self.assertTrue(item_near.is_alert_due(window_seconds=3600, ref_time=self.ref_time))
        self.assertFalse(item_far.is_alert_due(window_seconds=3600, ref_time=self.ref_time))

        alerted = check_and_trigger_alerts([item_near, item_far], window_seconds=3600, ref_time=self.ref_time)
        self.assertEqual(len(alerted), 1)
        self.assertEqual(alerted[0].event_name, "Imminent Proposal Submission")
        self.assertIsNotNone(alerted[0].last_alerted_at)

        # Subsequent check should not alert again (anti-spam)
        alerted_again = check_and_trigger_alerts([item_near], window_seconds=3600, ref_time=self.ref_time)
        self.assertEqual(len(alerted_again), 0)

    def test_state_merge_and_mark_completed(self):
        item = DeadlineItem(
            event_name="PyData Conference",
            deadline_iso="2026-10-08T18:00:00+00:00",
            deadline_text="October 08, 2026",
        )
        item.generate_id()

        # Merge
        merged = self.state_mgr.merge_deadlines([item])
        self.assertEqual(len(merged), 1)
        self.assertFalse(merged[0].is_completed)

        # Mark completed via CLI identifier
        completed = self.state_mgr.mark_completed(item.id)
        self.assertIsNotNone(completed)
        self.assertTrue(completed.is_completed)
        self.assertIsNotNone(completed.completed_at)

        # Re-load from disk to ensure persistence
        reloaded = self.state_mgr.load_items()
        self.assertTrue(reloaded[0].is_completed)

    def test_sync_completion_from_markdown_checkbox(self):
        item = DeadlineItem(
            event_name="Cloud Security Briefing",
            deadline_iso="2026-10-03T17:00:00+00:00",
            deadline_text="October 03, 2026",
        )
        item.generate_id()
        self.state_mgr.save_items([item])

        # Write markdown file with checked task box: - [x] Cloud Security Briefing
        md_text = f"""# Deadlines Report
- [x] {item.event_name}
- **Task ID:** `{item.id}`
"""
        self.md_file.write_text(md_text, encoding="utf-8")

        completed = self.state_mgr.sync_from_markdown(self.md_file)
        self.assertIn("Cloud Security Briefing", completed)

        # Check state
        items = self.state_mgr.load_items()
        self.assertTrue(items[0].is_completed)


if __name__ == "__main__":
    unittest.main()
