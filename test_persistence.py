#!/usr/bin/env python3
"""Test task persistence across simulated restarts."""

import sys
import tempfile
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from agent_mcp.protocol import TaskRequest, TaskRecord, TaskStatus, TaskType, OutputFormat, TaskPriority
from agent_mcp.storage import TaskStorage
import uuid


def test_persistence():
    """Test that tasks survive storage reload (simulating restart)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "tasks"
        
        # Create storage and add a task
        storage1 = TaskStorage(storage_path)
        
        request = TaskRequest(
            type=TaskType.CODE,
            description="Test task for persistence",
            priority=TaskPriority.NORMAL,
            output_format=OutputFormat.TEXT,
        )
        
        record = TaskRecord(
            task_id=str(uuid.uuid4()),
            request=request,
            requester_did="test-requester-did"
        )
        task_id = record.task_id
        
        # Write as pending
        storage1.write_task(record)
        print(f"✓ Created task {task_id} with status {record.status.value}")
        
        # Move to running
        record.status = TaskStatus.RUNNING
        storage1.move_task(task_id, TaskStatus.PENDING, TaskStatus.RUNNING)
        storage1.write_task(record)
        print(f"✓ Moved task to {record.status.value}")
        
        # Simulate restart: create new storage instance
        storage2 = TaskStorage(storage_path)
        
        # Load the task
        loaded = storage2.load_task(task_id)
        assert loaded is not None, "Task not found after reload!"
        assert loaded.task_id == task_id
        assert loaded.status == TaskStatus.RUNNING
        print(f"✓ Loaded task after 'restart': {loaded.task_id} status={loaded.status.value}")
        
        # Complete it
        loaded.status = TaskStatus.COMPLETED
        storage2.move_task(task_id, TaskStatus.RUNNING, TaskStatus.COMPLETED)
        storage2.write_task(loaded)
        print(f"✓ Completed task")
        
        # Verify with third instance
        storage3 = TaskStorage(storage_path)
        final = storage3.load_task(task_id)
        assert final.status == TaskStatus.COMPLETED
        print(f"✓ Verified completed status persists")
        
        # List all
        all_tasks = storage3.load_all()
        print(f"✓ Total tasks in storage: {len(all_tasks)}")
        
        print("\n✅ Persistence test PASSED")


if __name__ == "__main__":
    test_persistence()
