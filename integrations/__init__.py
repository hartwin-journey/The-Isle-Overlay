"""Optional, server-agnostic external integration support."""

from integrations.contracts import MapIdentity, load_map_identity
from integrations.manager import IntegrationManager

__all__ = ["IntegrationManager", "MapIdentity", "load_map_identity"]
