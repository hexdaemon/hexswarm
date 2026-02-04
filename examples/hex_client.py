#!/usr/bin/env python3
"""Example client: Hex submits a task to Codex and polls for result."""

from __future__ import annotations

import time

from agent_mcp.client import MCPClient


def main() -> None:
    client = MCPClient("codex")
    response = client.call(
        "submit_task",
        type="code",
        description="Add hive_fleet_snapshot to MCP server",
        files=["/home/sat/bin/cl-hive/tools/mcp-hive-server.py"],
        callback="hex.task_completed",
    )
    task_id = response.get("task_id")
    print("Submitted:", response)

    if not task_id:
        return

    while True:
        status = client.call("task_status", task_id=task_id)
        print("Status:", status)
        if status.get("status") in {"completed", "failed", "cancelled"}:
            break
        time.sleep(2)

    result = client.call("task_result", task_id=task_id)
    print("Result:", result)


if __name__ == "__main__":
    main()
