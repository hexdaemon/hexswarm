import asyncio
import importlib.util
import tempfile
import unittest
from pathlib import Path

from agent_mcp.protocol import TaskRecord, TaskRequest, TaskType, TaskResult, TaskStatus
from agent_mcp.storage import TaskStorage


MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None


class DummyServerTests(unittest.TestCase):
    @unittest.skipUnless(MCP_AVAILABLE, "mcp package not installed")
    def test_submit_and_result(self):
        from agent_mcp.server import BaseAgentServer

        class DummyServer(BaseAgentServer):
            async def execute_task(self, record: TaskRecord) -> TaskResult:
                return TaskResult(task_id=record.task_id, status=TaskStatus.COMPLETED, result="ok")

        def run(coro):
            return asyncio.get_event_loop().run_until_complete(coro)

        with tempfile.TemporaryDirectory() as tmp:
            storage = TaskStorage(Path(tmp))
            server = DummyServer("dummy", "did:cid:dummy", ["test"], storage)
            response = run(server.submit_task({"type": "general", "description": "demo"}))
            task_id = response["task_id"]
            self.assertEqual(response["status"], "accepted")
            run(asyncio.sleep(0.01))
            result = server.task_result(task_id)
            self.assertEqual(result["status"], "completed")


if __name__ == "__main__":
    unittest.main()
