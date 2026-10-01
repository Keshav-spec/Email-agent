# Implementation Plan: Email Deadline Agent

A robust, modular, Python-based background agent application that connects securely to email servers via IMAP, retrieves messages received **today** (both read and unread), extracts event and registration deadlines using **Google Gemini AI** (with rule-based fallback), dispatches **1-hour approaching deadline alerts** (Windows toast and sound chime), and maintains persistent active deadlines with **interactive completion checkboxes** in `deadlines.md`.

---

## 1. System Architecture

```mermaid
graph TD
    subgraph Input Sources
        A1[Live IMAP Server<br/>Gmail / Outlook / Custom] -->|SSL/TLS + App Password<br/>SINCE Today Query| B[Email Connector]
        A2[Mock Email Dataset<br/>Realistic Samples] -->|--mock flag| B
    end

    subgraph Core Processing Pipeline
        B -->|All Today's Messages Read + Unread| C[Email Content Extractor]
        C -->|Plain Text, HTML Links, Headers| D[Keyword Screener]
        D -->|Filtered Candidates| E[Deadline Parser Engine]
        
        subgraph Parsing Backends
            E -->|GEMINI_API_KEY| F1[Google Gemini 2.5 Flash]
            E -->|No API Key / Offline| F2[Heuristic Regex & dateutil Parser]
        end
        
        F1 --> G[Pydantic Validation & Normalizer]
        F2 --> G
    end

    subgraph State & Alerts
        G --> M[State Manager<br/>deadlines_state.json]
        M -->|Sync Checkboxes| MD1[deadlines.md Task Checkboxes]
        M --> AL[Alert System<br/>Window = 1 Hour]
        AL -->|Approaching <= 60m| W1[Windows Toast Notification]
        AL -->|Approaching <= 60m| W2[Audio Chime & Console Alert]
    end

    subgraph Output & Reporting
        M -->|Persistent Active & Completed Items| H[Markdown Reporter]
        M -->|Rich Terminal UI| I[Interactive CLI Output]
        H --> J[deadlines.md Report<br/>- [ ] Active & - [x] Completed]
        I --> K[Terminal Table Dashboard]
    end
```

---

## 2. Directory Structure

```text
agent/
├── .env.example              # Sample environment configuration template
├── .gitignore                # Protects credentials, logs, and venv
├── README.md                 # User instructions, setup guide, security practices
├── requirements.txt          # Python dependencies
├── main.py                   # Main entry point CLI & daemon
├── deadlines.md              # Output Markdown report with interactive checkboxes
├── deadlines_state.json      # Persistent tracking store
├── src/
│   ├── __init__.py
│   ├── alerts.py             # 1-hour approaching alert engine (Windows Toast + Audio Chime)
│   ├── config.py             # Environment settings & validation (Gemini, Today filter, 1h window)
│   ├── models.py             # Pydantic data schemas (EmailMessage, DeadlineItem, AgentRunSummary)
│   ├── connector.py          # IMAP client with SSL, SINCE Today query, HTML link extractor
│   ├── parser.py             # Intelligent deadline extraction (Gemini AI only + Heuristic fallback)
│   ├── reporter.py           # Markdown & terminal report generator with completion checkboxes
│   ├── state_manager.py      # Persistence manager, checkbox sync, deduplication
│   └── mock_data.py          # Sample dummy emails for zero-risk offline testing
└── tests/
    ├── __init__.py
    ├── test_connector.py     # Connector unit tests
    ├── test_parser.py        # Parser tests (mock emails, regex fallback)
    ├── test_reporter.py      # Markdown output formatting tests
    └── test_state_and_alerts.py # 1-hour alerts, completion sync, and persistence tests
```

---

## 3. Key Components & Implementation Details

### A. Configuration & Security (`src/config.py`)
- Employs `python-dotenv` to safely load configuration from `.env`.
- Gemini as the designated AI provider (`GEMINI_API_KEY`, `GEMINI_MODEL=gemini-2.5-flash`).
- `TODAY_ONLY=True`: Filters emails received today.
- `UNREAD_ONLY=False`: Scans all emails including read ones.
- `ALERT_WINDOW_MINUTES=60`: Configurable window for approaching deadline alerts.

### B. Secure Email Connector (`src/connector.py`)
- **IMAP over SSL (`imaplib.IMAP4_SSL`)**:
  - Validates TLS handshake.
  - Searches `(SINCE "DD-Mon-YYYY")` to fetch today's emails (read and unread).
- **Non-destructive Fetching**:
  - Uses `BODY.PEEK[]` query so unread emails stay unread during scanning.

### C. Gemini AI Parser (`src/parser.py`)
- Communicates directly with Google Gemini REST API.
- Prompts for strict JSON schema extracting Event Name, Normalized ISO Deadline, Verbatim text, Urgency, and Action URL.
- Zero-config rule-based fallback when offline or without API key.

### D. Alert System (`src/alerts.py`)
- Checks for deadlines expiring within 60 minutes.
- Fires native Windows Toast notifications, plays an audible chime, and displays high-visibility console banners.
- Tracks `last_alerted_at` to avoid repeated alert spam.

### E. State Manager & Checkbox Completion (`src/state_manager.py`)
- Active deadlines **remain** across runs until the user marks them complete.
- Two completion workflows:
  1. Check `- [x]` in `deadlines.md`: Auto-detected and archived on the next scan.
  2. CLI command: `python main.py --complete <ID_or_Name>`.
