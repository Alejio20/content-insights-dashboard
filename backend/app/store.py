from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from .config import DATA_PATH
from .data_loader import DataLoadResult, VideoDatasetLoader


class ConnectionManager:
    """Manages WebSocket connections and broadcasts refresh signals."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections = [c for c in self._connections if c is not ws]

    async def broadcast(self, message: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)


class DataStore:
    """Thread-safe in-memory data store that can be swapped on CSV upload."""

    def __init__(self) -> None:
        self._result: DataLoadResult | None = None
        self._lock = asyncio.Lock()

    def load_default(self) -> DataLoadResult:
        if self._result is None:
            self._result = VideoDatasetLoader(DATA_PATH).load()
        return self._result

    async def replace_from_bytes(self, raw: bytes, filename: str) -> DataLoadResult:
        async with self._lock:
            self._result = VideoDatasetLoader.load_from_bytes(raw, filename)
            return self._result

    @property
    def result(self) -> DataLoadResult:
        return self.load_default()


data_store = DataStore()
ws_manager = ConnectionManager()
