"""
In-memory data store and WebSocket connection manager.

Provides a singleton ``DataStore`` that lazily loads the default CSV on
first access and can be hot-swapped via CSV upload, plus a
``ConnectionManager`` that broadcasts real-time refresh events to
connected dashboard clients.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from .config import DATA_PATH
from .data_loader import DataLoadResult, VideoDatasetLoader


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts JSON messages.

    Stale connections (those that raise on send) are automatically pruned
    during the next broadcast.
    """

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        """Accept a new WebSocket handshake and register the connection."""
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a connection after the client disconnects."""
        self._connections = [c for c in self._connections if c is not ws]

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send *message* to every connected client, pruning dead sockets."""
        stale: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)


class DataStore:
    """Thread-safe in-memory data store that can be swapped on CSV upload.

    On first access the default sample CSV is loaded and cached.
    ``replace_from_bytes`` allows hot-swapping the dataset at runtime,
    protected by an asyncio lock to prevent concurrent writes.
    """

    def __init__(self) -> None:
        self._result: DataLoadResult | None = None
        self._lock = asyncio.Lock()

    def load_default(self) -> DataLoadResult:
        """Lazily load the default sample CSV on first access."""
        if self._result is None:
            self._result = VideoDatasetLoader(DATA_PATH).load()
        return self._result

    async def replace_from_bytes(self, raw: bytes, filename: str) -> DataLoadResult:
        """Parse uploaded CSV bytes and atomically replace the stored dataset."""
        async with self._lock:
            self._result = VideoDatasetLoader.load_from_bytes(raw, filename)
            return self._result

    @property
    def result(self) -> DataLoadResult:
        """Return the current dataset, loading defaults if needed."""
        return self.load_default()


# Module-level singletons shared by the FastAPI application.
data_store = DataStore()
ws_manager = ConnectionManager()
