"""Agent completion notifications - allows agents to signal task completion."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict


NOTIFICATIONS_DIR = Path(os.environ.get("AGENT_NOTIFICATIONS_DIR", "~/.agent/notifications")).expanduser()


@dataclass
class TaskCompletion:
    """Notification that a task completed."""
    task_id: str
    agent_name: str
    status: str  # "completed" | "failed"
    summary: str
    result: Optional[Any] = None
    error: Optional[str] = None
    files_created: Optional[list] = None
    completed_at: float = None
    
    def __post_init__(self):
        if self.completed_at is None:
            self.completed_at = time.time()


def ensure_dirs():
    """Create notification directories."""
    NOTIFICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    (NOTIFICATIONS_DIR / "pending").mkdir(exist_ok=True)
    (NOTIFICATIONS_DIR / "processed").mkdir(exist_ok=True)


def notify_completion(
    task_id: str,
    agent_name: str,
    status: str,
    summary: str,
    result: Any = None,
    error: str = None,
    files_created: list = None,
) -> Path:
    """
    Write a completion notification that Hex can check.
    
    Called by agents when they finish a task (e.g., from tmux).
    
    Usage from shell:
        python -c "from agent_mcp.notifications import notify_completion; notify_completion('task123', 'codex', 'completed', 'Created shared_memory.py')"
    """
    ensure_dirs()
    
    notification = TaskCompletion(
        task_id=task_id,
        agent_name=agent_name,
        status=status,
        summary=summary,
        result=result,
        error=error,
        files_created=files_created,
    )
    
    filename = f"{agent_name}_{task_id}_{int(notification.completed_at)}.json"
    path = NOTIFICATIONS_DIR / "pending" / filename
    payload = asdict(notification)
    path.write_text(json.dumps(payload, indent=2, default=str))

    # Also write a signed receipt file (doesn't break existing tooling)
    try:
        from .archon_utils import sign_json
        signed = sign_json({
            "type": "hexswarmCompletionReceipt",
            "issuer": "did:cid:bagaaieratn3qejd6mr4y2bk3nliriafoyeftt74tkl7il6bbvakfdupahkla",
            "payload": payload,
        })
        if signed:
            signed_path = path.with_suffix(".signed.json")
            signed_path.write_text(json.dumps(signed, indent=2, default=str))
    except Exception:
        pass

    # Also log to HexMem (daily log + events)
    try:
        from .shared_memory import log_agent_event, log_daily_log
        log_agent_event(agent_name, "hexswarm_completion", f"{status}: {task_id}", summary)
        log_daily_log(
            "ops",
            f"hexswarm completion: {agent_name} {status}",
            f"{task_id}: {summary}",
            source="hexswarm",
        )
    except Exception:
        pass

    return path


def check_notifications(agent_name: str = None) -> list[Dict[str, Any]]:
    """
    Check for pending completion notifications.
    
    Returns list of notifications, optionally filtered by agent.
    """
    ensure_dirs()
    
    notifications = []
    pending_dir = NOTIFICATIONS_DIR / "pending"
    
    for path in pending_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            if agent_name is None or data.get("agent_name") == agent_name:
                data["_path"] = str(path)
                notifications.append(data)
        except (json.JSONDecodeError, IOError):
            continue
    
    return sorted(notifications, key=lambda x: x.get("completed_at", 0))


def acknowledge_notification(notification: Dict[str, Any]) -> bool:
    """Move a notification from pending to processed."""
    path = Path(notification.get("_path", ""))
    if not path.exists():
        return False
    
    processed_path = NOTIFICATIONS_DIR / "processed" / path.name
    path.rename(processed_path)
    return True


def clear_old_notifications(max_age_hours: int = 24):
    """Clean up old processed notifications."""
    ensure_dirs()
    cutoff = time.time() - (max_age_hours * 3600)
    
    for path in (NOTIFICATIONS_DIR / "processed").glob("*.json"):
        try:
            data = json.loads(path.read_text())
            if data.get("completed_at", 0) < cutoff:
                path.unlink()
        except (json.JSONDecodeError, IOError):
            path.unlink()


# Shell helper for agents to call
NOTIFY_SHELL_CMD = '''
python3 -c "
import sys
sys.path.insert(0, '/home/sat/bin/agent-mcp')
from agent_mcp.notifications import notify_completion
notify_completion(
    task_id='$TASK_ID',
    agent_name='$AGENT_NAME', 
    status='$STATUS',
    summary='$SUMMARY'
)
print('Notification sent')
"
'''
