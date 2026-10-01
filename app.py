"""
Direct launcher for DeadlinePilot Web Application.
Run with:
    python app.py
"""

import sys
import uvicorn

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    
    print(f"\n========================================================")
    print(f"  ⚡ DeadlinePilot Web Application")
    print(f"  Access Dashboard: http://{host}:{port}")
    print(f"  Auto-rescan: Every 4 hours in background")
    print(f"========================================================\n")
    uvicorn.run("src.server:app", host=host, port=port, reload=False)
