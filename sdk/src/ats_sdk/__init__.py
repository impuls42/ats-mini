"""ATS-Mini CBOR-RPC Communication SDK.

A fully async SDK for communicating with ESP32-S3 based ATS-Mini radio receivers
via Serial, WebSocket, or BLE using CBOR-RPC protocol.
"""

from .base import AsyncRpcTransport
from .transports import AsyncSerialRpc, AsyncWebSocketRpc, AsyncBleRpc
from .framing import decode_frame, encode_frame
from .radio import Radio, RpcError

__all__ = [
    # High-level
    "Radio",
    "RpcError",
    # Async transports
    "AsyncRpcTransport",
    "AsyncSerialRpc",
    "AsyncWebSocketRpc",
    "AsyncBleRpc",
    # Framing utilities
    "encode_frame",
    "decode_frame",
]

__version__ = "0.2.0"
