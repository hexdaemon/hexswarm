#!/usr/bin/env python3
"""Hex MCP server implementation.

Hex (me) primarily receives callbacks and coordinates work, 
rather than executing tasks directly. This server handles:
- task_completed callbacks from other agents
- Status reporting for fleet coordination
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List

from agent_mcp.protocol import TaskRecord, TaskResult, TaskStatus
from agent_mcp.server import BaseAgentServer
from agent_mcp.storage import TaskStorage


class HexServer(BaseAgentServer):
    """MCP server for Hex (coordination agent)."""
    
    def __init__(self) -> None:
        storage_dir = Path(os.environ.get("HEX_TASK_DIR", "~/.agent/hex/tasks"))
        storage = TaskStorage(storage_dir)
        name = os.environ.get("HEX_AGENT_NAME", "hex")
        # My actual DID
        did = os.environ.get("HEX_AGENT_DID", "did:cid:bagaaieratn3qejd6mr4y2bk3nliriafoyeftt74tkl7il6bbvakfdupahkla")
        capabilities = ["coordination", "monitoring", "fleet-management"]
        super().__init__(name=name, did=did, capabilities=capabilities, storage=storage)

    async def execute_task(self, record: TaskRecord) -> TaskResult:
        """Hex doesn't execute tasks directly - delegates to other agents.
        
        This method handles any tasks that are explicitly sent to Hex,
        typically coordination or status requests.
        """
        task_type = record.request.type.value
        
        if task_type == "general":
            # For general tasks, Hex can provide status info or coordinate
            return TaskResult(
                task_id=record.task_id,
                status=TaskStatus.COMPLETED,
                result={
                    "message": "Hex coordination task completed",
                    "description": record.request.description[:100],
                },
                summary="Hex processed coordination request.",
            )
        else:
            # For code/research/analysis, Hex should delegate
            return TaskResult(
                task_id=record.task_id,
                status=TaskStatus.FAILED,
                result=None,
                summary=f"Hex does not execute {task_type} tasks directly. Use Codex or Gemini.",
            )


async def main() -> None:
    """Run the Hex MCP server."""
    server = HexServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
