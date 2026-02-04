"""Agent resource tracking for intelligent delegation."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class AgentResources:
    """Track an agent's resource usage and limits."""
    
    name: str
    context_limit: int  # max tokens
    context_used: int = 0
    tokens_used_session: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_task_at: Optional[float] = None
    last_error: Optional[str] = None
    
    # Budget limits (0 = unlimited)
    token_budget: int = 0
    cost_budget_usd: float = 0.0
    cost_used_usd: float = 0.0
    
    @property
    def context_remaining(self) -> int:
        return max(0, self.context_limit - self.context_used)
    
    @property
    def context_percent_used(self) -> float:
        if self.context_limit == 0:
            return 0.0
        return (self.context_used / self.context_limit) * 100
    
    @property
    def is_exhausted(self) -> bool:
        """True if agent has no more usable context."""
        # Consider exhausted if >90% context used
        return self.context_percent_used > 90
    
    @property
    def is_budget_exhausted(self) -> bool:
        """True if agent has hit token or cost budget."""
        if self.token_budget > 0 and self.tokens_used_session >= self.token_budget:
            return True
        if self.cost_budget_usd > 0 and self.cost_used_usd >= self.cost_budget_usd:
            return True
        return False
    
    @property
    def can_accept_task(self) -> bool:
        """True if agent can accept more work."""
        return not self.is_exhausted and not self.is_budget_exhausted
    
    def record_task(self, tokens_used: int, success: bool, error: Optional[str] = None) -> None:
        """Record a completed task."""
        self.tokens_used_session += tokens_used
        self.context_used += tokens_used  # Approximation
        self.last_task_at = time.time()
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1
            self.last_error = error
    
    def reset_session(self) -> None:
        """Reset session-level counters (e.g., on agent restart)."""
        self.context_used = 0
        self.tokens_used_session = 0
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "context_limit": self.context_limit,
            "context_used": self.context_used,
            "context_remaining": self.context_remaining,
            "context_percent_used": round(self.context_percent_used, 1),
            "tokens_used_session": self.tokens_used_session,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "is_exhausted": self.is_exhausted,
            "can_accept_task": self.can_accept_task,
            "last_task_at": self.last_task_at,
            "last_error": self.last_error,
        }


# Default context limits (conservative estimates)
AGENT_CONTEXT_LIMITS = {
    "codex": 128_000,
    "gemini": 1_000_000,
    "hex": 200_000,
}


class ResourceTracker:
    """Track resources across all agents."""
    
    def __init__(self, state_path: Optional[Path] = None):
        self.state_path = state_path or Path("~/.agent/resources.json").expanduser()
        self.agents: Dict[str, AgentResources] = {}
        self._load()
    
    def _load(self) -> None:
        """Load state from disk."""
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                for name, agent_data in data.get("agents", {}).items():
                    self.agents[name] = AgentResources(
                        name=name,
                        context_limit=agent_data.get("context_limit", AGENT_CONTEXT_LIMITS.get(name, 100_000)),
                        context_used=agent_data.get("context_used", 0),
                        tokens_used_session=agent_data.get("tokens_used_session", 0),
                        tasks_completed=agent_data.get("tasks_completed", 0),
                        tasks_failed=agent_data.get("tasks_failed", 0),
                        last_task_at=agent_data.get("last_task_at"),
                        last_error=agent_data.get("last_error"),
                    )
            except (json.JSONDecodeError, KeyError):
                pass
    
    def _save(self) -> None:
        """Persist state to disk."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "agents": {name: agent.to_dict() for name, agent in self.agents.items()},
            "updated_at": time.time(),
        }
        self.state_path.write_text(json.dumps(data, indent=2))
    
    def get_agent(self, name: str) -> AgentResources:
        """Get or create agent resource tracker."""
        if name not in self.agents:
            self.agents[name] = AgentResources(
                name=name,
                context_limit=AGENT_CONTEXT_LIMITS.get(name, 100_000),
            )
        return self.agents[name]
    
    def record_task(self, agent_name: str, tokens_used: int, success: bool, error: Optional[str] = None) -> None:
        """Record a task for an agent."""
        agent = self.get_agent(agent_name)
        agent.record_task(tokens_used, success, error)
        self._save()
    
    def best_agent_for(self, task_type: str, exclude: Optional[list] = None) -> Optional[str]:
        """Find the best available agent for a task type.
        
        Returns None if no suitable agent is available (Hex should take over).
        """
        exclude = exclude or []
        
        # Agent capabilities
        capabilities = {
            "codex": ["code", "analysis"],
            "gemini": ["research", "analysis", "general"],
        }
        
        candidates = []
        for name, caps in capabilities.items():
            if name in exclude:
                continue
            if task_type not in caps:
                continue
            agent = self.get_agent(name)
            if agent.can_accept_task:
                candidates.append((name, agent.context_remaining))
        
        if not candidates:
            return None  # Hex takes over
        
        # Return agent with most context remaining
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
    
    def status_summary(self) -> Dict:
        """Get status of all agents."""
        return {
            name: agent.to_dict() 
            for name, agent in self.agents.items()
        }


def parse_codex_tokens(output: str) -> int:
    """Extract token count from Codex output."""
    # Codex outputs: "tokens used\n5,264"
    match = re.search(r'tokens used\s*\n\s*([\d,]+)', output, re.IGNORECASE)
    if match:
        return int(match.group(1).replace(',', ''))
    return 0


def parse_gemini_tokens(output: str) -> int:
    """Extract token count from Gemini output."""
    # TODO: Check Gemini output format
    match = re.search(r'tokens?[:\s]+([\d,]+)', output, re.IGNORECASE)
    if match:
        return int(match.group(1).replace(',', ''))
    return 0
