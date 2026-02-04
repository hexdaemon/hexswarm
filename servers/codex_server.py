#!/usr/bin/env python3
"""Codex MCP server implementation."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import List

from agent_mcp.protocol import TaskRecord, TaskResult, TaskStatus
from agent_mcp.resources import parse_codex_tokens
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


class CodexServer(BaseAgentServer):
    def __init__(self) -> None:
        storage_dir = Path(os.environ.get("CODEX_TASK_DIR", "~/.agent/codex/tasks"))
        storage = TaskStorage(storage_dir)
        name = os.environ.get("CODEX_AGENT_NAME", "codex")
        did = os.environ.get("CODEX_AGENT_DID", "did:cid:codex")
        capabilities = ["code", "analysis"]
        super().__init__(name=name, did=did, capabilities=capabilities, storage=storage)

    async def execute_task(self, record: TaskRecord) -> TaskResult:
        cmd = os.environ.get("CODEX_CLI", "codex")
        timeout = record.request.timeout_seconds or int(os.environ.get("CODEX_TASK_TIMEOUT", "1800"))
        workdir = os.environ.get("CODEX_WORKDIR", os.path.expanduser("~/clawd"))
        prompt = _build_prompt(record)

        # Use 'codex exec' for non-interactive execution
        # Run from a trusted git directory to avoid security checks
        args = [cmd, "exec", prompt]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"Codex task timed out after {timeout}s")

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"Codex failed: {stderr_text.strip()}")

        # Parse token usage from stderr (Codex outputs tokens there)
        token_usage = parse_codex_tokens(stderr_text)
        
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
            summary="Codex task completed.",
            token_usage=token_usage,
        )


async def main() -> None:
    server = CodexServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
