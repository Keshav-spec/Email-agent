"""
Email Deadline Agent - Command Line Interface.
Connects to email, retrieves messages, extracts deadlines, monitors 1-hour
approaching alerts, and manages persistent deadline completion.
"""

import argparse
import logging
from pathlib import Path
import sys
import time
from datetime import datetime, timezone

# Ensure Windows terminal handles UTF-8 smoothly
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.alerts import check_and_trigger_alerts
from src.config import AgentConfig
from src.connector import EmailConnector
from src.mock_data import get_mock_emails
from src.models import EmailMessage
from src.parser import DeadlineParser
from src.reporter import MarkdownReporter, console
from src.state_manager import StateManager


def setup_logging(verbose: bool = False) -> None:
    """Configures console logging format and level."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)


def handle_completion(identifier: str, state_mgr: StateManager, output_path: str) -> None:
    """Marks a deadline completed and refreshes report."""
    item = state_mgr.mark_completed(identifier)
    if item:
        console.print(f"[bold green][DONE] Marked '{item.event_name}' (ID: {item.id}) as completed![/bold green]")
        # Refresh markdown report
        items = state_mgr.load_items()
        reporter = MarkdownReporter(output_path=output_path)
        summary = reporter.generate_summary(items=items, total_scanned=len(items))
        reporter.write_markdown(summary)
        console.print(f"[dim]Updated {output_path}[/dim]")
    else:
        console.print(f"[bold red][ERROR] No active deadline matching '{identifier}' was found.[/bold red]")


def handle_list(state_mgr: StateManager, output_path: str) -> None:
    """Lists all tracked deadlines and their statuses."""
    items = state_mgr.load_items()
    reporter = MarkdownReporter(output_path=output_path)
    summary = reporter.generate_summary(items=items, total_scanned=len(items))
    reporter.print_terminal_summary(summary)


def run_pipeline(
    config: AgentConfig,
    is_mock: bool = False,
    limit: int = 50,
    unread_only: bool = False,
    today_only: bool = True,
    mark_as_read: bool = False,
    output_path: str = "deadlines.md",
    dry_run: bool = False,
    ref_time: datetime = None,
) -> None:
    """Orchestrates sync, fetching, parsing, alerting, and reporting."""
    if ref_time is None:
        ref_time = datetime.now(timezone.utc)

    state_mgr = StateManager()

    # 1. Sync any checkboxes user checked as `- [x]` in deadlines.md
    md_file = Path(output_path)
    completed_from_md = state_mgr.sync_from_markdown(md_file)
    if completed_from_md:
        console.print(
            f"[bold green]Detected {len(completed_from_md)} newly completed tasks from {output_path} "
            f"checkboxes: {', '.join(completed_from_md)}[/bold green]"
        )

    # 2. Fetch Emails (Read + Unread from Today)
    emails = []
    if is_mock:
        console.print("[bold yellow][TEST] Running in MOCK TEST MODE with dummy email dataset...[/bold yellow]")
        emails = get_mock_emails()[:limit]
        console.print(f"[green]Loaded {len(emails)} synthetic email samples for evaluation.[/green]")
    else:
        config.validate_live_credentials()
        filter_desc = "today's messages (read + unread)" if today_only else "all messages"
        console.print(
            f"[bold cyan]Connecting to mail server {config.imap_host} as {config.email_address} "
            f"fetching {filter_desc}...[/bold cyan]"
        )
        with EmailConnector(config) as connector:
            emails = connector.fetch_emails(
                limit=limit,
                unread_only=unread_only,
                today_only=today_only,
                mark_as_read=mark_as_read
            )

    # 3. Extract Deadlines (Gemini)
    new_deadlines = []
    if emails:
        engine_label = "Gemini AI" if config.gemini_api_key else "Heuristic Engine"
        console.print(f"[bold cyan]Scanning {len(emails)} emails using {engine_label}...[/bold cyan]")
        parser = DeadlineParser(config)
        new_deadlines = parser.parse_batch(emails, ref_time=ref_time)
        console.print(f"[dim]Extracted {len(new_deadlines)} deadlines from batch.[/dim]")
    else:
        console.print("[dim]No new emails matched today's filter. Checking persistent tracked deadlines...[/dim]")

    # 4. Merge into persistent state (Deadlines REMAIN until completed!)
    all_tracked_items = state_mgr.merge_deadlines(new_deadlines)

    # 5. Check for approaching deadlines within 1 hour and trigger alerts!
    alert_sec = config.alert_window_minutes * 60
    alerted = check_and_trigger_alerts(all_tracked_items, window_seconds=alert_sec, ref_time=ref_time)
    if alerted:
        state_mgr.save_items(all_tracked_items)

    # 6. Generate Summary and render Reports
    reporter = MarkdownReporter(output_path=output_path)
    summary = reporter.generate_summary(
        items=all_tracked_items,
        total_scanned=len(emails),
        ref_time=ref_time
    )

    # Render interactive terminal table
    reporter.print_terminal_summary(summary)

    # Write Markdown file
    if not dry_run:
        reporter.write_markdown(summary)
        console.print(f"[bold green][SUCCESS] Report updated at '{output_path}'[/bold green]")
    else:
        console.print("[yellow]Dry-run mode: report was not saved to disk.[/yellow]")


def parse_arguments() -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(
        description="Autonomous Python Agent for extracting event & registration deadlines from email."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode with realistic sample emails (no live mailbox needed)",
    )
    parser.add_argument(
        "--complete",
        type=str,
        metavar="ID_OR_NAME",
        help="Mark a deadline task as completed by ID (e.g. 7a3b4f12) or partial event name",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Display all currently tracked active and completed deadlines",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of emails to scan",
    )
    parser.add_argument(
        "--today-only",
        dest="today_only",
        action="store_true",
        default=None,
        help="Limit scan to emails received today (default: True)",
    )
    parser.add_argument(
        "--all-dates",
        dest="today_only",
        action="store_false",
        help="Scan emails regardless of date received",
    )
    parser.add_argument(
        "--unread-only",
        dest="unread_only",
        action="store_true",
        default=None,
        help="Scan only unread messages",
    )
    parser.add_argument(
        "--read-all",
        dest="unread_only",
        action="store_false",
        help="Scan all messages (both read and unread, default: True)",
    )
    parser.add_argument(
        "--mark-read",
        action="store_true",
        default=None,
        help="Mark scanned emails as read on the mail server",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output Markdown report path (default: deadlines.md)",
    )
    parser.add_argument(
        "--alert-window",
        type=int,
        default=None,
        help="Approaching deadline alert window in minutes (default: 60)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results to console only; do not create or overwrite Markdown file",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously as a background service polling periodically and alerting",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Polling interval in seconds when running in daemon mode (default: 300s)",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch the interactive Todo Web UI dashboard on http://localhost:8000",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the Web UI server (default: 8000)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address for the Web UI server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed debug logs",
    )
    return parser.parse_args()


def main():
    """Application entry point."""
    args = parse_arguments()
    setup_logging(args.verbose)

    config = AgentConfig()

    # CLI argument overrides
    if args.limit is not None:
        config.fetch_limit = args.limit
    if args.unread_only is not None:
        config.unread_only = args.unread_only
    if args.today_only is not None:
        config.today_only = args.today_only
    if args.mark_read is not None:
        config.mark_as_read = args.mark_read
    if args.output:
        config.output_path = args.output
    if args.alert_window is not None:
        config.alert_window_minutes = args.alert_window

    state_mgr = StateManager()

    # Launch Web Server if --web passed
    if args.web:
        import uvicorn
        console.print(
            f"[bold magenta]Starting DeadlinePilot Web Hub at http://{args.host}:{args.port}[/bold magenta]\n"
            f"[dim]Background 4-hour auto-rescan is active. Press Ctrl+C to stop.[/dim]\n"
        )
        uvicorn.run("src.server:app", host=args.host, port=args.port, reload=False)
        return

    # If --complete command invoked
    if args.complete:
        handle_completion(args.complete, state_mgr, config.output_path)
        return

    # If --list command invoked
    if args.list:
        handle_list(state_mgr, config.output_path)
        return

    try:
        if args.daemon:
            console.print(
                f"[bold magenta]Starting Email Deadline Agent in Daemon Mode "
                f"(Polling every {args.interval}s, 1-hour Alert Window: {config.alert_window_minutes}m)...[/bold magenta]"
            )
            try:
                while True:
                    run_pipeline(
                        config=config,
                        is_mock=args.mock,
                        limit=config.fetch_limit,
                        unread_only=config.unread_only,
                        today_only=config.today_only,
                        mark_as_read=config.mark_as_read,
                        output_path=config.output_path,
                        dry_run=args.dry_run,
                    )
                    console.print(f"[dim]Sleeping for {args.interval} seconds... (Ctrl+C to stop)[/dim]\n")
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                console.print("\n[yellow]Daemon stopped by user.[/yellow]")
        else:
            run_pipeline(
                config=config,
                is_mock=args.mock,
                limit=config.fetch_limit,
                unread_only=config.unread_only,
                today_only=config.today_only,
                mark_as_read=config.mark_as_read,
                output_path=config.output_path,
                dry_run=args.dry_run,
            )
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
