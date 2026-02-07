"""Legacy synchronous RPC clients (deprecated).

These clients are maintained for backwards compatibility but are deprecated
in favor of the async clients in the transports module.

Use AsyncSerialRpc and AsyncWebSocketRpc instead.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

import cbor2
import serial
from websockets.sync.client import connect

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
    """Legacy synchronous Serial RPC client (deprecated).

    Use AsyncSerialRpc instead for better performance and async/await support.
    """

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
    """Legacy synchronous WebSocket RPC client (deprecated).

    Use AsyncWebSocketRpc instead for better performance and async/await support.
    """

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
