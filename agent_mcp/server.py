"""Base MCP server for agents."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .auth import verify_auth
from .protocol import TaskRecord, TaskRequest, TaskResult, TaskStatus, SUBMIT_TASK_SCHEMA
from .resources import ResourceTracker, parse_codex_tokens, parse_gemini_tokens
from .storage import TaskStorage
from .shared_memory import (
    log_agent_event, share_fact, get_shared_context, record_handoff,
    share_lesson, get_lessons_for_domain, get_agent_lessons, search_lessons,
)
from .context_builder import (
    build_task_context, record_agent_performance, get_agent_performance,
    get_best_agent_for_task,
)
from .notifications import check_notifications, acknowledge_notification, notify_completion


class BaseAgentServer:
    def __init__(
        self,
        name: str,
        did: str,
        capabilities: List[str],
        storage: TaskStorage,
        version: str = "0.1.0",
    ) -> None:
        self.name = name
        self.did = did
        self.capabilities = capabilities
        self.version = version
        self.storage = storage
        self.server = Server(name)
        self._tasks: Dict[str, TaskRecord] = {}
        self._task_futures: Dict[str, asyncio.Task] = {}
        self._started_at = time.time()
        self.resource_tracker = ResourceTracker()

        self._load_tasks()
        self._register_tools()

    def _load_tasks(self) -> None:
        self._tasks = self.storage.load_all()
        for record in list(self._tasks.values()):
            if record.status == TaskStatus.RUNNING:
                record.status = TaskStatus.FAILED
                record.completed_at = datetime.utcnow().isoformat()
                record.error = "Server restarted while task was running."
                self.storage.write_task(record)

    def _register_tools(self) -> None:
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(
                    name="agent_info",
                    description="Return agent identity and capabilities.",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="agent_status",
                    description="Return agent availability and queue status.",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="submit_task",
                    description="Submit a task to the agent.",
                    inputSchema=SUBMIT_TASK_SCHEMA,
                ),
                Tool(
                    name="task_status",
                    description="Get status of a task.",
                    inputSchema={
                        "type": "object",
                        "properties": {"task_id": {"type": "string"}},
                        "required": ["task_id"],
                    },
                ),
                Tool(
                    name="task_result",
                    description="Get result of a completed task.",
                    inputSchema={
                        "type": "object",
                        "properties": {"task_id": {"type": "string"}},
                        "required": ["task_id"],
                    },
                ),
                Tool(
                    name="cancel_task",
                    description="Cancel a pending or running task.",
                    inputSchema={
                        "type": "object",
                        "properties": {"task_id": {"type": "string"}, "reason": {"type": "string"}},
                        "required": ["task_id"],
                    },
                ),
                Tool(
                    name="agent_resources",
                    description="Get resource usage for all agents (context, tokens, capacity).",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="agent_memory",
                    description="Share and query memory via HexMem.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "log_event", "share_fact", "get_context", "record_handoff",
                                    "share_lesson", "get_lessons", "search_lessons", "get_agent_lessons",
                                ],
                            },
                            "agent_name": {"type": "string"},
                            "event_type": {"type": "string"},
                            "summary": {"type": "string"},
                            "details": {"type": "string"},
                            "subject": {"type": "string"},
                            "predicate": {"type": "string"},
                            "object": {"type": "string"},
                            "topic": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                            "from_agent": {"type": "string"},
                            "to_agent": {"type": "string"},
                            "task_id": {"type": "string"},
                            "reason": {"type": "string"},
                            "domain": {"type": "string"},
                            "lesson": {"type": "string"},
                            "context": {"type": "string"},
                            "query": {"type": "string"},
                        },
                        "required": ["action"],
                    },
                ),
                Tool(
                    name="agent_performance",
                    description="Track and query agent performance on task types.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["record", "get_stats", "best_for_task"],
                            },
                            "agent_name": {"type": "string"},
                            "task_type": {"type": "string"},
                            "success": {"type": "boolean"},
                            "duration_seconds": {"type": "number"},
                            "tokens_used": {"type": "integer"},
                            "available_agents": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["action"],
                    },
                ),
                Tool(
                    name="check_notifications",
                    description="Check for task completion notifications from other agents.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_name": {"type": "string", "description": "Filter by agent name"},
                            "acknowledge": {"type": "boolean", "description": "Mark notifications as processed"},
                        },
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            try:
                if name == "agent_info":
                    result = self.agent_info()
                elif name == "agent_status":
                    result = self.agent_status()
                elif name == "submit_task":
                    result = await self.submit_task(arguments)
                elif name == "task_status":
                    result = self.task_status(arguments.get("task_id", ""))
                elif name == "task_result":
                    result = self.task_result(arguments.get("task_id", ""))
                elif name == "cancel_task":
                    result = await self.cancel_task(arguments.get("task_id", ""), arguments.get("reason"))
                elif name == "agent_resources":
                    result = self.agent_resources()
                elif name == "agent_memory":
                    result = self.agent_memory(arguments)
                elif name == "agent_performance":
                    result = self.agent_performance(arguments)
                elif name == "check_notifications":
                    result = self.check_agent_notifications(arguments)
                else:
                    result = {"error": f"Unknown tool: {name}"}
            except Exception as e:
                result = {"error": str(e)}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

    def agent_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "did": self.did,
            "capabilities": self.capabilities,
            "status": "ready" if not self._task_futures else "busy",
            "version": self.version,
        }

    def agent_status(self) -> Dict[str, Any]:
        current_task = None
        for task_id, future in self._task_futures.items():
            if not future.done():
                current_task = task_id
                break
        return {
            "status": "busy" if current_task else "ready",
            "current_task": current_task,
            "queue_depth": len(self._task_futures),
            "uptime_seconds": int(time.time() - self._started_at),
        }

    def agent_resources(self) -> Dict[str, Any]:
        """Get resource status for all tracked agents."""
        summary = self.resource_tracker.status_summary()
        # Add best agent recommendations
        best_for_code = self.resource_tracker.best_agent_for("code")
        best_for_research = self.resource_tracker.best_agent_for("research")
        return {
            "agents": summary,
            "recommendations": {
                "code": best_for_code or "hex (all agents exhausted)",
                "research": best_for_research or "hex (all agents exhausted)",
            },
        }

    def agent_memory(self, args: Dict[str, Any]) -> Dict[str, Any]:
        action = args.get("action")
        if action == "log_event":
            return log_agent_event(
                args.get("agent_name", "unknown"),
                args.get("event_type", "observation"),
                args.get("summary", ""),
                args.get("details"),
            )
        if action == "share_fact":
            return share_fact(
                args.get("agent_name", "unknown"),
                args.get("subject", ""),
                args.get("predicate", ""),
                args.get("object", ""),
            )
        if action == "get_context":
            return {
                "results": get_shared_context(
                    args.get("topic", ""),
                    int(args.get("limit", 10)),
                )
            }
        if action == "record_handoff":
            return record_handoff(
                args.get("from_agent", "unknown"),
                args.get("to_agent", "unknown"),
                args.get("task_id", ""),
                args.get("reason"),
            )
        if action == "share_lesson":
            return share_lesson(
                args.get("agent_name", "unknown"),
                args.get("domain", "general"),
                args.get("lesson", ""),
                args.get("context"),
            )
        if action == "get_lessons":
            return {
                "lessons": get_lessons_for_domain(
                    args.get("domain", "general"),
                    int(args.get("limit", 10)),
                )
            }
        if action == "search_lessons":
            return {
                "lessons": search_lessons(
                    args.get("query", ""),
                    int(args.get("limit", 10)),
                )
            }
        if action == "get_agent_lessons":
            return {
                "lessons": get_agent_lessons(
                    args.get("agent_name", "unknown"),
                    int(args.get("limit", 10)),
                )
            }
        return {"error": f"Unknown action: {action}"}

    def agent_performance(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Track and query agent performance."""
        action = args.get("action")
        if action == "record":
            return record_agent_performance(
                args.get("agent_name", "unknown"),
                args.get("task_type", "general"),
                args.get("success", True),
                args.get("duration_seconds", 0.0),
                args.get("tokens_used", 0),
            )
        if action == "get_stats":
            return get_agent_performance(args.get("agent_name", "unknown"))
        if action == "best_for_task":
            agents = args.get("available_agents", ["codex", "gemini"])
            best = get_best_agent_for_task(args.get("task_type", "general"), agents)
            return {"best_agent": best, "task_type": args.get("task_type", "general")}
        return {"error": f"Unknown action: {action}"}

    def check_agent_notifications(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check for task completion notifications from other agents."""
        agent_name = args.get("agent_name")
        should_acknowledge = args.get("acknowledge", False)
        
        notifications = check_notifications(agent_name)
        
        if should_acknowledge:
            for n in notifications:
                acknowledge_notification(n)
        
        return {
            "count": len(notifications),
            "notifications": [
                {
                    "task_id": n.get("task_id"),
                    "agent_name": n.get("agent_name"),
                    "status": n.get("status"),
                    "summary": n.get("summary"),
                    "completed_at": n.get("completed_at"),
                }
                for n in notifications
            ],
        }

    async def submit_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        allowed, requester_did = verify_auth(args.get("auth"))
        if not allowed:
            return {"task_id": None, "status": "rejected", "reason": "unauthorized"}

        # Log submission (auditable, even for MCP path)
        try:
            log_agent_event(
                self.name,
                "hexswarm_task_received",
                f"Received task ({args.get('type','general')})",
                args.get("description", "")[:500],
            )
        except Exception:
            pass

        request = TaskRequest.from_dict(args)
        task_id = f"task_{uuid.uuid4().hex}"
        record = TaskRecord(task_id=task_id, request=request, requester_did=requester_did)
        self._tasks[task_id] = record
        self.storage.write_task(record)

        # Execute synchronously for stdio transport (server exits after each call)
        # This blocks until task completes but ensures result is returned
        await self._run_task(record)
        
        # Return result directly
        if record.result:
            resp = {
                "task_id": task_id,
                "status": record.status.value,
                "result": record.result.result,
                "summary": record.result.summary,
                "duration_seconds": record.result.duration_seconds,
            }

            # Best-effort: emit an Archon-signed receipt for the result
            try:
                from .archon_utils import sign_json
                signed = sign_json({
                    "type": "hexswarmTaskResult",
                    "issuer": self.did,
                    "task_id": task_id,
                    "status": record.status.value,
                    "summary": record.result.summary,
                    "duration_seconds": record.result.duration_seconds,
                })
                if signed:
                    resp["signed_receipt"] = signed
            except Exception:
                pass

            return resp
        return {
            "task_id": task_id,
            "status": record.status.value,
            "error": record.error,
        }

    def task_status(self, task_id: str) -> Dict[str, Any]:
        record = self._tasks.get(task_id) or self.storage.load_task(task_id)
        if not record:
            return {"task_id": task_id, "status": "unknown"}
        return {
            "task_id": task_id,
            "status": record.status.value,
            "progress": record.progress,
            "started_at": record.started_at,
            "completed_at": record.completed_at,
            "error": record.error,
        }

    def task_result(self, task_id: str) -> Dict[str, Any]:
        record = self._tasks.get(task_id) or self.storage.load_task(task_id)
        if not record:
            return {"task_id": task_id, "status": "unknown"}
        if record.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return {"task_id": task_id, "status": record.status.value}
        if record.result:
            return record.result.to_dict()
        return {"task_id": task_id, "status": record.status.value, "error": record.error}

    async def cancel_task(self, task_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        record = self._tasks.get(task_id)
        if not record:
            return {"success": False, "status": "unknown"}

        if record.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return {"success": False, "status": record.status.value}

        future = self._task_futures.get(task_id)
        if future and not future.done():
            future.cancel()
        record.status = TaskStatus.CANCELLED
        record.completed_at = datetime.utcnow().isoformat()
        record.error = reason or "cancelled"
        self.storage.write_task(record)
        return {"success": True, "status": record.status.value}

    async def _run_task(self, record: TaskRecord) -> None:
        record.status = TaskStatus.RUNNING
        record.started_at = datetime.utcnow().isoformat()
        self.storage.write_task(record)

        start = time.time()
        try:
            result = await self.execute_task(record)
            if result is None:
                raise RuntimeError("Task returned no result")
            record.status = TaskStatus.COMPLETED
            record.completed_at = datetime.utcnow().isoformat()
            result.duration_seconds = time.time() - start
            record.result = result
            self.storage.write_task(record)
            # Track resources
            tokens = result.token_usage or 0
            self.resource_tracker.record_task(self.name, tokens, success=True)
        except asyncio.CancelledError:
            record.status = TaskStatus.CANCELLED
            record.completed_at = datetime.utcnow().isoformat()
            record.error = "cancelled"
            self.storage.write_task(record)
            self.resource_tracker.record_task(self.name, 0, success=False, error="cancelled")
        except Exception as e:
            record.status = TaskStatus.FAILED
            record.completed_at = datetime.utcnow().isoformat()
            record.error = str(e)
            record.result = TaskResult(task_id=record.task_id, status=TaskStatus.FAILED, error=str(e))
            self.storage.write_task(record)
            self.resource_tracker.record_task(self.name, 0, success=False, error=str(e))

    async def execute_task(self, record: TaskRecord) -> TaskResult:
        raise NotImplementedError

    async def run(self) -> None:
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, self.server.create_initialization_options())
