import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

import cbor2
import serial
from websockets.sync.client import connect

from .base import AsyncRpcTransport
from .framing import SWITCH_BYTE, encode_frame, decode_frame

# Configure logger - can be enabled via ATSMINI_DEBUG env var
logger = logging.getLogger("ats_sdk")
_debug_enabled = os.getenv("ATSMINI_DEBUG", "").lower() in ("1", "true", "yes")

# Set log level based on ATSMINI_DEBUG, but let pytest/application handle output
if _debug_enabled:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)

# Prevent log propagation to root logger to avoid duplicates
logger.propagate = True  # Keep True to allow pytest to capture logs


class SerialRpcClient:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0) -> None:
        logger.debug(f"Opening serial port {port} at {baudrate} baud (timeout={timeout}s)")
        self.serial = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        # Assert DTR to enable Serial on ESP32-S3
        self.serial.dtr = True
        self.serial.rts = False
        logger.debug(f"Set DTR=True, RTS=False")

        # Brief settle time
        time.sleep(0.1)

        # Flush any pending data
        flushed = self.serial.in_waiting
        self.serial.reset_input_buffer()
        if flushed > 0:
            logger.debug(f"Flushed {flushed} bytes from input buffer")

        self._next_id = 1
        logger.info(f"SerialRpcClient connected to {port}")

    def close(self) -> None:
        logger.debug(f"Closing serial port {self.serial.port}")
        self.serial.close()
        logger.info(f"SerialRpcClient disconnected")

    def switch_mode(self) -> None:
        logger.debug(f"Switching to CBOR-RPC mode (sending 0x{SWITCH_BYTE:02X})")
        self.serial.write(bytes([SWITCH_BYTE]))
        self.serial.flush()
        time.sleep(0.1)
        logger.info("CBOR-RPC mode activated")

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, request_id: Optional[int] = None) -> int:
        if request_id is None:
            request_id = self._next_id
            self._next_id += 1
        payload = {
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        frame = encode_frame(cbor2.dumps(payload))
        logger.debug(f"→ REQUEST id={request_id} method={method} params={params} ({len(frame)} bytes)")
        self.serial.write(frame)
        self.serial.flush()
        return request_id

    def read_message(self, timeout: float = 3.0) -> Dict[str, Any]:
        deadline = time.time() + timeout
        logger.debug(f"Reading message header (timeout={timeout}s)...")
        header = self._read_exact(4, deadline)
        length = int.from_bytes(header, "big")
        logger.debug(f"Message length: {length} bytes")
        payload = self._read_exact(length, deadline)
        message = cbor2.loads(payload)
        msg_type = message.get("type", "response")
        if msg_type == "event":
            logger.debug(f"← EVENT {message.get('event')} params={message.get('params')}")
        else:
            logger.debug(f"← RESPONSE id={message.get('id')} result={message.get('result')} error={message.get('error')}")
        return message

    def read_response(self, request_id: int, timeout: float = 5.0) -> Dict[str, Any]:
        deadline = time.time() + timeout
        logger.debug(f"Waiting for response to request id={request_id} (timeout={timeout}s)")
        skipped_events = 0
        while time.time() < deadline:
            msg = self.read_message(timeout=timeout)
            if msg.get("type") == "event":
                skipped_events += 1
                continue
            if msg.get("id") == request_id:
                if skipped_events > 0:
                    logger.debug(f"Skipped {skipped_events} event(s) while waiting for response")
                return msg
        raise TimeoutError(f"Timed out waiting for response to request id={request_id}")

    def _read_exact(self, size: int, deadline: float) -> bytes:
        data = bytearray()
        start_time = time.time()
        while len(data) < size:
            if time.time() > deadline:
                elapsed = time.time() - start_time
                raise TimeoutError(f"Timed out waiting for data: got {len(data)}/{size} bytes in {elapsed:.3f}s")
            chunk = self.serial.read(size - len(data))
            if chunk:
                data.extend(chunk)
        return bytes(data)


class WebSocketRpcClient:
    def __init__(self, url: str, timeout: float = 3.0) -> None:
        logger.debug(f"Connecting to WebSocket {url} (timeout={timeout}s)")
        self.ws = connect(url, open_timeout=timeout)
        self._next_id = 1
        logger.info(f"WebSocketRpcClient connected to {url}")

    def close(self) -> None:
        logger.debug("Closing WebSocket connection")
        self.ws.close()
        logger.info("WebSocketRpcClient disconnected")

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, request_id: Optional[int] = None) -> int:
        if request_id is None:
            request_id = self._next_id
            self._next_id += 1
        payload = {
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        frame = encode_frame(cbor2.dumps(payload))
        logger.debug(f"→ WS REQUEST id={request_id} method={method} params={params} ({len(frame)} bytes)")
        self.ws.send(frame)
        return request_id

    def read_message(self, timeout: float = 3.0) -> Dict[str, Any]:
        logger.debug(f"Reading WebSocket message (timeout={timeout}s)...")
        message = self.ws.recv(timeout=timeout)
        if isinstance(message, str):
            raise ValueError("Expected binary WebSocket message")
        payload = decode_frame(message)
        msg = cbor2.loads(payload)
        msg_type = msg.get("type", "response")
        if msg_type == "event":
            logger.debug(f"← WS EVENT {msg.get('event')} params={msg.get('params')}")
        else:
            logger.debug(f"← WS RESPONSE id={msg.get('id')} result={msg.get('result')} error={msg.get('error')}")
        return msg

    def read_response(self, request_id: int, timeout: float = 5.0) -> Dict[str, Any]:
        deadline = time.time() + timeout
        logger.debug(f"Waiting for WebSocket response to request id={request_id} (timeout={timeout}s)")
        skipped_events = 0
        while time.time() < deadline:
            msg = self.read_message(timeout=timeout)
            if msg.get("type") == "event":
                skipped_events += 1
                continue
            if msg.get("id") == request_id:
                if skipped_events > 0:
                    logger.debug(f"Skipped {skipped_events} event(s) while waiting for response")
                return msg
        raise TimeoutError(f"Timed out waiting for WebSocket response to request id={request_id}")


class AsyncSerialRpc(AsyncRpcTransport):
    """Async Serial RPC client using asyncio.to_thread() for blocking I/O.

    Uses DTR control for ESP32-S3 and requires mode switching (0x1E byte)
    to activate CBOR-RPC protocol.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None
        self._lock = asyncio.Lock()  # Protect serial port access

    async def connect(self) -> None:
        """Establish serial connection and configure port."""
        def _open_serial():
            self.logger.debug(f"Opening serial port {self.port} at {self.baudrate} baud (timeout={self.timeout}s)")
            ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)
            # Assert DTR to enable Serial on ESP32-S3
            ser.dtr = True
            ser.rts = False
            self.logger.debug("Set DTR=True, RTS=False")
            return ser

        self._serial = await asyncio.to_thread(_open_serial)

        # Brief settle time
        await asyncio.sleep(0.1)

        # Flush any pending data
        async with self._lock:
            flushed = await asyncio.to_thread(lambda: self._serial.in_waiting)
            await asyncio.to_thread(self._serial.reset_input_buffer)
            if flushed > 0:
                self.logger.debug(f"Flushed {flushed} bytes from input buffer")

        self.logger.info(f"AsyncSerialRpc connected to {self.port}")

    async def close(self) -> None:
        """Close serial connection."""
        if self._serial:
            self.logger.debug(f"Closing serial port {self._serial.port}")
            await asyncio.to_thread(self._serial.close)
            self._serial = None
            self.logger.info("AsyncSerialRpc disconnected")

    async def switch_mode(self) -> None:
        """Switch device to CBOR-RPC mode (Serial only).

        Sends the SWITCH_BYTE (0x1E) to activate CBOR-RPC protocol.
        Required before making RPC requests.
        """
        if not self._serial:
            raise ConnectionError("Not connected")

        self.logger.debug(f"Switching to CBOR-RPC mode (sending 0x{SWITCH_BYTE:02X})")

        async with self._lock:
            await asyncio.to_thread(self._serial.write, bytes([SWITCH_BYTE]))
            await asyncio.to_thread(self._serial.flush)

        await asyncio.sleep(0.1)
        self.logger.info("CBOR-RPC mode activated")

    async def write_frame(self, frame: bytes) -> None:
        """Write frame to serial port."""
        if not self._serial:
            raise ConnectionError("Not connected")

        async with self._lock:
            await asyncio.to_thread(self._serial.write, frame)
            await asyncio.to_thread(self._serial.flush)

    async def read_frame(self, timeout: float) -> bytes:
        """Read frame from serial port."""
        if not self._serial:
            raise ConnectionError("Not connected")

        deadline = asyncio.get_event_loop().time() + timeout

        # Read 4-byte header
        header = await self._read_exact(4, deadline)
        length = int.from_bytes(header, "big")
        self.logger.debug(f"Message length: {length} bytes")

        # Read payload
        payload = await self._read_exact(length, deadline)

        return header + payload

    async def _read_exact(self, size: int, deadline: float) -> bytes:
        """Read exact number of bytes with timeout."""
        data = bytearray()

        while len(data) < size:
            remaining_time = deadline - asyncio.get_event_loop().time()
            if remaining_time <= 0:
                raise TimeoutError(
                    f"Timeout reading {size} bytes (got {len(data)} bytes)"
                )

            # Read in thread to avoid blocking event loop
            async with self._lock:
                chunk = await asyncio.to_thread(
                    self._serial.read,
                    size - len(data)
                )

            if chunk:
                data.extend(chunk)
            else:
                # Small sleep to avoid tight loop
                await asyncio.sleep(0.01)

        return bytes(data)


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
