"""Shared model-provider adapters."""

from .mistral import MistralChatClient, build_mistral_client

__all__ = ["MistralChatClient", "build_mistral_client"]
