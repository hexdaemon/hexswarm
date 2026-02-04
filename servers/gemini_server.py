#!/usr/bin/env python3
"""Gemini MCP server implementation."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import List

from agent_mcp.protocol import TaskRecord, TaskResult, TaskStatus
from agent_mcp.resources import parse_gemini_tokens
from agent_mcp.server import BaseAgentServer
from agent_mcp.storage import TaskStorage


def _build_prompt(record: TaskRecord) -> str:
    parts: List[str] = [record.request.description]
    if record.request.context:
        parts.append("Context:\n" + record.request.context)
    if record.request.files:
        parts.append("Files:\n" + "\n".join(record.request.files))
    if record.request.constraints:
        parts.append("Constraints:\n" + "\n".join(record.request.constraints))
    return "\n\n".join(parts)


class GeminiServer(BaseAgentServer):
    def __init__(self) -> None:
        storage_dir = Path(os.environ.get("GEMINI_TASK_DIR", "~/.agent/gemini/tasks"))
        storage = TaskStorage(storage_dir)
        name = os.environ.get("GEMINI_AGENT_NAME", "gemini")
        did = os.environ.get("GEMINI_AGENT_DID", "did:cid:gemini")
        capabilities = ["research", "analysis", "general"]
        super().__init__(name=name, did=did, capabilities=capabilities, storage=storage)

    async def execute_task(self, record: TaskRecord) -> TaskResult:
        cmd = os.environ.get("GEMINI_CLI", "gemini")
        timeout = record.request.timeout_seconds or int(os.environ.get("GEMINI_TASK_TIMEOUT", "1800"))
        workdir = os.environ.get("GEMINI_WORKDIR", os.path.expanduser("~/clawd"))
        prompt = _build_prompt(record)

        # Use --prompt for non-interactive mode, --yolo for auto-approve
        args = [cmd, "--prompt", prompt, "--yolo"]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise RuntimeError(f"Gemini task timed out after {timeout}s")

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        
        if proc.returncode != 0:
            # Check if stderr is empty, if so, maybe stdout has the error or it just failed
            error_msg = stderr_text.strip() or stdout_text.strip() or "Unknown error"
            raise RuntimeError(f"Gemini failed: {error_msg} (Exit: {proc.returncode})")

        # Parse token usage from output
        token_usage = parse_gemini_tokens(stdout_text)
        
        result_payload = stdout_text.strip()
        if record.request.output_format.value == "json":
            try:
                result_payload = json.loads(result_payload)
            except json.JSONDecodeError:
                pass

        return TaskResult(
            task_id=record.task_id,
            status=TaskStatus.COMPLETED,
            result=result_payload,
            summary="Gemini task completed.",
            token_usage=token_usage,
        )


async def main() -> None:
    server = GeminiServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
