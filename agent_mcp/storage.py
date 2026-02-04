"""Filesystem-backed task storage."""

from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Dict, Iterable, List

from .protocol import TaskRecord, TaskStatus


class TaskStorage:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).expanduser()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for status in TaskStatus:
            (self.base_dir / status.value).mkdir(parents=True, exist_ok=True)

    def _path_for(self, task_id: str, status: TaskStatus) -> Path:
        return self.base_dir / status.value / f"{task_id}.json"

    def write_task(self, record: TaskRecord) -> None:
        # Remove from all other status directories first
        for status in TaskStatus:
            if status != record.status:
                old_path = self._path_for(record.task_id, status)
                if old_path.exists():
                    old_path.unlink()
        
        # Write to correct status directory
        path = self._path_for(record.task_id, record.status)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(record.to_dict(), indent=2))
        tmp_path.replace(path)

    def move_task(self, task_id: str, old_status: TaskStatus, new_status: TaskStatus) -> None:
        old_path = self._path_for(task_id, old_status)
        new_path = self._path_for(task_id, new_status)
        if old_path.exists():
            old_path.replace(new_path)

    def load_task(self, task_id: str) -> TaskRecord | None:
        for status in TaskStatus:
            path = self._path_for(task_id, status)
            if path.exists():
                return TaskRecord.from_dict(json.loads(path.read_text()))
        return None

    def load_all(self) -> Dict[str, TaskRecord]:
        tasks: Dict[str, TaskRecord] = {}
        for status in TaskStatus:
            status_dir = self.base_dir / status.value
            for path in status_dir.glob("*.json"):
                record = TaskRecord.from_dict(json.loads(path.read_text()))
                tasks[record.task_id] = record
        return tasks

    def list_by_status(self, status: TaskStatus) -> Iterable[TaskRecord]:
        status_dir = self.base_dir / status.value
        for path in status_dir.glob("*.json"):
            yield TaskRecord.from_dict(json.loads(path.read_text()))
