"""
Alert and Notification module for Email Deadline Agent.
Monitors approaching deadlines (e.g. 1 hour before due time) and fires
Windows desktop toast notifications, audio chimes, and console alerts.
"""

import logging
import subprocess
import sys
from datetime import datetime, timezone
from typing import List, Optional
import winsound
from rich.console import Console
from rich.panel import Panel

from .models import DeadlineItem

logger = logging.getLogger("AlertSystem")

# Ensure UTF-8 console encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(file=sys.stdout, legacy_windows=False, force_terminal=True)


def send_audio_chime() -> None:
    """Plays standard Windows alert chime."""
    try:
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception as e:
        logger.debug(f"Audio chime could not be played: {e}")


def send_windows_toast(title: str, message: str) -> bool:
    """Dispatches a native Windows Toast notification via PowerShell."""
    # Sanitize inputs for PowerShell
    clean_title = title.replace('"', '`"').replace("'", "''")
    clean_msg = message.replace('"', '`"').replace("'", "''")

    ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName("text")
$textNodes.Item(0).AppendChild($template.CreateTextNode("{clean_title}")) | Out-Null
$textNodes.Item(1).AppendChild($template.CreateTextNode("{clean_msg}")) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Deadline Agent").Show($toast)
"""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=6,
            text=True
        )
        return res.returncode == 0
    except Exception as e:
        logger.debug(f"Windows Toast notification failed: {e}")
        return False


def check_and_trigger_alerts(
    items: List[DeadlineItem],
    window_seconds: int = 3600,
    ref_time: Optional[datetime] = None
) -> List[DeadlineItem]:
    """
    Checks all items for approaching deadlines within window_seconds (default: 1 hour)
    and fires audio chime, desktop toast, and console alerts.
    """
    if ref_time is None:
        ref_time = datetime.now(timezone.utc)

    alerted_items: List[DeadlineItem] = []

    for item in items:
        if item.is_completed:
            continue

        if item.is_alert_due(window_seconds=window_seconds, ref_time=ref_time):
            # Calculate exact minutes remaining
            mins_left = 60
            try:
                dt_clean = item.deadline_iso.replace("Z", "+00:00")
                parsed_dt = datetime.fromisoformat(dt_clean)
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                mins_left = max(1, int((parsed_dt - ref_time).total_seconds() / 60))
            except Exception:
                pass

            alert_title = f"🚨 DEADLINE ALERT: {item.event_name[:35]}"
            alert_msg = f"Due in ~{mins_left} minutes! ({item.deadline_text})"
            if item.action_link:
                alert_msg += f" - Link: {item.action_link}"

            # 1. Audio chime
            send_audio_chime()

            # 2. Desktop notification
            send_windows_toast(alert_title, alert_msg)

            # 3. High-visibility console banner
            try:
                console.print()
                console.print(Panel(
                    f"[bold white on red] [!] APPROACHING DEADLINE WARNING (< 1 HOUR) [/bold white on red]\n\n"
                    f"[bold yellow]Event:[/bold yellow] [bold white]{item.event_name}[/bold white]\n"
                    f"[bold yellow]Deadline:[/bold yellow] [bold red]{item.deadline_text}[/bold red] ([bold]{mins_left} mins remaining[/bold])\n"
                    f"[bold yellow]Action Link:[/bold yellow] [underline cyan]{item.action_link or 'None'}[/underline cyan]\n"
                    f"[dim]Mark complete in deadlines.md or run: python main.py --complete \"{item.id}\"[/dim]",
                    title="Action Required Immediately",
                    border_style="bold red"
                ))
                console.print()
            except Exception:
                print(f"\n*** [!] APPROACHING DEADLINE (< 1 HOUR): {item.event_name} due in ~{mins_left} mins! ***\n")

            # Mark alerted timestamp to avoid spamming
            item.last_alerted_at = ref_time.isoformat()
            alerted_items.append(item)

    return alerted_items
