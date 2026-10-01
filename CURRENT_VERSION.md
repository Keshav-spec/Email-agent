# Current Version & Feature Changelog: Email Deadline Agent

**Current Version:** `v1.2.0`  
**Last Updated:** October 01, 2026  
**Status:** Stable & Active

---

## Completed Core Features

### 1. Secure Email & IMAP Connectivity
- **IMAP over SSL (`imaplib.IMAP4_SSL`)**: Encrypted connection to Gmail / Google Workspace / Outlook via standard port 993.
- **App Password Security**: Compatible with Google 2-Step Verification App Passwords so account master passwords are never exposed.
- **Non-Destructive Fetching**: Utilizes `(BODY.PEEK[])` queries to scan emails without marking unread messages as read.
- **RFC 2047 MIME Header & HTML Decoder**: Robust parsing of encoded sender/subject fragments, strips HTML scripts/styles, and extracts embedded anchor URLs (`<a href="...">`).

### 2. Today's Email Filter & Full Inbox Scanning
- **`TODAY_ONLY=True`**: Dynamically constructs IMAP `(SINCE "DD-Mon-YYYY")` queries to process all emails arriving since midnight today.
- **`UNREAD_ONLY=False`**: Reads both unopened and previously opened emails from today so no time-sensitive announcements are missed.
- **Batch limit (`FETCH_LIMIT=50`)**: Prevents out-of-memory overhead during high email volume days.

### 3. Google Gemini AI Extraction Engine
- **Exclusive AI Provider**: Powered by Google Gemini (`gemini-3-flash-preview` / `gemini-2.5-flash`).
- **Multi-Email Batching**: Groups candidate emails into batches of 4 per prompt, reducing API request counts by ~75% and preventing free-tier rate-limit throttling (5 RPM limit).
- **Auto-Failover Model Pool**: If primary model encounters quota limits (`429`) or temporary server spikes (`503`), the agent automatically fails over across alternative models (`gemini-3-flash-preview`, `gemini-flash-lite-latest`, `gemini-3.1-flash-lite-preview`, `gemini-flash-latest`).
- **Intelligent Pacing & Exponential Backoff**: Automatically reads `retryDelay` from API responses to safely back off before retrying.
- **Pre-filtering Screener**: Keyword detection (`register by`, `deadline`, `due date`, `rsvp`, `closes on`) skips non-actionable marketing newsletters and receipts before calling the LLM.
- **Offline Heuristic Fallback**: Zero-dependency regex and `dateutil` fuzzy parser works 100% offline when no API key or network is present.

### 4. Approaching Deadline Alerts (< 1 Hour)
- **Automatic 1-Hour Monitoring**: Scans uncompleted deadlines expiring within 60 minutes (`ALERT_WINDOW_MINUTES=60`).
- **Native Windows Toast Notifications**: Dispatches native Windows desktop notifications via PowerShell runtime when running locally on Windows.
- **Audible Chime Alert**: Plays system alert chime when available.
- **Prominent Terminal Banner**: Renders high-visibility urgency banners.
- **Anti-Spam Alert State**: Tracks `last_alerted_at` timestamps to avoid repeated alert spamming.

### 5. Persistent State & Task Completion
- **State Store (`deadlines_state.json`)**: Active deadlines **remain in the list across runs** until explicitly marked completed.
- **Interactive Markdown Checkboxes**: In `deadlines.md`, users can change `- [ ]` to `- [x]`. The agent automatically detects and archives completed tasks on subsequent scans.
- **CLI Completion**: Direct command-line completion via `python main.py --complete <ID_or_Name>`.
- **Chronological Markdown Summary (`deadlines.md`)**: Automatically updated with urgency status indicators (Urgent <=48h, Upcoming 3-7d, Later >7d), action links, and completed task archive.

### 6. Web Application & Todo Dashboard
- **Web App (`python app.py` / `python main.py --web`)**: Modern web dashboard built with FastAPI, Vanilla CSS, and reactive JavaScript.
- **Interactive Todo Structure**:
  - Converts email deadlines into dynamic Todo task cards.
  - Interactive circular check-off button with smooth animation.
  - Checking off a task immediately removes it from the active list and moves it to the "Completed Archive".
  - One-click "Restore / Undo" capability to move tasks back to the active Todo list.
- **Search & Filter Controls**: Live text search across event titles, senders, and descriptions, plus urgency filter pills (All, Urgent <48h, Upcoming 3-7d, Later >7d).
- **On-Demand "Rescan Inbox" Button**: Instant rescan trigger directly from the web interface with loading state, refreshing deadlines immediately.
- **4-Hour Automatic Background Sync**:
  - Built-in background daemon loop asynchronously runs an inbox scan every 4 hours (`14,400` seconds).
  - Live header countdown timer showing real-time hours, minutes, and seconds until the next automatic scan.
  - Account connection indicator displaying connected email address.

### 7. Automated Test Suite
- 12 comprehensive unit tests covering connector, parsing accuracy, chronological sorting, 1-hour alert triggers, state deduplication, and markdown checkbox synchronization.
