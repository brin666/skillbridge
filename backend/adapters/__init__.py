"""Agent adapters for SkillBridge.

Each adapter is independent and knows how to detect one AI Agent on this
machine and locate its local Skill installation directories.
"""

from .base import AgentAdapter
from .codex import CodexAdapter
from .claude import ClaudeAdapter
from .qwen import QwenAdapter
from .trae import TraeAdapter
from .codebuddy import CodeBuddyAdapter
from .lingma import LingmaAdapter
from .hermes import HermesAdapter
from .dsh import DSHAdapter

__all__ = [
    "AgentAdapter",
    "CodexAdapter",
    "ClaudeAdapter",
    "QwenAdapter",
    "TraeAdapter",
    "CodeBuddyAdapter",
    "LingmaAdapter",
    "HermesAdapter",
    "DSHAdapter",
]
