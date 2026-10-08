"""Shared runtime composition boundary."""

from .architectures import ArchitectureRegistry, default_architecture_registry
from .factory import AgentRuntime, build_runtime

__all__ = ["AgentRuntime", "ArchitectureRegistry", "build_runtime", "default_architecture_registry"]
