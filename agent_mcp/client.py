"""Client helper for calling other agents (stdio or mcporter wrapper)."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Dict


class MCPClient:
    def __init__(self, server_name: str, mcporter_bin: str = "mcporter") -> None:
        self.server_name = server_name
        self.mcporter_bin = mcporter_bin

    def call(self, tool: str, **kwargs: Any) -> Dict[str, Any]:
        """Call an MCP tool via mcporter CLI.

        Requires mcporter in PATH. This is a convenience helper for demos.
        """
        args = [self.mcporter_bin, "call", f"{self.server_name}.{tool}"]
        for key, value in kwargs.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            args.append(f"{key}={value}")

        result = subprocess.run(args, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "mcporter call failed")
        return json.loads(result.stdout)
