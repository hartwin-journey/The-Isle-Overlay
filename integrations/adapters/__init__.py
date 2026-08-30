"""Transport adapters for optional integration services."""

from integrations.adapters.base import IntegrationTransport
from integrations.adapters.websocket import WebSocketAdapter

__all__ = ["IntegrationTransport", "WebSocketAdapter"]
