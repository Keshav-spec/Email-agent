"""
Reporter module for formatting and exporting extracted email deadlines.
Generates structured Markdown reports (deadlines.md) with interactive completion
checkboxes, 1-hour approaching deadline alerts, and terminal tables.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import AgentRunSummary, DeadlineItem

# Configure Console with UTF-8 support
console = Console(file=sys.stdout, force_terminal=True, legacy_windows=False)


class MarkdownReporter:
    """Formats and exports deadline summaries to clean GitHub-flavored Markdown."""

    def __init__(self, output_path: str = "deadlines.md"):
        self.output_path = Path(output_path)

    def generate_summary(
        self, 
        items: List[DeadlineItem], 
        total_scanned: int,
        ref_time: Optional[datetime] = None
    ) -> AgentRunSummary:
        """Builds an AgentRunSummary object from parsed deadline items."""
        if ref_time is None:
            ref_time = datetime.now(timezone.utc)

        # Refresh urgencies
        for it in items:
            if not it.id:
                it.generate_id()
            it.compute_urgency(ref_time)

        # Active items sorted chronologically
        active_items = [it for it in items if not it.is_completed]
        active_sorted = sorted(active_items, key=lambda x: x.deadline_iso or "9999-99-99")
        completed_items = [it for it in items if it.is_completed]

        all_sorted = active_sorted + completed_items

        urgent_count = sum(1 for x in active_sorted if x.urgency == "Urgent")
        upcoming_count = sum(1 for x in active_sorted if x.urgency == "Upcoming")
        later_count = sum(1 for x in active_sorted if x.urgency == "Later")
        expired_count = sum(1 for x in active_sorted if x.urgency == "Expired")

        return AgentRunSummary(
            run_timestamp=ref_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            total_scanned=total_scanned,
            emails_with_deadlines=len(active_sorted),
            total_deadlines=len(active_sorted),
            urgent_count=urgent_count,
            upcoming_count=upcoming_count,
            later_count=later_count,
            expired_count=expired_count,
            items=all_sorted,
        )

    def write_markdown(self, summary: AgentRunSummary) -> str:
        """Writes the structured Markdown report with interactive checkboxes."""
        lines = []

        active_items = [it for it in summary.items if not it.is_completed]
        completed_items = [it for it in summary.items if it.is_completed]

        # Header & Metadata
        lines.append("# Email Deadline & Event Summary Report")
        lines.append("")
        lines.append(f"> **Report Generated:** `{summary.run_timestamp}`  ")
        lines.append(
            f"> **Status:** **{len(active_items)} active deadlines** remaining | "
            f"**{len(completed_items)} completed** | {summary.total_scanned} emails scanned today"
        )
        lines.append("")

        # Metrics badges / stats bar
        lines.append("### Active Deadlines Overview")
        lines.append("")
        lines.append("| Active Tasks | Urgent (<=48h) | Upcoming (3-7d) | Later (>7d) | Expired | Completed |")
        lines.append("|:---:|:---:|:---:|:---:|:---:|:---:|")
        lines.append(
            f"| **{len(active_items)}** | "
            f"**{summary.urgent_count}** | **{summary.upcoming_count}** | "
            f"**{summary.later_count}** | **{summary.expired_count}** | "
            f"**{len(completed_items)}** |"
        )
        lines.append("")
        lines.append(
            "> **How to complete a task:** Deadlines **remain active** until you complete them. "
            "Simply check the box `- [x]` below in this file (it will sync automatically on the next scan), "
            "or run: `python main.py --complete <ID_or_Name>`."
        )
        lines.append("")

        # Active Chronological Deadlines Table
        lines.append("## Active Deadlines Schedule")
        lines.append("")

        badge_map = {
            "Urgent": "**Urgent**",
            "Upcoming": "**Upcoming**",
            "Later": "Later",
            "Expired": "*Expired*",
            "Unknown": "Unknown",
        }

        if active_items:
            lines.append("| Status | ID | Event / Task | Deadline Date & Time | Time Remaining | Action Link | Complete |")
            lines.append("|:---|:---:|:---|:---|:---|:---|:---:|")

            for item in active_items:
                status_badge = badge_map.get(item.urgency, item.urgency)
                
                # Check for 1-hour approaching warning
                alert_prefix = ""
                if item.days_remaining is not None and 0 <= item.days_remaining * 24 <= 1.0:
                    alert_prefix = "**< 1 HOUR!** "

                # Format time remaining string
                if item.days_remaining is not None:
                    if item.days_remaining < 0:
                        time_rem = f"{abs(item.days_remaining):.1f}d ago"
                    elif item.days_remaining < 1:
                        hrs = max(1, int(item.days_remaining * 24))
                        mins = max(1, int(item.days_remaining * 1440))
                        if mins <= 60:
                            time_rem = f"**{mins} mins left!**"
                        else:
                            time_rem = f"**{hrs} hours left**"
                    else:
                        time_rem = f"{item.days_remaining:.1f} days left"
                else:
                    time_rem = "N/A"

                # Format action link
                if item.action_link:
                    action_md = f"[Register / Open]({item.action_link})"
                else:
                    action_md = "*(None listed)*"

                # Clean display datetime
                display_dt = item.deadline_text
                if item.deadline_iso:
                    try:
                        dt_obj = datetime.fromisoformat(item.deadline_iso.replace("Z", "+00:00"))
                        display_dt = dt_obj.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        display_dt = item.deadline_iso.split(".")[0].replace("T", " ")

                clean_title = item.event_name.replace("|", "-")
                lines.append(
                    f"| {alert_prefix}{status_badge} | `{item.id}` | **{clean_title}** | "
                    f"`{display_dt}` | {time_rem} | {action_md} | `[ ]` |"
                )
            lines.append("")
        else:
            lines.append("*No active pending deadlines. All caught up.*")
            lines.append("")

        lines.append("---")
        lines.append("")

        # Detailed Active Cards with Checkboxes
        lines.append("## Active Tasks & Action Items")
        lines.append("")

        if active_items:
            for idx, item in enumerate(active_items, 1):
                badge = badge_map.get(item.urgency, item.urgency)
                alert_banner = ""
                if item.days_remaining is not None and 0 <= item.days_remaining * 24 <= 1.0:
                    mins = max(1, int(item.days_remaining * 1440))
                    alert_banner = f"\n> **URGENT ALERT: This deadline expires in ~{mins} minutes!**\n"

                lines.append(f"### - [ ] {item.event_name}")
                if alert_banner:
                    lines.append(alert_banner)
                lines.append(f"- **Task ID:** `{item.id}` *(Complete CLI: `python main.py --complete \"{item.id}\"`)*")
                lines.append(f"- **Status:** {badge}")
                lines.append(f"- **Deadline:** `{item.deadline_text}`" + (f" *(Normalized: `{item.deadline_iso}`)*" if item.deadline_iso else ""))
                if item.days_remaining is not None:
                    lines.append(f"- **Countdown:** {item.days_remaining:.1f} days remaining")
                if item.action_link:
                    lines.append(f"- **Action / Registration Link:** [{item.action_link}]({item.action_link})")
                if item.summary:
                    lines.append(f"- **Summary:** {item.summary}")
                lines.append(f"- **Source Email:** `{item.source_subject}` from `{item.source_sender}`" + (f" on `{item.source_date}`" if item.source_date else ""))
                lines.append("")
        else:
            lines.append("*No active tasks.*")
            lines.append("")

        # Completed Section
        if completed_items:
            lines.append("---")
            lines.append("")
            lines.append("## Completed Tasks")
            lines.append("")
            lines.append("*(These deadlines were marked as completed and will remain archived)*")
            lines.append("")
            for item in completed_items:
                completed_on = item.completed_at or "Previously completed"
                lines.append(f"- [x] ~~**{item.event_name}**~~ — *Deadline: `{item.deadline_text}`* (Completed: `{completed_on}`)")
            lines.append("")

        content = "\n".join(lines) + "\n"
        self.output_path.write_text(content, encoding="utf-8")
        return content

    def print_terminal_summary(self, summary: AgentRunSummary) -> None:
        """Renders active deadlines table in terminal console."""
        active_items = [it for it in summary.items if not it.is_completed]
        completed_items = [it for it in summary.items if it.is_completed]

        console.print()
        console.print(Panel.fit(
            f"[bold cyan]Email Deadline Agent Report[/bold cyan]\n"
            f"[dim]Generated: {summary.run_timestamp}[/dim]\n"
            f"Active Deadlines: [bold green]{len(active_items)}[/bold green] "
            f"([red]{summary.urgent_count} Urgent[/red], [yellow]{summary.upcoming_count} Upcoming[/yellow]) | "
            f"Completed: [bold]{len(completed_items)}[/bold]",
            border_style="cyan"
        ))

        if not active_items:
            console.print("[green]No active deadlines pending! All tasks complete.[/green]\n")
            return

        table = Table(title="Active Action Deadlines", header_style="bold magenta", border_style="dim")
        table.add_column("ID", justify="center", style="dim", max_width=10)
        table.add_column("Urgency", justify="center", style="bold")
        table.add_column("Event / Task", style="cyan", no_wrap=False, max_width=30)
        table.add_column("Deadline", style="green", no_wrap=False, max_width=25)
        table.add_column("Remaining", justify="right")
        table.add_column("Action URL", style="blue underline", no_wrap=False, max_width=32)

        for item in active_items:
            if item.days_remaining is not None and 0 <= item.days_remaining * 24 <= 1.0:
                urg_style = "[bold white on red] < 1 HR! [/bold white on red]"
            elif item.urgency == "Urgent":
                urg_style = "[bold red]URGENT[/bold red]"
            elif item.urgency == "Upcoming":
                urg_style = "[bold yellow]UPCOMING[/bold yellow]"
            elif item.urgency == "Expired":
                urg_style = "[dim red]EXPIRED[/dim red]"
            else:
                urg_style = "[dim green]LATER[/dim green]"

            if item.days_remaining is not None:
                if item.days_remaining < 0:
                    rem_str = f"[red]{abs(item.days_remaining):.1f}d ago[/red]"
                elif item.days_remaining * 24 <= 1.0:
                    mins = max(1, int(item.days_remaining * 1440))
                    rem_str = f"[bold red]{mins}m left[/bold red]"
                elif item.days_remaining <= 2:
                    rem_str = f"[bold red]{item.days_remaining:.1f}d[/bold red]"
                else:
                    rem_str = f"{item.days_remaining:.1f}d"
            else:
                rem_str = "N/A"

            link_str = item.action_link or "[dim]None[/dim]"
            deadline_str = item.deadline_text or (item.deadline_iso or "Unknown")

            table.add_row(item.id, urg_style, item.event_name, deadline_str, rem_str, link_str)

        console.print(table)
        console.print(
            f"[dim]Mark complete by checking `- [x]` in [bold]{self.output_path.name}[/bold] "
            f"or run: [bold cyan]python main.py --complete <ID>[/bold cyan][/dim]\n"
        )
