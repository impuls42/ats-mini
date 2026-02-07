"""Async WebSocket RPC transport."""

import asyncio

from ..base import AsyncRpcTransport


class AsyncWebSocketRpc(AsyncRpcTransport):
    """Async WebSocket RPC client.

    No mode switching required - WebSocket is always CBOR-RPC.
    """

    def __init__(self, url: str, timeout: float = 3.0):
        super().__init__()
        self.url = url
        self.timeout = timeout
        self._ws = None

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        import websockets

        self.logger.debug(f"Connecting to WebSocket {self.url} (timeout={self.timeout}s)")

        self._ws = await websockets.connect(
            self.url,
            open_timeout=self.timeout
        )

        self.logger.info(f"AsyncWebSocketRpc connected to {self.url}")

    async def close(self) -> None:
        """Close WebSocket connection."""
        if self._ws:
            self.logger.debug("Closing WebSocket connection")
            await self._ws.close()
            self._ws = None
            self.logger.info("AsyncWebSocketRpc disconnected")

    async def write_frame(self, frame: bytes) -> None:
        """Send frame over WebSocket."""
        if not self._ws:
            raise ConnectionError("Not connected")

        await self._ws.send(frame)

    async def read_frame(self, timeout: float) -> bytes:
        """Receive frame from WebSocket."""
        if not self._ws:
            raise ConnectionError("Not connected")

        try:
            message = await asyncio.wait_for(
                self._ws.recv(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"WebSocket read timeout after {timeout}s")

        if isinstance(message, str):
            raise ValueError("Expected binary WebSocket message")

        return message
