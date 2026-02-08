"""Abstract base class for async RPC transports."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import cbor2

from .framing import decode_frame, encode_frame


class AsyncRpcTransport(ABC):
    """Abstract base class for async RPC transports (Serial, WebSocket, BLE).

    This class provides common RPC protocol logic (request/response handling,
    event skipping, timeouts) while delegating transport-specific I/O to
    subclasses.
    """

    def __init__(self):
        self._next_id = 1
        self.logger = logging.getLogger(f"ats_sdk.{self.__class__.__name__}")

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the device.

        Raises:
            ConnectionError: If connection fails
            TimeoutError: If connection times out
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connection and cleanup resources."""
        pass

    @abstractmethod
    async def write_frame(self, frame: bytes) -> None:
        """Write a complete framed message to the transport.

        Args:
            frame: Framed message (4-byte length header + payload)

        Raises:
            ConnectionError: If not connected or connection lost
        """
        pass

    @abstractmethod
    async def read_frame(self, timeout: float) -> bytes:
        """Read a complete framed message from the transport.

        Args:
            timeout: Read timeout in seconds

        Returns:
            Framed message (4-byte length header + payload)

        Raises:
            TimeoutError: If timeout expires before frame is received
            ConnectionError: If connection lost during read
        """
        pass

    async def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[int] = None,
    ) -> int:
        """Send an RPC request and return the request ID.

        Args:
            method: RPC method name (e.g. "volume.set", "status.get")
            params: Optional method parameters
            request_id: Optional explicit request ID (auto-generated if None)

        Returns:
            Request ID for matching with response

        Raises:
            ConnectionError: If not connected or write fails
        """
        if request_id is None:
            request_id = self._next_id
            self._next_id += 1

        payload = {
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        cbor_data = cbor2.dumps(payload)
        frame = encode_frame(cbor_data)

        self.logger.debug(
            f"→ REQUEST id={request_id} method={method} params={params} ({len(frame)} bytes)"
        )

        await self.write_frame(frame)
        return request_id

    async def read_message(self, timeout: float = 3.0) -> Dict[str, Any]:
        """Read and decode the next message (response or event).

        Args:
            timeout: Read timeout in seconds

        Returns:
            Decoded message dictionary

        Raises:
            TimeoutError: If timeout expires
            ConnectionError: If connection lost
        """
        frame = await self.read_frame(timeout)
        payload = decode_frame(frame)

        try:
            message = cbor2.loads(payload)
        except Exception as e:
            self.logger.error(f"CBOR decode failed: {e}")
            self.logger.error(
                f"Payload ({len(payload)} bytes): {payload[:64].hex()}..."
            )
            raise ValueError(f"Failed to decode CBOR message: {e}") from e

        msg_type = message.get("type", "response")
        if msg_type == "event":
            self.logger.debug(
                f"← EVENT {message.get('event')} params={message.get('params')}"
            )
        else:
            self.logger.debug(
                f"← RESPONSE id={message.get('id')} "
                f"result={message.get('result')} error={message.get('error')}"
            )

        return message

    async def read_response(
        self, request_id: int, timeout: float = 5.0
    ) -> Dict[str, Any]:
        """Read response for a specific request ID, skipping any events.

        Args:
            request_id: Request ID to wait for
            timeout: Total timeout in seconds

        Returns:
            Response message dictionary

        Raises:
            TimeoutError: If timeout expires before response received
            ConnectionError: If connection lost
        """
        deadline = asyncio.get_event_loop().time() + timeout
        self.logger.debug(
            f"Waiting for response to request id={request_id} (timeout={timeout}s)"
        )

        skipped_events = 0

        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break

            msg = await self.read_message(timeout=remaining)

            # Skip events - we're looking for a response
            if msg.get("type") == "event":
                skipped_events += 1
                continue

            # Check if this is the response we're waiting for
            if msg.get("id") == request_id:
                if skipped_events > 0:
                    self.logger.debug(
                        f"Skipped {skipped_events} event(s) while waiting for response"
                    )
                return msg

        raise TimeoutError(f"Timed out waiting for response to request id={request_id}")

    async def __aenter__(self):
        """Async context manager entry - connects to device."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes connection."""
        await self.close()
        return False
