import tempfile
import unittest
from pathlib import Path

from agent_mcp.protocol import TaskRecord, TaskRequest, TaskType, TaskStatus
from agent_mcp.storage import TaskStorage


class StorageTests(unittest.TestCase):
    def test_storage_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = TaskStorage(Path(tmp))
            record = TaskRecord(
                task_id="task_test",
                request=TaskRequest(type=TaskType.GENERAL, description="demo"),
                status=TaskStatus.PENDING,
            )
            storage.write_task(record)
            loaded = storage.load_task("task_test")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.task_id, "task_test")
            self.assertEqual(loaded.request.description, "demo")


if __name__ == "__main__":
    unittest.main()
