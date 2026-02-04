"""Protocol dataclasses, enums, and schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskType(str, Enum):
    CODE = "code"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    GENERAL = "general"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"
    FILE = "file"


@dataclass
class TaskRequest:
    type: TaskType
    description: str
    files: List[str] = field(default_factory=list)
    context: Optional[str] = None
    constraints: List[str] = field(default_factory=list)
    output_format: OutputFormat = OutputFormat.TEXT
    priority: TaskPriority = TaskPriority.NORMAL
    callback: Optional[str] = None
    timeout_seconds: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRequest":
        return cls(
            type=TaskType(data.get("type", TaskType.GENERAL)),
            description=data.get("description", ""),
            files=list(data.get("files", []) or []),
            context=data.get("context"),
            constraints=list(data.get("constraints", []) or []),
            output_format=OutputFormat(data.get("output_format", OutputFormat.TEXT)),
            priority=TaskPriority(data.get("priority", TaskPriority.NORMAL)),
            callback=data.get("callback"),
            timeout_seconds=data.get("timeout_seconds"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "description": self.description,
            "files": self.files,
            "context": self.context,
            "constraints": self.constraints,
            "output_format": self.output_format.value,
            "priority": self.priority.value,
            "callback": self.callback,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    result: Optional[Any] = None
    files_created: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    token_usage: Optional[int] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result,
            "files_created": self.files_created,
            "summary": self.summary,
            "token_usage": self.token_usage,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


@dataclass
class TaskRecord:
    task_id: str
    request: TaskRequest
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: Optional[int] = None
    result: Optional[TaskResult] = None
    error: Optional[str] = None
    requester_did: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "request": self.request.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "progress": self.progress,
            "result": self.result.to_dict() if self.result else None,
            "error": self.error,
            "requester_did": self.requester_did,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        request = TaskRequest.from_dict(data.get("request", {}))
        result_data = data.get("result")
        result = None
        if isinstance(result_data, dict):
            result = TaskResult(
                task_id=result_data.get("task_id", data.get("task_id", "")),
                status=TaskStatus(result_data.get("status", TaskStatus.COMPLETED)),
                result=result_data.get("result"),
                files_created=list(result_data.get("files_created", []) or []),
                summary=result_data.get("summary"),
                token_usage=result_data.get("token_usage"),
                duration_seconds=result_data.get("duration_seconds"),
                error=result_data.get("error"),
            )
        return cls(
            task_id=data.get("task_id", ""),
            request=request,
            status=TaskStatus(data.get("status", TaskStatus.PENDING)),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            progress=data.get("progress"),
            result=result,
            error=data.get("error"),
            requester_did=data.get("requester_did"),
        )


AGENT_INFO_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "did": {"type": "string"},
        "capabilities": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string", "enum": ["ready", "busy", "offline"]},
        "version": {"type": "string"},
    },
}

SUBMIT_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["code", "research", "analysis", "general"]},
        "description": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "context": {"type": "string"},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "output_format": {"type": "string", "enum": ["text", "json", "file"]},
        "priority": {"type": "string", "enum": ["low", "normal", "high"]},
        "callback": {"type": "string"},
        "timeout_seconds": {"type": "number"},
        "auth": {"type": "object"},
    },
    "required": ["type", "description"],
}
