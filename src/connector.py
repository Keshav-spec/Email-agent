"""
Email Connector module using imaplib and email standard libraries.
Provides secure SSL IMAP connection, non-destructive fetching, and MIME decoding.
"""

import email
import email.header
import email.message
import email.utils
import imaplib
import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup

from .config import AgentConfig
from .models import EmailMessage

logger = logging.getLogger("EmailConnector")


class EmailConnector:
    """Manages secure connection to an IMAP mail server and retrieves messages."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.client: Optional[imaplib.IMAP4] = None

    def connect(self) -> None:
        """Establishes an encrypted connection to the IMAP server and logs in."""
        logger.info(f"Connecting to {self.config.imap_host}:{self.config.imap_port} (SSL={self.config.use_ssl})...")
        try:
            if self.config.use_ssl:
                self.client = imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port)
            else:
                self.client = imaplib.IMAP4(self.config.imap_host, self.config.imap_port)

            self.client.login(self.config.email_address, self.config.email_password)
            logger.info("Successfully authenticated with mail server.")
        except imaplib.IMAP4.error as e:
            err_msg = str(e)
            if "AUTHENTICATIONFAILED" in err_msg or "Invalid credentials" in err_msg:
                raise ConnectionError(
                    f"IMAP Authentication failed: {err_msg}.\n"
                    "If using Gmail, ensure you are using a 16-character 'App Password' "
                    "(https://myaccount.google.com/apppasswords), NOT your normal Google password."
                ) from e
            raise ConnectionError(f"IMAP Connection failed: {err_msg}") from e
        except Exception as e:
            raise ConnectionError(f"Could not connect to {self.config.imap_host}: {e}") from e

    def disconnect(self) -> None:
        """Safely logs out and closes the IMAP session."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            try:
                self.client.logout()
            except Exception:
                pass
            self.client = None
            logger.info("Disconnected from IMAP server.")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def fetch_emails(
        self, 
        limit: Optional[int] = None, 
        unread_only: Optional[bool] = None,
        today_only: Optional[bool] = None,
        mark_as_read: Optional[bool] = None
    ) -> List[EmailMessage]:
        """
        Retrieves messages from INBOX.
        Supports filtering to today's messages and reading both read/unread emails.
        Uses BODY.PEEK to prevent unintentionally marking unread emails as read.
        """
        if not self.client:
            raise RuntimeError("IMAP client is not connected. Call connect() first.")

        fetch_limit = limit if limit is not None else self.config.fetch_limit
        is_unread_only = unread_only if unread_only is not None else self.config.unread_only
        is_today_only = today_only if today_only is not None else self.config.today_only
        do_mark_read = mark_as_read if mark_as_read is not None else self.config.mark_as_read

        # Select INBOX
        status, _ = self.client.select("INBOX")
        if status != "OK":
            raise RuntimeError("Failed to select INBOX.")

        # Construct Search Query
        if is_today_only:
            today = datetime.now()
            imap_date = today.strftime("%d-%b-%Y")
            if is_unread_only:
                search_query = f'(UNSEEN SINCE "{imap_date}")'
            else:
                search_query = f'(SINCE "{imap_date}")'
            logger.info(f"Searching INBOX for emails from today ({imap_date}) [unread_only={is_unread_only}]...")
        else:
            search_query = "(UNSEEN)" if is_unread_only else "ALL"
            logger.info(f"Searching INBOX with query {search_query}...")

        status, data = self.client.search(None, search_query)
        if status != "OK":
            logger.warning(f"Search failed with status: {status}")
            return []

        message_ids = data[0].split()
        if not message_ids:
            logger.info(f"No emails matched query: {search_query}")
            return []

        # Get latest message IDs up to fetch_limit
        selected_ids = message_ids[-fetch_limit:] if fetch_limit else message_ids
        # Reverse so newest are processed first
        selected_ids.reverse()

        logger.info(f"Found {len(message_ids)} matching emails. Fetching {len(selected_ids)} latest...")

        messages: List[EmailMessage] = []
        for msg_id_bytes in selected_ids:
            msg_id = msg_id_bytes.decode()
            try:
                # Use BODY.PEEK[] to preserve unread flag unless mark_as_read is True
                fetch_cmd = "(RFC822)" if do_mark_read else "(BODY.PEEK[])"
                status, msg_data = self.client.fetch(msg_id, fetch_cmd)
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                parsed_msg = email.message_from_bytes(raw_email)
                email_obj = self._parse_email_message(msg_id, parsed_msg)
                messages.append(email_obj)

                if do_mark_read:
                    self.client.store(msg_id, "+FLAGS", "(\\Seen)")
            except Exception as e:
                logger.error(f"Error fetching message ID {msg_id}: {e}")
                continue

        return messages

    @staticmethod
    def decode_header_value(header_value: Optional[str]) -> str:
        """Decodes RFC 2047 encoded email headers into clean unicode strings."""
        if not header_value:
            return ""
        decoded_fragments = email.header.decode_header(header_value)
        text_parts = []
        for fragment, charset in decoded_fragments:
            if isinstance(fragment, bytes):
                if charset:
                    try:
                        text_parts.append(fragment.decode(charset, errors="replace"))
                    except (LookupError, UnicodeDecodeError):
                        text_parts.append(fragment.decode("utf-8", errors="replace"))
                else:
                    text_parts.append(fragment.decode("utf-8", errors="replace"))
            else:
                text_parts.append(str(fragment))
        return " ".join(text_parts).strip()

    def _parse_email_message(self, msg_id: str, msg: email.message.Message) -> EmailMessage:
        """Extracts metadata and clean plain text from email.message.Message object."""
        subject = self.decode_header_value(msg.get("Subject", "(No Subject)"))
        sender = self.decode_header_value(msg.get("From", "Unknown"))
        date_str = msg.get("Date")
        message_id = msg.get("Message-ID")

        parsed_date: Optional[datetime] = None
        if date_str:
            try:
                parsed_date = email.utils.parsedate_to_datetime(date_str)
            except Exception:
                parsed_date = None

        # Extract plain text body and HTML links
        body_text, links = self._extract_body_and_links(msg)

        # Append discovered action links to body so parser can analyze them
        if links:
            body_text += "\n\n[Links extracted from email]:\n" + "\n".join(f"- {link}" for link in links[:8])

        return EmailMessage(
            id=msg_id,
            subject=subject,
            sender=sender,
            date_str=date_str,
            date=parsed_date,
            body=body_text.strip(),
            message_id=message_id,
        )

    def _extract_body_and_links(self, msg: email.message.Message) -> Tuple[str, List[str]]:
        """Traverses MIME parts to extract plain text and HTML hyperlinks."""
        text_parts = []
        extracted_links: List[str] = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                payload = part.get_payload(decode=True)
                if not payload:
                    continue

                charset = part.get_content_charset() or "utf-8"
                try:
                    decoded = payload.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    decoded = payload.decode("utf-8", errors="replace")

                if content_type == "text/plain":
                    text_parts.append(decoded)
                elif content_type == "text/html":
                    html_text, links = self._clean_html(decoded)
                    extracted_links.extend(links)
                    if not text_parts:  # fallback if no plain text part
                        text_parts.append(html_text)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    decoded = payload.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    decoded = payload.decode("utf-8", errors="replace")

                if msg.get_content_type() == "text/html":
                    html_text, links = self._clean_html(decoded)
                    text_parts.append(html_text)
                    extracted_links.extend(links)
                else:
                    text_parts.append(decoded)

        # Extract plain text links as well
        plain_links = re.findall(r"https?://[^\s<>\"']+", " ".join(text_parts))
        extracted_links.extend(plain_links)

        # Deduplicate links preserving order
        unique_links = []
        for l in extracted_links:
            clean_l = l.rstrip(".,;)>]")
            if clean_l and clean_l not in unique_links:
                unique_links.append(clean_l)

        full_body = "\n".join(text_parts)
        return full_body, unique_links

    @staticmethod
    def _clean_html(html_content: str) -> Tuple[str, List[str]]:
        """Converts HTML to clean plain text and collects anchor href links."""
        links: List[str] = []
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            # Collect links
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith("http://") or href.startswith("https://"):
                    text = a.get_text(strip=True)
                    if text:
                        links.append(f"{text}: {href}")
                    else:
                        links.append(href)

            # Strip style & script
            for s in soup(["script", "style", "meta", "noscript"]):
                s.decompose()

            text = soup.get_text(separator="\n")
            # Normalize whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return "\n".join(lines), links
        except Exception:
            # Fallback regex strip
            clean_text = re.sub(r"<[^>]+>", " ", html_content)
            clean_text = re.sub(r"\s+", " ", clean_text)
            return clean_text.strip(), []

    @staticmethod
    def has_deadline_indicators(text: str) -> bool:
        """
        Lightweight heuristic screener to check if email text mentions deadlines,
        registrations, or closing dates.
        """
        keywords = [
            "deadline", "register by", "registration", "rsvp", "due date",
            "closes on", "closes at", "ends on", "apply by", "submit by",
            "last day to", "last chance", "early bird", "expiring", "expire",
            "reminder:", "before it's too late", "final call", "submission due"
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)
