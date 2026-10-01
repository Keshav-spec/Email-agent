"""
FastAPI Web Server for Email Deadline Agent.
Provides REST APIs for:
- Fetching active & completed Todo items
- Interactive deadline completion, undo, and deletion
- On-demand Rescan button triggering live email fetch + Gemini extraction
- 4-Hour background auto-rescan scheduler
- Serving the frontend web interface
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .alerts import check_and_trigger_alerts
from .config import AgentConfig
from .connector import EmailConnector
from .mock_data import get_mock_emails
from .models import DeadlineItem, EmailMessage
from .parser import DeadlineParser
from .reporter import MarkdownReporter
from .state_manager import StateManager

logger = logging.getLogger("DeadlineServer")
ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"

# Global state tracking
server_state = {
    "is_scanning": False,
    "last_scan_at": None,
    "last_scan_status": "Idle",
    "last_emails_scanned": 0,
    "last_deadlines_found": 0,
    "next_auto_scan_at": None,
    "auto_scan_interval_seconds": 4 * 3600,  # 4 hours
}


def perform_scan(is_mock: bool = False) -> dict:
    """Executes email scan, extraction, alert check, and markdown sync."""
    server_state["is_scanning"] = True
    server_state["last_scan_status"] = "Scanning emails..."
    config = AgentConfig()
    state_mgr = StateManager()
    ref_time = datetime.now(timezone.utc)

    try:
        # 1. Sync markdown checkboxes
        state_mgr.sync_from_markdown(Path(config.output_path))

        # 2. Fetch Emails
        emails: List[EmailMessage] = []
        if is_mock or not config.email_address or "xxxx" in config.email_password:
            emails = get_mock_emails()
        else:
            with EmailConnector(config) as connector:
                emails = connector.fetch_emails(
                    limit=config.fetch_limit,
                    unread_only=config.unread_only,
                    today_only=config.today_only,
                    mark_as_read=config.mark_as_read
                )

        server_state["last_emails_scanned"] = len(emails)

        # 3. Extract deadlines with Gemini
        new_items = []
        if emails:
            parser = DeadlineParser(config)
            new_items = parser.parse_batch(emails, ref_time=ref_time)

        server_state["last_deadlines_found"] = len(new_items)

        # 4. Merge into state
        all_items = state_mgr.merge_deadlines(new_items)

        # 5. Check 1-hour approaching alerts
        alert_sec = config.alert_window_minutes * 60
        check_and_trigger_alerts(all_items, window_seconds=alert_sec, ref_time=ref_time)
        state_mgr.save_items(all_items)

        # 6. Update deadlines.md report
        reporter = MarkdownReporter(output_path=config.output_path)
        summary = reporter.generate_summary(items=all_items, total_scanned=len(emails), ref_time=ref_time)
        reporter.write_markdown(summary)

        now = datetime.now(timezone.utc)
        server_state["last_scan_at"] = now.isoformat()
        server_state["next_auto_scan_at"] = (now + timedelta(seconds=server_state["auto_scan_interval_seconds"])).isoformat()
        server_state["last_scan_status"] = f"Completed successfully ({len(new_items)} deadlines found)"

        return {
            "success": True,
            "emails_scanned": len(emails),
            "deadlines_found": len(new_items),
            "active_deadlines": sum(1 for it in all_items if not it.is_completed),
            "timestamp": now.isoformat()
        }

    except Exception as e:
        logger.error(f"Scan error: {e}")
        server_state["last_scan_status"] = f"Error: {str(e)[:100]}"
        return {"success": False, "error": str(e)}
    finally:
        server_state["is_scanning"] = False


async def auto_scan_worker():
    """Background task that runs perform_scan every 4 hours."""
    # Perform initial scan on startup after 3 seconds
    await asyncio.sleep(3)
    logger.info("Triggering initial email scan on startup...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, perform_scan, False)

    while True:
        try:
            interval = server_state["auto_scan_interval_seconds"]
            logger.info(f"Next auto-scan in {interval // 3600} hours...")
            await asyncio.sleep(interval)
            logger.info("Executing scheduled 4-hour auto-rescan...")
            await loop.run_in_executor(None, perform_scan, False)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in auto-scan worker: {e}")
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages background 4-hour scheduler lifecycle."""
    now = datetime.now(timezone.utc)
    server_state["next_auto_scan_at"] = (now + timedelta(seconds=server_state["auto_scan_interval_seconds"])).isoformat()
    worker_task = asyncio.create_task(auto_scan_worker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Email Deadline Agent Web UI", lifespan=lifespan)

# Mount static web directory
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the main web dashboard."""
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>Web UI is initializing... Please refresh in a moment.</h1>")


@app.get("/api/deadlines")
async def get_deadlines():
    """Returns active and completed deadline items with real-time countdowns."""
    config = AgentConfig()
    state_mgr = StateManager()
    ref_time = datetime.now(timezone.utc)

    # Sync markdown checkboxes first
    state_mgr.sync_from_markdown(Path(config.output_path))
    items = state_mgr.load_items()

    for it in items:
        if not it.id:
            it.generate_id()
        it.compute_urgency(ref_time)

    active_items = [it for it in items if not it.is_completed]
    active_sorted = sorted(active_items, key=lambda x: x.deadline_iso or "9999-99-99")
    completed_items = [it for it in items if it.is_completed]

    urgent_count = sum(1 for x in active_sorted if x.urgency == "Urgent")
    upcoming_count = sum(1 for x in active_sorted if x.urgency == "Upcoming")
    approaching_1h = sum(
        1 for x in active_sorted 
        if x.days_remaining is not None and 0 <= x.days_remaining * 24 <= 1.0
    )

    return {
        "active_items": [it.model_dump() for it in active_sorted],
        "completed_items": [it.model_dump() for it in completed_items],
        "stats": {
            "total_active": len(active_sorted),
            "urgent": urgent_count,
            "upcoming": upcoming_count,
            "approaching_1h": approaching_1h,
            "completed": len(completed_items),
        },
        "config": {
            "email_address": config.email_address or "Not configured",
            "model": config.gemini_model,
            "today_only": config.today_only,
            "auto_interval_hours": server_state["auto_scan_interval_seconds"] // 3600,
        },
        "status": server_state
    }


@app.post("/api/deadlines/{item_id}/complete")
async def mark_complete(item_id: str):
    """Marks a deadline task as completed."""
    state_mgr = StateManager()
    config = AgentConfig()
    item = state_mgr.mark_completed(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Deadline item not found")

    # Refresh deadlines.md
    items = state_mgr.load_items()
    reporter = MarkdownReporter(output_path=config.output_path)
    summary = reporter.generate_summary(items=items, total_scanned=len(items))
    reporter.write_markdown(summary)

    return {"success": True, "item": item.model_dump()}


@app.post("/api/deadlines/{item_id}/uncomplete")
async def mark_uncomplete(item_id: str):
    """Restores a completed deadline back to active status."""
    state_mgr = StateManager()
    config = AgentConfig()
    items = state_mgr.load_items()
    target = None

    for it in items:
        if it.id == item_id or it.event_name.lower() == item_id.lower():
            it.is_completed = False
            it.completed_at = None
            target = it
            break

    if not target:
        raise HTTPException(status_code=404, detail="Deadline item not found")

    state_mgr.save_items(items)

    # Refresh deadlines.md
    reporter = MarkdownReporter(output_path=config.output_path)
    summary = reporter.generate_summary(items=items, total_scanned=len(items))
    reporter.write_markdown(summary)

    return {"success": True, "item": target.model_dump()}


@app.delete("/api/deadlines/{item_id}")
async def delete_deadline(item_id: str):
    """Permanently deletes a deadline item from tracking."""
    state_mgr = StateManager()
    config = AgentConfig()
    items = state_mgr.load_items()
    filtered = [it for it in items if it.id != item_id and it.event_name.lower() != item_id.lower()]

    if len(filtered) == len(items):
        raise HTTPException(status_code=404, detail="Item not found")

    state_mgr.save_items(filtered)

    # Refresh deadlines.md
    reporter = MarkdownReporter(output_path=config.output_path)
    summary = reporter.generate_summary(items=filtered, total_scanned=len(filtered))
    reporter.write_markdown(summary)

    return {"success": True, "deleted_id": item_id}


@app.post("/api/rescan")
async def trigger_rescan(background_tasks: BackgroundTasks, is_mock: bool = False):
    """Triggers an on-demand rescan of the inbox."""
    if server_state["is_scanning"]:
        return {"success": False, "message": "Scan already in progress"}

    # Run in threadpool executor so it doesn't block FastAPI
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, perform_scan, is_mock)
    return result


@app.get("/api/status")
async def get_status():
    """Returns server background status and scan countdown."""
    return server_state
