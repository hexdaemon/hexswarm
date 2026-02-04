import unittest

from agent_mcp.protocol import TaskRequest, TaskType, TaskPriority, OutputFormat


class ProtocolTests(unittest.TestCase):
    def test_task_request_roundtrip(self):
        req = TaskRequest(
            type=TaskType.CODE,
            description="test",
            files=["a", "b"],
            context="ctx",
            constraints=["c1"],
            output_format=OutputFormat.JSON,
            priority=TaskPriority.HIGH,
            callback="cb",
            timeout_seconds=5,
        )
        data = req.to_dict()
        req2 = TaskRequest.from_dict(data)
        self.assertEqual(req.type, req2.type)
        self.assertEqual(req.description, req2.description)
        self.assertEqual(req.files, req2.files)
        self.assertEqual(req.context, req2.context)
        self.assertEqual(req.constraints, req2.constraints)
        self.assertEqual(req.output_format, req2.output_format)
        self.assertEqual(req.priority, req2.priority)
        self.assertEqual(req.callback, req2.callback)
        self.assertEqual(req.timeout_seconds, req2.timeout_seconds)


if __name__ == "__main__":
    unittest.main()
