import time
from typing import Any, Dict, Optional

import cbor2
import serial
from websockets.sync.client import connect

from .framing import SWITCH_BYTE, encode_frame, decode_frame


class SerialRpcClient:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0) -> None:
        self.serial = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        # Assert DTR to enable Serial on ESP32-S3
        self.serial.dtr = True
        self.serial.rts = False
        
        # Brief settle time
        time.sleep(0.1)
        
        # Flush any pending data
        self.serial.reset_input_buffer()
            
        self._next_id = 1

    def close(self) -> None:
        self.serial.close()

    def switch_mode(self) -> None:
        self.serial.write(bytes([SWITCH_BYTE]))
        self.serial.flush()
        time.sleep(0.1)

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, request_id: Optional[int] = None) -> int:
        if request_id is None:
            request_id = self._next_id
            self._next_id += 1
        payload = {
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        self.serial.write(encode_frame(cbor2.dumps(payload)))
        self.serial.flush()
        return request_id

    def read_message(self, timeout: float = 3.0) -> Dict[str, Any]:
        deadline = time.time() + timeout
        header = self._read_exact(4, deadline)
        length = int.from_bytes(header, "big")
        payload = self._read_exact(length, deadline)
        return cbor2.loads(payload)

    def read_response(self, request_id: int, timeout: float = 5.0) -> Dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self.read_message(timeout=timeout)
            if msg.get("type") == "event":
                continue
            if msg.get("id") == request_id:
                return msg
        raise TimeoutError("Timed out waiting for response")

    def _read_exact(self, size: int, deadline: float) -> bytes:
        data = bytearray()
        while len(data) < size:
            if time.time() > deadline:
                raise TimeoutError("Timed out waiting for data")
            chunk = self.serial.read(size - len(data))
            if chunk:
                data.extend(chunk)
        return bytes(data)


class WebSocketRpcClient:
    def __init__(self, url: str, timeout: float = 3.0) -> None:
        self.ws = connect(url, open_timeout=timeout)
        self._next_id = 1

    def close(self) -> None:
        self.ws.close()

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, request_id: Optional[int] = None) -> int:
        if request_id is None:
            request_id = self._next_id
            self._next_id += 1
        payload = {
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        self.ws.send(encode_frame(cbor2.dumps(payload)))
        return request_id

    def read_message(self, timeout: float = 3.0) -> Dict[str, Any]:
        message = self.ws.recv(timeout=timeout)
        if isinstance(message, str):
            raise ValueError("Expected binary WebSocket message")
        payload = decode_frame(message)
        return cbor2.loads(payload)

    def read_response(self, request_id: int, timeout: float = 5.0) -> Dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self.read_message(timeout=timeout)
            if msg.get("type") == "event":
                continue
            if msg.get("id") == request_id:
                return msg
        raise TimeoutError("Timed out waiting for response")
