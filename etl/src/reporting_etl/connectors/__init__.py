from .base import Connection, Connector, ExtractedRow, ExtractionResult, QueryDef
from .dummy import DummyConnector
from .ga4 import GA4Connector

CONNECTOR_REGISTRY: dict[str, type[Connector]] = {
    "dummy": DummyConnector,
    "ga4": GA4Connector,
}

__all__ = [
    "Connection",
    "Connector",
    "ExtractedRow",
    "ExtractionResult",
    "QueryDef",
    "CONNECTOR_REGISTRY",
]
