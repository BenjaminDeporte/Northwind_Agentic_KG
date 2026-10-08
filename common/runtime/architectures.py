"""Architecture registration and selection."""

from __future__ import annotations

from typing import Any, Callable


ArchitectureBuilder = Callable[..., Any]


class ArchitectureRegistry:
    def __init__(self):
        self._builders: dict[str, ArchitectureBuilder | None] = {}

    def register(self, name: str, builder: ArchitectureBuilder | None) -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("Architecture name is required")
        if normalized in self._builders:
            raise ValueError(f"Architecture is already registered: {normalized}")
        self._builders[normalized] = builder

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._builders))

    def build(self, name: str, **kwargs: Any) -> Any:
        normalized = name.strip().lower()
        if normalized not in self._builders:
            available = ", ".join(self.names()) or "none"
            raise ValueError(f"Unknown architecture {name!r}; available: {available}")
        builder = self._builders[normalized]
        if builder is None:
            raise NotImplementedError(
                f"Architecture {normalized!r} is registered but its implementation is not available yet"
            )
        return builder(**kwargs)


def default_architecture_registry() -> ArchitectureRegistry:
    from architectures.generic.graph import compile_graph
    from architectures.generic_reflection.graph import compile_graph as compile_reflection
    from architectures.curated.graph import compile_graph as compile_curated
    from architectures.curated_reflection.graph import compile_graph as compile_curated_reflection

    registry = ArchitectureRegistry()
    registry.register("generic", compile_graph)
    registry.register("generic_reflection", compile_reflection)
    registry.register("curated", compile_curated)
    registry.register("curated_reflection", compile_curated_reflection)
    return registry


__all__ = ["ArchitectureRegistry", "default_architecture_registry"]
