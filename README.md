# 📅 Email Deadline Agent

A secure, autonomous Python background agent that connects to your mailbox (via IMAP SSL), scans all emails received **today** (including both read and unread messages), extracts registration and event deadlines using **Google Gemini AI**, monitors for deadlines approaching within **1 hour** to dispatch **instant desktop alerts**, and maintains a persistent, actionable Markdown report (`deadlines.md`) where deadlines **remain active until you mark them complete**.

---

## ✨ Key Features & Updates

- **🔔 1-Hour Approaching Deadline Alerts**:
  - Automatically triggers when any uncompleted deadline is within **60 minutes** of expiration.
  - Sends a **native Windows Toast notification** directly to your desktop.
  - Plays an audible alert chime (`winsound`).
  - Highlights a prominent red action banner in the terminal console.
  - Built-in anti-spam tracking ensures you are notified cleanly without repeat bombardment.
- **♊ Google Gemini as Sole AI Model**:
  - Direct integration with Google Gemini (`gemini-2.5-flash` / Pro).
  - Just add your `GEMINI_API_KEY` to `.env`.
  - Includes a zero-config offline rule-based heuristic fallback if testing offline or in mock mode.
- **📬 Scans Today's Emails (Read & Unread)**:
  - Defaults to `TODAY_ONLY=True` and `UNREAD_ONLY=False`.
  - Uses IMAP `SINCE <Today>` to retrieve all messages that arrived today, regardless of whether you've already opened them.
- **☑️ Persistent Deadlines & Completion Option**:
  - Deadlines **remain on the active list across runs** until you complete them.
  - **Option 1 (In Markdown)**: Simply check the task box `- [x]` directly in `deadlines.md`. The agent automatically detects the checkmark on the next run and archives it!
  - **Option 2 (Via CLI)**: Run `python main.py --complete <ID_or_Name>` (e.g. `python main.py --complete adc4863f`).
  - Completed items are neatly moved to `## ✅ Completed Tasks` with timestamped completion records.
- **🔒 Non-Destructive IMAP SSL**:
  - Uses `BODY.PEEK[]` query so inbox read/unread flags remain untouched unless you explicitly ask to mark them as read (`--mark-read`).

---

## 📁 Project Architecture

```text
agent/
├── .env.example              # Environment template with Gemini & IMAP instructions
├── .gitignore                # Protects credentials (.env), state, and caches
├── README.md                 # Documentation and user guide
├── requirements.txt          # Python dependencies
├── main.py                   # Main CLI entry point & background daemon
├── deadlines.md              # Auto-updating Markdown dashboard with task checkboxes
├── deadlines_state.json      # Persistent tracking store for deadline completion & alert status
├── src/
│   ├── __init__.py           # Package marker
│   ├── alerts.py             # 1-hour approaching alert engine (Windows Toast + Audio Chime)
│   ├── config.py             # Configuration loader (dotenv, Gemini, Today filter, 1h window)
│   ├── connector.py          # IMAP SSL client, SINCE Today query, HTML link extractor
│   ├── mock_data.py          # Realistic dummy email dataset for safe offline testing
│   ├── models.py             # Pydantic schemas (EmailMessage, DeadlineItem, AgentRunSummary)
│   ├── parser.py             # Google Gemini extraction engine & heuristic fallback
│   ├── reporter.py           # Markdown generator with interactive checkboxes & Rich tables
│   └── state_manager.py      # Persistence manager, Markdown checkbox sync, deduplication
└── tests/
    ├── test_connector.py     # RFC 2047 decoding, MIME and HTML link parsing tests
    ├── test_parser.py        # Date extraction and negative newsletter screening tests
    ├── test_reporter.py      # Markdown formatting and urgency sorting tests
    └── test_state_and_alerts.py # 1-hour alerts, completion sync, and persistence tests
```

---

## 🚀 Quick Start (Zero-Setup Mock Mode)

Test the complete agent and alert system right away without live credentials:

```bash
# 1. Install dependencies (if not already installed)
pip install -r requirements.txt

# 2. Run in Mock Mode
python main.py --mock
```

You will see:
- 6 synthetic email samples evaluated.
- Deadlines extracted and assigned unique Task IDs.
- Terminal table with urgency levels.
- Updated `deadlines.md` generated with interactive task checkboxes!

---

## ⚙️ Live Mailbox Setup

### Step 1: Create your `.env` file
```bash
copy .env.example .env
```

### Step 2: Configure Credentials in `.env`
```env
# 1. Email Account (IMAP)
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_PASSWORD=abcd efgh ijkl mnop   # 16-character Google App Password
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
USE_SSL=True

# 2. Google Gemini API (Only AI Engine)
GEMINI_API_KEY=your_actual_gemini_api_key_from_aistudio
GEMINI_MODEL=gemini-2.5-flash

# 3. Agent Runtime Behavior
TODAY_ONLY=True             # Scan emails received today
UNREAD_ONLY=False           # Read both read and unread messages
ALERT_WINDOW_MINUTES=60     # Alert 1 hour before approaching deadline
FETCH_LIMIT=50              # Maximum emails to scan today
OUTPUT_PATH=deadlines.md
```

*(Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com/)).*

---

## 💻 CLI Commands & Usage

### 1. Scan Today's Emails
Fetches all emails from today (read and unread), checks for deadlines, fires 1-hour alerts if due, and updates `deadlines.md`:
```bash
python main.py
```

### 2. Marking Deadlines as Complete
Active deadlines **remain** on the list until completed. You have two easy ways to complete them:

#### Method A: Directly in `deadlines.md`
Open `deadlines.md` in your editor or GitHub/IDE preview and check the box from `[ ]` to `[x]`:
```markdown
### - [x] CS610: Final Project Proposal - Due Date Announcement
```
The agent automatically detects the checked box on the next scan and archives the task!

#### Method B: From the Terminal
```bash
# Mark complete using the Task ID:
python main.py --complete adc4863f

# Or mark complete using partial event title:
python main.py --complete "CS610"
```

### 3. List All Tracked Deadlines
Inspect current active and completed tasks in the terminal without fetching new emails:
```bash
python main.py --list
```

### 4. Background Daemon Mode (With 1-Hour Alerts)
Runs continuously in the background, checking mailbox and monitoring approaching deadlines every 5 minutes (300s):
```bash
python main.py --daemon --interval 300
```
When a deadline enters the 1-hour window, you will receive an immediate Windows Toast notification and audio chime on your desktop!

### 5. CLI Flags Reference

| Flag | Description | Default |
|---|---|---|
| `--mock` | Run in offline test mode with synthetic dummy emails | `False` |
| `--complete <ID_or_NAME>` | Mark a deadline completed by ID or event name | None |
| `--list` | Display current active and completed deadlines | `False` |
| `--today-only` | Scan only emails received today | `True` |
| `--all-dates` | Scan emails regardless of date received | `False` |
| `--unread-only` | Scan only unread emails | `False` |
| `--read-all` | Scan all emails (both read and unread) | `True` |
| `--alert-window <mins>`| Window in minutes for approaching alerts | `60` |
| `--daemon` | Run continuously in background polling loop | `False` |
| `--interval <sec>` | Polling interval in seconds for daemon mode | `300` |
| `--output <path>` | Path for output Markdown report | `deadlines.md` |
| `--dry-run` | Print terminal output without modifying files | `False` |

---

## 🧪 Running Automated Tests

Run the full automated test suite (12 tests covering connector, Gemini/heuristic parser, markdown reporter, state manager, and 1-hour alert triggers):

```bash
python -m unittest discover tests -v
```

Expected output:
```text
test_decode_header_plain (test_connector.TestEmailConnector) ... ok
test_decode_header_rfc2047 (test_connector.TestEmailConnector) ... ok
test_has_deadline_indicators (test_connector.TestEmailConnector) ... ok
test_html_cleaning_and_link_extraction (test_connector.TestEmailConnector) ... ok
test_chronological_ordering (test_parser.TestDeadlineParser) ... ok
test_hackathon_extraction (test_parser.TestDeadlineParser) ... ok
test_mock_emails_extraction_count (test_parser.TestDeadlineParser) ... ok
test_markdown_generation (test_reporter.TestMarkdownReporter) ... ok
test_1_hour_approaching_alert (test_state_and_alerts.TestStateAndAlerts) ... ok
test_deadline_id_generation (test_state_and_alerts.TestStateAndAlerts) ... ok
test_state_merge_and_mark_completed (test_state_and_alerts.TestStateAndAlerts) ... ok
test_sync_completion_from_markdown_checkbox (test_state_and_alerts.TestStateAndAlerts) ... ok

----------------------------------------------------------------------
Ran 12 tests in 0.35s

OK
```
