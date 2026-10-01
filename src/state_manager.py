"""
State Manager for Email Deadline Agent.
Manages persistent tracking in deadlines_state.json, syncs completions from
deadlines.md task checkboxes, and preserves active deadlines until completed.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models import DeadlineItem

logger = logging.getLogger("StateManager")
DEFAULT_STATE_FILE = Path(__file__).resolve().parent.parent / "deadlines_state.json"


class StateManager:
    """Handles persistence, deduplication, and completion synchronization."""

    def __init__(self, state_file: Path = DEFAULT_STATE_FILE):
        self.state_file = Path(state_file)

    def load_items(self) -> List[DeadlineItem]:
        """Loads stored deadlines from JSON file."""
        if not self.state_file.exists():
            return []
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            items = [DeadlineItem(**raw) for raw in data]
            for it in items:
                if not it.id:
                    it.generate_id()
            return items
        except Exception as e:
            logger.error(f"Failed to load state file {self.state_file}: {e}")
            return []

    def save_items(self, items: List[DeadlineItem]) -> None:
        """Serializes deadline items to JSON state file."""
        try:
            data = [it.model_dump() for it in items]
            self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save state file {self.state_file}: {e}")

    def sync_from_markdown(self, markdown_path: Path) -> List[str]:
        """
        Parses deadlines.md to check if the user checked any `- [x]` boxes.
        Returns list of newly completed event names.
        """
        if not markdown_path.exists():
            return []

        try:
            content = markdown_path.read_text(encoding="utf-8")
        except Exception:
            return []

        # Find all checked tasks: e.g. "- [x] 1. Event Name" or "- [x] **Event Name**" or "- [x] ~~**Event Name**~~"
        checked_patterns = re.findall(r"-\s*\[[xX]\]\s*(?:~~\s*)?(?:\d+\.\s*)?\*?\*?([^\n\r*~|]+)", content)
        checked_titles = [t.strip().rstrip(":") for t in checked_patterns if t.strip()]

        if not checked_titles:
            return []

        items = self.load_items()
        updated_any = False
        completed_titles = []

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        for item in items:
            if not item.is_completed:
                item_title_lower = item.event_name.lower().strip()
                # Check if item title or item ID is among the checked titles
                for chk in checked_titles:
                    chk_lower = chk.lower().strip()
                    if chk_lower in item_title_lower or item_title_lower in chk_lower or item.id == chk.strip():
                        item.is_completed = True
                        item.completed_at = now_str
                        updated_any = True
                        completed_titles.append(item.event_name)
                        break

        if updated_any:
            self.save_items(items)

        return completed_titles

    def merge_deadlines(self, new_items: List[DeadlineItem]) -> List[DeadlineItem]:
        """
        Merges newly discovered deadlines with existing saved state.
        Preserves existing items and completion statuses. Deadlines remain
        active until explicitly completed.
        """
        existing_items = self.load_items()
        existing_by_id = {it.id or it.generate_id(): it for it in existing_items}
        existing_by_key = {self._match_key(it): it for it in existing_items}

        for new_it in new_items:
            new_id = new_it.generate_id()
            match_key = self._match_key(new_it)

            if new_id in existing_by_id:
                # Update details but preserve status
                existing = existing_by_id[new_id]
                self._update_fields(existing, new_it)
            elif match_key in existing_by_key:
                existing = existing_by_key[match_key]
                self._update_fields(existing, new_it)
            else:
                existing_items.append(new_it)
                existing_by_id[new_id] = new_it
                existing_by_key[match_key] = new_it

        self.save_items(existing_items)
        return existing_items

    def mark_completed(self, identifier: str) -> Optional[DeadlineItem]:
        """Marks a deadline completed by ID or event name keyword."""
        items = self.load_items()
        target = None
        ident_lower = identifier.lower().strip()

        for it in items:
            if it.id.lower() == ident_lower or ident_lower in it.event_name.lower():
                it.is_completed = True
                it.completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                target = it
                break

        if target:
            self.save_items(items)
        return target

    @staticmethod
    def _match_key(item: DeadlineItem) -> str:
        """Normalized key for fuzzy deduplication."""
        clean_name = re.sub(r"[^a-zA-Z0-9]", "", item.event_name).lower()[:25]
        clean_date = (item.deadline_iso or item.deadline_text)[:10]
        return f"{clean_name}|{clean_date}"

    @staticmethod
    def _update_fields(existing: DeadlineItem, new_it: DeadlineItem) -> None:
        """Updates metadata without overwriting completion or alert flags."""
        if not existing.action_link and new_it.action_link:
            existing.action_link = new_it.action_link
        if not existing.summary and new_it.summary:
            existing.summary = new_it.summary
        if new_it.confidence > existing.confidence:
            existing.deadline_iso = new_it.deadline_iso
            existing.deadline_text = new_it.deadline_text
