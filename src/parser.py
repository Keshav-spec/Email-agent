"""
Intelligent Deadline Parser module for Google Gemini.
Features:
- Multi-email batching (packs multiple emails into 1 API call to minimize requests)
- Resilient auto-failover across Gemini models (handles 429 quota and 503 high demand)
- Exponential backoff with retryDelay parsing
- Pacing delay to stay well within free-tier rate limits (5 RPM / 15 RPM)
- Rule-based heuristic fallback if API quota is temporarily exhausted
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import dateutil.parser
import requests
from rich.console import Console

from .config import AgentConfig
from .models import DeadlineItem, EmailMessage

logger = logging.getLogger("DeadlineParser")
console = Console(legacy_windows=False, force_terminal=True)

BATCH_SYSTEM_PROMPT = """You are an expert deadline and time-sensitive event extraction assistant.
Your task is to analyze the provided batch of emails and identify any registration deadlines, online tests, coding assessments, exams, interviews, submission due dates, contest timings, early-bird ticket closing, RSVP deadlines, or critical action times.

Input contains one or more emails indexed as [EMAIL 0], [EMAIL 1], etc.

Output ONLY a valid JSON object matching this exact schema:
{
  "results": [
    {
      "email_index": 0,
      "has_deadline": true,
      "deadlines": [
        {
          "event_name": "Clear, concise title of the event, test, company assessment, course, or webinar (e.g. 'Axxela Research & Analytics - Test 1')",
          "deadline_iso": "YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD in ISO 8601 format. If only a time is given (e.g. '7:00 PM today'), combine with the email date or reference date.",
          "deadline_text": "Exact verbatim phrase from the email specifying the deadline date and time (e.g. 'Today at 7:00 PM' or 'October 03, 2026 at 5:00 PM PDT')",
          "action_link": "Primary link to take the test, register, RSVP, or submit (e.g. https://tests.mettl.com/... or Google Forms), or null if none",
          "urgency": "Urgent" | "Upcoming" | "Later" | "Expired" | "Unknown",
          "summary": "1 sentence explaining what action needs to be taken before or at this time (e.g. 'Join test link at sharp 7:00 PM; link valid for 5 minutes.')"
        }
      ]
    }
  ]
}

Important Rules:
1. Include online tests, exams, and assessments (e.g. 'Test 1: 7:00 PM', 'join at sharp 7:00 PM', 'Link valid for 5 mins') as critical action deadlines.
2. If the email specifies a time today (e.g. 'Test 1 : 7:00 PM' or 'today at 7:00 PM'), use the reference date/email date to construct the full ISO deadline.
3. If an email has NO time-sensitive action (e.g. routine newsletter, receipt), set "has_deadline": false and "deadlines": [].
4. Return ONLY raw JSON without markdown backticks or commentary.
"""


class DeadlineParser:
    """Parses email batches using Google Gemini with quota protection & failover."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.api_key = config.gemini_api_key

        # Model failover pool (handles 429 quota exhaustion & 503 high demand)
        primary_model = config.gemini_model.replace("models/", "")
        self.model_pool = [
            primary_model,
            "gemini-3-flash-preview",
            "gemini-flash-lite-latest",
            "gemini-3.1-flash-lite-preview",
            "gemini-flash-latest"
        ]
        # Deduplicate while preserving order
        seen = set()
        self.model_pool = [m for m in self.model_pool if not (m in seen or seen.add(m))]

    def parse_batch(
        self, 
        emails: List[EmailMessage], 
        ref_time: Optional[datetime] = None
    ) -> List[DeadlineItem]:
        """
        Parses a list of emails with keyword pre-screening and batching.
        Saves API requests by packing multiple emails per prompt.
        """
        if ref_time is None:
            ref_time = datetime.now(timezone.utc)

        # 1. Pre-filter candidate emails with keyword indicators
        candidates: List[EmailMessage] = []
        for msg in emails:
            combined = f"{msg.subject}\n{msg.body}"
            if self._has_keywords(combined):
                candidates.append(msg)
            else:
                logger.debug(f"Skipping '{msg.subject[:30]}' - no deadline keywords.")

        if not candidates:
            return []

        # If no Gemini API key configured, use local heuristic parser
        if not self.api_key:
            all_deadlines = self._parse_candidates_with_heuristic(candidates, ref_time)
            all_deadlines.sort(key=lambda x: x.deadline_iso or "9999-99-99")
            return all_deadlines

        # 2. Batch candidates into chunks of up to 4 emails per LLM call
        batch_size = 4
        all_deadlines: List[DeadlineItem] = []

        for i in range(0, len(candidates), batch_size):
            chunk = candidates[i : i + batch_size]
            try:
                # Small pacing delay between batch calls to stay within free-tier rate limits
                if i > 0:
                    time.sleep(2.0)

                items = self._parse_chunk_with_gemini(chunk, ref_time)
                all_deadlines.extend(items)
            except Exception as e:
                logger.warning(f"Batch LLM processing encountered error: {e}. Falling back to heuristic for this batch.")
                heuristic_items = self._parse_candidates_with_heuristic(chunk, ref_time)
                all_deadlines.extend(heuristic_items)

        # Sort chronologically by deadline_iso
        all_deadlines.sort(key=lambda x: x.deadline_iso or "9999-99-99")
        return all_deadlines

    def parse_email(
        self, 
        email_msg: EmailMessage, 
        ref_time: Optional[datetime] = None
    ) -> List[DeadlineItem]:
        """Parses a single email."""
        return self.parse_batch([email_msg], ref_time=ref_time)

    # --------------------------------------------------------------------------
    # RESILIENT GEMINI CALL ENGINE
    # --------------------------------------------------------------------------

    def _parse_chunk_with_gemini(
        self, 
        chunk: List[EmailMessage], 
        ref_time: datetime
    ) -> List[DeadlineItem]:
        """Sends a batched prompt to Gemini with auto-failover and backoff."""
        prompt = self._build_batch_prompt(chunk, ref_time)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{BATCH_SYSTEM_PROMPT}\n\n{prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        # Try models in pool on 429 (quota) or 503 (high demand)
        last_error = None
        for model in self.model_pool:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            
            for attempt in range(2):  # up to 2 attempts per model
                try:
                    resp = requests.post(url, json=payload, timeout=25)
                    
                    if resp.status_code == 200:
                        res_json = resp.json()
                        raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                        return self._process_batch_json(raw_text, chunk, ref_time)

                    # Handle 429 Quota Exceeded
                    elif resp.status_code == 429:
                        last_error = f"Model '{model}' 429 Rate Limit (Free Tier quota)"
                        retry_delay = self._extract_retry_delay(resp.text)
                        if retry_delay and retry_delay <= 10 and attempt == 0:
                            logger.info(f"Rate limited on {model}. Pausing {retry_delay}s before retry...")
                            time.sleep(retry_delay)
                            continue
                        # If delay is too long (e.g. 40s), switch to next model immediately!
                        logger.info(f"Model '{model}' quota reached. Switching to alternative model...")
                        break

                    # Handle 503 High Demand
                    elif resp.status_code == 503:
                        last_error = f"Model '{model}' 503 High Demand"
                        logger.info(f"Model '{model}' busy (503). Switching to alternative model...")
                        time.sleep(1.5)
                        break

                    else:
                        last_error = f"Model '{model}' returned HTTP {resp.status_code}"
                        break

                except requests.RequestException as e:
                    last_error = str(e)
                    break

        raise RuntimeError(f"All Gemini models exhausted. Last error: {last_error}")

    def _build_batch_prompt(self, chunk: List[EmailMessage], ref_time: datetime) -> str:
        """Packs multiple emails into a clean, tagged batch context."""
        parts = [f"Reference Current Time: {ref_time.isoformat()}\n"]
        for idx, msg in enumerate(chunk):
            parts.append(
                f"[EMAIL {idx}]\n"
                f"Subject: {msg.subject}\n"
                f"Sender: {msg.sender}\n"
                f"Date: {msg.date_str or 'Unknown'}\n"
                f"Body Content:\n{msg.body[:2500]}\n"
                f"[/EMAIL {idx}]\n"
            )
        return "\n".join(parts)

    def _process_batch_json(
        self, 
        raw_text: str, 
        chunk: List[EmailMessage], 
        ref_time: datetime
    ) -> List[DeadlineItem]:
        """Parses batch JSON response and maps deadlines back to their source emails."""
        clean_text = raw_text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?", "", clean_text)
            clean_text = re.sub(r"```$", "", clean_text).strip()

        data = json.loads(clean_text)
        results = data.get("results", [])

        extracted_items: List[DeadlineItem] = []

        for res in results:
            if not res.get("has_deadline"):
                continue

            idx = res.get("email_index", 0)
            if 0 <= idx < len(chunk):
                source_msg = chunk[idx]
            else:
                source_msg = chunk[0]

            for d in res.get("deadlines", []):
                action_link = d.get("action_link") or self._extract_best_url(source_msg.body)
                item = DeadlineItem(
                    event_name=d.get("event_name", source_msg.subject),
                    deadline_iso=d.get("deadline_iso"),
                    deadline_text=d.get("deadline_text", "Deadline mentioned in email"),
                    action_link=action_link,
                    summary=d.get("summary", ""),
                    source_subject=source_msg.subject,
                    source_sender=source_msg.sender,
                    source_date=source_msg.date_str,
                    confidence=0.95
                )
                item.generate_id()
                item.compute_urgency(ref_time)
                extracted_items.append(item)

        return extracted_items

    @staticmethod
    def _extract_retry_delay(error_body: str) -> Optional[float]:
        """Extracts seconds from retryDelay or 'Please retry in Xs' message."""
        match = re.search(r"retry\s+in\s+([\d.]+)\s*s", error_body, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                pass
        match_json = re.search(r'"retryDelay":\s*"(\d+)s"', error_body)
        if match_json:
            try:
                return float(match_json.group(1))
            except Exception:
                pass
        return None

    # --------------------------------------------------------------------------
    # HEURISTIC FALLBACK PARSER
    # --------------------------------------------------------------------------

    def _parse_candidates_with_heuristic(
        self, 
        candidates: List[EmailMessage], 
        ref_time: datetime
    ) -> List[DeadlineItem]:
        """Extracts deadlines using rule-based heuristics when LLM is unavailable."""
        items: List[DeadlineItem] = []
        for msg in candidates:
            parsed = self._parse_single_heuristic(msg, ref_time)
            if parsed:
                items.extend(parsed)
        return items

    def _parse_single_heuristic(
        self, 
        email_msg: EmailMessage, 
        ref_time: datetime
    ) -> List[DeadlineItem]:
        """Extracts deadline using regex and dateutil."""
        combined = f"{email_msg.subject}\n{email_msg.body}"

        patterns = [
            r"(?:registration\s+deadline|submission\s+deadline|due\s+date|rsvp\s+deadline|early\s+bird(?:\s+pricing|\s+tickets)?\s+closes|closes\s+on|closes\s+at|due\s+by|register\s+by|apply\s+by|submit\s+by|ends\s+on)\s*[:\-]?\s*([A-Za-z0-9,\s:\-\/]+?)(?=\.|\n|$|\b(?:to confirm|prior to|late|please|after|awards|don't)\b)",
            r"(?:due|closes|register)\s+by\s+([A-Za-z0-9,\s:\-\/]+?)(?=\.|\n|$|\b(?:to|prior|late)\b)",
            r"(?:test\s*\d*|exam|assessment|interview|slot|time|join\s+at|sharp|valid\s+till|valid\s+until)\s*[:\-]\s*([A-Za-z0-9,\s:\-\/]+?)(?=\.|\n|$|\b(?:to|prior|note|please|link)\b)",
        ]

        found_deadline_text = None
        parsed_dt = None

        for pat in patterns:
            matches = re.finditer(pat, combined, re.IGNORECASE)
            for m in matches:
                candidate = m.group(1).strip()
                parsed = self._try_parse_date(candidate, ref_time)
                if parsed:
                    found_deadline_text = candidate
                    parsed_dt = parsed
                    break
            if parsed_dt:
                break

        if not parsed_dt:
            fallback_match = re.search(
                r"(?:deadline|register|due|closes)[^\n.]{0,40}?"
                r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?(?:\s+(?:at|by)?\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|UTC|EST|PST|EDT|PDT)?)?)",
                combined,
                re.IGNORECASE
            )
            if fallback_match:
                candidate = fallback_match.group(1).strip()
                parsed = self._try_parse_date(candidate, ref_time)
                if parsed:
                    found_deadline_text = candidate
                    parsed_dt = parsed

        if not parsed_dt:
            return []

        clean_name = self._clean_subject_for_event(email_msg.subject)
        action_link = self._extract_best_url(email_msg.body)
        parsed_dt = parsed_dt.replace(microsecond=0)

        item = DeadlineItem(
            event_name=clean_name,
            deadline_iso=parsed_dt.isoformat(),
            deadline_text=found_deadline_text or parsed_dt.strftime("%Y-%m-%d %H:%M"),
            action_link=action_link,
            summary=f"Action or registration required before {found_deadline_text}.",
            source_subject=email_msg.subject,
            source_sender=email_msg.sender,
            source_date=email_msg.date_str,
            confidence=0.85
        )
        item.generate_id()
        item.compute_urgency(ref_time)
        return [item]

    @staticmethod
    def _try_parse_date(date_str: str, ref_time: datetime) -> Optional[datetime]:
        """Attempts to parse string with dateutil fuzzy parser and assigns default year/tz."""
        clean = re.sub(r"(?i)\b(at|on|by|est|pst|edt|pdt|utc|gmt)\b", " ", date_str)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) < 3:
            return None

        try:
            parsed = dateutil.parser.parse(
                clean, 
                fuzzy=True, 
                default=ref_time
            )
            if parsed.year < ref_time.year:
                parsed = parsed.replace(year=ref_time.year)

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None

    @staticmethod
    def _clean_subject_for_event(subject: str) -> str:
        """Strips tags like [Action Required], Fwd:, Re:, Kind Attention!! to get clean event name."""
        cleaned = re.sub(r"^\[.*?\]\s*", "", subject)
        cleaned = re.sub(r"^(?:Re|Fwd|Notice|Alert):\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^\s*Kind\s+Attention!*!\s*", "", cleaned, flags=re.IGNORECASE)
        parts = cleaned.split(":")
        if len(parts) > 1 and len(parts[0].strip()) > 5:
            return parts[0].strip()
        return cleaned.strip()

    @staticmethod
    def _extract_best_url(body: str) -> Optional[str]:
        """Finds primary registration, ticket, or submission URL in body."""
        urls = re.findall(r"https?://[^\s<>\"')\]]+", body)
        if not urls:
            return None

        keywords = ["register", "rsvp", "ticket", "apply", "gradescope", "forms", "submit", "join", "mettl", "test", "exam", "assessment"]
        for u in urls:
            for kw in keywords:
                if kw in u.lower():
                    return u.rstrip(".,;)>]")

        return urls[0].rstrip(".,;)>]")

    @staticmethod
    def _has_keywords(text: str) -> bool:
        """Fast keyword check for time-sensitive emails."""
        keywords = [
            "deadline", "register", "due date", "registration", "rsvp",
            "closes", "ends on", "apply by", "submit", "submission", "last day to",
            "last chance", "early bird", "due by", "final call", "closes soon",
            "test", "exam", "assessment", "interview", "quiz", "contest",
            "valid for", "valid till", "valid until", "join at", "sharp",
            "mettl", "hackerrank", "shortlisted", "applied students",
            "kind attention", "scheduled at", "scheduled on"
        ]
        text_lower = text.lower()
        if any(kw in text_lower for kw in keywords):
            return True

        has_time = bool(re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", text_lower))
        has_day = bool(re.search(r"\b(today|tonight|tomorrow|sharp)\b", text_lower))
        if has_time and has_day:
            return True

        return False
